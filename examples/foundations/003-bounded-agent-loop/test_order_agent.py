import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from order_agent_deepseek import (
    COMPLETED,
    INVALID_TOOL_CALL,
    MAX_MODEL_ROUNDS_REACHED,
    MAX_TOOL_CALLS_REACHED,
    REPEATED_TOOL_CALL,
    TOOL_DEFINITIONS,
    TOOL_EXECUTION_FAILED,
    TOOL_REGISTRY,
    create_tool_call_signature,
    parse_and_validate_tool_arguments,
    run_agent_loop,
)


class FakeAssistantMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self, exclude_none=True):
        message = {"role": "assistant"}
        if self.content is not None:
            message["content"] = self.content
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in self.tool_calls
            ]
        return message


def fake_tool_call(call_id, tool_name, arguments):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=tool_name,
            arguments=json.dumps(arguments) if isinstance(arguments, dict) else arguments,
        ),
    )


def fake_response(content=None, tool_calls=None):
    message = FakeAssistantMessage(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
    )


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if not self.responses:
            raise AssertionError("The fake model received more calls than expected")
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        completions = FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=completions)


def initial_messages():
    return [
        {"role": "system", "content": "Use the available tools."},
        {"role": "user", "content": "Can I return order ORD-123?"},
    ]


class ToolArgumentValidationTests(unittest.TestCase):
    def test_accepts_valid_order_arguments(self):
        arguments = parse_and_validate_tool_arguments(
            "get_order_status",
            '{"order_id": "ORD-123"}',
        )
        self.assertEqual(arguments, {"order_id": "ORD-123"})

    def test_accepts_valid_return_policy_arguments(self):
        arguments = parse_and_validate_tool_arguments(
            "get_return_policy",
            '{"product_category": "electronics"}',
        )
        self.assertEqual(arguments, {"product_category": "electronics"})

    def test_rejects_invalid_json(self):
        with self.assertRaisesRegex(ValueError, "Invalid JSON"):
            parse_and_validate_tool_arguments(
                "get_order_status",
                '{"order_id": }',
            )

    def test_rejects_non_object_json(self):
        with self.assertRaisesRegex(ValueError, "must be a JSON object"):
            parse_and_validate_tool_arguments(
                "get_order_status",
                '["ORD-123"]',
            )

    def test_rejects_missing_argument(self):
        with self.assertRaisesRegex(ValueError, "Missing arguments"):
            parse_and_validate_tool_arguments("get_order_status", "{}")

    def test_rejects_unexpected_argument(self):
        with self.assertRaisesRegex(ValueError, "Unexpected arguments"):
            parse_and_validate_tool_arguments(
                "get_order_status",
                '{"order_id": "ORD-123", "admin": "true"}',
            )

    def test_rejects_non_string_argument(self):
        with self.assertRaisesRegex(ValueError, "must be a string"):
            parse_and_validate_tool_arguments(
                "get_order_status",
                '{"order_id": 123}',
            )

    def test_rejects_empty_argument(self):
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            parse_and_validate_tool_arguments(
                "get_return_policy",
                '{"product_category": "   "}',
            )

    def test_rejects_tool_without_argument_specification(self):
        with self.assertRaisesRegex(ValueError, "No argument specification"):
            parse_and_validate_tool_arguments("unknown_tool", "{}")


class ToolCallSignatureTests(unittest.TestCase):
    def test_signature_is_stable_across_argument_order(self):
        first = create_tool_call_signature(
            "example_tool",
            {"order_id": "ORD-123", "region": "US"},
        )
        second = create_tool_call_signature(
            "example_tool",
            {"region": "US", "order_id": "ORD-123"},
        )
        self.assertEqual(first, second)


