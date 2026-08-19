---
name: antigravity-implementation-loop
description: "Orchestrate software implementation with Google Antigravity CLI (agy): inspect the repository, create a verifiable plan, delegate coding, inspect actual diffs, run checks, audit independently, and iterate with precise feedback. Use when a user asks Antigravity/agy to implement or repair a feature and Codex must remain the final reviewer."
---

# Antigravity implementation loop

Use Codex as planner and quality gate; use `agy` only as an implementation worker. Never accept an Antigravity completion summary as proof.

## 1. Inspect before delegating

- Read repository instructions (including `AGENTS.md`) and relevant module contracts, tests, and documentation.
- Check the installed CLI before selecting flags:

  ```bash
  codex --version
  agy --version
  agy --help
  ```

- Produce internally: Goal, Implementation Plan, Acceptance Criteria, Affected Areas, and Potential Risks. Make each acceptance criterion objectively testable.

## 2. Delegate a bounded task

Give `agy` a concise prompt containing:

```text
TASK
CONTEXT
FILES / AREAS TO INSPECT
IMPLEMENTATION PLAN
ACCEPTANCE CRITERIA
CONSTRAINTS
PREVIOUS REVIEW FINDINGS (if any)
```

Prefer non-interactive print mode and machine-readable output when supported. Use the bundled wrapper for consistent capture:

```bash
./.agents/skills/antigravity-implementation-loop/scripts/run_agy.sh prompt.txt output.json
```

The wrapper must not push, merge, reset, or rewrite history. Keep implementation in the working tree so Codex can inspect it.

## 3. Inspect the real result

After every worker invocation, run `git status --short`, `git diff`, and `git diff --check`. Read changed source and tests, not just the worker report. Confirm changes stay within the owning module unless a boundary change is justified.

## 4. Verify independently

Detect the project stack and run narrow relevant tests first, then integration tests, lint, typecheck, build, and compile checks when applicable. Do not weaken or rewrite tests merely to make them pass. Check success, failure, concurrency, persistence, security, and compatibility paths.

For every criterion record `PASS`, `FAIL`, or `UNKNOWN` with concrete evidence (file/line, command, and output). Treat failed checks and unavailable required checks as blockers until resolved or explicitly reported.

## 5. Iterate safely

If any criterion is `FAIL`, or a critical regression is found, send the same worker/session a focused feedback package:

```text
ITERATION: N
FAILED CRITERIA
BUGS FOUND
EVIDENCE
REQUIRED CHANGES
DO NOT CHANGE
TESTS THAT MUST PASS
```

Send only the original goal summary plus new findings and relevant errors; do not resend the whole conversation. Re-inspect the complete diff and rerun verification after each fix. Default to at most five iterations. If the limit is reached, stop and report `BLOCKED`, remaining failures, likely cause, attempted iterations, and the human decision needed.

## Completion contract

Report `IMPLEMENTATION VERIFIED` only when every acceptance criterion is `PASS`, applicable checks pass, and no blocker or critical regression remains. Include iterations, verification commands/results, changed files, important decisions, and non-blocking concerns. Never push or alter Git history unless the user explicitly requests it.
