from unittest.mock import patch


def _compressor():
    from agent.context_compressor import ContextCompressor

    with patch(
        "agent.context_compressor.get_model_context_length",
        return_value=100_000,
    ):
        return ContextCompressor(
            model="test/model",
            threshold_percent=0.85,
            protect_first_n=0,
            protect_last_n=1,
            quiet_mode=True,
        )


def test_align_boundary_forward_skips_legacy_function_results():
    c = _compressor()
    messages = [
        {"role": "system", "content": "system"},
        {"role": "function", "name": "old_tool", "content": "legacy result"},
        {"role": "user", "content": "next user"},
    ]

    assert c._align_boundary_forward(messages, 1) == 2


def test_align_boundary_backward_keeps_legacy_function_result_with_parent_call():
    c = _compressor()
    messages = [
        {"role": "user", "content": "question"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "function",
            "tool_call_id": "call-1",
            "name": "lookup",
            "content": "legacy result",
        },
        {"role": "user", "content": "tail"},
    ]

    assert c._align_boundary_backward(messages, 3) == 1


def test_system_head_falls_through_to_assistant_summary_role():
    from agent.context_compressor import SUMMARY_PREFIX

    c = _compressor()
    c.tail_token_budget = 1
    c.compression_count = 1
    messages = [{"role": "system", "content": "system"}]
    for idx in range(8):
        messages.append({"role": "user", "content": f"middle question {idx}"})
        messages.append({"role": "assistant", "content": f"middle answer {idx}"})
    messages.append({"role": "user", "content": "latest"})

    with patch.object(
        c,
        "_generate_summary",
        return_value=f"{SUMMARY_PREFIX}\ncompressed middle",
    ):
        compressed = c.compress(messages, current_tokens=90_000)

    summary_rows = [
        msg for msg in compressed
        if isinstance(msg.get("content"), str)
        and msg["content"].startswith(SUMMARY_PREFIX)
    ]
    assert len(summary_rows) == 1
    assert summary_rows[0]["role"] == "assistant"
