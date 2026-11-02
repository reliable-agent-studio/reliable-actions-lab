import json
import os
from typing import Any, Dict, List, Optional


COMPLETED = "completed"
MAX_MODEL_ROUNDS_REACHED = "max_model_rounds_reached"
MAX_TOOL_CALLS_REACHED = "max_tool_calls_reached"
REPEATED_TOOL_CALL = "repeated_tool_call"
INVALID_TOOL_CALL = "invalid_tool_call"
TOOL_EXECUTION_FAILED = "tool_execution_failed"


def get_order_status(order_id: str) -> str:
    return (
        f"Order {order_id} contains an electronics item, has shipped, "
        "and was purchased 10 days ago."
    )


def get_return_policy(product_category: str) -> str:
    policies = {
        "electronics": "Electronics can be returned within 14 days.",
        "clothing": "Clothing can be returned within 30 days.",
    }
    return policies.get(
        product_category.lower(),
        "The standard return period is 30 days.",
    )


TOOL_REGISTRY = {
    "get_order_status": get_order_status,
    "get_return_policy": get_return_policy,
}

TOOL_ARGUMENTS = {
    "get_order_status": {"order_id"},
    "get_return_policy": {"product_category"},
}

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": (
                "Return the current status, product category, and purchase age "
                "of an order."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The order identifier supplied by the user.",
                    }
                },
                "required": ["order_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_return_policy",
            "description": "Return the return policy for a product category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_category": {
                        "type": "string",
                        "description": (
                            "The product category, such as electronics or clothing."
                        ),
                    }
                },
                "required": ["product_category"],
                "additionalProperties": False,
            },
        },
    },
]


def parse_and_validate_tool_arguments(
    tool_name: str,
    raw_arguments: str,
) -> Dict[str, str]:
    """Parse model-generated JSON and enforce the tool's argument contract."""
    if tool_name not in TOOL_ARGUMENTS:
        raise ValueError(f"No argument specification for tool: {tool_name}")

    try:
        arguments = json.loads(raw_arguments)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Invalid JSON arguments for {tool_name}") from exc

    if not isinstance(arguments, dict):
        raise ValueError(f"Arguments for {tool_name} must be a JSON object")

    expected_arguments = TOOL_ARGUMENTS[tool_name]
    actual_arguments = set(arguments)

    missing_arguments = expected_arguments - actual_arguments
    if missing_arguments:
        raise ValueError(
            f"Missing arguments for {tool_name}: {sorted(missing_arguments)}"
        )

    unexpected_arguments = actual_arguments - expected_arguments
    if unexpected_arguments:
        raise ValueError(
            f"Unexpected arguments for {tool_name}: {sorted(unexpected_arguments)}"
        )

    for argument_name, argument_value in arguments.items():
        if not isinstance(argument_value, str):
            raise ValueError(
                f"Argument '{argument_name}' for {tool_name} must be a string"
            )

        if not argument_value.strip():
            raise ValueError(
                f"Argument '{argument_name}' for {tool_name} must not be empty"
            )

    return arguments


def prepare_tool_call(tool_call: Any) -> Dict[str, Any]:
    """Validate a proposed tool call without executing it."""
    tool_name = tool_call.function.name

    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool: {tool_name}")

    arguments = parse_and_validate_tool_arguments(
        tool_name=tool_name,
        raw_arguments=tool_call.function.arguments,
    )

    return {
        "tool_call_id": tool_call.id,
        "tool_name": tool_name,
        "arguments": arguments,
    }


