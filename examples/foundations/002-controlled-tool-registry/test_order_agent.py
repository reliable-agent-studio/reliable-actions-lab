import unittest

from order_agent_deepseek import parse_and_validate_tool_arguments


class ToolArgumentValidationTests(unittest.TestCase):
    def test_accepts_valid_order_arguments(self) -> None:
        arguments = parse_and_validate_tool_arguments(
            "get_order_status",
            '{"order_id": "ORD-123"}',
        )

        self.assertEqual(arguments, {"order_id": "ORD-123"})

    def test_accepts_valid_return_policy_arguments(self) -> None:
        arguments = parse_and_validate_tool_arguments(
            "get_return_policy",
            '{"product_category": "electronics"}',
        )

        self.assertEqual(arguments, {"product_category": "electronics"})

    def test_rejects_invalid_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid JSON"):
            parse_and_validate_tool_arguments(
                "get_order_status",
                '{"order_id": }',
            )

    def test_rejects_non_object_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be a JSON object"):
            parse_and_validate_tool_arguments(
                "get_order_status",
                '["ORD-123"]',
            )

    def test_rejects_missing_argument(self) -> None:
        with self.assertRaisesRegex(ValueError, "Missing arguments"):
            parse_and_validate_tool_arguments("get_order_status", "{}")

    def test_rejects_unexpected_argument(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unexpected arguments"):
            parse_and_validate_tool_arguments(
                "get_order_status",
                '{"order_id": "ORD-123", "admin": "true"}',
            )

    def test_rejects_non_string_argument(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be a string"):
            parse_and_validate_tool_arguments(
                "get_order_status",
                '{"order_id": 123}',
            )

    def test_rejects_empty_argument(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            parse_and_validate_tool_arguments(
                "get_return_policy",
                '{"product_category": "   "}',
            )

    def test_rejects_tool_without_argument_specification(self) -> None:
        with self.assertRaisesRegex(ValueError, "No argument specification"):
            parse_and_validate_tool_arguments("unknown_tool", "{}")


if __name__ == "__main__":
    unittest.main()
