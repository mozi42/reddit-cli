"""File-based cache storage for Reddit CLI.

Layout:
  reddit-cli/data/reddit/
    cache/
      <slug>_<hash>.json
    meta.json

We keep meta.json as a simple dict of cache_key -> entry.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import config

config.ensure_dirs()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(s: str, max_len: int = 80) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s[:max_len] if s else "cache"


def _hash10(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


@dataclass
class CacheMeta:
    cache_key: str
    filename: str
    fetched_at: str  # ISO
    expires_at: str  # ISO
    status: int
    request_kind: str
    url: str
    params: dict[str, Any]
    from_cache: bool = False
    error: Optional[str] = None
    ratelimit_remaining: Optional[str] = None
    ratelimit_reset: Optional[str] = None

    def is_expired(self) -> bool:
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return _utcnow() > exp
        except Exception:
            return True


class CacheStore:
    def __init__(self, cache_dir: Path | None = None, meta_path: Path | None = None):
        self.cache_dir = cache_dir or config.CACHE_DIR
        self.meta_path = meta_path or config.META_PATH

    def _load_meta(self) -> dict[str, Any]:
        if not self.meta_path.exists():
            return {}
        try:
            return json.loads(self.meta_path.read_text())
        except Exception:
            return {}

    def _save_meta(self, meta: dict[str, Any]) -> None:
        tmp = self.meta_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, indent=2, sort_keys=True))
        tmp.replace(self.meta_path)

    def _filename_for_key(self, cache_key: str) -> str:
        return f"{_slugify(cache_key)}_{_hash10(cache_key)}.json"

    def get(self, cache_key: str) -> tuple[Optional[Any], Optional[CacheMeta]]:
        meta = self._load_meta()
        entry = meta.get(cache_key)
        if not entry:
            return None, None

        cm = CacheMeta(**entry)
        cm.from_cache = True

        if cm.is_expired():
            return None, cm

        path = self.cache_dir / cm.filename
        if not path.exists():
            return None, cm

        try:
            return json.loads(path.read_text()), cm
        except Exception as e:
            return None, CacheMeta(**{**entry, "error": f"cache read/parse failed: {e}"})

    def put(
        self,
        cache_key: str,
        payload: Any,
        *,
        request_kind: str,
        url: str,
        params: dict[str, Any],
        ttl_seconds: int,
        status: int,
        ratelimit_remaining: Optional[str] = None,
        ratelimit_reset: Optional[str] = None,
        error: Optional[str] = None,
    ) -> CacheMeta:
        filename = self._filename_for_key(cache_key)
        path = self.cache_dir / filename

        fetched = _utcnow()
        expires = fetched.timestamp() + ttl_seconds
        expires_dt = datetime.fromtimestamp(expires, tz=timezone.utc)

        # Write cache payload (even for error responses, if provided)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload))
        tmp.replace(path)

        cm = CacheMeta(
            cache_key=cache_key,
            filename=filename,
            fetched_at=fetched.isoformat(),
            expires_at=expires_dt.isoformat(),
            status=status,
            request_kind=request_kind,
            url=url,
            params=params,
            from_cache=False,
            error=error,
            ratelimit_remaining=ratelimit_remaining,
            ratelimit_reset=ratelimit_reset,
        )

        meta = self._load_meta()
        meta[cache_key] = asdict(cm)
        self._save_meta(meta)

        return cm
