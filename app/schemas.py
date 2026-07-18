from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=20)
    password: str = Field(min_length=6, max_length=100)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class ChatCreate(BaseModel):
    other_user_id: int


class ChatResponse(BaseModel):
    id: int
    created_at: datetime
    other_user: UserResponse


class ChatListItem(BaseModel):
    id: int
    created_at: datetime
    other_user: UserResponse


class MessageCreate(BaseModel):
    ciphertext: str = Field(min_length=1)
    iv: str = Field(min_length=1, max_length=24)
    key_version: int = Field(default=1, ge=1)


class MessageResponse(BaseModel):
    id: int
    chat_id: int
    sender_id: int
    ciphertext: str
    iv: str
    key_version: int
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }

class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
    next_before_id: int | None
    has_more: bool


class PublicKeyCreate(BaseModel):
    public_key: str = Field(
        min_length=10,
        max_length=10000,
    )

    algorithm: str = Field(
        default="RSA-OAEP-2048",
        min_length=1,
        max_length=50,
    )


class PublicKeyResponse(BaseModel):
    user_id: int
    public_key: str
    algorithm: str
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
    }