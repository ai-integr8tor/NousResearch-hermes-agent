---
name: moa-swarm-approach
description: "Use when the user asks for a MoA swarm, swarm approach with Mixture of Agents, best-of-K planning, multi-agent orchestration, MoA-guided plan review, or MoA result review. Provides a general-purpose swarm workflow where MoA crafts plans and reviews compact evidence, while tool-using workers gather evidence or implement scoped work."
license: MIT
metadata:
  hermes:
    tags: [swarm, moa, mixture-of-agents, best-of-k, delegation, orchestration, planning, synthesis, kanban, worktree, cron]
    related_skills: [heavy-thinking-review, subagent-driven-development, requesting-code-review, kanban-orchestrator]
---

# MoA Swarm Approach

## Overview

MoA Swarm Approach is a general-purpose fan-out / fan-in workflow for complex work. It uses Mixture of Agents (MoA) for plan crafting and result review, while preserving ordinary engineering discipline: scoped workers, explicit side-effect boundaries, objective verification, and durable handoffs when needed.

Use it as a working method, not as a topic. When invoked, do not answer in one ordinary serial pass and do not blindly launch a large worker pool immediately.

Run this staged orchestration:

```text
User asks for A
-> gather a compact context pack
-> MoA planning checkpoint compresses and decomposes A
-> user reviews / iterates the plan when needed
-> choose the smallest safe execution substrate
-> deploy focused workers only where useful
-> liaisons compress worker output
-> MoA result-review checkpoint reviews compact evidence where useful
-> parent/orchestrator verifies and decides
-> leave durable state when needed
-> return the result
```

The default full swarm node uses **K=10 workers**. Ten is a preset, not a hard requirement. The point is to search solution space in parallel while keeping each worker focused and each report compact enough for a final decision maker to reason about.

Core idea:

```text
MoA plans and reviews.
Workers inspect, implement, or gather evidence.
The parent/orchestrator owns side effects and final verification.
```

Do not use MoA as proof. MoA can improve plans and expose missing evidence, but real success claims still require inspected files, command output, tests, service checks, artifacts, or other objective evidence.

## MoA Contract

MoA is an advisor-fanout plus aggregator pattern:

- reference advisors critique the request from different angles
- advisors should not perform side effects
- advisors may be tool-blind depending on runtime
- the aggregator returns one actionable plan or verdict
- the parent/orchestrator decides what to execute and verifies the result
- full traces may persist sensitive context in some runtimes, so redact before fan-out

In Hermes-style runtimes, MoA may appear as:

- provider: `moa`
- model/preset: `default`, `review`, `plan`, or a local preset name
- one-shot entry: `/moa <prompt>`
- persistent model/provider selection for longer sessions

If MoA is unavailable, do not pretend it ran. Say:

```text
MoA checkpoint unavailable in this runtime; fallback planning used.
```

Then use a normal parent planning pass, `heavy-thinking-review`, or a small bounded worker panel.

## When to Use

Use this skill when the user says or implies:

- `moa-swarm-approach`
- `MoA swarm`
- `use MoA for the swarm`
- `swarm approach with MoA`
- `best-of-K with MoA planning`
- `make multiple agents plan this`
- `fan this out and use MoA to synthesize`
- `review the worker results with MoA`
- `use a mixture of agents for the plan`

Best fit:

- code review or cleanup sweeps
- architecture decisions
- implementation planning
- complex debugging or incident triage
- product strategy or roadmap tradeoffs
- creative concept generation where diversity matters
- research synthesis
- security, privacy, reliability, or migration reviews
- multi-day work that needs task state and re-entry
- codebase changes where workers need isolated worktrees and parent-controlled merge/verification
- operational QA suites that need evidence artifacts and final review gates
- recurring monitors or health checks that may later become scheduled jobs

Do not use this skill for:

- trivial deterministic tasks
- one obvious tool call
- arithmetic or basic current-system checks
- tasks with no definable success criteria
- tasks where the user explicitly asks for a cheap, fast, or single-pass answer
- live side effects without approval
- contexts containing raw secrets, credentials, private keys, raw PII, or sensitive logs unless the context has been redacted and the user accepts the fan-out risk
- recurring automation until a manual or dry-run path has been proven
- parallel code editing in one checkout without explicit worktree or branch isolation
- creating new durable folders, boards, or state just because a swarm ran once

