import json
import os

from openai import OpenAI


def get_order_status(order_id: str) -> str:
    print(f"[2. LOCAL TOOL EXECUTION] Looking up {order_id}")
    return f"Order {order_id} has shipped and will arrive tomorrow."


tools = [
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
            },
        },
    }
]

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
                "Use get_order_status when the user provides an order ID. "
                "Treat the tool result as the authoritative source. "
                "Do not invent an order status."
            ),
        },
        {"role": "user", "content": "Where is order ORD-123?"},
    ]

    print("[1. MODEL DECISION] Asking the model what to do...")
    first_response = client.chat.completions.create(
        model="deepseek-flash",
        messages=messages,
        tools=tools,
        extra_body={"thinking": {"type": "disabled"}},
    )

    assistant_message = first_response.choices[0].message
    messages.append(assistant_message.model_dump(exclude_none=True))

    if not assistant_message.tool_calls:
        print("The model did not request a tool call.")
        print(assistant_message.content)
        return

    for tool_call in assistant_message.tool_calls:
        if tool_call.function.name != "get_order_status":
            raise ValueError(f"Unexpected tool: {tool_call.function.name}")

        arguments = json.loads(tool_call.function.arguments)
        tool_result = get_order_status(arguments["order_id"])

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
