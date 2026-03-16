"""Pretty-format output for Reddit CLI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import re

from parser import Post, Comment

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def _count_urls(text: str) -> int:
    """Count distinct URLs in text (cheap heuristic; no extra requests)."""
    if not text:
        return 0
    found = _URL_RE.findall(text)
    if not found:
        return 0
    cleaned = [f.rstrip(")].,;") for f in found]
    seen: set[str] = set()
    for u in cleaned:
        seen.add(u)
    return len(seen)


def _rel_time_from_utc(ts: float) -> str:
    """Return a short relative time token (no automatic 'ago' suffix).

    Examples: "just now", "5m", "3h", "2d"
    """
    if not ts:
        return "?"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    diff = now - dt
    s = diff.total_seconds()
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{int(s // 60)}m"
    if s < 86400:
        return f"{int(s // 3600)}h"
    return f"{int(s // 86400)}d"


def _oneline(s: str) -> str:
    """Keep text readable in one line without truncating."""
    return (s or "").replace("\n", " ").strip()


def format_posts_list(
    subreddit: str,
    sort: str,
    posts: list[Post],
    limit: int,
    *,
    source: str | None = None,
) -> str:
    lines: list[str] = []
    src = f" ({source})" if source else ""
    lines.append(f"r/{subreddit} -- {sort} ({min(limit, len(posts))}){src}\n")

    for i, p in enumerate(posts[:limit], start=1):
        title = _oneline(p.title)
        domain = "self" if p.is_self else (p.domain or "")
        age = _rel_time_from_utc(p.created_utc)
        age_str = age if age in ("just now", "?") else f"{age} ago"

        markers: list[str] = []
        if getattr(p, "media_urls", None):
            markers.append("img")
        if getattr(p, "selftext_urls", None):
            markers.append("urls")
        if getattr(p, "thumbnail", "") and not getattr(p, "media_urls", None):
            markers.append("thumb")
        marker_str = f" [{' '.join(markers)}]" if markers else ""

        lines.append(
            f"{i}.  [{p.score}↑] {title}{marker_str} ({p.num_comments} comments) [id:{p.id}]"
        )
        lines.append(f"    {domain} | {age_str} by u/{p.author}")

        thumb = getattr(p, "thumbnail", "")
        if thumb:
            lines.append(f"    thumbnail: {thumb}")

        media_urls = list(getattr(p, "media_urls", []) or [])
        for mu in media_urls[:3]:
            lines.append(f"    media: {mu}")
        if len(media_urls) > 3:
            lines.append(f"    media: (+{len(media_urls) - 3} more)")

        text_links = list(getattr(p, "selftext_urls", []) or [])
        if text_links:
            lines.append(f"    text_links: {len(text_links)}")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def format_post_detail(post: Post) -> str:
    lines: list[str] = []
    age = _rel_time_from_utc(post.created_utc)
    age_str = age if age in ("just now", "?") else f"{age} ago"
    lines.append(f"{post.title} (r/{post.subreddit})")
    lines.append(f"by u/{post.author} • {age_str}")
    lines.append(f"{post.score} points • {post.num_comments} comments")
    lines.append("")
    if post.url:
        lines.append(post.url)
        lines.append("")

    thumb = getattr(post, "thumbnail", "")
    media_urls = list(getattr(post, "media_urls", []) or [])
    selftext_urls = list(getattr(post, "selftext_urls", []) or [])

    if thumb and thumb != post.url:
        lines.append(f"Thumbnail: {thumb}")

    extra_media = [u for u in media_urls if u and u != post.url]
    if extra_media:
        lines.append("Media:")
        for u in extra_media[:5]:
            lines.append(f"- {u}")
        if len(extra_media) > 5:
            lines.append(f"- (+{len(extra_media) - 5} more)")
        lines.append("")

    if post.selftext:
        lines.append(post.selftext.strip())
        lines.append("")

    if selftext_urls:
        lines.append("Links in text:")
        for u in selftext_urls[:5]:
            lines.append(f"- {u}")
        if len(selftext_urls) > 5:
            lines.append(f"- (+{len(selftext_urls) - 5} more)")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def format_comments(
    comments: list[Comment],
    *,
    header: str = "Top comments:",
    max_comments: Optional[int] = None,
) -> str:
    lines: list[str] = []
    lines.append(header)
    lines.append("")

    count = 0
    for idx, c in enumerate(comments):
        if max_comments is not None and count >= max_comments:
            break
        _render_comment(lines, c)
        count += 1
        # Exactly one blank line between top-level comments.
        if max_comments is None or count < max_comments:
            if idx != len(comments) - 1:
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_comment(lines: list[str], c: Comment) -> None:
    age = _rel_time_from_utc(c.created_utc)
    age_str = age if age in ("just now", "?") else f"{age} ago"

    # Compact, explicit threading markers.
    # Example:
    #   d2 RE:abc123 [340↑] u/name • 4h ago  id:def456
    prefix = f"d{c.depth}"
    if c.depth > 0 and getattr(c, "parent", ""):
        prefix += f" RE:{c.parent}"

    url_count = _count_urls(c.body or "")
    url_suffix = f"  urls:{url_count}" if url_count else ""
    lines.append(f"{prefix} [{c.score}↑] u/{c.author} • {age_str}  id:{c.id}{url_suffix}")

    body = (c.body or "").rstrip()
    for bl in body.splitlines() or [""]:
        if bl.strip() == "":
            lines.append("")
        else:
            lines.append(f"  {bl}")

    for r in c.replies:
        _render_comment(lines, r)
