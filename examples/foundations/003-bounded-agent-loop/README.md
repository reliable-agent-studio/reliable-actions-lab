# Bounded Agent Loop with DeepSeek

This experiment turns the fixed two-stage flow from Experiment 002 into a
bounded, observable agent loop.

The model may request tools across multiple rounds, but the application—not the
model—decides whether execution may continue. It enforces model-round and tool
call budgets, validates every proposed call, stops exact repetitions before
execution, and records a structured trace explaining how the run ended.

This is Experiment 003 in the Reliable Actions Lab foundation series:

1. [DeepSeek Tool Loop](../001-deepseek-tool-loop/)
2. [Controlled Tool Registry](../002-controlled-tool-registry/)
3. **Bounded Agent Loop**

## What this experiment demonstrates

- Repeatedly giving the model access to tools until it returns a final answer.
- Supporting sequential tool use across multiple model rounds.
- Limiting model rounds and successfully executed tool calls.
- Normalizing tool names and arguments into stable call signatures.
- Rejecting an exact repeated call before the tool runs a second time.
- Converting invalid calls and tool exceptions into explicit run states.
- Capturing model requests, model responses, tool executions, rejections, and
  the final stop reason in a structured trace.
- Testing the loop without an API key or network request.

The central rule is:

> The model may propose the next step, but trusted application code controls
> validation, execution, budgets, repetition, and stopping.

## Why the fixed flow from Experiment 002 is not enough

Experiment 002 deliberately uses two model calls:

```text
model -> tools -> model final answer
```

That works when every required tool is known in a single round. Some tasks need
the output of one tool before the model can select the next tool. For example:

```text
User asks whether order ORD-123 is returnable
    |
    v
Round 1: get_order_status("ORD-123")
    |
    | result reveals product category and purchase age
    v
Round 2: get_return_policy("electronics")
    |
    v
Round 3: final answer
```

A general loop enables that sequence, but an unbounded loop can repeatedly call
the model, consume tokens, invoke tools, and accumulate cost. The loop therefore
needs explicit control boundaries.

## Architecture

```text
User request
    |
    v
+---------------------------+
| Bounded application loop  |
+---------------------------+
    |
    | send messages + TOOL_DEFINITIONS
    v
DeepSeek model round
    |
    +-- no tool calls --------------------------+
    |                                           |
    |                                           v
    |                                      completed
    |
    +-- proposed tool calls
            |
            v
      Check tool-call budget
            |
            v
      Allowlist + argument validation
            |
            v
      Normalize exact call signature
            |
            v
      Reject if already executed
            |
            v
      Execute trusted local function
            |
            v
      Append tool result + trace event
            |
            +-------------------------> next model round
```

The check order matters. Repetition and validation are evaluated before the
tool runs, so a rejected call cannot produce a second effect.

## Project files

```text
003-bounded-agent-loop/
├── order_agent_deepseek.py  # Bounded loop, tools, controls, and trace
├── test_order_agent.py      # 21 offline tests using a fake model client
├── requirements.txt         # Pinned direct runtime dependency
└── README.md
```

## Requirements

- Python 3.8 or later
- A DeepSeek API key for the live demo
- `openai==2.2.0`

The runtime dependency is imported only inside `main()`. The offline tests do
not require the OpenAI package, an API key, or a network connection.

## Setup

From this directory, create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the pinned dependency:

```bash
python -m pip install -r requirements.txt
```

Set your DeepSeek API key:

```bash
export DEEPSEEK_API_KEY="your-api-key"
```

Do not commit API keys or `.env` files to Git.

## Run the live demo

```bash
python order_agent_deepseek.py
```

The example asks:

```text
Check order ORD-123 and determine whether its item can still be returned.
```

One possible run is:

```text
Round 1 -> get_order_status(order_id="ORD-123")
Round 2 -> get_return_policy(product_category="electronics")
Round 3 -> final answer
```

Model behavior is nondeterministic. The model may request both tools in one
round, use them across two rounds, or answer differently. Inspect the execution
trace rather than assuming an exact sequence.

## Run the offline tests

```bash
python -m unittest -v test_order_agent.py
```

Expected summary:

```text
Ran 21 tests

OK
```

The tests cover:

- valid and invalid tool arguments;
- stable signatures independent of JSON key order;
- completion without a tool call;
- one tool call followed by completion;
- different tools used across multiple rounds;
- exact repetition rejected before a second execution;
- maximum model rounds;
- maximum executed tool calls;
- unknown tools and malformed arguments;
- tool exceptions converted into an explicit stop state;
- tool definitions included in every model round;
- invalid loop-limit configuration.

