from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.database import SessionLocal
from app.dependencies import get_websocket_user_id
from app.models import User
from app.websocket_manager import manager


router = APIRouter(
    prefix="/api/ws",
    tags=["websocket"],
)


def websocket_user_exists(user_id: int) -> bool:
    with SessionLocal() as session:
        user = session.get(User, user_id)
        return user is not None


@router.websocket("")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int = Depends(get_websocket_user_id),
):
    if not websocket_user_exists(user_id):
        await websocket.close(code=1008)
        return

    await manager.connect(
        user_id=user_id,
        websocket=websocket,
    )

    try:
        await websocket.send_json(
            {
                "type": "connection.ready",
                "user_id": user_id,
            }
        )

        while True:
            data = await websocket.receive_json()

            event_type = data.get("type")

            if event_type == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                    }
                )

    except WebSocketDisconnect:
        pass

    finally:
        manager.disconnect(
            user_id=user_id,
            websocket=websocket,
        )