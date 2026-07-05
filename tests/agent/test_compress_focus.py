"""Tests for focus_topic flowing through the compressor.

Verifies that _generate_summary and compress accept and use the focus_topic
parameter correctly.  Inspired by Claude Code's /compact <focus>.
"""

from unittest.mock import MagicMock, patch

from agent.context_compressor import (
    COMPRESSED_SUMMARY_METADATA_KEY,
    ContextCompressor,
    SUMMARY_PREFIX,
)


def _make_compressor():
    """Create a ContextCompressor with minimal state for testing."""
    compressor = ContextCompressor.__new__(ContextCompressor)
    compressor.protect_first_n = 2
    compressor.protect_last_n = 5
    compressor.tail_token_budget = 20000
    compressor.context_length = 200000
    compressor.threshold_percent = 0.80
    compressor.threshold_tokens = 160000
    compressor.max_summary_tokens = 10000
    compressor.quiet_mode = True
    compressor.compression_count = 0
    compressor.last_prompt_tokens = 0
    compressor._previous_summary = None
    compressor._summary_failure_cooldown_until = 0.0
    compressor.summary_model = None
    compressor.model = "test-model"
    compressor.provider = "test"
    compressor.base_url = "http://localhost"
    compressor.api_key = "test-key"
    compressor.api_mode = "chat_completions"
    return compressor


def test_focus_topic_injected_into_summary_prompt():
    """When focus_topic is provided, the LLM prompt includes focus guidance."""
    compressor = _make_compressor()
    turns = [
        {"role": "user", "content": "Tell me about the database schema"},
        {"role": "assistant", "content": "The schema has tables: users, orders, products."},
    ]

    captured_prompt = {}

    def mock_call_llm(**kwargs):
        captured_prompt["messages"] = kwargs["messages"]
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "## Goal\nUnderstand DB schema."
        return resp

    with patch("agent.context_compressor.call_llm", mock_call_llm):
        result = compressor._generate_summary(turns, focus_topic="database schema")

    assert result is not None
    prompt_text = captured_prompt["messages"][0]["content"]
    assert 'FOCUS TOPIC: "database schema"' in prompt_text
    assert "PRIORITISE" in prompt_text
    assert "60-70%" in prompt_text


def test_no_focus_topic_no_injection():
    """Without focus_topic, the prompt doesn't contain focus guidance."""
    compressor = _make_compressor()
    turns = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
    ]

    captured_prompt = {}

    def mock_call_llm(**kwargs):
        captured_prompt["messages"] = kwargs["messages"]
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "## Goal\nGreeting."
        return resp

    with patch("agent.context_compressor.call_llm", mock_call_llm):
        result = compressor._generate_summary(turns)

    prompt_text = captured_prompt["messages"][0]["content"]
    assert "FOCUS TOPIC" not in prompt_text


def test_summary_prompt_is_not_locked_to_conversation_language():
    """Regression: the summary prompt must not tell the model to keep the whole summary in the conversation language."""
    compressor = _make_compressor()
    turns = [
        {"role": "user", "content": "¿Puedes revisar esto?"},
        {"role": "assistant", "content": "Sí, lo reviso."},
    ]

    captured_prompt = {}

    def mock_call_llm(**kwargs):
        captured_prompt["messages"] = kwargs["messages"]
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "## Goal\nReview request."
        return resp

    with patch("agent.context_compressor.call_llm", mock_call_llm):
        compressor._generate_summary(turns)

    prompt_text = captured_prompt["messages"][0]["content"]
    assert "same language the user was using" not in prompt_text
    assert "clear neutral English" in prompt_text
    assert "preserve exact user quotes verbatim" in prompt_text
    assert "reply-language instruction for later turns" in prompt_text


def test_compress_passes_focus_to_generate_summary():
    """compress() passes focus_topic through to _generate_summary."""
    compressor = _make_compressor()

    # Track what _generate_summary receives
    received_kwargs = {}
    original_generate = compressor._generate_summary

    def tracking_generate(turns, **kwargs):
        received_kwargs.update(kwargs)
        return "## Goal\nTest."

    compressor._generate_summary = tracking_generate

    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply1"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "reply2"},
        {"role": "user", "content": "third"},
        {"role": "assistant", "content": "reply3"},
        {"role": "user", "content": "fourth"},
        {"role": "assistant", "content": "reply4"},
    ]

    compressor.compress(messages, current_tokens=100000, focus_topic="authentication flow")

    assert received_kwargs.get("focus_topic") == "authentication flow"


