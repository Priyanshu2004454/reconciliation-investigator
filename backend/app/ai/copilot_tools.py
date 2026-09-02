"""
AI Copilot tools -- read-only, merchant-scoped database queries the Copilot
can call to ground its answers in real data. This intentionally reuses the
same models the reconciliation engine and Investigator already use (no
duplicated database logic), and follows the exact same architectural
pattern as app/ai/tools.py + app/ai/db_data_store.py: every tool is scoped
to one merchant_account_id, so the Copilot can never see another
merchant's data even if it tries.

Every tool result is tracked as a "source" by the orchestrator (app/ai/copilot.py)
so the frontend can show a small evidence chip (e.g. "Source: Case #0091") --
the Copilot is never allowed to state a financial fact that didn't come from
one of these tool calls.
"""

import uuid
from typing import Any, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reconciliation import ReconciliationCase, ReconciliationRun, Investigation
from app.models.financial import RazorpaySettlement

COPILOT_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "search_cases",
        "description": (
            "Search reconciliation cases for this merchant. Returns cases sorted by the size of "
            "their financial difference (largest first) by default -- useful for 'what needs "
            "attention', 'biggest mismatch', or 'cases above amount X' questions. "
            "Always use this instead of guessing which cases exist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["MATCHED", "EXPLAINED", "NEEDS_REVIEW", "RESOLVED", "FALSE_POSITIVE"],
                    "description": "Filter by case status. Omit to search all statuses.",
                },
                "min_amount": {"type": "number", "description": "Only cases with actual_amount >= this value."},
                "limit": {"type": "integer", "description": "Max results, default 10, max 25."},
            },
        },
    },
    {
        "name": "get_case",
        "description": "Fetch full detail for one reconciliation case, including its latest AI investigation if one exists.",
        "input_schema": {
            "type": "object",
            "properties": {"case_id": {"type": "string", "description": "The reconciliation case UUID."}},
            "required": ["case_id"],
        },
    },
    {
        "name": "list_runs",
        "description": "List recent reconciliation batch runs with their match rates and record counts.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max results, default 5."}},
        },
    },
    {
        "name": "get_dashboard_summary",
        "description": "Fetch current aggregate reconciliation metrics for this merchant (totals, match rate, amounts).",
        "input_schema": {"type": "object", "properties": {}},
    },
]


class CopilotDataStore:
    """Merchant-scoped, read-only. See module docstring."""

    def __init__(self, db: AsyncSession, merchant_account_id: uuid.UUID):
        self.db = db
        self.merchant_account_id = merchant_account_id

    async def search_cases(
        self, status: Optional[str] = None, min_amount: Optional[float] = None, limit: int = 10,
    ) -> list[dict]:
        limit = max(1, min(limit or 10, 25))
        stmt = select(ReconciliationCase).where(ReconciliationCase.merchant_account_id == self.merchant_account_id)
        if status:
            stmt = stmt.where(ReconciliationCase.status == status)
        if min_amount is not None:
            stmt = stmt.where(ReconciliationCase.actual_amount >= min_amount)
        stmt = stmt.order_by(func.abs(ReconciliationCase.difference).desc().nulls_last()).limit(limit)

        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            {
                "case_id": str(r.id),
                "razorpay_settlement_id": r.razorpay_settlement_id,
                "status": r.status,
                "match_rule": r.match_rule,
                "actual_amount": float(r.actual_amount) if r.actual_amount is not None else None,
                "difference": float(r.difference) if r.difference is not None else None,
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rows
        ]

    async def get_case(self, case_id: str) -> Optional[dict]:
        try:
            case_uuid = uuid.UUID(case_id)
        except ValueError:
            return None
        case = (
            await self.db.execute(
                select(ReconciliationCase).where(
                    ReconciliationCase.id == case_uuid,
                    ReconciliationCase.merchant_account_id == self.merchant_account_id,
                )
            )
        ).scalar_one_or_none()
        if case is None:
            return None

        investigation = (
            await self.db.execute(
                select(Investigation)
                .where(Investigation.case_id == case_uuid)
                .order_by(Investigation.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        utr = None
        if case.razorpay_settlement_id:
            settlement = (
                await self.db.execute(
                    select(RazorpaySettlement).where(
                        RazorpaySettlement.razorpay_settlement_id == case.razorpay_settlement_id,
                        RazorpaySettlement.merchant_account_id == self.merchant_account_id,
                    )
                )
            ).scalar_one_or_none()
            utr = settlement.utr if settlement else None

        return {
            "case_id": str(case.id),
            "razorpay_settlement_id": case.razorpay_settlement_id,
            "razorpay_payment_id": case.razorpay_payment_id,
            "utr": utr,
            "status": case.status,
            "match_rule": case.match_rule,
            "expected_amount": float(case.expected_amount) if case.expected_amount is not None else None,
            "actual_amount": float(case.actual_amount) if case.actual_amount is not None else None,
            "difference": float(case.difference) if case.difference is not None else None,
            "investigation": (
                {
                    "classification": investigation.classification,
                    "root_cause": investigation.root_cause,
                    "confidence": investigation.confidence,
                    "recommended_action": investigation.recommended_action,
                    "human_decision": investigation.human_decision,
                }
                if investigation
                else None
            ),
        }

    async def list_runs(self, limit: int = 5) -> list[dict]:
        limit = max(1, min(limit or 5, 20))
        rows = (
            await self.db.execute(
                select(ReconciliationRun)
                .where(ReconciliationRun.merchant_account_id == self.merchant_account_id)
                .order_by(ReconciliationRun.started_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "run_id": str(r.id),
                "status": r.status,
                "total_records": r.total_transactions,
                "matched": r.matched_count,
                "explained": r.explained_count,
                "needs_review": r.needs_review_count,
                "match_rate": float(r.match_rate or 0),
                "started_at": r.started_at.isoformat(),
            }
            for r in rows
        ]

    async def get_dashboard_summary(self) -> dict:
        from app.services import dashboard_service
        summary = await dashboard_service.get_dashboard_summary(self.db, self.merchant_account_id)
        return summary.model_dump(mode="json")


class CopilotToolExecutionError(Exception):
    pass


async def execute_copilot_tool(name: str, tool_input: dict, store: CopilotDataStore) -> dict:
    if name == "search_cases":
        results = await store.search_cases(
            status=tool_input.get("status"), min_amount=tool_input.get("min_amount"), limit=tool_input.get("limit", 10),
        )
        return {"count": len(results), "cases": results}

    if name == "get_case":
        case_id = tool_input.get("case_id", "")
        if not case_id:
            raise CopilotToolExecutionError("case_id is required")
        result = await store.get_case(case_id)
        return {"found": result is not None, "case": result}

    if name == "list_runs":
        results = await store.list_runs(limit=tool_input.get("limit", 5))
        return {"count": len(results), "runs": results}

    if name == "get_dashboard_summary":
        return await store.get_dashboard_summary()

    raise CopilotToolExecutionError(f"Unknown tool: {name}")
