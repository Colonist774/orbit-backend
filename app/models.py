from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Identity,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Identity(always=True),
        primary_key=True,
    )

    username: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    chat_memberships: Mapped[list["ChatMember"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="sender",
        cascade="all, delete-orphan",
    )

    public_key: Mapped["UserPublicKey | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )

    def __repr__(self):
        return f"User(id={self.id}, username='{self.username}')"


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(
        Identity(always=True),
        primary_key=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    members: Mapped[list["ChatMember"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"Chat(id={self.id})"


class ChatMember(Base):
    __tablename__ = "chat_members"

    __table_args__ = (
        UniqueConstraint(
            "chat_id",
            "user_id",
            name="uq_chat_members_chat_user",
        ),
    )

    id: Mapped[int] = mapped_column(
        Identity(always=True),
        primary_key=True,
    )

    chat_id: Mapped[int] = mapped_column(
        ForeignKey(
            "chats.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    chat: Mapped["Chat"] = relationship(
        back_populates="members",
    )

    user: Mapped["User"] = relationship(
        back_populates="chat_memberships",
    )

    def __repr__(self):
        return (
            f"ChatMember("
            f"id={self.id}, "
            f"chat_id={self.chat_id}, "
            f"user_id={self.user_id}"
            f")"
        )
    

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)

    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"),
        index=True,
    )

    sender_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    ciphertext: Mapped[str] = mapped_column(Text)

    iv: Mapped[str] = mapped_column(
        String(24),
    )

    key_version: Mapped[int] = mapped_column(
        default=1,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    chat: Mapped["Chat"] = relationship(
        back_populates="messages",
    )

    sender: Mapped["User"] = relationship(
        back_populates="messages",
    )


class UserPublicKey(Base):
    __tablename__ = "user_public_keys"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )

    public_key: Mapped[str] = mapped_column(Text)

    algorithm: Mapped[str] = mapped_column(
        String(50),
        default="RSA-OAEP-2048",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(
        back_populates="public_key",
    )