# Timeout After Commit

This lab reproduces an ambiguous outcome in a side-effecting tool call and
compares a naive retry with a stable business idempotency key:

> The external provider commits a refund, but its success response is lost. The
> caller observes a timeout, assumes failure, retries, and commits a second
> refund.

This is the first failure lab in Reliable Actions Lab. It intentionally starts
without an LLM so the execution failure remains deterministic and separate from
model behavior.

## Lab status

**Baseline complete.** The failure and its first mitigation are covered by four
deterministic offline tests and were last verified on 2026-11-04.

This lab is intentionally framework-independent. It establishes the external
state invariant and test oracle that later Agent-specific labs must preserve.

## Problem

A timeout describes what the caller observed: no response arrived before its
deadline. It does not prove what happened in the external system.

The same timeout can mean that:

- the request never reached the provider;
- the provider is still processing the request;
- the provider rejected the request;
- the provider committed the refund but its response was delayed or lost.

Treating all four cases as a definite failure makes an automatic retry unsafe.

## Relationship to Agent reliability

Timeout ambiguity and idempotency are established distributed-systems
techniques; they are not new inventions created by AI agents. This lab keeps
that provenance explicit.

It belongs in Reliable Actions Lab because an Agent runtime can obscure or
break the identity that idempotency depends on. A model may retry after reading
an exception, produce a new tool-call ID, change arguments while replanning, or
replay an action after checkpoint resume. Those Agent-specific mechanisms will
be tested separately against the invariant defined here.

## Production invariant

For one approved refund intent:

```text
committed refund count == 1
committed refund amount == approved refund amount
```

Both comparison scenarios use:

```text
order_id: ORD-123
approved amount: 1000 cents
```

## Failure hypothesis

If the first refund commits and then raises `TimeoutError`, a caller that treats
the exception as proof of failure and retries without a stable action identity
will create two refunds.

## Failure timeline

```text
Caller                    Fake refund provider
  |                                |
  | issue_refund(ORD-123, 1000)     |
  |------------------------------->|
  |                                | commit refund-1
  |                                | lose success response
  |<---------- TimeoutError -------|
  |                                |
  | assume failure                 |
  | retry same business action     |
  |------------------------------->|
  |                                | commit refund-2
  |<---------- refund-2 -----------|
```

The caller receives a successful result for `refund-2`, while the provider has
already committed both `refund-1` and `refund-2`.

## Project files

```text
001-timeout-after-commit/
├── fake_refund_provider.py       # Deterministic external system simulation
├── test_timeout_after_commit.py  # Failure and mitigation comparisons
└── README.md
```

## Failure injection

`FakeRefundProvider.issue_refund()` deliberately commits before injecting the
failure:

```python
self.refunds.append(refund)

if lose_response_after_commit:
    raise TimeoutError(
        "Refund committed, but the success response was lost"
    )
```

The order is the experiment. Moving the exception before `self.refunds.append()`
would simulate a different failure: timeout before commit.

## Mitigation: stable business idempotency key

The protected caller assigns one identity to the approved refund intent and
reuses it after the timeout:

```text
idempotency_key = refund:ORD-123:1000:v1
```

The provider binds that key to the first committed refund before the response
is lost. On retry, it finds the existing binding and returns `refund-1` instead
of committing `refund-2`:

```text
first request with key
    -> commit refund-1
    -> bind key to refund-1
    -> lose response

retry with same key and arguments
    -> find refund-1
    -> return refund-1
    -> do not commit another refund
```

The key must identify the same business intent across retries. Generating a new
key for each network attempt would not prevent duplication.

The fixture also binds the key to `order_id` and `amount_cents`. Reusing the
same key with a different amount raises `IdempotencyConflictError` instead of
silently returning the wrong result.

## Run the experiment

No API key, model provider, network request, or third-party dependency is
required.

```bash
python3 -m unittest -v test_timeout_after_commit.py
```

Expected result:

```text
test_different_idempotency_keys_represent_different_actions ... ok
test_idempotency_key_is_bound_to_refund_arguments ... ok
test_naive_retry_reproduces_duplicate_refund ... ok
test_stable_idempotency_key_prevents_duplicate_refund ... ok

Ran 4 tests

OK
```

The passing test does **not** mean the refund workflow is correct. It means the
failure is reproduced deterministically. The assertions confirm the observed
bad state:

```text
expected business result: 1 refund, 1000 cents
observed external result: 2 refunds, 2000 cents
```

The mitigation test verifies the contrasting result:

```text
stable key expected result: 1 refund, 1000 cents
stable key observed result: 1 refund, 1000 cents
retry returns: refund-1
```

## Comparison

| Caller behavior | Keys used | Committed refunds | Total amount |
| --- | --- | ---: | ---: |
| Retry after timeout without action identity | none | 2 | 2000 cents |
| Retry the same intent with the same stable key | one stable key | 1 | 1000 cents |
| Retry the same intent with a new key | two different keys | 2 | 2000 cents |

## Observed event sequence

The fake provider records evidence independently of what the caller believes:

```text
refund_committed  refund-1
response_lost     refund-1
refund_committed  refund-2
response_returned refund-2
```

This separates the caller's observation from external state. The caller sees a
timeout followed by success; the provider records two commits.

With a stable idempotency key, the provider instead records:

```text
refund_committed   refund-1
response_lost      refund-1
idempotency_replay refund-1
response_returned  refund-1
```

The retry returns the original refund and does not add another commit.

## What this version proves

- A timeout is not evidence that an external action failed.
- A successful retry result does not prove that only one action occurred.
- Caller-visible control flow and provider-visible state can disagree.
- The external state must be part of the test oracle for side-effecting tools.
- A stable key can make retry return the first result instead of repeating the
  side effect.
- A key is meaningful only when it is stable across attempts and bound to the
  original action arguments.
- The mitigation is a known distributed-systems pattern; this lab provides a
  deterministic baseline rather than claiming a novel Agent technique.

## What this version does not solve

This version intentionally does not include:

- a durable action record;
- lookup or reconciliation after an ambiguous outcome;
- concurrent requests;
- process crashes or checkpoint resume;
- an Agent or LLM tool loop;
- a real payment provider.

The provider is a deterministic in-memory test fixture. It demonstrates one
failure boundary; it does not claim to reproduce every payment API behavior.

The in-memory fixture records the refund and its key binding sequentially. A
production design must make that relationship durable and atomic, or delegate
it to a provider with documented idempotency guarantees. If a process can crash
after committing the action but before persisting the key binding, the same
ambiguity reappears inside the mitigation.

## Next lab: Agent retry regenerates action identity

Lab 002 will connect this invariant to an Agent execution boundary. It will
compare two designs:

```text
unsafe: model tool_call_id becomes idempotency key
        -> retry creates a new tool_call_id
        -> duplicate refund

safe:   application-owned action_id becomes idempotency key
        -> retry reuses the durable action_id
        -> original refund returned
```

The new lab will have its own focused README and tests. It may reuse the minimal
fake provider behavior, but it should not duplicate this entire directory or
present classic idempotency as an Agent-specific discovery.

## Environment and verification

- Python: 3.8 or later
- External dependencies: none
- Synthetic data only
- Last verified: 2026-11-04
