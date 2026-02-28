import json

# In-memory storage when Redis is not available
_memory_store: dict[str, str] = {}


class MemoryService:
    def __init__(self):
        self.session_ttl = 3600  # 1 hour

    async def save_session(self, session_id: str, data: dict) -> None:
        key = f"session:{session_id}"
        _memory_store[key] = json.dumps(data, ensure_ascii=False)

    async def get_session(self, session_id: str) -> dict | None:
        key = f"session:{session_id}"
        data = _memory_store.get(key)
        if data:
            return json.loads(data)
        return None

    async def delete_session(self, session_id: str) -> None:
        key = f"session:{session_id}"
        _memory_store.pop(key, None)

    async def save_user_preference(self, user_id: str, preferences: dict) -> None:
        key = f"user_pref:{user_id}"
        _memory_store[key] = json.dumps(preferences, ensure_ascii=False)

    async def get_user_preference(self, user_id: str) -> dict | None:
        key = f"user_pref:{user_id}"
        data = _memory_store.get(key)
        if data:
            return json.loads(data)
        return None

    async def close(self):
        pass
