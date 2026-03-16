"""Configuration for minimal Reddit CLI.

Goals:
- Use Reddit's public JSON endpoints (no OAuth)
- Keep paths relative to this project directory
- Centralize TTL + request settings
"""

from __future__ import annotations

from pathlib import Path
import os

# Project directory (where this file lives). Resolve symlinks for robustness.
PROJECT_DIR = Path(__file__).resolve().parent

# HTTP
BASE_URL = "https://www.reddit.com"
REQUEST_TIMEOUT = 30  # seconds
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)

# Storage
# Use XDG cache dir so the CLI works from any CWD and survives repo moves.
# Can be overridden with REDDIT_CLI_DATA_DIR.
_DEFAULT_CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
DATA_DIR = Path(os.environ.get("REDDIT_CLI_DATA_DIR", _DEFAULT_CACHE_ROOT / "reddit-cli"))
CACHE_DIR = DATA_DIR / "cache"
META_PATH = DATA_DIR / "meta.json"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


class TTL:
    """TTLs in seconds."""

    # Posts listing
    POSTS_HOT = 10 * 60
    POSTS_NEW = 5 * 60
    POSTS_TOP = 30 * 60
    POSTS_RISING = 10 * 60

    # Post details / comments
    POST_DETAILS = 15 * 60
    COMMENTS = 10 * 60

    # Errors (backoff)
    ERROR_RATE_LIMIT = 60
    ERROR_NETWORK = 30
    ERROR_SERVER = 2 * 60
    ERROR_CLIENT = 5 * 60
    ERROR_PARSE = 60

    @classmethod
    def for_request(cls, request_kind: str) -> int:
        return {
            "posts:hot": cls.POSTS_HOT,
            "posts:new": cls.POSTS_NEW,
            "posts:top": cls.POSTS_TOP,
            "posts:rising": cls.POSTS_RISING,
            "post": cls.POST_DETAILS,
            "comments": cls.COMMENTS,
        }.get(request_kind, cls.POST_DETAILS)

    @classmethod
    def for_error(cls, http_status: int | None, parse_error: bool = False) -> int:
        if parse_error:
            return cls.ERROR_PARSE
        if http_status is None:
            return cls.ERROR_NETWORK
        if http_status == 429:
            return cls.ERROR_RATE_LIMIT
        if 500 <= http_status < 600:
            return cls.ERROR_SERVER
        if 400 <= http_status < 500:
            return cls.ERROR_CLIENT
        return cls.ERROR_NETWORK
