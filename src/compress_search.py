#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["headroom-ai"]
# ///
"""PostToolUse hook: compress grep/rg/ag output from the Bash tool via headroom's
SearchCompressor before it reaches Claude. Never breaks the underlying tool call -
any failure/ambiguity results in a silent no-op (exit 0, empty stdout).
"""

import json
import os
import shlex
import sys

SEARCH_BINS = {"grep", "egrep", "fgrep", "rgrep", "rg", "ripgrep", "ag", "ack"}
SHELL_OPERATORS = {"|", "||", "&&", ";"}
VALUE_FLAGS = {
    "-e", "--regexp", "-f", "--file", "-m", "--max-count",
    "-g", "--glob", "-t", "--type", "-A", "-B", "-C",
    "--context", "--after-context", "--before-context",
}


def bail(code: int = 0) -> None:
    sys.exit(code)


def split_segments(command: str):
    """Split a shell command into segments on |, ||, &&, ; using shlex."""
    lexer = shlex.shlex(command, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    tokens = list(lexer)

    segments, current = [], []
    for tok in tokens:
        if tok in SHELL_OPERATORS:
            if current:
                segments.append(current)
            current = []
        else:
            current.append(tok)
    if current:
        segments.append(current)
    return segments


def find_search_segment(command: str):
    """Return the first command segment that invokes a search binary, or None."""
    segments = split_segments(command)
    for seg in segments:
        for tok in seg:
            # skip leading env-var assignments like FOO=bar
            if "=" in tok and tok.split("=", 1)[0].isidentifier():
                continue
            base = os.path.basename(tok)
            if base in SEARCH_BINS:
                return seg
            if base == "git" and len(seg) > 1 and seg[1] == "grep":
                return seg
            break  # first real token wasn't a search binary
    return None


def extract_query(seg: list[str]) -> str:
    """Best-effort extraction of the search pattern for BM25 relevance hinting.

    Prefers an explicit -e/--regexp value; otherwise falls back to the first
    positional (non-flag, non-flag-value) argument after the binary name.
    """
    # drop leading binary name(s): 'grep' or 'git grep'
    args = seg[1:]
    if seg[0] == "git" and args and args[0] == "grep":
        args = args[1:]

    explicit = None
    positional = None
    awaiting_value_for = None  # flag name whose value is the next token

    for tok in args:
        if awaiting_value_for is not None:
            if awaiting_value_for in ("-e", "--regexp") and explicit is None:
                explicit = tok
            awaiting_value_for = None
            continue

        if tok in ("-e", "--regexp"):
            awaiting_value_for = tok
            continue

        if tok.startswith(("-e=", "--regexp=")):
            if explicit is None:
                explicit = tok.split("=", 1)[1]
            continue

        base_flag = tok.split("=", 1)[0]
        if base_flag in VALUE_FLAGS:
            if "=" not in tok:
                awaiting_value_for = base_flag
            continue

        if tok.startswith("-"):
            continue

        if positional is None:
            positional = tok

    return explicit or positional or ""


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        bail()
        return

    if payload.get("tool_name") != "Bash":
        bail()
        return

    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command.strip():
        bail()
        return

    tool_result = payload.get("tool_result") or {}
    text = tool_result.get("text")
    if not isinstance(text, str):
        bail()
        return

    min_chars = int(os.environ.get("SEARCH_COMPRESS_MIN_CHARS", "2000"))
    if len(text) < min_chars:
        bail()
        return

    try:
        segment = find_search_segment(command)
    except ValueError:
        # shlex couldn't parse the command (unbalanced quotes, etc.)
        bail()
        return

    if segment is None:
        bail()
        return

    query = extract_query(segment)

    try:
        from headroom.transforms import SearchCompressor, SearchCompressorConfig

        cfg = SearchCompressorConfig(
            max_total_matches=int(os.environ.get("SEARCH_COMPRESS_MAX_MATCHES", "30")),
            max_matches_per_file=int(os.environ.get("SEARCH_COMPRESS_MAX_PER_FILE", "5")),
            max_files=int(os.environ.get("SEARCH_COMPRESS_MAX_FILES", "15")),
            boost_errors=True,
        )
        result = SearchCompressor(cfg).compress(text, context=query)
    except Exception:
        bail()
        return

    if result.matches_omitted <= 0 or len(result.compressed) >= len(text):
        bail()
        return

    banner = (
        f"[search-compress] showing {result.compressed_match_count}/"
        f"{result.original_match_count} matches across {result.files_affected} files "
        f"({result.matches_omitted} omitted) - re-run with a narrower pattern for full output\n"
    )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedToolOutput": {
                "type": "text",
                "text": banner + result.compressed,
            },
        },
        "suppressOutput": True,
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