def create_tool_call_signature(
    tool_name: str,
    arguments: Dict[str, str],
) -> str:
    """Create a stable signature for an exact tool name and argument set."""
    normalized_arguments = json.dumps(
        arguments,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{tool_name}:{normalized_arguments}"


def build_run_result(
    status: str,
    final_answer: Optional[str],
    model_rounds: int,
    tool_calls: int,
    trace: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "status": status,
        "final_answer": final_answer,
        "model_rounds": model_rounds,
        "tool_calls": tool_calls,
        "trace": trace,
    }


def run_agent_loop(
    client: Any,
    messages: List[Dict[str, Any]],
    model: str = "deepseek-flash",
    max_model_rounds: int = 4,
    max_tool_calls: int = 6,
) -> Dict[str, Any]:
    """Run a bounded tool-calling loop and return its result and trace."""
    if max_model_rounds < 1:
        raise ValueError("max_model_rounds must be at least 1")
    if max_tool_calls < 1:
        raise ValueError("max_tool_calls must be at least 1")

    trace: List[Dict[str, Any]] = []
    seen_tool_calls = set()
    executed_tool_calls = 0

    for model_round in range(1, max_model_rounds + 1):
        trace.append(
            {
                "event": "model_request",
                "round": model_round,
            }
        )

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            extra_body={"thinking": {"type": "disabled"}},
        )

        assistant_message = response.choices[0].message
        messages.append(assistant_message.model_dump(exclude_none=True))
        requested_tool_calls = list(assistant_message.tool_calls or [])

        trace.append(
            {
                "event": "model_response",
                "round": model_round,
                "requested_tool_calls": len(requested_tool_calls),
                "has_content": bool(assistant_message.content),
            }
        )

        if not requested_tool_calls:
            trace.append(
                {
                    "event": "run_stopped",
                    "reason": COMPLETED,
                }
            )
            return build_run_result(
                status=COMPLETED,
                final_answer=assistant_message.content,
                model_rounds=model_round,
                tool_calls=executed_tool_calls,
                trace=trace,
            )

        for tool_call in requested_tool_calls:
            if executed_tool_calls >= max_tool_calls:
                trace.append(
                    {
                        "event": "run_stopped",
                        "reason": MAX_TOOL_CALLS_REACHED,
                    }
                )
                return build_run_result(
                    status=MAX_TOOL_CALLS_REACHED,
                    final_answer=None,
                    model_rounds=model_round,
                    tool_calls=executed_tool_calls,
                    trace=trace,
                )

            try:
                prepared_call = prepare_tool_call(tool_call)
            except ValueError as error:
                trace.append(
                    {
                        "event": "tool_rejected",
                        "round": model_round,
                        "tool_name": tool_call.function.name,
                        "error": str(error),
                    }
                )
                trace.append(
                    {
                        "event": "run_stopped",
                        "reason": INVALID_TOOL_CALL,
                    }
                )
                return build_run_result(
                    status=INVALID_TOOL_CALL,
                    final_answer=None,
                    model_rounds=model_round,
                    tool_calls=executed_tool_calls,
                    trace=trace,
                )

            signature = create_tool_call_signature(
                prepared_call["tool_name"],
                prepared_call["arguments"],
            )

            if signature in seen_tool_calls:
                trace.append(
                    {
                        "event": "tool_rejected",
                        "round": model_round,
                        "tool_name": prepared_call["tool_name"],
                        "arguments": prepared_call["arguments"],
                        "error": "Exact tool call already executed in this run",
                    }
                )
                trace.append(
                    {
                        "event": "run_stopped",
                        "reason": REPEATED_TOOL_CALL,
                    }
                )
                return build_run_result(
                    status=REPEATED_TOOL_CALL,
                    final_answer=None,
                    model_rounds=model_round,
                    tool_calls=executed_tool_calls,
                    trace=trace,
                )

            tool_function = TOOL_REGISTRY[prepared_call["tool_name"]]
            try:
                tool_result = tool_function(**prepared_call["arguments"])
            except Exception as error:  # The boundary converts tool failure to run state.
                trace.append(
                    {
                        "event": "tool_failed",
                        "round": model_round,
                        "tool_name": prepared_call["tool_name"],
                        "arguments": prepared_call["arguments"],
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
                trace.append(
                    {
                        "event": "run_stopped",
                        "reason": TOOL_EXECUTION_FAILED,
                    }
                )
                return build_run_result(
                    status=TOOL_EXECUTION_FAILED,
                    final_answer=None,
                    model_rounds=model_round,
                    tool_calls=executed_tool_calls,
                    trace=trace,
                )

            seen_tool_calls.add(signature)
            executed_tool_calls += 1

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": prepared_call["tool_call_id"],
                    "content": str(tool_result),
                }
            )

            trace.append(
                {
                    "event": "tool_executed",
                    "round": model_round,
                    "tool_name": prepared_call["tool_name"],
                    "arguments": prepared_call["arguments"],
                    "result": str(tool_result),
                }
            )

    trace.append(
        {
            "event": "run_stopped",
            "reason": MAX_MODEL_ROUNDS_REACHED,
        }
    )
    return build_run_result(
        status=MAX_MODEL_ROUNDS_REACHED,
        final_answer=None,
        model_rounds=max_model_rounds,
        tool_calls=executed_tool_calls,
        trace=trace,
    )


def main() -> None:
    # Import lazily so the offline tests do not require the OpenAI package.
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a friendly order-support assistant. "
                "Use tools when order or return information is needed. "
                "You may call tools across multiple rounds. "
                "Treat tool results as authoritative. "
                "Do not invent order statuses or return policies."
            ),
        },
        {
            "role": "user",
            "content": (
                "Check order ORD-123 and determine whether its item can still "
                "be returned."
            ),
        },
    ]

    result = run_agent_loop(
        client=client,
        messages=messages,
        max_model_rounds=4,
        max_tool_calls=6,
    )

    print("\n[RUN RESULT]")
    print(f"Status: {result['status']}")
    print(f"Model rounds: {result['model_rounds']}")
    print(f"Tool calls: {result['tool_calls']}")
    if result["final_answer"]:
        print(f"Final answer: {result['final_answer']}")

    print("\n[EXECUTION TRACE]")
    for trace_event in result["trace"]:
        print(json.dumps(trace_event, ensure_ascii=False))


if __name__ == "__main__":
    main()
