# Session Loop Detection

Use this when the agent repeats the same tool calls, fails to make progress across multiple turns, or the user reports "stuck in a loop."

## Detection pattern

A turn-level loop occurs when:

1. The same tool is called with identical or trivially-different arguments on ≥3 consecutive assistant turns
2. The tool result does not change the agent's next action
3. No user message was injected between the repeated calls

## Quick check

Read the last N assistant turns from the session:

```bash
tail -400 <session-file> | grep '"role":"assistant"' | grep -o '"name":"[^"]*"' | sort | uniq -c | sort -rn
```

If any tool appears >3 times without an intervening user turn, flag it.

## What to do when a loop is detected

1. **Stop the current turn.** Report to the user immediately — do not try to self-correct within the loop.

2. **Identify the root cause category:**
   - **Perception failure** — the agent misread a tool result and keeps retrying the same action
   - **Goal ambiguity** — the user's request is underspecified, making the agent spin
   - **Tool failure** — a tool keeps returning errors, but the agent doesn't recognize them as terminal
   - **Context saturation** — the context window is full and the agent is repeating because it can't see earlier context

3. **Apply the appropriate mitigation:**
   - For perception failure: ask the user to clarify or provide an example
   - For goal ambiguity: break the task into discrete, verifiable sub-goals
   - For tool failure: check the tool output format; add explicit error handling instructions
   - For context saturation: suggest `/new` or compaction

## Prevention

To reduce loop risk proactively:
- After 3 consecutive tool calls without progress, pause and describe what was learned
- When a tool returns an error, treat it as terminal unless explicitly told to retry
- Before retrying a failed action, state what will be different about the retry
