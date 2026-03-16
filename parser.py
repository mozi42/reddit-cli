"""Parse Reddit JSON responses into simple Python structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import html
import re


@dataclass
class Post:
    id: str
    subreddit: str
    title: str
    author: str
    score: int
    num_comments: int
    created_utc: float
    domain: str
    url: str
    permalink: str
    is_self: bool
    selftext: str

    # Optional extra signals (no extra requests)
    thumbnail: str
    media_urls: list[str]
    selftext_urls: list[str]


@dataclass
class Comment:
    id: str
    parent: str  # id without t1_/t3_ prefix
    author: str
    score: int
    created_utc: float
    body: str
    depth: int
    replies: list["Comment"]


_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def _dedupe_keep_order(urls: list[str], *, max_items: int = 8) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        u = (u or "").strip()
        if not u:
            continue
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= max_items:
            break
    return out


def _extract_thumbnail(d: dict[str, Any]) -> str:
    t = d.get("thumbnail")
    if isinstance(t, str) and t.startswith("http"):
        return html.unescape(t)
    return ""


def _extract_media_urls(d: dict[str, Any]) -> list[str]:
    urls: list[str] = []

    # Direct link that looks like an image
    u = d.get("url")
    if isinstance(u, str) and re.search(r"\.(png|jpe?g|gif|webp)(\?|$)", u, re.IGNORECASE):
        urls.append(u)

    # preview.images[*].source.url
    preview = d.get("preview")
    if isinstance(preview, dict):
        images = preview.get("images")
        if isinstance(images, list):
            for im in images:
                if not isinstance(im, dict):
                    continue
                src = im.get("source")
                if isinstance(src, dict):
                    su = src.get("url")
                    if isinstance(su, str):
                        urls.append(html.unescape(su))

    # gallery: media_metadata[*].s.u
    if d.get("is_gallery") and isinstance(d.get("media_metadata"), dict):
        mm = d.get("media_metadata") or {}
        for _, v in mm.items():
            if not isinstance(v, dict):
                continue
            s = v.get("s")
            if isinstance(s, dict):
                su = s.get("u") or s.get("gif")
                if isinstance(su, str):
                    urls.append(html.unescape(su))

    return _dedupe_keep_order(urls, max_items=8)


def _extract_selftext_urls(selftext: str) -> list[str]:
    if not selftext:
        return []
    found = _URL_RE.findall(selftext)
    # Strip common trailing punctuation from markdown-ish text.
    cleaned: list[str] = []
    for f in found:
        cleaned.append(f.rstrip(")].,;"))
    return _dedupe_keep_order(cleaned, max_items=8)


def parse_posts_listing(payload: dict[str, Any]) -> list[Post]:
    children = (((payload or {}).get("data") or {}).get("children") or [])
    posts: list[Post] = []
    for child in children:
        if not isinstance(child, dict):
            continue
        if child.get("kind") != "t3":
            continue
        d = child.get("data") or {}
        selftext = str(d.get("selftext") or "")
        posts.append(
            Post(
                id=str(d.get("id") or ""),
                subreddit=str(d.get("subreddit") or ""),
                title=str(d.get("title") or ""),
                author=str(d.get("author") or ""),
                score=int(d.get("score") or 0),
                num_comments=int(d.get("num_comments") or 0),
                created_utc=float(d.get("created_utc") or 0.0),
                domain=str(d.get("domain") or ""),
                url=str(d.get("url") or ""),
                permalink=str(d.get("permalink") or ""),
                is_self=bool(d.get("is_self") or False),
                selftext=selftext,
                thumbnail=_extract_thumbnail(d),
                media_urls=_extract_media_urls(d),
                selftext_urls=_extract_selftext_urls(selftext),
            )
        )
    return posts


def parse_post_and_comments(payload: Any, *, max_depth: Optional[int] = None) -> tuple[Optional[Post], list[Comment]]:
    """Payload is typically a 2-element list: [post_listing, comments_listing]."""
    if not isinstance(payload, list) or len(payload) < 1:
        return None, []

    post_listing = payload[0]
    post: Optional[Post] = None
    try:
        posts = parse_posts_listing(post_listing)
        post = posts[0] if posts else None
    except Exception:
        post = None

    comments: list[Comment] = []
    if len(payload) >= 2:
        comments_listing = payload[1]
        comments = parse_comments_listing(comments_listing, max_depth=max_depth)

    return post, comments


def parse_comments_listing(payload: dict[str, Any], *, max_depth: Optional[int] = None) -> list[Comment]:
    children = (((payload or {}).get("data") or {}).get("children") or [])
    out: list[Comment] = []
    for child in children:
        c = _parse_comment_child(child, depth=0, max_depth=max_depth)
        if c:
            out.append(c)
    return out


def _parse_comment_child(child: Any, *, depth: int, max_depth: Optional[int]) -> Optional[Comment]:
    if max_depth is not None and depth >= max_depth:
        return None

    if not isinstance(child, dict):
        return None

    kind = child.get("kind")
    if kind != "t1":
        # skip "more" and unknown kinds for minimal CLI
        return None

    d = child.get("data") or {}
    replies_field = d.get("replies")

    parent_id = str(d.get("parent_id") or "")
    parent = parent_id
    if parent.startswith("t1_") or parent.startswith("t3_"):
        parent = parent[3:]

    replies: list[Comment] = []
    if isinstance(replies_field, dict):
        # replies is a listing
        rep_children = (((replies_field.get("data") or {}).get("children")) or [])
        for rc in rep_children:
            parsed = _parse_comment_child(rc, depth=depth + 1, max_depth=max_depth)
            if parsed:
                replies.append(parsed)

    return Comment(
        id=str(d.get("id") or ""),
        parent=parent,
        author=str(d.get("author") or ""),
        score=int(d.get("score") or 0),
        created_utc=float(d.get("created_utc") or 0.0),
        body=str(d.get("body") or ""),
        depth=depth,
        replies=replies,
    )
