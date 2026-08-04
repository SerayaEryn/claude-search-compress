import pytest

from compress_search import extract_query, find_search_segment, split_segments


class TestSplitSegments:
    def test_single_command(self):
        assert split_segments("rg foo") == [["rg", "foo"]]

    def test_pipe(self):
        assert split_segments("rg foo | wc -l") == [["rg", "foo"], ["wc", "-l"]]

    def test_and_chain(self):
        assert split_segments("cd src && rg foo") == [["cd", "src"], ["rg", "foo"]]

    def test_or_chain(self):
        assert split_segments("rg foo || echo none") == [["rg", "foo"], ["echo", "none"]]

    def test_semicolon_chain(self):
        # shlex only treats ";" as a separate token when whitespace-delimited;
        # "foo;" glued together stays one token, matching real shell tokenizing.
        assert split_segments("rg foo ; rg bar") == [["rg", "foo"], ["rg", "bar"]]

    def test_quoted_operator_stays_in_segment(self):
        # The pipe inside quotes is data, not a shell operator.
        assert split_segments('grep "a|b" file') == [["grep", "a|b", "file"]]

    def test_empty_string(self):
        assert split_segments("") == []


class TestFindSearchSegment:
    @pytest.mark.parametrize(
        "binary", ["grep", "egrep", "fgrep", "rgrep", "rg", "ripgrep", "ag", "ack"]
    )
    def test_each_known_binary(self, binary):
        assert find_search_segment(f"{binary} pattern file.txt") == [binary, "pattern", "file.txt"]

    def test_absolute_path_binary(self):
        assert find_search_segment("/usr/bin/rg pattern") == ["/usr/bin/rg", "pattern"]

    def test_git_grep_matched(self):
        assert find_search_segment("git grep pattern") == ["git", "grep", "pattern"]

    def test_bare_git_log_not_matched(self):
        assert find_search_segment("git log --oneline") is None

    def test_git_alone_not_matched(self):
        assert find_search_segment("git") is None

    def test_env_prefix_skipped(self):
        # The env-assignment token is skipped when scanning for the binary,
        # but the returned segment still includes it verbatim (not trimmed).
        assert find_search_segment("FOO=bar rg pattern") == ["FOO=bar", "rg", "pattern"]

    def test_search_binary_in_later_pipe_segment(self):
        assert find_search_segment("cat file | grep pattern") == ["grep", "pattern"]

    def test_non_search_command(self):
        assert find_search_segment("ls -la") is None

    def test_no_match_across_multiple_segments(self):
        assert find_search_segment("echo hi && ls -la") is None


class TestExtractQuery:
    def test_bare_positional(self):
        assert extract_query(["grep", "foo", "file.txt"]) == "foo"

    def test_dash_e_flag(self):
        assert extract_query(["grep", "-e", "foo", "file.txt"]) == "foo"

    def test_long_regexp_flag(self):
        assert extract_query(["grep", "--regexp", "foo", "file.txt"]) == "foo"

    def test_regexp_equals_inline(self):
        assert extract_query(["grep", "--regexp=foo", "file.txt"]) == "foo"

    def test_dash_e_equals_inline(self):
        assert extract_query(["grep", "-e=foo", "file.txt"]) == "foo"

    def test_explicit_wins_over_positional(self):
        # positional "file.txt" would otherwise be picked up first
        assert extract_query(["grep", "file.txt", "-e", "foo"]) == "foo"

    @pytest.mark.parametrize(
        "flag,value",
        [
            ("-m", "5"),
            ("--max-count", "5"),
            ("-g", "*.py"),
            ("--glob", "*.py"),
            ("-t", "py"),
            ("--type", "py"),
            ("-A", "3"),
            ("-B", "3"),
            ("-C", "3"),
            ("--context", "3"),
            ("--after-context", "3"),
            ("--before-context", "3"),
        ],
    )
    def test_value_flags_consume_next_token(self, flag, value):
        assert extract_query(["rg", flag, value, "pattern"]) == "pattern"

    def test_inline_equals_value_flag(self):
        assert extract_query(["rg", "--type=py", "pattern"]) == "pattern"

    def test_git_grep_dash_e(self):
        assert extract_query(["git", "grep", "-e", "pat"]) == "pat"

    def test_no_pattern_flags_only(self):
        assert extract_query(["grep", "-i", "-n"]) == ""

    def test_first_dash_e_wins_over_second(self):
        assert extract_query(["grep", "-e", "first", "-e", "second"]) == "first"

    def test_clustered_short_flags_known_limitation(self):
        # extract_query does not expand clustered short flags like -in into -i -n;
        # "-in" is treated as a single flag token, so "pattern" is the only
        # positional and is correctly picked up here. Documented so a future
        # change to flag-clustering support is a deliberate, visible break.
        assert extract_query(["grep", "-in", "pattern"]) == "pattern"