For source-of-truth domains, never majority-vote facts into existence. If evidence is missing, clarify, inspect sources, or block.

## Core Contract

When invoked, follow this contract unless the user overrides it.

### 1. Decide whether a swarm is justified

Use a swarm only when there are separable angles, meaningful uncertainty, high risk, broad search space, or enough complexity to benefit from independent views.

If one direct parent pass or one compact MoA checkpoint is enough, do that and say why.

### 2. Define the target

Before worker fan-out, write:

```text
Goal:
Done means:
Non-goals:
Out-of-scope files/systems:
Known risky surfaces:
Approval boundaries:
```

### 3. Build a context pack

The parent/orchestrator gathers only the context the MoA advisors and workers need.

```text
Goal:
Done means:
Relevant facts already verified:
Files/docs/diffs inspected:
Known constraints:
Non-goals:
Risky surfaces:
Forbidden side effects:
Candidate verification commands/checks:
Open questions:
Budget: mini | standard | deep | wide
```

Rules:

- Redact secrets, tokens, private contact data, raw PII, and unnecessary logs.
- Include evidence handles, not huge raw dumps.
- State what is unknown instead of letting advisors infer it.
- Skip MoA if the context is too sensitive to fan out.

### 4. Run the MoA planning checkpoint

Prompt MoA like this:

```text
You are the MoA planning checkpoint for a multi-agent swarm workflow.

Reference advisors should critique from different angles, but the final answer must be one actionable plan.
Do not majority-vote. Judge by evidence, uncertainty, and risk.
Do not invent repo/runtime/domain facts beyond the context pack.
Do not perform side effects.
Decide whether this needs a swarm, what kind, and how to verify it.

Context pack:
<insert compact context pack>

Return only this schema:

Goal:
Done means:
Non-goals / forbidden side effects:
Why swarm?:
MoA-worthiness: yes | no + why
Execution substrate: single-pass | delegate_task | Kanban | worktree | cron | mixed
Subtasks:
Swarm nodes:
- name:
  purpose:
  suggested K: 1 | 3 | 5 | 10 | other
  worker angles:
  needs tools: yes | no
  needs worktree: yes | no
  durable state needed: yes | no
Single-pass/tool nodes:
Roots / toolsets:
Worktree/branch plan if code edits:
Handoff/state artifacts:
Risks and approval gates:
MoA result review needed: yes | no + why
Verification plan:
Budget risk: low | medium | high
Recommended next step:
```

Do not create boards, worktrees, handoff folders, scheduled jobs, commits, pull requests, deployments, migrations, or live operational side effects during planning unless explicitly approved.

### 5. Ask for user review when needed

Pause before expensive, durable, risky, or live work unless the user already authorized that exact class of action.

Use this prompt:

```text
I have not deployed the full swarm yet. This is the MoA-backed plan for review.
Approve, modify, or tell me where to narrow it.
```

Approval is required before:

- K=10 fan-out
- durable task board creation
- worktree implementation branches
- commits, pull requests, pushes, deploys, or migrations
- cron/background jobs
- live messages or actions affecting external people or systems
- credential, profile, plugin, skill, permission, or production config changes

### 6. Choose the execution substrate

Use the smallest safe substrate:

| Substrate | Use when | Avoid when |
|---|---|---|
| MoA | Need several model perspectives to craft a plan or review compact evidence | Workers need tools, isolated edits, durable state, or independent side effects |
| `delegate_task` | Bounded in-session fan-out; read-only inspection; concise research; tool-using workers need separate contexts | Work must survive interruption or produce durable audit artifacts |
| Kanban | Multi-day, high-risk, validation-heavy, or interruption-safe work | One short deterministic task is enough |
| Worktree | Parallel code edits, branch/PR work, risky implementation isolation | Workers only need read-only review |
| Cron | Proven recurring loops with bounded prompts and quiet healthy behavior | Manual/dry-run has not proven the loop |
| Mixed | Complex work needing several substrates | The plan cannot name clear boundaries and handoffs |

### 7. Guard every worker

Every worker prompt must name:

- assigned role/angle
- goal
- scope/root/worktree
- allowed tools
- forbidden side effects
- read-only vs edit-capable status
- required evidence
- compact output format
- stop condition

Unless explicitly approved, workers may not:

- deploy, push, commit, merge, or open pull requests
- send live messages or trigger external actions
- mutate credentials, permissions, profiles, plugins, skills, scheduled jobs, or production config
- run broad staging commands such as `git add .` or `git add -A`
- create recurring jobs or background automation
- expose credentials or copy secrets into reports

