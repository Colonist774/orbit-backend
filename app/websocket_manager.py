from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(
        self,
        user_id: int,
        websocket: WebSocket,
    ) -> None:
        await websocket.accept()
        self.active_connections[user_id].add(websocket)

    def disconnect(
        self,
        user_id: int,
        websocket: WebSocket,
    ) -> None:
        connections = self.active_connections.get(user_id)

        if connections is None:
            return

        connections.discard(websocket)

        if not connections:
            del self.active_connections[user_id]

    async def send_to_user(
        self,
        user_id: int,
        data: dict,
    ) -> None:
        connections = self.active_connections.get(user_id)

        if not connections:
            return

        dead_connections: list[WebSocket] = []

        for websocket in connections.copy():
            try:
                await websocket.send_json(data)
            except Exception:
                dead_connections.append(websocket)

        for websocket in dead_connections:
            self.disconnect(
                user_id=user_id,
                websocket=websocket,
            )


manager = ConnectionManager()