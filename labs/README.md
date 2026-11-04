# Labs

Each lab should be independently runnable and use synthetic data and local
fake providers by default.

## Published labs

1. [Timeout After Commit](001-timeout-after-commit/) — deterministic comparison
   of naive retry and a stable business idempotency key.

## Next lab

`002-agent-retry-regenerates-action-identity` will test why a model-generated
tool-call ID is not a durable business-action identity.

New labs should copy the required section structure below, not duplicate an
earlier lab wholesale. Reuse only the smallest fixture behavior needed to keep
each experiment independently understandable and runnable.

## Required lab sections

1. Problem
2. Production invariant
3. Failure hypothesis
4. Environment and versions
5. Failure injection
6. Expected behavior
7. Observed behavior
8. Automated assertions
9. Mitigation
10. Trade-offs and limitations
11. Last verification date

