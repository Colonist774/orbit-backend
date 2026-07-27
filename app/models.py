from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Identity,
    Integer,
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

    # text, image, audio или video.
    message_type: Mapped[str] = mapped_column(
        String(20),
        default="text",
        server_default="text",
        nullable=False,
    )

    # Для текста здесь находится зашифрованный текст и ключи.
    # Для вложения — только зашифрованные AES-ключи; зашифрованные
    # байты самого файла хранятся отдельно.
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

    attachment: Mapped["Attachment | None"] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Пока одно вложение связано с одним сообщением.
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    # Относительный путь зашифрованного файла.
    storage_key: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    width: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    height: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    message: Mapped["Message"] = relationship(
        back_populates="attachment",
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

    encrypted_private_key: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    private_key_iv: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    private_key_salt: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    private_key_kdf: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    private_key_iterations: Mapped[int | None] = mapped_column(
        nullable=True,
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
