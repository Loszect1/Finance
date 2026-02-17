from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Tuple


class TTLCache:
    """Simple in-memory TTL cache suitable for single-process FastAPI apps.

    For production scaling across multiple instances, replace with Redis or similar.
    """

    def __init__(self) -> None:
        self._store: Dict[str, Tuple[datetime, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if not item:
            return None
        expires_at, value = item
        if datetime.utcnow() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        self._store[key] = (expires_at, value)

    def cached(
        self,
        key_builder: Callable[..., str],
        ttl_seconds: int,
    ) -> Callable:
        """Decorator-style helper to cache function results with custom key."""

        def decorator(func: Callable) -> Callable:
            def wrapper(*args, **kwargs):
                cache_key = key_builder(*args, **kwargs)
                cached_value = self.get(cache_key)
                if cached_value is not None:
                    return cached_value
                result = func(*args, **kwargs)
                self.set(cache_key, result, ttl_seconds)
                return result

            return wrapper

        return decorator


ttl_cache = TTLCache()

