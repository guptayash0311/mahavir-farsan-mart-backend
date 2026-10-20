from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    guest_token: str | None = None


class RefreshIn(BaseModel):
    refresh_token: str


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MessageOut(BaseModel):
    message: str
    reset_token: str | None = None


class MeOut(BaseModel):
    id: UUID
    email: str
    is_active: bool
    roles: list[str]
    permissions: list[str]


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = ""
    role: str = "customer"


class UserOut(BaseModel):
    id: UUID
    email: str
    is_active: bool
    roles: list[str]


class RolesIn(BaseModel):
    roles: list[str] = Field(min_length=1)