class AgentLoopTests(unittest.TestCase):
    def test_completes_when_model_returns_no_tool_calls(self):
        client = FakeClient([fake_response(content="No tool is needed.")])

        result = run_agent_loop(client, initial_messages())

        self.assertEqual(result["status"], COMPLETED)
        self.assertEqual(result["final_answer"], "No tool is needed.")
        self.assertEqual(result["model_rounds"], 1)
        self.assertEqual(result["tool_calls"], 0)

    def test_executes_one_tool_then_completes(self):
        client = FakeClient(
            [
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "call-1",
                            "get_order_status",
                            {"order_id": "ORD-123"},
                        )
                    ]
                ),
                fake_response(content="The order arrives tomorrow."),
            ]
        )

        result = run_agent_loop(client, initial_messages())

        self.assertEqual(result["status"], COMPLETED)
        self.assertEqual(result["model_rounds"], 2)
        self.assertEqual(result["tool_calls"], 1)

    def test_executes_different_tools_across_multiple_rounds(self):
        client = FakeClient(
            [
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "call-1",
                            "get_order_status",
                            {"order_id": "ORD-123"},
                        )
                    ]
                ),
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "call-2",
                            "get_return_policy",
                            {"product_category": "electronics"},
                        )
                    ]
                ),
                fake_response(content="The item is still returnable."),
            ]
        )

        result = run_agent_loop(client, initial_messages())

        self.assertEqual(result["status"], COMPLETED)
        self.assertEqual(result["model_rounds"], 3)
        self.assertEqual(result["tool_calls"], 2)
        executed_events = [
            event for event in result["trace"] if event["event"] == "tool_executed"
        ]
        self.assertEqual(
            [event["tool_name"] for event in executed_events],
            ["get_order_status", "get_return_policy"],
        )

    def test_stops_repeated_call_before_second_execution(self):
        tracked_tool = Mock(return_value="Order found")
        repeated_call = lambda call_id: fake_tool_call(
            call_id,
            "get_order_status",
            {"order_id": "ORD-123"},
        )
        client = FakeClient(
            [
                fake_response(tool_calls=[repeated_call("call-1")]),
                fake_response(tool_calls=[repeated_call("call-2")]),
            ]
        )

        with patch.dict(TOOL_REGISTRY, {"get_order_status": tracked_tool}):
            result = run_agent_loop(client, initial_messages())

        self.assertEqual(result["status"], REPEATED_TOOL_CALL)
        self.assertEqual(result["tool_calls"], 1)
        tracked_tool.assert_called_once_with(order_id="ORD-123")

    def test_stops_after_maximum_model_rounds(self):
        client = FakeClient(
            [
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "call-1",
                            "get_order_status",
                            {"order_id": "ORD-123"},
                        )
                    ]
                )
            ]
        )

        result = run_agent_loop(
            client,
            initial_messages(),
            max_model_rounds=1,
        )

        self.assertEqual(result["status"], MAX_MODEL_ROUNDS_REACHED)
        self.assertEqual(result["model_rounds"], 1)
        self.assertEqual(result["tool_calls"], 1)

    def test_stops_before_exceeding_maximum_tool_calls(self):
        client = FakeClient(
            [
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "call-1",
                            "get_order_status",
                            {"order_id": "ORD-123"},
                        ),
                        fake_tool_call(
                            "call-2",
                            "get_return_policy",
                            {"product_category": "electronics"},
                        ),
                    ]
                )
            ]
        )

        result = run_agent_loop(
            client,
            initial_messages(),
            max_tool_calls=1,
        )

        self.assertEqual(result["status"], MAX_TOOL_CALLS_REACHED)
        self.assertEqual(result["tool_calls"], 1)

    def test_rejects_unknown_tool_without_execution(self):
        client = FakeClient(
            [
                fake_response(
                    tool_calls=[
                        fake_tool_call("call-1", "delete_database", {})
                    ]
                )
            ]
        )

        result = run_agent_loop(client, initial_messages())

        self.assertEqual(result["status"], INVALID_TOOL_CALL)
        self.assertEqual(result["tool_calls"], 0)

    def test_rejects_malformed_arguments_without_execution(self):
        tracked_tool = Mock(return_value="Order found")
        client = FakeClient(
            [
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "call-1",
                            "get_order_status",
                            '{"order_id": }',
                        )
                    ]
                )
            ]
        )

        with patch.dict(TOOL_REGISTRY, {"get_order_status": tracked_tool}):
            result = run_agent_loop(client, initial_messages())

        self.assertEqual(result["status"], INVALID_TOOL_CALL)
        self.assertEqual(result["tool_calls"], 0)
        tracked_tool.assert_not_called()

    def test_converts_tool_exception_to_explicit_stop_state(self):
        failing_tool = Mock(side_effect=TimeoutError("provider timed out"))
        client = FakeClient(
            [
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "call-1",
                            "get_order_status",
                            {"order_id": "ORD-123"},
                        )
                    ]
                )
            ]
        )

        with patch.dict(TOOL_REGISTRY, {"get_order_status": failing_tool}):
            result = run_agent_loop(client, initial_messages())

        self.assertEqual(result["status"], TOOL_EXECUTION_FAILED)
        self.assertEqual(result["tool_calls"], 0)
        self.assertIn("TimeoutError", result["trace"][-2]["error"])

    def test_sends_tool_definitions_on_every_model_round(self):
        client = FakeClient(
            [
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "call-1",
                            "get_order_status",
                            {"order_id": "ORD-123"},
                        )
                    ]
                ),
                fake_response(content="Done."),
            ]
        )

        run_agent_loop(client, initial_messages())

        self.assertEqual(len(client.chat.completions.requests), 2)
        for request in client.chat.completions.requests:
            self.assertEqual(request["tools"], TOOL_DEFINITIONS)

    def test_rejects_non_positive_limits(self):
        client = FakeClient([])

        with self.assertRaisesRegex(ValueError, "max_model_rounds"):
            run_agent_loop(client, initial_messages(), max_model_rounds=0)

        with self.assertRaisesRegex(ValueError, "max_tool_calls"):
            run_agent_loop(client, initial_messages(), max_tool_calls=0)


if __name__ == "__main__":
    unittest.main()
