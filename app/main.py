from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import (OAuth2PasswordRequestForm)
from sqlalchemy.orm import Session

from app.dependencies import get_current_user

from app.schemas import TokenResponse, UserResponse
from app.database import get_session
from app.models import User
from app.security import (
    create_access_token,
    decode_access_token,
    verify_password,
)
from app.api.users import router as users_router
from app.api.chats import router as chats_router
from app.api import messages
from app.api import websocket
from app.api import keys


app = FastAPI()


app.include_router(users_router)
app.include_router(chats_router)
app.include_router(messages.router)
app.include_router(websocket.router)
app.include_router(keys.router)


@app.post(
    "/api/login",
    response_model=TokenResponse,
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    user = (
        session.query(User)
        .filter_by(username=form_data.username)
        .first()
    )

    if (
        user is None
        or not verify_password(
            form_data.password,
            user.password_hash,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Неверное имя пользователя или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
    }


@app.get(
    "/api/me",
    response_model=UserResponse,
)
def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user