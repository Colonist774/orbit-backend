from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.models import User, UserPublicKey
from app.schemas import PublicKeyCreate, PublicKeyResponse


router = APIRouter(
    prefix="/api/keys",
    tags=["keys"],
)


@router.put(
    "/me",
    response_model=PublicKeyResponse,
)
def save_public_key(
    data: PublicKeyCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    public_key = (
        session.query(UserPublicKey)
        .filter(UserPublicKey.user_id == current_user.id)
        .first()
    )

    if public_key is None:
        public_key = UserPublicKey(
            user_id=current_user.id,
            public_key=data.public_key,
            algorithm=data.algorithm,
        )

        session.add(public_key)
    else:
        public_key.public_key = data.public_key
        public_key.algorithm = data.algorithm

    session.commit()
    session.refresh(public_key)

    return public_key


@router.get(
    "/users/{user_id}",
    response_model=PublicKeyResponse,
)
def get_user_public_key(
    user_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    user = session.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    public_key = (
        session.query(UserPublicKey)
        .filter(UserPublicKey.user_id == user_id)
        .first()
    )

    if public_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Public key not found",
        )

    return public_key