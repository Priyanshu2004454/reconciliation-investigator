# Reconciliation Investigator

AI-powered financial reconciliation investigator for Razorpay merchants —
built for the Razorpay AI Buildathon 2026 (AI Finance Controller track).

> Don't just show me a mismatch. Find out WHY it happened.

## Status

Currently implemented (Phases 1–5 of the build plan):

- [x] **Phase 1** — Project scaffold, backend config, database schema (13 tables), migrations setup
- [x] **Phase 2** — Razorpay Test Mode service layer (payments/orders/settlements/refunds), pagination, retries, normalization
- [x] **Phase 3** — Bank statement CSV import: column auto-detection, duplicate/malformed row handling
- [x] **Phase 4** — Deterministic reconciliation engine (Rules 1–6), zero AI involvement, all 6 spec example cases passing
- [x] **Phase 5** — DB persistence for reconciliation runs/cases, full audit trail, dashboard aggregation queries

Not yet built:

- [ ] Phase 6 — AI Investigator (tool calling, structured output, evidence, confidence)
- [ ] Phase 7 — Dashboard frontend (Next.js)
- [ ] Phase 8 — Webhooks
- [ ] Phase 9+ — Testing polish, demo data, README completion

## Quick start

```bash
docker compose up -d               # starts local Postgres
cd backend
pip install -r requirements.txt
cp .env.example .env               # fill in your own values — never commit this file
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/health` to confirm the backend is running.

## Running tests

```bash
cd backend
pip install -r requirements.txt
pytest -v
```

All service-layer logic (Razorpay integration, CSV parsing, reconciliation
engine) is unit-tested without needing real Razorpay credentials or a live
database — see `backend/tests/`.

## Architecture

```
Merchant → Next.js Frontend → FastAPI Backend → Razorpay API
                                     ↓
                              Webhook Processor
                                     ↓
                               PostgreSQL
                                     ↓
                          Reconciliation Engine (deterministic)
                                     ↓
                            AI Investigator (Claude)
                                     ↓
                       Investigation + Audit Log
```

## Security notes

- `RAZORPAY_KEY_SECRET` and `ANTHROPIC_API_KEY` are read only from environment
  variables and are never persisted to the database or returned in any API response.
- `.env` is git-ignored; only `.env.example` (placeholder values) is committed.
