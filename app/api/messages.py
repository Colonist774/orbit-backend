from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.models import Chat, ChatMember, Message, User
from app.schemas import (
    MessageCreate,
    MessageListResponse,
    MessageResponse,
)
from app.websocket_manager import manager


router = APIRouter(
    prefix="/api/chats",
    tags=["messages"],
)


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

    event = {
        "type": "message.created",
        "message": {
            "id": message.id,
            "chat_id": message.chat_id,
            "sender_id": message.sender_id,
            "ciphertext": message.ciphertext,
            "iv": message.iv,
            "key_version": message.key_version,
            "created_at": message.created_at.isoformat(),
        },
    }

    for member_id in member_ids:
        await manager.send_to_user(
            user_id=member_id,
            data=event,
        )

    return message


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

    query = session.query(Message).filter(
        Message.chat_id == chat_id,
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
        "messages": messages,
        "next_before_id": next_before_id,
        "has_more": has_more,
    }


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

    session.delete(message)
    session.commit()

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