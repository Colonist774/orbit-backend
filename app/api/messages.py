import logging
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import get_session
from app.dependencies import get_current_user
from app.models import Attachment, Chat, ChatMember, Message, User
from app.schemas import (
    MessageCreate,
    MessageListResponse,
    MessageResponse,
)
from app.websocket_manager import manager


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/chats",
    tags=["messages"],
)

ALLOWED_ATTACHMENT_TYPES = {
    "image": {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/avif",
    },
    "audio": {
        "audio/webm",
        "audio/ogg",
        "audio/mpeg",
        "audio/mp4",
        "audio/x-m4a",
        "audio/wav",
        "audio/x-wav",
        "audio/aac",
        "audio/flac",
    },
    "video": {
        "video/mp4",
        "video/webm",
        "video/quicktime",
        "video/x-m4v",
        "video/ogg",
    },
}

ATTACHMENT_MESSAGE_TYPES = tuple(
    ALLOWED_ATTACHMENT_TYPES.keys()
)

UPLOAD_ROOT = Path(settings.orbit_upload_dir)
ATTACHMENT_UPLOAD_DIR = UPLOAD_ROOT / "attachments"

# Старые изображения уже лежат здесь и должны продолжать открываться.
LEGACY_IMAGE_UPLOAD_DIR = UPLOAD_ROOT / "images"

FILE_CHUNK_SIZE = 1024 * 1024


def normalize_mime_type(mime_type: str) -> str:
    return mime_type.split(";", 1)[0].strip().lower()


def get_max_size_mb(message_type: str) -> int:
    if message_type == "image":
        return settings.max_image_size_mb

    if message_type == "audio":
        return settings.max_audio_size_mb

    if message_type == "video":
        return settings.max_video_size_mb

    raise ValueError(f"Unknown attachment type: {message_type}")


def get_attachment_path(storage_key: str) -> Path:
    current_path = ATTACHMENT_UPLOAD_DIR / storage_key

    if current_path.is_file():
        return current_path

    legacy_path = LEGACY_IMAGE_UPLOAD_DIR / storage_key

    if legacy_path.is_file():
        return legacy_path

    return current_path


def check_chat_membership(
    chat_id: int,
    user_id: int,
    session: Session,
) -> None:
    chat_exists = (
        session.query(Chat.id)
        .filter(Chat.id == chat_id)
        .first()
    )

    if chat_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found",
        )

    membership = (
        session.query(ChatMember.id)
        .filter(
            ChatMember.chat_id == chat_id,
            ChatMember.user_id == user_id,
        )
        .first()
    )

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this chat",
        )


def get_chat_member_ids(
    chat_id: int,
    session: Session,
) -> list[int]:
    rows = (
        session.query(ChatMember.user_id)
        .filter(ChatMember.chat_id == chat_id)
        .all()
    )

    return [
        user_id
        for user_id, in rows
    ]


def serialize_attachment(
    attachment: Attachment | None,
) -> dict | None:
    if attachment is None:
        return None

    return {
        "id": attachment.id,
        "message_id": attachment.message_id,
        "mime_type": attachment.mime_type,
        "size_bytes": attachment.size_bytes,
        "width": attachment.width,
        "height": attachment.height,
        "duration_ms": attachment.duration_ms,
        "created_at": attachment.created_at,
    }


def serialize_message(message: Message) -> dict:
    return {
        "id": message.id,
        "chat_id": message.chat_id,
        "sender_id": message.sender_id,
        "message_type": message.message_type,
        "ciphertext": message.ciphertext,
        "iv": message.iv,
        "key_version": message.key_version,
        "created_at": message.created_at,
        "attachment": serialize_attachment(
            message.attachment
        ),
    }


async def notify_message_created(
    message: Message,
    member_ids: list[int],
) -> None:
    serialized_message = serialize_message(message)
    serialized_message["created_at"] = (
        message.created_at.isoformat()
    )

    attachment = serialized_message.get("attachment")

    if attachment is not None:
        attachment["created_at"] = (
            message.attachment.created_at.isoformat()
        )

    event = {
        "type": "message.created",
        "message": serialized_message,
    }

    for member_id in member_ids:
        await manager.send_to_user(
            user_id=member_id,
            data=event,
        )


