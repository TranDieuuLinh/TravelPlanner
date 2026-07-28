from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.users.model import User
from app.modules.users.schema import CreatorApplicationCreate, ProfileUpdate, UserCreate


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self) -> list[User]:
        return list(self.db.scalars(select(User).order_by(User.created_at.desc())))

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email.strip().lower()))

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def create(self, payload: UserCreate) -> User:
        data = payload.model_dump(by_alias=False)
        data["email"] = str(payload.email).strip().lower()
        user = User(**data)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def create_registered(self, email: str, full_name: str, password_hash: str) -> User:
        user = User(
            email=email.strip().lower(),
            full_name=full_name.strip(),
            password_hash=password_hash,
            role="traveler",
            status="active",
        )
        self.db.add(user)
        self.db.flush()
        return user

    def update_profile(self, user: User, payload: ProfileUpdate) -> User:
        changes = payload.model_dump(exclude_unset=True, by_alias=False)
        if "avatar_url" in changes and changes["avatar_url"] is not None:
            changes["avatar_url"] = str(changes["avatar_url"])
        for field, value in changes.items():
            setattr(user, field, value)
        self.db.flush()
        return user

    def submit_creator_application(self, user: User, payload: CreatorApplicationCreate) -> User:
        user.bio = payload.bio.strip()
        user.creator_portfolio_urls = [str(url) for url in payload.portfolio_urls]
        user.creator_status = "pending"
        self.db.flush()
        return user

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    def refresh(self, user: User) -> None:
        self.db.refresh(user)
