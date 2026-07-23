from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_session
from app.dependencies import get_current_user
from app.models import User
from app.schemas import UserCreate, UserResponse
from app.security import hash_password


router = APIRouter(
    prefix="/api/users",
    tags=["users"],
)


@router.get(
    "/search",
    response_model=list[UserResponse],
)
def search_users(
    q: str = Query(min_length=1, max_length=20),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    users = (
        session.query(User)
        .filter(
            User.username.ilike(f"%{q}%"),
            User.id != current_user.id,
        )
        .limit(20)
        .all()
    )

    return users


@router.get(
    "/{user_id}",
    response_model=UserResponse,
)
def get_user(
    user_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    user = (
        session.query(User)
        .filter_by(id=user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Пользователь не найден",
        )

    return user


@router.post(
    "",
    response_model=UserResponse,
    status_code=201,
)
def create_user(
    user_data: UserCreate,
    session: Session = Depends(get_session),
):
    existing_user = (
        session.query(User)
        .filter_by(username=user_data.username)
        .first()
    )

    if existing_user is not None:
        raise HTTPException(
            status_code=409,
            detail="Пользователь с таким именем уже существует",
        )

    new_user = User(
        username=user_data.username,
        password_hash=hash_password(user_data.password),
    )

    session.add(new_user)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()

        raise HTTPException(
            status_code=409,
            detail="Пользователь с таким именем уже существует",
        )

    session.refresh(new_user)
    session.commit()

    return new_user