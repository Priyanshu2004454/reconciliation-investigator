# Reconciliation Investigator — Frontend

Next.js (App Router, TypeScript, Tailwind v4) frontend for the Reconciliation
Investigator backend. See the root README for the full project.

## Setup

```bash
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL if backend isn't on localhost:8000
npm run dev
```

Open http://localhost:3000. The backend must be running — every page here
calls real API endpoints, nothing is mocked.

## Pages

| Route | Purpose |
|---|---|
| /login | Register / sign in (JWT stored client-side) |
| /dashboard | Summary cards, recent activity, mismatch breakdown |
| /reconciliation | Case list with status filters, Sync Razorpay + Run Reconciliation actions |
| /reconciliation/[caseId] | Case detail: transaction/settlement/bank fields, AI investigation, evidence, human decision |
| /bank-statements | CSV upload with import summary and column-mapping display |
| /audit-log | Immutable timeline of every AI/human/system action |
| /settings | Backend/AI connection status, Razorpay merchant account setup |

## Notes

- Auth token lives in localStorage (this is a normal deployed web app, not
  a sandboxed artifact -- standard JWT storage applies).
- src/lib/api.ts is the single place that talks to the backend; src/lib/types.ts
  mirrors the backend's Pydantic schemas field-for-field.
- No mocked API responses -- every page either shows real data or an empty/error state.

## Build

```bash
npm run build   # type-checks + production build
npm run lint
```
