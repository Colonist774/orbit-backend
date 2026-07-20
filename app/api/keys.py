from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.models import User, UserPublicKey
from app.schemas import (
    PublicKeyCreate,
    PublicKeyResponse,
    UserPublicKeyResponse,
)


router = APIRouter(
    prefix="/api/keys",
    tags=["keys"],
)


@router.put(
    "/me",
    response_model=PublicKeyResponse,
)
def save_my_key(
    data: PublicKeyCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    key_record = (
        session.query(UserPublicKey)
        .filter(UserPublicKey.user_id == current_user.id)
        .first()
    )

    if key_record is None:
        key_record = UserPublicKey(
            user_id=current_user.id,
            public_key=data.public_key,
            algorithm=data.algorithm,
        )
        session.add(key_record)

    key_record.public_key = data.public_key
    key_record.algorithm = data.algorithm

    key_record.encrypted_private_key = (
        data.encrypted_private_key
    )
    key_record.private_key_iv = data.private_key_iv
    key_record.private_key_salt = (
        data.private_key_salt
    )
    key_record.private_key_kdf = data.private_key_kdf
    key_record.private_key_iterations = (
        data.private_key_iterations
    )

    session.commit()
    session.refresh(key_record)

    return key_record


@router.get(
    "/me",
    response_model=PublicKeyResponse,
)
def get_my_key(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    key_record = (
        session.query(UserPublicKey)
        .filter(UserPublicKey.user_id == current_user.id)
        .first()
    )

    if key_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key backup not found",
        )

    return key_record


@router.get(
    "/users/{user_id}",
    response_model=UserPublicKeyResponse,
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

    key_record = (
        session.query(UserPublicKey)
        .filter(UserPublicKey.user_id == user_id)
        .first()
    )

    if key_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Public key not found",
        )

    return key_record