async def save_encrypted_upload(
    upload: UploadFile,
    destination: Path,
    *,
    max_size_mb: int,
    media_label: str,
) -> int:
    max_bytes = max_size_mb * 1024 * 1024

    # AES-GCM добавляет authentication tag, поэтому оставляем
    # небольшой запас сверх лимита исходного файла.
    max_encrypted_bytes = max_bytes + 1024
    written_bytes = 0

    try:
        with destination.open("wb") as output_file:
            while True:
                chunk = await upload.read(FILE_CHUNK_SIZE)

                if not chunk:
                    break

                written_bytes += len(chunk)

                if written_bytes > max_encrypted_bytes:
                    raise HTTPException(
                        status_code=(
                            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                        ),
                        detail=(
                            f"{media_label} exceeds the allowed "
                            f"size of {max_size_mb} MB"
                        ),
                    )

                output_file.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    if written_bytes == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded {media_label.lower()} is empty",
        )

    return written_bytes


async def create_attachment_message(
    *,
    chat_id: int,
    file: UploadFile,
    message_type: str,
    ciphertext: str,
    iv: str,
    key_version: int,
    mime_type: str,
    width: int | None,
    height: int | None,
    duration_ms: int | None,
    session: Session,
    current_user: User,
) -> dict:
    check_chat_membership(
        chat_id=chat_id,
        user_id=current_user.id,
        session=session,
    )

    normalized_type = message_type.strip().lower()
    normalized_mime = normalize_mime_type(mime_type)

    allowed_mime_types = ALLOWED_ATTACHMENT_TYPES.get(
        normalized_type
    )

    if allowed_mime_types is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported message type",
        )

    if normalized_mime not in allowed_mime_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported {normalized_type} format: "
                f"{normalized_mime or 'unknown'}"
            ),
        )

    if normalized_type == "image":
        if width is None or height is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Image width and height are required",
            )

        duration_ms = None

    if normalized_type == "audio":
        width = None
        height = None

    target_directory = (
        ATTACHMENT_UPLOAD_DIR / normalized_type
    )
    target_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    storage_key = (
        f"{normalized_type}/{uuid4().hex}.enc"
    )
    destination = ATTACHMENT_UPLOAD_DIR / storage_key

    try:
        size_bytes = await save_encrypted_upload(
            upload=file,
            destination=destination,
            max_size_mb=get_max_size_mb(
                normalized_type
            ),
            media_label=normalized_type.capitalize(),
        )
    except HTTPException:
        raise
    except OSError as error:
        logger.exception(
            "Could not save encrypted %s",
            normalized_type,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Could not save {normalized_type}"
            ),
        ) from error

    message = Message(
        chat_id=chat_id,
        sender_id=current_user.id,
        message_type=normalized_type,
        ciphertext=ciphertext,
        iv=iv,
        key_version=key_version,
    )

    attachment = Attachment(
        storage_key=storage_key,
        mime_type=normalized_mime,
        size_bytes=size_bytes,
        width=width,
        height=height,
        duration_ms=duration_ms,
    )

    message.attachment = attachment

    try:
        session.add(message)
        session.commit()
        session.refresh(message)
    except Exception as error:
        session.rollback()
        destination.unlink(missing_ok=True)
        logger.exception(
            "Could not create %s message",
            normalized_type,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Could not create {normalized_type} message"
            ),
        ) from error

    member_ids = get_chat_member_ids(
        chat_id=chat_id,
        session=session,
    )

    await notify_message_created(
        message=message,
        member_ids=member_ids,
    )

    return serialize_message(message)


