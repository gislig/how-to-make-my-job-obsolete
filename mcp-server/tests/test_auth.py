import pytest

from obsolete_mcp.auth import match_key, parse_keys

K1, K2 = "a" * 40, "b" * 40


def test_parse_and_match():
    keys = parse_keys(f"grokbot:{K1}, sre-agent:{K2}")
    assert match_key(K1, keys) == "grokbot" and match_key(K2, keys) == "sre-agent"
    assert match_key("nope", keys) is None and match_key(None, keys) is None


@pytest.mark.parametrize("raw", ["grokbot", "grokbot:short", f":{K1}"])
def test_rejects_bad_config(raw):
    with pytest.raises(ValueError):
        parse_keys(raw)


def test_server_refuses_to_start_without_keys():
    from fakes import FakeBackend

    from obsolete_mcp.server import create_app
    from obsolete_mcp.settings import Settings

    with pytest.raises(RuntimeError):
        create_app(Settings("s", "rg", None, "", False, 5, [], 8000), FakeBackend())
