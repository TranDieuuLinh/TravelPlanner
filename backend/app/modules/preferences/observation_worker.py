from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.preferences.extractor import (
    PreferenceExtractionError,
    PreferenceExtractor,
    PreferencePolicy,
)
from app.modules.preferences.observation_repository import (
    PreferenceObservationJobRepository,
)
from app.modules.preferences.repository import TravelerProfileRepository
from app.modules.preferences.service import PreferenceLearningService


logger = logging.getLogger(__name__)


class PreferenceObservationWorker:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        extractor: PreferenceExtractor,
        *,
        poll_interval_seconds: float = 0.75,
        max_attempts: int = 3,
    ) -> None:
        self.session_factory = session_factory
        self.extractor = extractor
        self.policy = PreferencePolicy()
        self.learning = PreferenceLearningService()
        self.poll_interval_seconds = poll_interval_seconds
        self.max_attempts = max_attempts

    def recover_interrupted(self) -> int:
        with self.session_factory() as db:
            return PreferenceObservationJobRepository(db).recover_interrupted()

    async def run_forever(self) -> None:
        recovered = self.recover_interrupted()
        if recovered:
            logger.info("Requeued %s interrupted preference jobs", recovered)
        while True:
            try:
                processed = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Preference observation worker iteration failed")
                processed = False
            if not processed:
                await asyncio.sleep(self.poll_interval_seconds)

    async def run_once(self) -> bool:
        with self.session_factory() as db:
            jobs = PreferenceObservationJobRepository(db)
            skipped = jobs.skip_ineligible_turns()
            job = jobs.claim_next()
            if job is None:
                return bool(skipped)
            loaded = jobs.load_message_and_chat(job)
            if loaded is None:
                jobs.retry_or_fail(
                    job.id,
                    max_attempts=1,
                    code="MESSAGE_NOT_FOUND",
                    message="Preference source message is unavailable.",
                )
                return True
            message, chat = loaded
            try:
                result = await self.extractor.extract(
                    message.content,
                    destination=chat.destination,
                )
                snapshot = self.policy.to_snapshot(result)
                if snapshot.signals:
                    if db.get_bind().dialect.name == "postgresql":
                        db.execute(
                            text(
                                "SELECT pg_advisory_xact_lock("
                                "hashtext(:lock_key))"
                            ),
                            {
                                "lock_key": (
                                    f"travelplanner:traveler-profile:{job.user_id}"
                                )
                            },
                        )
                    profiles = TravelerProfileRepository(db)
                    profile = self.learning.merge(
                        profiles.get(job.user_id),
                        snapshot,
                    )
                    profiles.save(
                        job.user_id,
                        profile,
                        evidence_intake_id=job.message_id,
                    )
                jobs.complete(job)
                db.commit()
            except PreferenceExtractionError as exc:
                db.rollback()
                jobs.retry_or_fail(
                    job.id,
                    max_attempts=self.max_attempts,
                    code="EXTRACTION_FAILED",
                    message=str(exc),
                )
            except Exception:
                logger.exception(
                    "Preference observation job failed",
                    extra={"job_id": job.id, "user_id": job.user_id},
                )
                db.rollback()
                jobs.retry_or_fail(
                    job.id,
                    max_attempts=self.max_attempts,
                    code="PERSISTENCE_FAILED",
                    message="Preference observation could not be persisted.",
                )
            return True
