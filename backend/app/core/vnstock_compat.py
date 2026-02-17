from __future__ import annotations

from typing import Callable, Optional, Type


def get_rate_limit_exception() -> Type[Exception]:
    """Return vnstock rate limit exception class for current installed version."""
    try:
        from vnstock.core.quota import RateLimitExceeded  # type: ignore

        return RateLimitExceeded
    except Exception:
        pass

    try:
        from vnstock.core.exceptions import RateLimitError  # type: ignore

        return RateLimitError
    except Exception:
        pass

    return Exception


RateLimitException = get_rate_limit_exception()


def get_set_api_key() -> Optional[Callable[[str], None]]:
    """Return callable to set vnstock API key, if available."""
    try:
        from vnstock.core.settings import set_api_key  # type: ignore

        return set_api_key
    except Exception:
        return None

