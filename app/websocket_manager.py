"""
websocket_manager.py
---------------------
Keeps track of active WebSocket connections per task_id and lets the
background agent runner broadcast live step updates to any client
watching that task (GET /status/{task_id} is the "pull" version of the
same data; the WebSocket is the "push" version).
"""

from fastapi import WebSocket
from collections import defaultdict


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, task_id: str, websocket: WebSocket):
        await websocket.accept()
        self._connections[task_id].append(websocket)

    def disconnect(self, task_id: str, websocket: WebSocket):
        if websocket in self._connections.get(task_id, []):
            self._connections[task_id].remove(websocket)
        if not self._connections.get(task_id):
            self._connections.pop(task_id, None)

    async def broadcast(self, task_id: str, message: dict):
        """Send `message` (JSON) to every client currently watching task_id."""
        dead = []
        for ws in self._connections.get(task_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(task_id, ws)


manager = ConnectionManager()
