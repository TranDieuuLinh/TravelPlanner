from __future__ import annotations

import asyncio
import json

from sqlalchemy.orm import sessionmaker

from app.integrations.llm.base import LLMClient
from app.modules.plans.chat_model import TripChat
from app.modules.plans.chat_repository import TripChatRepository
from app.modules.preferences.extractor import StructuredLLMPreferenceExtractor
from app.modules.preferences.observation_model import PreferenceObservationJob
from app.modules.preferences.observation_repository import (
    PreferenceObservationJobRepository,
)
from app.modules.preferences.observation_worker import PreferenceObservationWorker
from app.modules.preferences.repository import TravelerProfileRepository
from app.modules.users.repository import UserRepository


class _StructuredPreferenceLLM(LLMClient):
    async def generate_profile_plan(self, prompt: str) -> str:
        raise NotImplementedError

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        raise NotImplementedError

    async def generate_structured_json(
        self,
        system_prompt: str,
        user_payload: str,
        *,
        response_schema: dict,
    ) -> str:
        assert "không thích nơi đông người" in user_payload
        assert "observations" in response_schema["properties"]
        return json.dumps(
            {
                "observations": [
                    {
                        "dimension": "setting",
                        "value": "uncrowded",
                        "score": 1.0,
                        "confidence": 0.98,
                        "scope": "global",
                        "destination": None,
                        "explicitness": "explicit",
                        "action": "upsert",
                    }
                ]
            }
        )


def test_preference_observation_job_is_durable_private_and_idempotent(
    db_session,
    registered_client,
) -> None:
    user = UserRepository(db_session).get_by_email("traveler@example.com")
    assert user is not None
    chat = TripChat(
        id="chat-preference-worker",
        user_id=user.id,
        title="Preference worker",
        revision=0,
    )
    db_session.add(chat)
    db_session.commit()
    turn = TripChatRepository(db_session).create_turn(
        chat,
        client_turn_id="preference-worker-turn",
        content="Mình không thích nơi đông người",
        attachment_names=[],
        expected_revision=0,
    )
    TripChatRepository(db_session).update_turn(turn, status="completed")

    jobs = PreferenceObservationJobRepository(db_session)
    first = jobs.enqueue(message_id=turn.id, user_id=user.id)
    second = jobs.enqueue(message_id=turn.id, user_id=user.id)
    assert first.id == second.id
    assert "content" not in PreferenceObservationJob.__table__.columns

    worker_sessions = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_session.get_bind(),
    )
    worker = PreferenceObservationWorker(
        worker_sessions,
        StructuredLLMPreferenceExtractor(_StructuredPreferenceLLM()),
        poll_interval_seconds=0.1,
    )

    assert asyncio.run(worker.run_once()) is True
    assert asyncio.run(worker.run_once()) is False

    db_session.expire_all()
    job = db_session.get(PreferenceObservationJob, first.id)
    profile = TravelerProfileRepository(db_session).get(user.id)
    assert job is not None and job.status == "completed"
    assert profile.scores["setting:uncrowded"].observations == 1
    assert profile.top_values() == ["uncrowded"]

    db_session.expire(chat, ["messages"])
    planning_turn = TripChatRepository(db_session).create_turn(
        chat,
        client_turn_id="preference-worker-planning-turn",
        content="Lập plan nơi ít đông người",
        attachment_names=[],
        expected_revision=0,
    )
    TripChatRepository(db_session).update_turn(
        planning_turn,
        status="completed",
        intent="create_plan",
    )
    planning_job = jobs.enqueue(message_id=planning_turn.id, user_id=user.id)

    assert asyncio.run(worker.run_once()) is True
    db_session.expire_all()
    skipped = db_session.get(PreferenceObservationJob, planning_job.id)
    profile = TravelerProfileRepository(db_session).get(user.id)
    assert skipped is not None and skipped.status == "skipped"
    assert profile.scores["setting:uncrowded"].observations == 1
