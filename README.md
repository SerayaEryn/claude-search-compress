# Claude Search Compress

Claude Code plugin that compresses `grep`/`ripgrep`/`ag` output from the Bash tool via
headroom's `SearchCompressor`, before it reaches Claude's context.

## How it works

A `PostToolUse` hook (`src/compress_search.py`) inspects Bash tool calls. If the command
invokes a known search binary (`grep`, `egrep`, `fgrep`, `rgrep`, `rg`, `ripgrep`, `ag`,
`ack`, `git grep`) and the result is large, it compresses the output and replaces it with
a smaller, relevance-ranked version plus a banner noting how many matches were omitted.
Any parsing ambiguity or error results in a silent no-op — the original output is never
altered or lost.

### Environment variables

| Variable                       | Default | Purpose                                         |
|--------------------------------|---------|-------------------------------------------------|
| `SEARCH_COMPRESS_MIN_CHARS`    | `2000`  | Minimum output size before compression kicks in |
| `SEARCH_COMPRESS_MAX_MATCHES`  | `30`    | Max total matches kept                          |
| `SEARCH_COMPRESS_MAX_PER_FILE` | `5`     | Max matches kept per file                       |
| `SEARCH_COMPRESS_MAX_FILES`    | `15`    | Max files kept                                  |

## Install

Requires [`uv`](https://docs.astral.sh/uv/) on `PATH` — the hook runs via
`uv run --script`, which transparently installs the plugin's Python dependencies
(Python 3.10+) on first run, no separate setup needed.

```
/plugin marketplace add SerayaEryn/claude-search-compress
/plugin install claude-search-compress@claude-search-compress
```

## Development

```bash
uv sync --group dev
uv run pytest -v
```
