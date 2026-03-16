# reddit-cli (minimal)

Minimal unauthenticated Reddit CLI built on the public `.json` endpoints.

## Usage

```bash
reddit-cli technology
reddit-cli technology --new --limit 50
reddit-cli technology --top --time week

reddit-cli technology --post 1rv46ts
reddit-cli technology --post 1rv46ts --comments
reddit-cli technology --post 1rv46ts --comments --sort top --limit 10

# Explicit pagination
reddit-cli technology --limit 25 --after t3_abc123

reddit-cli technology --json
reddit-cli technology --force
```

## Notes

- Listing endpoint: `https://www.reddit.com/r/<sub>/<sort>.json?limit=...`
- Comments endpoint: `https://www.reddit.com/r/<sub>/comments/<id>.json?sort=best&limit=...`
- Default comment depth is 6 when using `--comments` (override with `--depth N`).
- Comment headers are explicit:
  - `dN` is the nesting depth
  - `RE:<id>` (for replies) indicates which comment id this is replying to
  - `urls:N` appears when a comment contains URL(s)
- Listings may show `text_links: N` when a post selftext contains links.
- Listings print `next: --after <cursor>` for simple, explicit pagination.
- Cache is stored under `~/.cache/reddit-cli/` (XDG) with TTL.
  - Override: set `REDDIT_CLI_DATA_DIR`.
