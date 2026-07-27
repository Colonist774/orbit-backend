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

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/avif",
}

UPLOAD_ROOT = Path(settings.orbit_upload_dir)
IMAGE_UPLOAD_DIR = UPLOAD_ROOT / "images"
FILE_CHUNK_SIZE = 1024 * 1024



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
) -> int:
    max_bytes = (
        settings.max_image_size_mb * 1024 * 1024
    )

    # AES-GCM добавляет небольшой authentication tag, поэтому
    # оставляем небольшой запас сверх лимита исходного файла.
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
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            "Image exceeds the allowed size "
                            f"of {settings.max_image_size_mb} MB"
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
            detail="Uploaded image is empty",
        )

    return written_bytes


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
    check_chat_membership(
        chat_id=chat_id,
        user_id=current_user.id,
        session=session,
    )

    if mime_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPEG, PNG and WebP images are supported",
        )

    IMAGE_UPLOAD_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    storage_key = f"{uuid4().hex}.enc"
    destination = IMAGE_UPLOAD_DIR / storage_key

    try:
        size_bytes = await save_encrypted_upload(
            upload=file,
            destination=destination,
        )
    except HTTPException:
        raise
    except OSError as error:
        logger.exception(
            "Could not save encrypted image"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save image",
        ) from error

    message = Message(
        chat_id=chat_id,
        sender_id=current_user.id,
        message_type="image",
        ciphertext=ciphertext,
        iv=iv,
        key_version=key_version,
    )

    attachment = Attachment(
        storage_key=storage_key,
        mime_type=mime_type,
        size_bytes=size_bytes,
        width=width,
        height=height,
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
            "Could not create image message"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create image message",
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
def download_image_attachment(
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
            Message.message_type == "image",
        )
        .first()
    )

    if message is None or message.attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image attachment not found",
        )

    file_path = (
        IMAGE_UPLOAD_DIR /
        message.attachment.storage_key
    )

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image file not found",
        )

    return FileResponse(
        path=file_path,
        media_type="application/octet-stream",
        filename=f"orbit-image-{message.id}.enc",
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
        attachment_path = (
            IMAGE_UPLOAD_DIR /
            message.attachment.storage_key
        )

    session.delete(message)
    session.commit()

    if attachment_path is not None:
        try:
            attachment_path.unlink(missing_ok=True)
        except OSError:
            logger.exception(
                "Could not delete image file %s",
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
