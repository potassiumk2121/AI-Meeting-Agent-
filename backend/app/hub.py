from fastapi import WebSocket


class Hub:
    def __init__(self) -> None:
        self.rooms: dict[str, set[WebSocket]] = {}

    def join(self, meeting_id: str, socket: WebSocket) -> None:
        self.rooms.setdefault(meeting_id, set()).add(socket)

    def leave(self, meeting_id: str, socket: WebSocket) -> None:
        room = self.rooms.get(meeting_id)
        if not room:
            return
        room.discard(socket)
        if not room:
            self.rooms.pop(meeting_id, None)

    async def broadcast(self, meeting_id: str, payload: dict) -> None:
        dead: list[WebSocket] = []
        for socket in list(self.rooms.get(meeting_id, set())):
            try:
                await socket.send_json(payload)
            except Exception:
                dead.append(socket)
        for socket in dead:
            self.leave(meeting_id, socket)


hub = Hub()
