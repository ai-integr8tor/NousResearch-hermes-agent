"""Tests for gateway.client_correlation."""

from gateway.client_correlation import format_correlation_log_suffix, parse_correlation_headers


def test_parse_correlation_headers_standard_request_id():
    corr = parse_correlation_headers(
        {"X-Request-Id": "abc-123", "X-Stream-Token": "tok-1"}
    )
    assert corr == {"request_id": "abc-123", "stream_token": "tok-1"}


def test_parse_correlation_headers_request_id_alias():
    corr = parse_correlation_headers({"X-Request-ID": "upper-case"})
    assert corr == {"request_id": "upper-case"}


def test_format_correlation_log_suffix():
    suffix = format_correlation_log_suffix(
        {"request_id": "r1", "stream_token": "s1"},
        session_id="sess-9",
    )
    assert "request_id=r1" in suffix
    assert "stream_token=s1" in suffix
    assert "session=sess-9" in suffix


def test_parse_bound_skills_header():
    from gateway.client_correlation import parse_bound_skills_header

    assert parse_bound_skills_header({}) == frozenset()
    assert parse_bound_skills_header({"X-Hermes-Bound-Skills": ""}) == frozenset()
    assert parse_bound_skills_header(
        {"X-Hermes-Bound-Skills": "arxiv, research/foo ,hermes-agent"}
    ) == frozenset({"arxiv", "research/foo", "hermes-agent"})