def test_compress_none_focus_by_default():
    """Auto compression derives focus_topic from recent user turns by default."""
    compressor = _make_compressor()

    received_kwargs = {}

    def tracking_generate(turns, **kwargs):
        received_kwargs.update(kwargs)
        return "## Goal\nTest."

    compressor._generate_summary = tracking_generate

    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply1"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "reply2"},
        {"role": "user", "content": "third"},
        {"role": "assistant", "content": "reply3"},
        {"role": "user", "content": "fourth"},
        {"role": "assistant", "content": "reply4"},
    ]

    compressor.compress(messages, current_tokens=100000)

    focus_topic = received_kwargs.get("focus_topic")
    assert focus_topic.startswith("Recent user focus:")
    assert "- second" in focus_topic
    assert "- third" in focus_topic
    assert "- fourth" in focus_topic


def test_auto_focus_skips_context_summary_handoff():
    """Persisted handoff messages should not become the inferred focus."""
    compressor = _make_compressor()
    messages = [
        {"role": "system", "content": "System prompt"},
        {
            "role": "user",
            "content": "[CONTEXT COMPACTION — REFERENCE ONLY] stale Bybit topic",
        },
        {"role": "assistant", "content": "handoff acknowledged"},
        {"role": "user", "content": "Can OpenViking support sqlite backends?"},
        {"role": "assistant", "content": "Let's inspect that."},
        {"role": "user", "content": "Compare OpenViking postgres and sqlite options."},
        {"role": "assistant", "content": "Working on it."},
        {"role": "user", "content": "Now focus on OpenViking database support."},
        {"role": "assistant", "content": "Latest tail response"},
    ]

    focus_topic = compressor._derive_auto_focus_topic(messages)

    assert "OpenViking" in focus_topic
    assert "Bybit" not in focus_topic


def test_summary_prompt_has_no_dutch_example_bias():
    """The summarizer template should not seed Dutch into English chats."""
    compressor = _make_compressor()
    turns = [
        {"role": "user", "content": "Why is provider set to OpenRouter?"},
        {"role": "assistant", "content": "Investigating."},
    ]

    captured_prompt = {}

    def mock_call_llm(**kwargs):
        captured_prompt["messages"] = kwargs["messages"]
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "## Goal\nInvestigate provider routing."
        return resp

    with patch("agent.context_compressor.call_llm", mock_call_llm):
        compressor._generate_summary(turns)

    prompt_text = captured_prompt["messages"][0]["content"]
    assert "waarom" not in prompt_text.lower()
    assert "optie" not in prompt_text.lower()
    assert "clear neutral English for internal reference" in prompt_text


def test_compress_inserts_language_authority_before_foreign_language_summary():
    """Regression: the assembled handoff must place the reply-language rule
    before a foreign-language summary block in the outgoing transcript."""
    compressor = _make_compressor()
    messages = [{"role": "system", "content": "System prompt"}]
    for i in range(1, 13):
        messages.append(
            {
                "role": "user" if i % 2 else "assistant",
                "content": f"message {i}",
            }
        )

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = (
        "## Historical Task Snapshot\n"
        "Resumen previo en español sobre trabajo ya hecho."
    )

    with (
        patch("agent.context_compressor.call_llm", return_value=mock_response),
        patch.object(compressor, "_find_tail_cut_by_tokens", return_value=8),
    ):
        compressed = compressor.compress(messages, current_tokens=100000)

    summary_msg = next(
        msg for msg in compressed if msg.get(COMPRESSED_SUMMARY_METADATA_KEY)
    )
    summary_text = summary_msg["content"]
    assert summary_text.startswith(SUMMARY_PREFIX)
    assert "latest live user message also controls your reply" in summary_text
    assert "Resumen previo en español" in summary_text
    assert summary_text.index("latest live user message also controls your reply") < summary_text.index("Resumen previo en español")
