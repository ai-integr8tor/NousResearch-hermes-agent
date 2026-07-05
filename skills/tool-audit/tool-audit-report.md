# Tool Audit Report

Generate a self-audit of tool usage from the current session transcript.

## When to use this
- The user asks "how are my tools performing?" or "audit your tool usage"
- After a long-running session (>50 turns) with many tool calls
- When the user suspects a tool is slow or failing
- When debugging agent loops or excessive tool calls

## How to run the audit

### 1. Gather raw data from the session transcript

First, find the active session file. It lives under the agent's sessions directory:

```bash
SESSION=$(ls -t ~/.hermes/agents/*/sessions/*.jsonl 2>/dev/null | head -1)
echo "Auditing: $SESSION"
```

### 2. Extract tool call statistics

Count tool calls by name from the JSONL transcript. The `tool_calls` field in assistant messages contains an array of `{function: {name: ...}}` objects.

```bash
grep -o '"name": *"[^"]*"' "$SESSION" \
  | sed 's/"name": *"//;s/"//g' \
  | sort | uniq -c | sort -rn
```

### 3. Calculate success/failure rates

A tool call succeeded when it has a subsequent `tool`-role message with the same `tool_call_id`. A tool call failed when:
- No matching tool result exists (orphaned call)
- The result contains `"error"` or `"exit_code": 1`
- The call was interrupted by a compaction marker

```bash
# Count tool results with errors
grep -c '"error"' "$SESSION"
# Count tool results with non-zero exit codes  
grep -c '"exit_code": *[1-9]' "$SESSION"
```

### 4. Report format

Summarize findings in a table:

```
## Tool Usage Report — Session <id>

| Tool | Calls | Success Rate | Avg Latency |
|------|-------|-------------|-------------|
| <name> | <count> | <rate> | <estimate> |

### Top Issues
1. <tool>: <problem> → <recommendation>
2. <tool>: <problem> → <recommendation>

### Optimization Tips
- <actionable suggestion 1>
- <actionable suggestion 2>
```

## Boundaries

- This skill only reads session transcripts — it never modifies them
- Latency estimates are approximate (based on turn timestamps)
- Do not run during an active conversation turn
- The audit report is for the operator, not for autonomous agent action
