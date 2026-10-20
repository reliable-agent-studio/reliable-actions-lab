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

## Status

This project is in its initial build phase. The first experiment is being
developed; no production-safety claims are made yet.

## First experiment: Timeout After Commit

A refund provider commits an action, but its response is lost or delayed long
enough for the caller to time out. The workflow retries and may issue the same
refund twice.

The experiment will compare:

1. retry without an idempotency key;
2. retry with a business-level idempotency key;
3. checkpoint and resume after an ambiguous outcome;
4. recovery using a durable action receipt.

## Planned labs

- Timeout After Commit
- Retry Without Idempotency
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

