# Reliable Actions Lab

> Failure experiments for production AI agents.

Reliable Actions Lab is an open engineering project from
[Reliable Agent Studio](https://reliableagentstudio.com). It studies a narrow
question:

> When an AI agent performs a real action, does that action remain correct
> across timeouts, retries, approvals, interruptions, resumes, and replays?

The project turns production failure modes into small, reproducible
experiments. Each lab aims to document the expected invariant, inject one
failure, capture the observed behavior, and test a concrete mitigation.

## Foundation experiments

The foundation series builds the smallest controllable tool-calling agent before
introducing side effects and recovery failures:

1. [DeepSeek Tool Loop](examples/foundations/001-deepseek-tool-loop/) — the
   model proposes one local tool call and receives its result.
2. [Controlled Tool Registry](examples/foundations/002-controlled-tool-registry/)
   — an explicit allowlist and runtime argument validation control execution.
3. [Bounded Agent Loop](examples/foundations/003-bounded-agent-loop/) —
   multi-round tool use with budgets, repetition protection, stop reasons, and
   a structured trace.

The next step is the first failure lab, **Timeout After Commit**. The foundation
series stops at Experiment 003 rather than growing into a general Agent tutorial.

## Status

This project is in its initial build phase. The first deterministic failure lab
is published; no production-safety claims are made yet.

## First failure lab: Timeout After Commit

A refund provider commits an action, but its response is lost or delayed long
enough for the caller to time out. The workflow retries and may issue the same
refund twice.

The completed baseline compares:

1. retry without an idempotency key;
2. retry with a stable business idempotency key;
3. reuse of one key with conflicting arguments;
4. separate business actions represented by separate keys.

Run the lab: [labs/001-timeout-after-commit](labs/001-timeout-after-commit/).

## Planned labs

- [Timeout After Commit](labs/001-timeout-after-commit/) — published baseline
- Agent Retry Regenerates Action Identity
- Resume Replays a Completed Action
- Approval Does Not Bind to Arguments
- Parallel Tools Lose an Output
- Multi-Agent Handoff Drops Required State
- Guardrail Misses a Handoff Boundary
- Trace Breaks Across Resume

## Evidence standard

Every completed lab should include:

- the production invariant being tested;
- a deterministic failure-injection mechanism;
- expected and observed behavior;
- runnable code and automated assertions;
- framework, model, SDK, and dependency versions;
- traces or logs with secrets removed;
- a mitigation and its trade-offs;
- explicit limitations and a verification date.

## Repository layout

```text
examples/   Small foundation experiments for understanding the execution loop
labs/       Reproducible failure experiments
patterns/   Architecture patterns derived from verified experiments
fixtures/   Deterministic providers, events, and failure inputs
docs/       Methodology, roadmap, and project notes
```

## Principles

- Evidence before claims.
- Change one failure condition at a time.
- Separate model behavior from execution-layer failures.
- Treat retries and resumes as state transitions, not prompt tricks.
- Prefer deterministic assertions before model-based grading.
- Publish negative and inconclusive results.
- Never include real credentials, customer data, or production endpoints.

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md).

## Contributing

The most useful early contributions are concrete failure reports with a
minimal reproduction, affected versions, expected behavior, observed behavior,
and an explanation of the production impact.

The contribution process and code license will be finalized before accepting
substantial external code contributions.

