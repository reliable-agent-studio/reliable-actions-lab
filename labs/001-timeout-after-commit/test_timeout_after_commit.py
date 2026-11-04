import unittest

from fake_refund_provider import FakeRefundProvider, IdempotencyConflictError


def issue_refund_with_naive_retry(
    provider: FakeRefundProvider,
    order_id: str,
    amount_cents: int,
):
    """Retry once because a timeout is incorrectly treated as a failed refund."""
    try:
        return provider.issue_refund(
            order_id=order_id,
            amount_cents=amount_cents,
            lose_response_after_commit=True,
        )
    except TimeoutError:
        return provider.issue_refund(
            order_id=order_id,
            amount_cents=amount_cents,
        )


def issue_refund_with_idempotent_retry(
    provider: FakeRefundProvider,
    order_id: str,
    amount_cents: int,
    idempotency_key: str,
):
    """Retry once with the same identity for the same business action."""
    try:
        return provider.issue_refund(
            order_id=order_id,
            amount_cents=amount_cents,
            idempotency_key=idempotency_key,
            lose_response_after_commit=True,
        )
    except TimeoutError:
        return provider.issue_refund(
            order_id=order_id,
            amount_cents=amount_cents,
            idempotency_key=idempotency_key,
        )


class TimeoutAfterCommitTests(unittest.TestCase):
    def test_naive_retry_reproduces_duplicate_refund(self) -> None:
        provider = FakeRefundProvider()

        retry_result = issue_refund_with_naive_retry(
            provider=provider,
            order_id="ORD-123",
            amount_cents=1000,
        )

        # The caller sees only the retry result and may report success.
        self.assertEqual(retry_result["refund_id"], "refund-2")

        # The business invariant requires one refund, but two were committed.
        self.assertEqual(len(provider.refunds), 2)
        self.assertEqual(
            [refund["refund_id"] for refund in provider.refunds],
            ["refund-1", "refund-2"],
        )
        self.assertEqual(
            sum(refund["amount_cents"] for refund in provider.refunds),
            2000,
        )

        self.assertEqual(
            [event["event"] for event in provider.events],
            [
                "refund_committed",
                "response_lost",
                "refund_committed",
                "response_returned",
            ],
        )

    def test_stable_idempotency_key_prevents_duplicate_refund(self) -> None:
        provider = FakeRefundProvider()

        retry_result = issue_refund_with_idempotent_retry(
            provider=provider,
            order_id="ORD-123",
            amount_cents=1000,
            idempotency_key="refund:ORD-123:1000:v1",
        )

        self.assertEqual(retry_result["refund_id"], "refund-1")
        self.assertEqual(len(provider.refunds), 1)
        self.assertEqual(provider.refunds[0]["amount_cents"], 1000)
        self.assertEqual(
            [event["event"] for event in provider.events],
            [
                "refund_committed",
                "response_lost",
                "idempotency_replay",
                "response_returned",
            ],
        )

    def test_idempotency_key_is_bound_to_refund_arguments(self) -> None:
        provider = FakeRefundProvider()
        idempotency_key = "refund:ORD-123:1000:v1"

        provider.issue_refund(
            order_id="ORD-123",
            amount_cents=1000,
            idempotency_key=idempotency_key,
        )

        with self.assertRaisesRegex(
            IdempotencyConflictError,
            "different refund",
        ):
            provider.issue_refund(
                order_id="ORD-123",
                amount_cents=2000,
                idempotency_key=idempotency_key,
            )

        self.assertEqual(len(provider.refunds), 1)
        self.assertEqual(provider.events[-1]["event"], "idempotency_conflict")

    def test_different_idempotency_keys_represent_different_actions(self) -> None:
        provider = FakeRefundProvider()

        first = provider.issue_refund(
            order_id="ORD-123",
            amount_cents=1000,
            idempotency_key="refund:ORD-123:1000:v1",
        )
        second = provider.issue_refund(
            order_id="ORD-123",
            amount_cents=1000,
            idempotency_key="refund:ORD-123:1000:v2",
        )

        self.assertNotEqual(first["refund_id"], second["refund_id"])
        self.assertEqual(len(provider.refunds), 2)


if __name__ == "__main__":
    unittest.main()