Isolation rules:

- Read-only workers may share a checkout.
- Editing workers require isolated worktrees or branches.
- No two workers edit the same live files in parallel.
- Parent/orchestrator owns final merge, cherry-pick, apply, commit, push, and deploy decisions.

### 8. Define verification before launch

Pick the evidence that will decide PASS/BLOCK:

- targeted tests, full tests, lint, typecheck, build
- browser, API, CLI, or service smoke checks
- diff/status inspection
- security, privacy, or permissions checks
- migration or rollback dry-runs
- CI/deployment status when applicable
- artifact inspection for non-code deliverables
- MoA result review for risky, ambiguous, or durable work

### 9. Require compact worker reports

Default worker output:

```text
Verdict: PASS | BLOCK | REQUEST_CHANGES
Findings:
- Severity:
- File/path/source:
- Evidence:
- Why it matters:
- Suggested fix:
Commands run:
Artifacts:
Side effects performed: none | list
Confidence: low | medium | high
```

Do not raw-dump worker transcripts into the final answer. Preserve decisive evidence and drilldown handles.

### 10. Parent owns final success claims

The parent/orchestrator must:

- compare evidence, not vote count
- inspect files, diffs, artifacts, and command outputs directly when needed
- resolve disagreements explicitly
- apply only accepted fixes
- re-run checks after fixes
- state what passed, blocked, changed, and remains

Never claim success from worker self-report or MoA self-report alone.

## Deployment Shapes

### Simple Swarm

Use when there is one clear deliverable and no meaningful decomposition:

```text
MoA plan
-> focused workers
-> MoA result review or parent synthesis
-> final answer
```

Examples:

- generate and rank naming options
- critique one design surface
- produce several messaging angles
- inspect one bounded code area

### Planned Subtask Swarm

Default for complex work that fits inside one session:

```text
MoA planning checkpoint
-> user approval when needed
-> subtask A: focused workers + liaison
-> subtask B: direct tool check
-> subtask C: focused workers + liaison
-> MoA result-review checkpoint when useful
-> parent verification
-> final answer
```

Examples:

- integration plan for a third-party service
- codebase cleanup across several modules
- reliability review of an async workflow
- research synthesis across several sources

### Serial High-Severity Hardening

Use when there are severe findings that should be fixed one at a time:

```text
High item N
-> write or confirm a failing regression test where practical
-> parent applies the smallest safe fix
-> run targeted tests
-> run adjacent regression checks
-> run MoA result review over compact diff/evidence
-> apply accepted findings and re-test
-> mark N done only after evidence is green
-> then start high item N+1
```

Do not parallelize high-severity implementation across unrelated items unless isolation and merge rules are explicit.

### Worktree Code-Shipping Swarm

Use when workers may edit code in parallel or when a scoped change should end in a reviewable branch:

```text
MoA planning gate
-> parent creates or assigns isolated worktrees
-> implementation workers edit only assigned worktrees
-> liaisons summarize diffs and evidence
-> parent runs objective checks
-> MoA result review if risk warrants it
-> parent merges/cherry-picks/commits/opens PR only after proof
```

Final summary must include:

- base ref
- branch/worktree path
- changed files
- env/setup assumptions
- commands run
- verification result
- whether commit, PR, push, or deploy happened

### Durable Task Graph

Use when work should survive interruption, continue across sessions, or produce an audit trail:

```text
MoA planning gate
-> optional dry-run/manual first pass
-> durable task graph
-> worker tasks
-> liaison/synthesis task
-> MoA result review when risky or durable
-> parent verification gate
-> handoff/run record
```

Every durable task should include:

```text
Goal:
Workspace/root:
Assignee/profile:
Allowed tools:
Forbidden side effects:
Inputs/context:
Acceptance criteria:
Required evidence:
Handoff format:
Block if:
```

### Recurring Loop

Use scheduled or recurring execution only after a manual or dry-run path has succeeded.

Before creating a recurring job:

1. Input source is known.
2. Output or handoff target is known.
3. Side effects are forbidden or explicitly approved.
4. Failure/escalation behavior is defined.
5. The prompt is bounded and re-entry safe.
6. Healthy runs are quiet.

Recurring job prompt:

