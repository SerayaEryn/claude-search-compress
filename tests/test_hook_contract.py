import json

import pytest

BIG_TEXT = "x" * 3000  # over default SEARCH_COMPRESS_MIN_CHARS (2000)


def base_payload(**overrides):
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "rg pattern src/"},
        "tool_result": {"text": BIG_TEXT},
    }
    payload.update(overrides)
    return payload


class TestBailCases:
    def test_malformed_json_stdin(self, fake_headroom, run_hook):
        code, out = run_hook("not json{")
        assert code == 0
        assert out == ""

    def test_wrong_tool_name(self, fake_headroom, run_hook):
        code, out = run_hook(base_payload(tool_name="Read"))
        assert code == 0
        assert out == ""

    def test_missing_command(self, fake_headroom, run_hook):
        code, out = run_hook(base_payload(tool_input={}))
        assert code == 0
        assert out == ""

    def test_blank_command(self, fake_headroom, run_hook):
        code, out = run_hook(base_payload(tool_input={"command": "   "}))
        assert code == 0
        assert out == ""

    def test_non_string_command(self, fake_headroom, run_hook):
        code, out = run_hook(base_payload(tool_input={"command": 123}))
        assert code == 0
        assert out == ""

    def test_missing_tool_result(self, fake_headroom, run_hook):
        payload = base_payload()
        del payload["tool_result"]
        code, out = run_hook(payload)
        assert code == 0
        assert out == ""

    def test_text_not_string(self, fake_headroom, run_hook):
        code, out = run_hook(base_payload(tool_result={"text": 123}))
        assert code == 0
        assert out == ""

    def test_text_below_default_min_chars(self, fake_headroom, run_hook):
        code, out = run_hook(base_payload(tool_result={"text": "short"}))
        assert code == 0
        assert out == ""

    def test_text_below_custom_min_chars(self, monkeypatch, fake_headroom, run_hook):
        monkeypatch.setenv("SEARCH_COMPRESS_MIN_CHARS", "50000")
        code, out = run_hook(base_payload())  # BIG_TEXT is only 3000 chars
        assert code == 0
        assert out == ""

    def test_unbalanced_quotes_in_command(self, fake_headroom, run_hook):
        code, out = run_hook(base_payload(tool_input={"command": 'rg "unterminated'}))
        assert code == 0
        assert out == ""

    def test_no_search_binary_in_command(self, fake_headroom, run_hook):
        code, out = run_hook(base_payload(tool_input={"command": "ls -la"}))
        assert code == 0
        assert out == ""

    def test_compressor_raises_is_swallowed(self, fake_headroom, run_hook):
        fake_headroom.Compressor.raises = RuntimeError("boom")
        code, out = run_hook(base_payload())
        assert code == 0
        assert out == ""

    def test_zero_matches_omitted(self, fake_headroom, run_hook):
        fake_headroom.Compressor.result = fake_headroom.Result(
            compressed="short", matches_omitted=0
        )
        code, out = run_hook(base_payload())
        assert code == 0
        assert out == ""

    def test_compressed_not_smaller_than_original(self, fake_headroom, run_hook):
        fake_headroom.Compressor.result = fake_headroom.Result(
            compressed=BIG_TEXT + "more", matches_omitted=5
        )
        code, out = run_hook(base_payload())
        assert code == 0
        assert out == ""


class TestSuccessCase:
    def test_valid_payload_emits_hook_output(self, fake_headroom, run_hook):
        fake_headroom.Compressor.result = fake_headroom.Result(
            compressed="compressed body",
            matches_omitted=12,
            compressed_match_count=8,
            original_match_count=20,
            files_affected=3,
        )
        code, out = run_hook(base_payload())
        assert code == 0

        parsed = json.loads(out)
        assert parsed["suppressOutput"] is True
        hook_output = parsed["hookSpecificOutput"]
        assert hook_output["hookEventName"] == "PostToolUse"
        updated = hook_output["updatedToolOutput"]
        assert updated["type"] == "text"
        assert updated["text"].startswith(
            "[search-compress] showing 8/20 matches across 3 files (12 omitted)"
        )
        assert updated["text"].endswith("compressed body")

    def test_query_threaded_to_compressor(self, fake_headroom, run_hook):
        fake_headroom.Compressor.result = fake_headroom.Result(
            compressed="c", matches_omitted=1
        )
        run_hook(base_payload(tool_input={"command": "rg -e needle src/"}))
        assert fake_headroom.Compressor.last_call["context"] == "needle"
        assert fake_headroom.Compressor.last_call["text"] == BIG_TEXT

    def test_default_config_values(self, fake_headroom, run_hook):
        fake_headroom.Compressor.result = fake_headroom.Result(
            compressed="c", matches_omitted=1
        )
        run_hook(base_payload())
        assert fake_headroom.Config.last_kwargs == {
            "max_total_matches": 30,
            "max_matches_per_file": 5,
            "max_files": 15,
            "boost_errors": True,
        }

    def test_custom_config_values_from_env(self, monkeypatch, fake_headroom, run_hook):
        monkeypatch.setenv("SEARCH_COMPRESS_MAX_MATCHES", "99")
        monkeypatch.setenv("SEARCH_COMPRESS_MAX_PER_FILE", "7")
        monkeypatch.setenv("SEARCH_COMPRESS_MAX_FILES", "2")
        fake_headroom.Compressor.result = fake_headroom.Result(
            compressed="c", matches_omitted=1
        )
        run_hook(base_payload())
        assert fake_headroom.Config.last_kwargs == {
            "max_total_matches": 99,
            "max_matches_per_file": 7,
            "max_files": 2,
            "boost_errors": True,
        }
