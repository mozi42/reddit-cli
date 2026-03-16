"""HTTP client for Reddit public JSON endpoints + TTL-based cache."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Optional

import requests

import config
from storage import CacheStore, CacheMeta


class FetchStatus(Enum):
    SUCCESS = "success"
    NETWORK_ERROR = "network_error"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    CLIENT_ERROR = "client_error"
    PARSE_ERROR = "parse_error"


@dataclass
class FetchResult:
    ok: bool
    status: FetchStatus
    request_kind: str
    cache_key: str
    url: str
    params: dict[str, Any]
    payload: Optional[Any]
    meta: Optional[CacheMeta]
    http_status: Optional[int]
    error: Optional[str]
    from_cache: bool


def _determine_status(http_status: Optional[int], parse_error: bool = False) -> FetchStatus:
    if parse_error:
        return FetchStatus.PARSE_ERROR
    if http_status is None:
        return FetchStatus.NETWORK_ERROR
    if http_status == 429:
        return FetchStatus.RATE_LIMITED
    if 500 <= http_status < 600:
        return FetchStatus.SERVER_ERROR
    if 400 <= http_status < 500:
        return FetchStatus.CLIENT_ERROR
    if 200 <= http_status < 300:
        return FetchStatus.SUCCESS
    return FetchStatus.NETWORK_ERROR


def _normalize_subreddit(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("/"):
        s = s[1:]
    sl = s.lower()
    if sl.startswith("r/"):
        s = s[2:]
    return s.strip("/")


class RedditClient:
    def __init__(self, *, respect_ttl: bool = True, force_refresh: bool = False):
        self.respect_ttl = respect_ttl
        self.force_refresh = force_refresh
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        self.cache = CacheStore()

    def _cache_key(self, request_kind: str, url: str, params: dict[str, Any]) -> str:
        # normalize params ordering
        items = "&".join(f"{k}={params[k]}" for k in sorted(params.keys()))
        return f"{request_kind}|{url}?{items}"

    def get_posts(
        self,
        subreddit: str,
        *,
        sort: str = "hot",
        limit: int = 25,
        time: Optional[str] = None,
        after: Optional[str] = None,
        before: Optional[str] = None,
    ) -> FetchResult:
        subreddit = _normalize_subreddit(subreddit)
        sort = (sort or "hot").lower()

        url = f"{config.BASE_URL}/r/{subreddit}/{sort}.json"
        params: dict[str, Any] = {"limit": int(limit)}
        if sort == "top" and time:
            params["t"] = time
        if after:
            params["after"] = after
        if before:
            params["before"] = before

        request_kind = f"posts:{sort}"
        return self._get_json(request_kind, url, params)

    def get_post(
        self,
        subreddit: str,
        post_id: str,
    ) -> FetchResult:
        subreddit = _normalize_subreddit(subreddit)
        # Fetch via comments endpoint; we will ignore comments later.
        url = f"{config.BASE_URL}/r/{subreddit}/comments/{post_id}.json"
        params = {"limit": 1, "depth": 1}
        return self._get_json("post", url, params)

    def get_comments(
        self,
        subreddit: str,
        post_id: str,
        *,
        sort: str = "best",
        limit: int = 25,
        depth: Optional[int] = None,
    ) -> FetchResult:
        subreddit = _normalize_subreddit(subreddit)
        url = f"{config.BASE_URL}/r/{subreddit}/comments/{post_id}.json"
        params: dict[str, Any] = {"sort": sort, "limit": int(limit)}
        if depth is not None:
            params["depth"] = int(depth)
        return self._get_json("comments", url, params)

    def _get_json(self, request_kind: str, url: str, params: dict[str, Any]) -> FetchResult:
        cache_key = self._cache_key(request_kind, url, params)

        if not self.force_refresh:
            cached_payload, cached_meta = self.cache.get(cache_key)
            if cached_payload is not None and cached_meta is not None:
                cached_http = cached_meta.status if cached_meta.status != 0 else None
                cached_status = _determine_status(cached_http)
                cached_ok = cached_status == FetchStatus.SUCCESS and not cached_meta.error
                return FetchResult(
                    ok=cached_ok,
                    status=cached_status,
                    request_kind=request_kind,
                    cache_key=cache_key,
                    url=url,
                    params=params,
                    payload=cached_payload if cached_ok else None,
                    meta=cached_meta,
                    http_status=cached_http,
                    error=None if cached_ok else (cached_meta.error or f"HTTP {cached_http}"),
                    from_cache=True,
                )

        http_status: Optional[int] = None
        error: Optional[str] = None
        parse_error = False
        payload: Optional[Any] = None
        ratelimit_remaining: Optional[str] = None
        ratelimit_reset: Optional[str] = None

        try:
            resp = self.session.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
            http_status = resp.status_code
            ratelimit_remaining = resp.headers.get("x-ratelimit-remaining")
            ratelimit_reset = resp.headers.get("x-ratelimit-reset")

            # For Reddit, a 200 may still contain weird HTML if blocked; try json parse.
            try:
                payload = resp.json()
            except Exception as e:
                parse_error = True
                error = f"JSON parse failed: {e}"

            if not parse_error:
                if not (200 <= http_status < 300):
                    error = f"HTTP {http_status}"

        except requests.exceptions.Timeout:
            error = "Request timed out"
        except requests.exceptions.ConnectionError as e:
            error = f"Connection error: {e}"
        except requests.exceptions.RequestException as e:
            error = f"Request failed: {e}"
        except Exception as e:
            error = f"Unexpected error: {e}"

        status = _determine_status(http_status, parse_error)
        ok = status == FetchStatus.SUCCESS

        ttl = config.TTL.for_request(request_kind) if ok else config.TTL.for_error(http_status, parse_error)

        # Cache whatever we got (including error payload when available) to support backoff.
        cache_payload = payload if payload is not None else {"error": error, "http_status": http_status}
        meta = self.cache.put(
            cache_key,
            cache_payload,
            request_kind=request_kind,
            url=url,
            params=params,
            ttl_seconds=ttl,
            status=http_status or 0,
            ratelimit_remaining=ratelimit_remaining,
            ratelimit_reset=ratelimit_reset,
            error=error,
        )

        return FetchResult(
            ok=ok,
            status=status,
            request_kind=request_kind,
            cache_key=cache_key,
            url=url,
            params=params,
            payload=payload if ok else None,
            meta=meta,
            http_status=http_status,
            error=error,
            from_cache=False,
        )
