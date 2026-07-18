from fastapi import Depends, HTTPException, WebSocket, WebSocketException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import User
from app.security import decode_access_token


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/login",
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    try:
        user_id = decode_access_token(token)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Недействительный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = (
        session.query(User)
        .filter_by(id=user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Пользователь из токена не найден",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_websocket_user_id(
    websocket: WebSocket,
) -> int:
    token = websocket.query_params.get("token")

    if token is None:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Token is missing",
        )

    try:
        return decode_access_token(token)
    except ValueError:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid token",
        )