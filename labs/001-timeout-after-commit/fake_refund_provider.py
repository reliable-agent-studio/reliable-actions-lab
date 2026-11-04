from typing import Any, Dict, List, Optional


class IdempotencyConflictError(ValueError):
    """Raised when one idempotency key is reused for a different action."""


class FakeRefundProvider:
    """A deterministic local provider for refund failure experiments."""

    def __init__(self) -> None:
        self.refunds: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self.refunds_by_idempotency_key: Dict[str, Dict[str, Any]] = {}

    def issue_refund(
        self,
        order_id: str,
        amount_cents: int,
        lose_response_after_commit: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Commit a refund, optionally losing the response after the commit."""
        if idempotency_key is not None and not idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")

        if idempotency_key is not None:
            existing_refund = self.refunds_by_idempotency_key.get(idempotency_key)
            if existing_refund is not None:
                same_action = (
                    existing_refund["order_id"] == order_id
                    and existing_refund["amount_cents"] == amount_cents
                )
                if not same_action:
                    self.events.append(
                        {
                            "event": "idempotency_conflict",
                            "idempotency_key": idempotency_key,
                            "refund_id": existing_refund["refund_id"],
                        }
                    )
                    raise IdempotencyConflictError(
                        "Idempotency key is already bound to a different refund"
                    )

                self.events.append(
                    {
                        "event": "idempotency_replay",
                        "idempotency_key": idempotency_key,
                        "refund_id": existing_refund["refund_id"],
                    }
                )
                self.events.append(
                    {
                        "event": "response_returned",
                        "refund_id": existing_refund["refund_id"],
                    }
                )
                return existing_refund.copy()

        refund = {
            "refund_id": f"refund-{len(self.refunds) + 1}",
            "order_id": order_id,
            "amount_cents": amount_cents,
            "idempotency_key": idempotency_key,
        }

        # This append represents the external provider's irreversible commit.
        self.refunds.append(refund)
        if idempotency_key is not None:
            # The fixture records the key before response loss. A production
            # system must make the action and key binding durable together.
            self.refunds_by_idempotency_key[idempotency_key] = refund
        self.events.append(
            {
                "event": "refund_committed",
                "refund_id": refund["refund_id"],
                "idempotency_key": idempotency_key,
            }
        )

        if lose_response_after_commit:
            self.events.append(
                {
                    "event": "response_lost",
                    "refund_id": refund["refund_id"],
                }
            )
            raise TimeoutError(
                "Refund committed, but the success response was lost"
            )

        self.events.append(
            {
                "event": "response_returned",
                "refund_id": refund["refund_id"],
            }
        )
        return refund.copy()
