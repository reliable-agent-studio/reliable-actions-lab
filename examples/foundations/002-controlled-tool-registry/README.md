# Controlled Tool Registry with DeepSeek

This experiment upgrades a single hard-coded tool call into a small,
controlled multi-tool agent.

The model can choose between two tools, but it cannot execute Python code
directly. The application validates the requested tool and its arguments before
dispatching the call through an explicit allowlist.

This is Experiment 002 in the Reliable Actions Lab foundation series. If tool
calling is new to you, start with
[Experiment 001: DeepSeek Tool Loop](../001-deepseek-tool-loop/).

## What this experiment demonstrates

- Advertising multiple tools to a model with JSON Schema.
- Separating model-visible tool definitions from executable Python functions.
- Dispatching calls through an explicit `TOOL_REGISTRY` allowlist.
- Treating model-generated arguments as untrusted input.
- Rejecting invalid JSON, missing arguments, extra arguments, wrong types, and
  empty values before tool execution.
- Handling zero, one, or multiple tool calls returned in one model response.
- Returning tool results to the model for a grounded final answer.

The central rule is:

> The model proposes an action. Trusted application code validates and executes
> the action.

## Architecture

```text
User question
    |
    v
DeepSeek receives messages + TOOL_DEFINITIONS
    |
    v
Model returns zero, one, or more tool calls
    |
    v
Python checks the tool name against TOOL_REGISTRY
    |
    v
Python parses and validates the JSON arguments
    |
    v
Python executes the allowlisted function
    |
    v
Tool result is appended to the conversation
    |
    v
DeepSeek produces the final user-facing answer
```

The model selects a tool. The Python application remains responsible for
authorization, validation, execution, and error handling.

## Project files

```text
002-controlled-tool-registry/
├── order_agent_deepseek.py  # Demo agent and validation logic
├── test_order_agent.py      # Offline argument-validation tests
└── README.md
```

## Requirements

- Python 3.8 or later
- A DeepSeek API key
- `openai==2.2.0`

The example uses the OpenAI Python client with DeepSeek's OpenAI-compatible
endpoint. It does not require an OpenAI API key.

## Setup

From this directory, create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the client library:

```bash
python -m pip install openai==2.2.0
```

Set your DeepSeek API key:

```bash
export DEEPSEEK_API_KEY="your-api-key"
```

Do not commit API keys or `.env` files to Git.

## Run the demo

```bash
python order_agent_deepseek.py
```

The current example asks for both an order status and an electronics return
policy. The model can request both tools, Python executes each approved call,
and the model receives both results before generating its final answer.

To try other behaviors, change the user message in `main()`:

| User message | Expected behavior |
| --- | --- |
| `Where is order ORD-123?` | Request `get_order_status` |
| `What is the return policy for electronics?` | Request `get_return_policy` |
| `Can I return clothing after 20 days?` | Use the clothing policy result |
| `Hello, how are you?` | Answer without requesting a tool |
| `Check order ORD-123 and tell me the return policy for electronics.` | May request both tools |

Model behavior can vary, so inspect the requested tool names and arguments
rather than assuming every run will use the same call pattern.

## Two structures with different responsibilities

The demo intentionally keeps tool definitions and executable functions
separate.

### `TOOL_DEFINITIONS`: the model's tool menu

`TOOL_DEFINITIONS` contains serializable descriptions and JSON Schemas. It is
sent to the model:

```python
first_response = client.chat.completions.create(
    model="deepseek-flash",
    messages=messages,
    tools=TOOL_DEFINITIONS,
)
```

It tells the model:

- which tools exist;
- when each tool is useful;
- which arguments each tool expects;
- the expected argument types.

It does not contain executable Python functions.

### `TOOL_REGISTRY`: the application's execution allowlist

`TOOL_REGISTRY` maps public tool names to trusted local functions:

```python
TOOL_REGISTRY = {
    "get_order_status": get_order_status,
    "get_return_policy": get_return_policy,
}
```

It is used only by the Python application and is never sent to the model. The
registry prevents the model from naming and executing arbitrary functions.

If a function exists in Python but is absent from `TOOL_DEFINITIONS`, the model
is not intentionally given that capability. If a tool is advertised in
`TOOL_DEFINITIONS` but absent from `TOOL_REGISTRY`, the application rejects the
call as unknown.

