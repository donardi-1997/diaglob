"""AI prompt grounding tests for customer order context."""

from app import ai_generation


class FakeRuntime:
    def __init__(self):
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "usage": {
                "inputTokens": 10,
                "outputTokens": 5,
                "totalTokens": 15,
            },
            "output": {
                "message": {
                    "content": [
                        {"text": "Your order is out for delivery."}
                    ]
                }
            },
        }


def test_order_context_is_sufficient_grounding_without_rag(monkeypatch):
    runtime = FakeRuntime()
    monkeypatch.setattr(
        ai_generation,
        "get_bedrock_runtime",
        lambda: runtime,
    )

    result = ai_generation.generate_grounded_answer(
        question="Where is my order?",
        evidence=[],
        agent_name="Support",
        agent_role="Customer support",
        language="en",
        commerce_results=[],
        order_context={
            "requested": True,
            "orders": [
                {
                    "order_number": "#1002",
                    "financial_status": "paid",
                    "payment_status": None,
                    "fulfillment_status": "fulfilled",
                    "lifecycle_status": None,
                    "supplier_status": "SHIPPED",
                    "supplier_substatus": None,
                    "shipment": {
                        "status": "OUT_FOR_DELIVERY",
                        "tracking_number": "TRACK-1002",
                        "carrier": "USPS",
                        "delivery_time": None,
                        "delivered_at": None,
                        "last_event_at": "2026-09-24T09:00:00Z",
                        "events": [
                            {
                                "status": "OUT_FOR_DELIVERY",
                                "description": "Out for delivery",
                                "location": "New York, NY",
                                "event_at": "2026-09-24T09:00:00Z",
                            }
                        ],
                    },
                }
            ],
        },
    )

    assert result["answer"] == "Your order is out for delivery."
    prompt = runtime.calls[0]["messages"][0]["content"][0]["text"]
    assert "#1002" in prompt
    assert "TRACK-1002" in prompt
    assert "USPS" in prompt
    assert "Nunca inventes" in prompt


def test_empty_order_result_reaches_model_instead_of_generic_rag_fallback(
    monkeypatch,
):
    runtime = FakeRuntime()
    monkeypatch.setattr(
        ai_generation,
        "get_bedrock_runtime",
        lambda: runtime,
    )

    ai_generation.generate_grounded_answer(
        question="Where is my order?",
        evidence=[],
        agent_name="Support",
        agent_role="Customer support",
        language="en",
        commerce_results=[],
        order_context={
            "requested": True,
            "orders": [],
        },
    )

    assert len(runtime.calls) == 1
    prompt = runtime.calls[0]["messages"][0]["content"][0]["text"]
    assert "No se encontraron pedidos" in prompt
