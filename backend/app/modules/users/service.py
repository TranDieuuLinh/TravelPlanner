from fastapi import HTTPException, status

from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.modules.users.schema import UserCreate


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    def list_users(self) -> list[User]:
        return self.repository.list()

    def create_user(self, payload: UserCreate) -> User:
        if self.repository.get_by_email(payload.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already exists",
            )
        return self.repository.create(payload)