The fake client implements only the response attributes used by the loop. This
makes control-flow tests fast and deterministic while keeping live model
behavior outside the unit-test boundary.

## Stop conditions

Every run returns one of these statuses:

| Status | Meaning |
| --- | --- |
| `completed` | The model requested no tools and returned its final answer. |
| `max_model_rounds_reached` | The application used the configured number of model calls. |
| `max_tool_calls_reached` | The application reached its successful tool-execution budget. |
| `repeated_tool_call` | The same tool and normalized arguments were proposed again. |
| `invalid_tool_call` | The tool name or arguments failed validation. |
| `tool_execution_failed` | An allowlisted local tool raised an exception. |

The default limits are:

```python
max_model_rounds=4
max_tool_calls=6
```

These values are demonstration defaults, not production recommendations. Real
limits should reflect the workflow, tool risk, latency budget, and cost budget.

## Exact repeated-call detection

The application creates a stable signature from the tool name and validated
arguments:

```text
get_order_status:{"order_id":"ORD-123"}
```

If that exact signature appears again during the same run, the loop stops before
executing it. The comparison happens after validation and JSON normalization,
so formatting and key ordering do not bypass it.

This is intentionally strict for two deterministic, read-only tools. Exact
repetition is not universally wrong. Polling, state refreshes, pagination, and
eventually consistent reads may legitimately repeat a call. A production
runtime needs per-tool repetition policies rather than one global rule.

Repeated-call detection is also not idempotency. It protects only one in-memory
run. It does not prevent duplicates after a process crash, retry, checkpoint
resume, or new session. Those cases require durable action identity and are the
subject of the next failure lab.

## Execution trace

The returned result includes trace events such as:

```json
{"event":"model_request","round":1}
{"event":"model_response","round":1,"requested_tool_calls":1,"has_content":false}
{"event":"tool_executed","round":1,"tool_name":"get_order_status","arguments":{"order_id":"ORD-123"},"result":"..."}
{"event":"run_stopped","reason":"completed"}
```

The trace is evidence for this small experiment, not a production telemetry
format. It currently records complete deterministic arguments and results. A
real system must classify and redact credentials, personal data, customer data,
and sensitive tool output before storing or exporting traces.

## Important design questions

### Why are tools sent on every model round?

The model may need a second tool after observing the first result. Omitting the
tool definitions after round one would silently turn the loop back into a fixed
two-stage flow.

### Why count successful tool executions instead of requested calls?

`tool_calls` reports how many tools actually completed. Invalid, repeated, and
failed calls remain visible as trace events but do not claim a successful
execution. A production system may also track separate proposed, attempted,
and completed counters.

### Why stop when a tool raises an exception?

Automatically retrying would hide an important distinction: an exception does
not prove that an external action failed. The external system may have committed
the action before the response was lost. This experiment records the failure
and stops; the next lab will model that ambiguous outcome explicitly.

### Why return a status instead of raising every error?

Invalid model output, repetition, exhausted budgets, and tool failures are
expected run outcomes. Returning explicit states lets callers, tests, and traces
reason about them. Invalid application configuration still raises immediately.

## What this experiment does not solve

This remains a learning example, not a production agent runtime. It does not
provide:

- user- or tenant-specific authorization;
- semantic validation against a real order system;
- token, time, or monetary budgets;
- context-window management;
- durable checkpoints or execution records;
- cancellation or deadline propagation;
- per-tool retry and repetition policies;
- redaction of sensitive trace data;
- idempotency for side-effecting tools;
- recovery after an external action commits but its response is lost;
- protection across processes, sessions, or checkpoint resumes.

## Key takeaway

A tool loop becomes safer when the application can answer four questions for
every run:

```text
What may execute?
How many times may execution continue?
Has this exact step already run?
Why did the run stop?
```

The model proposes the next step. The application owns those answers.

## Next step: Timeout After Commit

This completes the foundation series. The next experiment moves from
deterministic read-only tools to a simulated action with an ambiguous outcome:

```text
refund commits
    -> response is lost
    -> caller observes a timeout
    -> naive retry issues the refund again
```

That failure lab will compare naive retry with a stable business idempotency
key and a durable action receipt. It will live under `labs/`, not as Foundation
Experiment 004.
