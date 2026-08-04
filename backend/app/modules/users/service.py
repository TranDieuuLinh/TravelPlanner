from fastapi import status

from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.modules.users.schema import UserCreate
from app.shared.errors import AppError


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    def list_users(self) -> list[User]:
        return self.repository.list()

    def create_user(self, payload: UserCreate) -> User:
        if self.repository.get_by_email(payload.email):
            raise AppError(
                status.HTTP_409_CONFLICT,
                "EMAIL_ALREADY_EXISTS",
                "Email đã được sử dụng.",
            )
        return self.repository.create(payload)
