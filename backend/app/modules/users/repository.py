from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.users.model import User
from app.modules.users.schema import UserCreate


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self) -> list[User]:
        return list(self.db.scalars(select(User).order_by(User.created_at.desc())))

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email))

    def create(self, payload: UserCreate) -> User:
        data = payload.model_dump(by_alias=False)
        user = User(**data)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
