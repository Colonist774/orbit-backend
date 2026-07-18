from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, aliased

from app.database import get_session
from app.dependencies import get_current_user
from app.models import Chat, ChatMember, User
from app.schemas import ChatCreate, ChatListItem, ChatResponse


router = APIRouter(
    prefix="/api/chats",
    tags=["chats"],
)


@router.get(
    "",
    response_model=list[ChatListItem],
)
def get_chats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    current_membership = aliased(ChatMember)
    other_membership = aliased(ChatMember)

    rows = (
        session.query(Chat, User)
        .join(
            current_membership,
            current_membership.chat_id == Chat.id,
        )
        .join(
            other_membership,
            other_membership.chat_id == Chat.id,
        )
        .join(
            User,
            User.id == other_membership.user_id,
        )
        .filter(
            current_membership.user_id == current_user.id,
            other_membership.user_id != current_user.id,
        )
        .order_by(Chat.created_at.desc())
        .all()
    )

    return [
        {
            "id": chat.id,
            "created_at": chat.created_at,
            "other_user": other_user,
        }
        for chat, other_user in rows
    ]


@router.post(
    "",
    response_model=ChatResponse,
    status_code=201,
)
def create_chat(
    chat_data: ChatCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if chat_data.other_user_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Нельзя создать чат с самим собой",
        )

    other_user = (
        session.query(User)
        .filter_by(id=chat_data.other_user_id)
        .first()
    )

    if other_user is None:
        raise HTTPException(
            status_code=404,
            detail="Собеседник не найден",
        )

    current_member = aliased(ChatMember)
    other_member = aliased(ChatMember)

    existing_chat = (
        session.query(Chat)
        .join(
            current_member,
            current_member.chat_id == Chat.id,
        )
        .join(
            other_member,
            other_member.chat_id == Chat.id,
        )
        .filter(
            current_member.user_id == current_user.id,
            other_member.user_id == other_user.id,
        )
        .first()
    )

    if existing_chat is not None:
        return {
            "id": existing_chat.id,
            "created_at": existing_chat.created_at,
            "other_user": other_user,
        }

    new_chat = Chat()

    new_chat.members = [
        ChatMember(user_id=current_user.id),
        ChatMember(user_id=other_user.id),
    ]

    session.add(new_chat)
    session.commit()
    session.refresh(new_chat)

    return {
        "id": new_chat.id,
        "created_at": new_chat.created_at,
        "other_user": other_user,
    }