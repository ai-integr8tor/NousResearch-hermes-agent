# Session Health Check

Use this workflow when:
- The agent seems stuck, slow, or unresponsive
- Context appears corrupted or truncated
- The user reports degraded behavior
- After a long session (>50 turns) or after compaction

## Step 1: Gather session metadata

Read the current session transcript to understand its shape:

```bash
# Session file size and message count
wc -l ~/.hermes/agents/*/sessions/*.jsonl | sort -rn | head -5

# Total byte volume per session
du -sh ~/.hermes/agents/*/sessions/*.jsonl | sort -rh | head -5
```

Record these facts before diagnosing:
- Session file path and byte size
- Approximate message count (lines ≈ messages in JSONL)
- Whether compaction has run recently

## Step 2: Scan for failure patterns

Look for these red-flag patterns in the most recent ~200 lines of the active session:

| Pattern | What to grep | What it means |
|---------|-------------|---------------|
| Empty assistant turns | `"role":"assistant","content":""` | Model produced no text; check token limits or provider errors |
| Tool-call loops | repeated tool call with same arguments | Agent is stuck; stop and add guidance |
| Compaction markers | `compaction` or `context_size` keys | Context window may be full |
| API errors | `error_code` or `rate_limit` in raw chunks | Provider-side issues |
| Truncated output | `... (truncated)` in tool results | Output limits hit; increase or reframe |

```bash
tail -200 <session-file> | grep -E '"content":""|"error"|"rate_limit"|truncated'
```

## Step 3: Check context window health

If the session is >30k tokens, compaction may be causing context loss:

1. Look at the most recent compaction timestamp (check `state.db` or session metadata)
2. If compaction ran in the last 10 turns, the agent may have lost important mid-conversation context
3. Check `MEMORY.md` or the memory tool for what was retained vs. lost

```bash
sqlite3 ~/.hermes/state.db "SELECT key, updated_at FROM session_state WHERE key LIKE '%compaction%' ORDER BY updated_at DESC LIMIT 5;"
```

## Step 4: Report and recommend

Summarize findings in this format:

```
## Session Health Report

**Session**: <path>
**Messages**: <count> | **Size**: <bytes>
**Last compaction**: <timestamp or "never">
**Issues found**: <count>

### Issues
1. <issue description> → <recommendation>
2. <issue description> → <recommendation>

### Recommendations
- <actionable step 1>
- <actionable step 2>
```

## Boundaries

- This skill only READS session files — never modifies them
- Do not run this skill during an active conversation turn
- For automated monitoring, schedule via cron rather than agent-triggered
- The report is for the user/operator, not for the agent to act on autonomously
