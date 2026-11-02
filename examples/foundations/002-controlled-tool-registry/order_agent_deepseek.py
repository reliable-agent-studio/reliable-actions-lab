import json
import os

from openai import OpenAI


def get_order_status(order_id: str) -> str:
    print(f"[2. LOCAL TOOL EXECUTION] Looking up {order_id}")
    return f"Order {order_id} has shipped and will arrive tomorrow."


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
            "description": "Return the current status of an order.",
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
) -> dict:
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


def main() -> None:
    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a friendly order-support assistant. "
                "Use get_order_status to check an order when an order ID is provided. "
                "Use get_return_policy for questions about product returns. "
                "Treat tool results as authoritative. "
                "Do not invent order statuses or return policies."
            ),
        },
        #{"role": "user", "content": "Where is order ORD-123?"},
        {"role": "user", "content": "Check order ORD-123 and tell me the return policy for electronics."},
    ]

    print("[1. MODEL DECISION] Asking the model what to do...")
    first_response = client.chat.completions.create(
        model="deepseek-flash",
        messages=messages,
        tools=TOOL_DEFINITIONS,
        extra_body={"thinking": {"type": "disabled"}},
    )

    assistant_message = first_response.choices[0].message
    messages.append(assistant_message.model_dump(exclude_none=True))

    if not assistant_message.tool_calls:
        print("The model did not request a tool call.")
        print(assistant_message.content)
        return

    for tool_call in assistant_message.tool_calls:
        tool_name = tool_call.function.name

        if tool_name not in TOOL_REGISTRY:
            raise ValueError(f"Unknown tool: {tool_name}")

        arguments = parse_and_validate_tool_arguments(
            tool_name=tool_name,
            raw_arguments=tool_call.function.arguments,
        )
        tool_function = TOOL_REGISTRY[tool_name]
        tool_result = tool_function(**arguments)

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            }
        )

    print("[3. MODEL SYNTHESIS] Returning the tool result to the model...")
    final_response = client.chat.completions.create(
        model="deepseek-flash",
        messages=messages,
        extra_body={"thinking": {"type": "disabled"}},
    )

    print("\n[4. FINAL OUTPUT]")
    print(final_response.choices[0].message.content)


if __name__ == "__main__":
    main()
