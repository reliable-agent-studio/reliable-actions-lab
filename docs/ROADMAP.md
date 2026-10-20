# Roadmap

## Phase 0 — Project foundation

- Define the lab format and evidence standard.
- Implement a deterministic fake action provider.
- Record action IDs, attempts, commits, responses, and recovery decisions.
- Publish the first before-and-after failure trace.

## Phase 1 — Retry and recovery

- Timeout After Commit
- Retry Without Idempotency
- Resume Replays a Completed Action
- Durable Action Receipt

## Phase 2 — Approval and governance

- Approval Does Not Bind to Arguments
- Approval Reuse After State Change
- Parallel Approved Actions
- Auditable Action Decisions

## Phase 3 — Multi-agent boundaries

- Handoff Drops Required State
- Handoff Drops Authorization Context
- Retried Parent Duplicates a Child Action
- Shared State Drift

## Phase 4 — Regression gates

- Versioned failure fixtures
- Model and SDK upgrade comparisons
- CI-ready deterministic assertions
- Canary action testing

The order may change when reproducible user reports show a more urgent or
common production failure.

