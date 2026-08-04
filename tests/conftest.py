import io
import json
import sys
import types

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Prevent host environment from leaking SEARCH_COMPRESS_* into tests."""
    for key in list(__import__("os").environ):
        if key.startswith("SEARCH_COMPRESS_"):
            monkeypatch.delenv(key, raising=False)


class FakeResult:
    def __init__(
        self,
        compressed="",
        matches_omitted=0,
        compressed_match_count=0,
        original_match_count=0,
        files_affected=0,
    ):
        self.compressed = compressed
        self.matches_omitted = matches_omitted
        self.compressed_match_count = compressed_match_count
        self.original_match_count = original_match_count
        self.files_affected = files_affected


class FakeConfig:
    """Records the kwargs it was constructed with."""

    last_kwargs = None

    def __init__(self, **kwargs):
        FakeConfig.last_kwargs = kwargs
        self.kwargs = kwargs


class FakeCompressor:
    """Records calls; result/raises are configured per-test via class attrs."""

    result = None
    raises = None
    last_call = None

    def __init__(self, config):
        self.config = config

    def compress(self, text, context=""):
        FakeCompressor.last_call = {"text": text, "context": context}
        if FakeCompressor.raises is not None:
            raise FakeCompressor.raises
        return FakeCompressor.result


@pytest.fixture
def fake_headroom(monkeypatch):
    """Install a fake headroom.transforms module and reset stub state per-test."""
    FakeConfig.last_kwargs = None
    FakeCompressor.result = FakeResult()
    FakeCompressor.raises = None
    FakeCompressor.last_call = None

    transforms_mod = types.ModuleType("headroom.transforms")
    transforms_mod.SearchCompressor = FakeCompressor
    transforms_mod.SearchCompressorConfig = FakeConfig

    headroom_mod = types.ModuleType("headroom")
    headroom_mod.transforms = transforms_mod

    monkeypatch.setitem(sys.modules, "headroom", headroom_mod)
    monkeypatch.setitem(sys.modules, "headroom.transforms", transforms_mod)

    return types.SimpleNamespace(Result=FakeResult, Config=FakeConfig, Compressor=FakeCompressor)


@pytest.fixture
def run_hook(monkeypatch, capsys):
    """Feed a payload dict to compress_search.main() via stdin, capture stdout.

    Returns (exit_code, stdout_str). main() always calls sys.exit via bail()
    or falls through (implicit exit code None -> treated as 0).
    """
    import compress_search

    def _run(payload):
        if isinstance(payload, str):
            stdin_text = payload
        else:
            stdin_text = json.dumps(payload)
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
        try:
            compress_search.main()
            code = 0
        except SystemExit as exc:
            code = exc.code if exc.code is not None else 0
        out = capsys.readouterr().out
        return code, out

    return _run
