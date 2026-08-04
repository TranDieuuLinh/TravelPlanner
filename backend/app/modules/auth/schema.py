from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.users.schema import UserRead


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)
    full_name: str = Field(min_length=2, max_length=255, alias="fullName")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if len(value) < 10:
            raise ValueError("Mật khẩu phải có ít nhất 10 ký tự.")
        if not any(character.islower() for character in value):
            raise ValueError("Mật khẩu phải có ít nhất một chữ thường.")
        if not any(character.isupper() for character in value):
            raise ValueError("Mật khẩu phải có ít nhất một chữ hoa.")
        if not any(character.isdigit() for character in value):
            raise ValueError("Mật khẩu phải có ít nhất một chữ số.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    user: UserRead