@router.post(
    "/{chat_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    chat_id: int,
    data: MessageCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    check_chat_membership(
        chat_id=chat_id,
        user_id=current_user.id,
        session=session,
    )

    message = Message(
        chat_id=chat_id,
        sender_id=current_user.id,
        message_type="text",
        ciphertext=data.ciphertext,
        iv=data.iv,
        key_version=data.key_version,
    )

    session.add(message)
    session.commit()
    session.refresh(message)

    member_ids = get_chat_member_ids(
        chat_id=chat_id,
        session=session,
    )

    await notify_message_created(
        message=message,
        member_ids=member_ids,
    )

    return serialize_message(message)


@router.post(
    "/{chat_id}/attachment-messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_attachment_message(
    chat_id: int,
    file: UploadFile = File(...),
    message_type: str = Form(..., min_length=1, max_length=20),
    ciphertext: str = Form(..., min_length=1),
    iv: str = Form(..., min_length=1, max_length=24),
    key_version: int = Form(default=1, ge=1),
    mime_type: str = Form(..., min_length=1, max_length=100),
    width: int | None = Form(
        default=None,
        ge=1,
        le=20000,
    ),
    height: int | None = Form(
        default=None,
        ge=1,
        le=20000,
    ),
    duration_ms: int | None = Form(
        default=None,
        ge=0,
        le=86400000,
    ),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return await create_attachment_message(
        chat_id=chat_id,
        file=file,
        message_type=message_type,
        ciphertext=ciphertext,
        iv=iv,
        key_version=key_version,
        mime_type=mime_type,
        width=width,
        height=height,
        duration_ms=duration_ms,
        session=session,
        current_user=current_user,
    )


# Оставлен для совместимости со старой версией frontend.
@router.post(
    "/{chat_id}/image-messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_image_message(
    chat_id: int,
    file: UploadFile = File(...),
    ciphertext: str = Form(..., min_length=1),
    iv: str = Form(..., min_length=1, max_length=24),
    key_version: int = Form(default=1, ge=1),
    mime_type: str = Form(...),
    width: int = Form(..., ge=1, le=20000),
    height: int = Form(..., ge=1, le=20000),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return await create_attachment_message(
        chat_id=chat_id,
        file=file,
        message_type="image",
        ciphertext=ciphertext,
        iv=iv,
        key_version=key_version,
        mime_type=mime_type,
        width=width,
        height=height,
        duration_ms=None,
        session=session,
        current_user=current_user,
    )


@router.get(
    "/{chat_id}/messages",
    response_model=MessageListResponse,
)
def get_messages(
    chat_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    before_id: int | None = Query(default=None, ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    check_chat_membership(
        chat_id=chat_id,
        user_id=current_user.id,
        session=session,
    )

    query = (
        session.query(Message)
        .options(selectinload(Message.attachment))
        .filter(Message.chat_id == chat_id)
    )

    if before_id is not None:
        query = query.filter(
            Message.id < before_id,
        )

    messages = (
        query
        .order_by(Message.id.desc())
        .limit(limit + 1)
        .all()
    )

    has_more = len(messages) > limit

    if has_more:
        messages = messages[:limit]

    messages.reverse()

    next_before_id = (
        messages[0].id
        if has_more and messages
        else None
    )

    return {
        "messages": [
            serialize_message(message)
            for message in messages
        ],
        "next_before_id": next_before_id,
        "has_more": has_more,
    }


@router.get(
    "/{chat_id}/messages/{message_id}/attachment",
)
def download_attachment(
    chat_id: int,
    message_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    check_chat_membership(
        chat_id=chat_id,
        user_id=current_user.id,
        session=session,
    )

    message = (
        session.query(Message)
        .options(selectinload(Message.attachment))
        .filter(
            Message.id == message_id,
            Message.chat_id == chat_id,
            Message.message_type.in_(
                ATTACHMENT_MESSAGE_TYPES
            ),
        )
        .first()
    )

    if message is None or message.attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )

    file_path = get_attachment_path(
        message.attachment.storage_key
    )

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment file not found",
        )

    return FileResponse(
        path=file_path,
        media_type="application/octet-stream",
        filename=(
            f"orbit-{message.message_type}-"
            f"{message.id}.enc"
        ),
    )


@router.delete(
    "/{chat_id}/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_message(
    chat_id: int,
    message_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    check_chat_membership(
        chat_id=chat_id,
        user_id=current_user.id,
        session=session,
    )

    message = (
        session.query(Message)
        .options(selectinload(Message.attachment))
        .filter(
            Message.id == message_id,
            Message.chat_id == chat_id,
        )
        .first()
    )

    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    if message.sender_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can delete only your own messages",
        )

    member_ids = get_chat_member_ids(
        chat_id=chat_id,
        session=session,
    )

    attachment_path = None

    if message.attachment is not None:
        attachment_path = get_attachment_path(
            message.attachment.storage_key
        )

    session.delete(message)
    session.commit()

    if attachment_path is not None:
        try:
            attachment_path.unlink(missing_ok=True)
        except OSError:
            logger.exception(
                "Could not delete attachment file %s",
                attachment_path,
            )

    event = {
        "type": "message.deleted",
        "message_id": message_id,
        "chat_id": chat_id,
    }

    for member_id in member_ids:
        await manager.send_to_user(
            user_id=member_id,
            data=event,
        )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )
