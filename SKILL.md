---
name: reddit-cli
description: Fetches and prints Reddit listings and comment threads with explicit, LLM-friendly formatting. Uses Reddit public JSON endpoints plus a local XDG cache. Use when you need quick subreddit/post/comment inspection from the terminal without API keys.
version: 1
tags: [cli, reddit, scraping]
metadata:
  git_remote: ""
  managed_by: mozi
---

## What this skill is

A small Python CLI for reading Reddit (subreddit listings + a post’s comment thread) with output designed to be easy for humans *and* LLMs to skim.

## Files

- `reddit_cli.py` — entrypoint (the `reddit-cli` command)
- `reddit_client.py` — HTTP client (Reddit public JSON endpoints)
- `formatter.py` — text/JSON formatting
- `storage.py` — filesystem cache (XDG cache dir)

## Install

```bash
bash skills/reddit-cli/install.sh
```

Creates/updates a symlink:
- `~/.local/bin/reddit-cli` → `<workspace>/skills/reddit-cli/reddit_cli.py`

## Usage

```bash
reddit-cli technology --new --limit 5
reddit-cli technology --after t3_xxxxxxx --limit 5
reddit-cli technology --post 1rv46ts --comments --depth 6
reddit-cli technology --post 1rv46ts --comments --json
```

### Caching

- Default cache: `~/.cache/reddit-cli/`
- Override: set `REDDIT_CLI_DATA_DIR=/some/path`
- Use `--force` to bypass cache.

### Output conventions (text mode)

- Listings include `next: --after <cursor>` for pagination.
- Comments include explicit thread markers (no indentation dependence): `dN`, `RE:<parentId>`, `id:<commentId>`.