## Why a registry instead of reflection?

The dispatcher performs an explicit allowlisted lookup:

```python
if tool_name not in TOOL_REGISTRY:
    raise ValueError(f"Unknown tool: {tool_name}")

tool_function = TOOL_REGISTRY[tool_name]
```

This remains generic as more tools are added, while limiting execution to
functions deliberately registered by the developer.

Avoid dispatching model output through `eval()`, `globals()`, or unrestricted
`getattr()`. Those approaches can expose functions that were never intended to
be model-callable.

## Runtime argument validation

JSON Schema helps the model generate well-formed arguments, but it is not the
application's security boundary. Model output is external input and must still
be checked before execution.

`parse_and_validate_tool_arguments()` enforces the following sequence:

1. The tool has a known argument specification.
2. The argument string contains valid JSON.
3. The decoded JSON value is an object, represented by a Python dictionary.
4. All required arguments are present.
5. No unexpected arguments are present.
6. Every value is a non-empty string.

Only validated arguments reach the function call:

```python
arguments = parse_and_validate_tool_arguments(
    tool_name=tool_name,
    raw_arguments=tool_call.function.arguments,
)

tool_function = TOOL_REGISTRY[tool_name]
tool_result = tool_function(**arguments)
```

That order matters. Calling `tool_function(**arguments)` before validation
would pass model-generated input directly into application code.

## Run the offline tests

The validation tests do not use an API key or make a network request:

```bash
python -m unittest -v test_order_agent.py
```

The nine tests cover:

- valid order-status arguments;
- valid return-policy arguments;
- malformed JSON;
- a JSON value that is not an object;
- a missing required argument;
- an unexpected argument;
- a non-string value;
- an empty string;
- a tool without an argument specification.

Expected summary:

```text
Ran 9 tests

OK
```

## Important design questions

### Why are both `TOOL_DEFINITIONS` and `TOOL_REGISTRY` necessary?

They live on opposite sides of the trust boundary:

- `TOOL_DEFINITIONS` tells the model what it may request.
- `TOOL_REGISTRY` tells the application what it may execute.

The API call receives `TOOL_DEFINITIONS`, not `TOOL_REGISTRY`. Python function
objects are not API tool schemas and should not be sent to the model.

### Why validate arguments when the schema already defines them?

The schema guides model output. Runtime validation protects the application.
Models, providers, integrations, or malformed requests may still produce
unexpected data. Validation ensures that only the intended argument contract
reaches internal code.

### Who executes the tools?

The model does not call the Python functions. It returns a tool name and a
JSON-encoded argument string. The application validates that request, looks up
the function, and executes it locally.

### Who controls the execution order of multiple calls?

The model returns an ordered `tool_calls` collection, but the application
decides how to process it. This demo executes calls sequentially in the order
received. A production system may add dependency handling, concurrency limits,
timeouts, approvals, or transaction rules.

### Why does the second model call omit tools?

This experiment has a deliberately fixed two-stage flow:

1. Let the model request tools.
2. Execute the approved tools and ask the model for the final answer.

Omitting tools from the second request prevents another tool-calling round and
keeps the example focused. A general agent loop should continue providing tool
definitions until the model stops requesting tools, subject to strict round and
cost limits. That is the focus of Experiment 003.

## What this demo does not solve

This is a learning example, not a production agent runtime. It does not yet
provide:

- authorization based on the current user;
- semantic validation of real order IDs or product categories;
- timeouts, retries, or rate-limit handling;
- redaction of sensitive tool inputs and outputs;
- durable execution records or audit logs;
- idempotency for tools with side effects;
- recovery from a crash after an external action succeeds;
- maximum model rounds, token budgets, or cost budgets;
- detection of repeated or looping tool calls.

The tools are intentionally read-only and deterministic. Writes such as
cancellations and refunds require stronger controls than this example provides.

## Key takeaway

A reliable tool-calling agent needs more than a list of Python functions. It
needs an explicit boundary between what the model can request and what the
application will execute:

```text
Model-visible schema
        +
Application allowlist
        +
Runtime validation
        =
Controlled tool execution
```

## Next experiment

Experiment 003 will turn this fixed two-stage flow into a bounded agent loop
with:

- a maximum number of model rounds;
- explicit stop conditions;
- sequential tool use across multiple rounds;
- repeated-call and loop protection;
- visible execution traces.