```text
Loop goal:
State/handoff location:
Allowed actions:
Forbidden side effects:
Verification/check command:
When to alert/block:
What to append/update:
```

## Worker Prompt Template

```text
You are one independent worker in a MoA swarm workflow.
Do not read or rely on other workers.

Assigned angle:
Goal:
Scope/root/worktree:
Allowed tools:
Forbidden side effects:
Read-only or edit-capable:
Success criteria:
Evidence required:
Stop condition:

Return a compact report only:
- verdict: PASS | BLOCK | REQUEST_CHANGES
- recommendation
- evidence / artifacts
- files inspected or changed
- commands run + pass/fail summary
- risks
- what remains to verify
- side effects performed: none | list
- confidence: low | medium | high
```

Good worker angles:

- correctness / logic
- security / privacy / permissions
- tests / verification
- user experience / accessibility
- performance / latency
- maintainability / simplicity
- edge cases / failure modes
- documentation / onboarding
- cost / operational complexity
- rollout / rollback plan

## Liaison Report Template

```text
Subtask:
Workers used:
Consensus:
Disagreements:
Best evidence:
Recommended action:
Risks:
Open questions:
Confidence:
Artifacts / paths:
Task IDs:
Worktree / branch:
Commands run:
Side effects performed:
Verification status:
Parent action needed:
Next safe step:
Raw-output drilldown needed? yes/no
```

The liaison must not hide material disagreement. A liaison report should be enough for a fresh orchestrator to resume without reading every raw worker transcript.

## MoA Result Review

Use MoA result review when:

- workers disagree
- risk is high
- evidence is incomplete
- the plan changed during execution
- the output will become a durable process, recurring job, public artifact, or code change
- the user asked for extra confidence

Prompt:

```text
You are the MoA result-review checkpoint for a multi-agent swarm workflow.

Reference advisors should independently evaluate the evidence, but the final answer must be one actionable PASS/BLOCK/REQUEST_CHANGES verdict.
Do not majority-vote. Judge evidence quality.
Do not invent facts. If evidence is missing, BLOCK or REQUEST_CHANGES.
Do not perform side effects.
MoA can recommend, but the parent owns final PASS/BLOCK.

Goal:
<goal>

Plan used:
<brief>

Worker/liaison findings:
<compact summaries>

Parent verification evidence:
<commands, outputs, changed paths, unresolved risks>

Return only:
Verdict: PASS | BLOCK | REQUEST_CHANGES
Confidence: low | medium | high
Blocking issues:
Non-blocking issues:
Evidence sufficient:
Evidence weak or missing:
Contradictions resolved:
Safe next step:
Do not do yet:
```

If MoA returns shallow output, gather sharper evidence and rerun the checkpoint or fall back to a direct hard review.

## Hard-Pass Boundaries

Insert a separate result-review gate before moving on when work touches:

- authentication, authorization, permissions, or isolation
- production/deployment config, secrets, callbacks, or webhooks
- durable state, migrations, idempotency, retry/replay logic, background jobs, or async execution
- data privacy, retention, export, or deletion behavior
- recurring automation that can act without a human watching
- CI/deployment automation that can push, merge, deploy, migrate, or message externally
- live actions affecting external people, accounts, systems, or money

Hard-pass shape:

```text
Parent gathers concrete evidence:
  - diff paths and key file:line anchors
  - command outputs and failures
  - runtime/deployment/migration state
  - unresolved risks and accepted tradeoffs
  - compact worker/liaison reports
-> MoA result-review checkpoint returns PASS | BLOCK | REQUEST_CHANGES
-> parent applies accepted fixes
-> parent adds or updates regression tests where practical
-> parent reruns verification
-> parent decides whether to proceed
```

Green tests mean ready for hard review, not automatically ready to ship.

## Durable Handoffs

For one-shot swarms, compact in-chat summaries are enough.

For durable, risky, interrupted, or recurring work, leave a run record in the relevant project location or task card.

Minimum run record:

```text
Run:
Goal:
Mode: single-pass | delegate_task | Kanban | worktree | cron | mixed
MoA checkpoints:
Task IDs:
Workers/roles:
Worktree/branch:
Artifacts/handoffs:
Changes applied:
Verification commands + results:
Result-review verdict:
Side effects performed:
Open blockers:
Next trigger / next safe step:
```

Write durable state only for tool-grounded findings, verified outcomes, decisions, or explicitly labeled hypotheses.

## Budget and Kill Criteria

