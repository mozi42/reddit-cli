#!/usr/bin/env python3
"""Minimal Reddit CLI (unauthenticated, JSON endpoints).

Usage:
  reddit_cli.py <subreddit> [options]

Examples:
  reddit_cli.py technology
  reddit_cli.py technology --new --limit 50
  reddit_cli.py technology --top --time week
  reddit_cli.py technology --post 1rv46ts
  reddit_cli.py technology --post 1rv46ts --comments --sort top --limit 10

Notes:
- Uses https://www.reddit.com/r/<sub>/<sort>.json and /comments/<id>.json
- No OAuth; public endpoints only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure local imports work when executed directly
PROJECT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_DIR))

from reddit_client import RedditClient
from parser import parse_posts_listing, parse_post_and_comments
from formatter import format_posts_list, format_post_detail, format_comments


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="reddit-cli", add_help=True)

    p.add_argument("subreddit", help="Subreddit name (without r/)")

    # Listing sort flags
    g = p.add_mutually_exclusive_group()
    g.add_argument("--hot", action="store_true", help="List hot posts (default)")
    g.add_argument("--new", action="store_true", help="List new posts")
    g.add_argument("--top", action="store_true", help="List top posts")
    g.add_argument("--rising", action="store_true", help="List rising posts")

    p.add_argument("--time", choices=["hour", "day", "week", "month", "year", "all"], help="Time filter for --top")

    # Post / comments
    p.add_argument("--post", metavar="ID", help="Post id (e.g. 1rv46ts)")
    p.add_argument("--comments", action="store_true", help="Include comments for --post")
    p.add_argument(
        "--sort",
        default=None,
        help="Sort. For listings: hot/new/top/rising. For comments: best/top/new/hot/controversial/old/qa",
    )
    p.add_argument("--depth", type=int, default=None, help="Max comment depth (default: 6 when using --comments)")

    p.add_argument("--limit", type=int, default=25, help="Items limit (posts or comments) (1-100)")

    # Pagination (explicit; no hidden state)
    p.add_argument("--after", default=None, help="Listing pagination cursor (e.g. t3_abc123)")
    p.add_argument("--before", default=None, help="Listing pagination cursor")

    # Global
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.add_argument("--force", action="store_true", help="Bypass cache")

    return p


def main() -> int:
    args = build_argparser().parse_args()

    subreddit = args.subreddit.strip()
    if subreddit.startswith("/"):
        subreddit = subreddit[1:]
    if subreddit.lower().startswith("r/"):
        subreddit = subreddit[2:]
    subreddit = subreddit.strip("/")
    limit = max(1, min(100, int(args.limit)))

    client = RedditClient(respect_ttl=not args.force, force_refresh=args.force)

    # Decide mode
    if args.post:
        post_id = args.post.strip()

        if args.comments:
            comment_sort = (args.sort or "best").lower()
            depth = args.depth if args.depth is not None else 6
            res = client.get_comments(subreddit, post_id, sort=comment_sort, limit=limit, depth=depth)
            if not res.ok or res.payload is None:
                print(f"Error fetching comments: {res.error or res.http_status}")
                return 1

            post, comments = parse_post_and_comments(res.payload, max_depth=depth)
            if args.json:
                print(json.dumps({"subreddit": subreddit, "post": post_id, "post_data": res.payload}, separators=(",", ":")))
                return 0

            if post:
                print(format_post_detail(post), end="")
            print(format_comments(comments, header=f"Top comments ({comment_sort}):", max_comments=limit), end="")
            return 0

        # Post-only
        res = client.get_post(subreddit, post_id)
        if not res.ok or res.payload is None:
            print(f"Error fetching post: {res.error or res.http_status}")
            return 1

        post, _ = parse_post_and_comments(res.payload)
        if args.json:
            print(json.dumps({"subreddit": subreddit, "post": post_id, "post_data": res.payload}, separators=(",", ":")))
            return 0

        if not post:
            print("Post not found (or parse failed)")
            return 1

        print(format_post_detail(post), end="")
        print("--comments to view discussion")
        return 0

    # Listing mode
    # sort selection precedence:
    # 1) explicit flags
    # 2) --sort if it looks like a listing sort
    sort = "hot"
    if args.new:
        sort = "new"
    elif args.top:
        sort = "top"
    elif args.rising:
        sort = "rising"
    elif args.hot:
        sort = "hot"
    elif args.sort and args.sort.lower() in ("hot", "new", "top", "rising"):
        sort = args.sort.lower()

    res = client.get_posts(subreddit, sort=sort, limit=limit, time=args.time, after=args.after, before=args.before)
    if not res.ok or res.payload is None:
        print(f"Error fetching posts: {res.error or res.http_status}")
        return 1

    if args.json:
        print(json.dumps({"subreddit": subreddit, "sort": sort, "limit": limit, "data": res.payload}, separators=(",", ":")))
        return 0

    posts = parse_posts_listing(res.payload)
    source = "cache" if res.from_cache else "fresh"
    print(format_posts_list(subreddit, sort, posts, limit, source=source), end="")

    data = res.payload.get("data") if isinstance(res.payload, dict) else None
    after = (data or {}).get("after")
    before = (data or {}).get("before")
    if after:
        print(f"next: --after {after}")
    if before:
        print(f"prev: --before {before}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
