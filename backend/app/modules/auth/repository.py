from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.model import AuthSession


class AuthSessionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(
        self,
        user_id: int,
        jti: str,
        refresh_token_hash: str,
        expires_at: datetime,
    ) -> AuthSession:
        session = AuthSession(
            user_id=user_id,
            jti=jti,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
        )
        self.db.add(session)
        self.db.flush()
        return session

    def get_by_jti(self, jti: str) -> AuthSession | None:
        return self.db.scalar(select(AuthSession).where(AuthSession.jti == jti))

    def revoke(self, session: AuthSession, revoked_at: datetime, replaced_by_jti: str | None = None) -> None:
        session.revoked_at = revoked_at
        session.replaced_by_jti = replaced_by_jti
        session.last_used_at = revoked_at
        self.db.flush()

    def revoke_all_for_user(self, user_id: int, revoked_at: datetime) -> None:
        sessions = self.db.scalars(
            select(AuthSession).where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
        )
        for session in sessions:
            session.revoked_at = revoked_at
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