Before starting, set a budget appropriate to the task:

```text
Max MoA checkpoints:
Max advisor width:
Max reference tokens:
Max worker count:
Max wall time:
Fallback trigger:
```

Fallback to a smaller workflow when:

- MoA is unavailable
- advisor outputs are generic or unsupported
- MoA adds latency without changing the plan
- context is too sensitive to fan out
- the task becomes tool-heavy and iterative
- the user says cheap, fast, stop, or single-pass
- cost or latency exceeds the agreed budget

Never continue spending just because a swarm started.

## Output Policy

Lead with the deliverable. Keep process notes short.

For substantial runs, append:

```text
Swarm note: plan=<MoA/fallback>; substrate=<single-pass/delegate_task/Kanban/worktree/cron/mixed>; workers=<n>; handoffs=<paths/task IDs>; result-review=<MoA pass/blocked/not needed>; verification=<commands/artifacts>.
```

For code/worktree runs, include branch/worktree and whether a commit, PR, push, or deploy was performed. For durable task runs, include task IDs and current status. For recurring loops, include job ID/schedule only if actually created; otherwise say `recurring job proposed, not created`.

When still in planning phase, say:

```text
I have not deployed the full swarm yet. This is the MoA-backed plan for review.
```

At the end of a MoA-backed run, include:

```text
MoA swarm measurement:
- checkpoints used:
- workers used:
- what MoA changed in the plan/result review:
- verification evidence:
- cost/latency concern: low | medium | high
- fallback recommended next time: yes | no
```

## Safety Rules

- Do not fan out secrets, credentials, private keys, raw PII, or sensitive logs.
- Do not enable persistent MoA traces for sensitive contexts without explicit approval.
- Do not let advisors override source-of-truth or tool evidence.
- Do not commit, push, deploy, message, migrate, or create recurring jobs from a MoA plan without approval and verification.
- Do not let a PASS from MoA replace parent verification.
- Do not majority-vote facts into existence.
- Do not let worker speculation become durable memory or project state.

## Common Pitfalls

1. **Blind K=10.** The preset is for full swarm nodes, not every trivial subtask.
2. **Duplicate prompts.** Identical workers do not create meaningful diversity.
3. **Skipping the MoA plan gate.** Planning is the cost-control layer.
4. **Raw-output flooding.** Compact reports keep synthesis possible.
5. **Majority-voting facts.** Votes do not override evidence.
6. **Parallel edits to live files.** Use isolated worktrees or keep workers read-only.
7. **No verification.** Swarm reasoning does not replace tests or source inspection.
8. **Unproven recurrence.** Scheduled jobs need a manual/dry-run proof path.
9. **Worker side effects.** Workers propose; the parent performs approved side effects.
10. **Green tests without behavior proof.** User-facing changes still need feature exercise.
11. **Trace leakage.** MoA traces may persist sensitive context.
12. **Durable state from weak claims.** Persist evidence-backed facts, not speculation.

## Verification Checklist

Before finalizing:

- [ ] The user invoked or approved the MoA swarm workflow.
- [ ] Goal, done criteria, non-goals, and side-effect boundaries were defined.
- [ ] Sensitive context was redacted or MoA was skipped.
- [ ] MoA crafted the initial plan, or fallback was clearly labeled.
- [ ] Execution substrate was explicit.
- [ ] User approval was obtained before expensive, durable, risky, or live actions.
- [ ] Workers had distinct angles, scope, tool limits, and compact output requirements.
- [ ] Code edits used safe parent edits or isolated worktrees/branches.
- [ ] Liaisons summarized evidence and disagreements.
- [ ] MoA reviewed compact results when warranted.
- [ ] Parent inspected artifacts/diffs and ran objective verification.
- [ ] Risky surfaces received a hard-pass result-review gate.
- [ ] Live side effects were approved and performed by the parent/orchestrator.
- [ ] Durable work has a run record or task state.
- [ ] Final output states what changed, what passed, what blocked, and what remains.

## Related Skills

- `heavy-thinking-review` - fallback or complement for high-confidence deliberation. - inspired by this: https://arxiv.org/abs/2605.02396
- `subagent-driven-development` - scoped implementation delegation.
- `kanban-orchestrator` - durable multi-task orchestration.
- `requesting-code-review` - review dimensions for quality, security, and maintainability.
- `assets/moa-swarm-workflow.svg` - visual overview of the task-completion flow.
