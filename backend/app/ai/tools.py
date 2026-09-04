from typing import Any

from app.ai.data_store import InvestigationDataStore

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "get_payment",
        "description": "Fetch a single Razorpay payment by its ID. Returns null if it doesn't exist.",
        "input_schema": {
            "type": "object",
            "properties": {"payment_id": {"type": "string", "description": "Razorpay payment ID, e.g. pay_ABC123"}},
            "required": ["payment_id"],
        },
    },
    {
        "name": "get_settlement",
        "description": "Fetch a single Razorpay settlement by its ID. Returns null if it doesn't exist.",
        "input_schema": {
            "type": "object",
            "properties": {"settlement_id": {"type": "string", "description": "Razorpay settlement ID, e.g. setl_ABC123"}},
            "required": ["settlement_id"],
        },
    },
    {
        "name": "get_refunds",
        "description": "Fetch all refunds issued against a payment. Returns an empty list if none exist.",
        "input_schema": {
            "type": "object",
            "properties": {"payment_id": {"type": "string"}},
            "required": ["payment_id"],
        },
    },
    {
        "name": "search_bank_transactions",
        "description": (
            "Search the merchant's uploaded bank statement for matching rows. "
            "At least one of utr, reference_id, or amount should be provided. "
            "Returns an empty list if nothing matches — this is a valid, meaningful result, "
            "not an error, and often IS the finding (e.g. 'no matching bank credit')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "utr": {"type": "string"},
                "reference_id": {"type": "string"},
                "amount": {"type": "number"},
                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
            },
        },
    },
    {
        "name": "get_reconciliation_case",
        "description": "Fetch the reconciliation case under investigation, including linked payment/settlement IDs.",
        "input_schema": {
            "type": "object",
            "properties": {"case_id": {"type": "string"}},
            "required": ["case_id"],
        },
    },
    {
        "name": "calculate_expected_settlement",
        "description": (
            "Deterministically calculates the expected settlement amount for a case "
            "(gross payment minus fees, tax, and refunds). Always use this instead of "
            "doing the arithmetic yourself — it is the same engine that produced the "
            "case in the first place."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"case_id": {"type": "string"}},
            "required": ["case_id"],
        },
    },
    {
        "name": "mark_case_for_review",
        "description": (
            "Flags this case as requiring mandatory human review, with a reason. "
            "Use this when evidence is insufficient or contradictory — never guess instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["case_id", "reason"],
        },
    },
]

_MUTATING_TOOLS = {"mark_case_for_review"}


class ToolExecutionError(Exception):
    pass


async def execute_tool(
    name: str, tool_input: dict, store: InvestigationDataStore, allowed_case_id: str,
) -> dict:
    """
    Dispatches a tool call. `allowed_case_id` scopes mutating tools (currently
    just mark_case_for_review) to the case this investigation was actually
    launched for — the AI cannot flag or touch an unrelated case even if it
    hallucinates a different case_id.
    """
    if name in _MUTATING_TOOLS:
        case_id = tool_input.get("case_id")
        if case_id != allowed_case_id:
            raise ToolExecutionError(
                f"Tool '{name}' attempted to act on case_id='{case_id}', but this "
                f"investigation is scoped to case_id='{allowed_case_id}'. Rejected."
            )

    if name == "get_payment":
        payment_id = tool_input.get("payment_id", "")
        if not payment_id:
            raise ToolExecutionError("payment_id is required")
        result = await store.get_payment(payment_id)
        return {"found": result is not None, "payment": result}

    if name == "get_settlement":
        settlement_id = tool_input.get("settlement_id", "")
        if not settlement_id:
            raise ToolExecutionError("settlement_id is required")
        result = await store.get_settlement(settlement_id)
        return {"found": result is not None, "settlement": result}

    if name == "get_refunds":
        payment_id = tool_input.get("payment_id", "")
        if not payment_id:
            raise ToolExecutionError("payment_id is required")
        result = await store.get_refunds(payment_id)
        return {"count": len(result), "refunds": result}

    if name == "search_bank_transactions":
        result = await store.search_bank_transactions(
            utr=tool_input.get("utr"),
            reference_id=tool_input.get("reference_id"),
            amount=tool_input.get("amount"),
            date_from=tool_input.get("date_from"),
            date_to=tool_input.get("date_to"),
        )
        return {"count": len(result), "matches": result}

    if name == "get_reconciliation_case":
        case_id = tool_input.get("case_id", "")
        if not case_id:
            raise ToolExecutionError("case_id is required")
        result = await store.get_reconciliation_case(case_id)
        return {"found": result is not None, "case": result}

    if name == "calculate_expected_settlement":
        case_id = tool_input.get("case_id", "")
        if not case_id:
            raise ToolExecutionError("case_id is required")
        result = await store.calculate_expected_settlement(case_id)
        return {"expected_settlement": result}

    if name == "mark_case_for_review":
        reason = tool_input.get("reason", "")
        if not reason:
            raise ToolExecutionError("reason is required")
        ok = await store.mark_case_for_review(tool_input["case_id"], reason)
        return {"success": ok}

    raise ToolExecutionError(f"Unknown tool: {name}")
