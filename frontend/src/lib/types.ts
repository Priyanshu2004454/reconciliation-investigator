// Mirrors backend/app/schemas/*.py — keep these in sync with the API contracts.

export interface User {
  id: string;
  email: string;
  full_name: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface MerchantAccount {
  id: string;
  business_name: string;
  razorpay_key_id: string;
  is_test_mode: boolean;
}

export interface SyncResult {
  source: string;
  fetched: number;
  created: number;
  updated: number;
  skipped: number;
  errors: string[];
  duration_ms: number;
}

export interface DemoSeedResponse {
  merchant_account_id: string;
  records_created: number;
  records_existing: number;
  payments_count: number;
  settlements_count: number;
  refunds_count: number;
  bank_transactions_count: number;
  total_records: number;
  counts: Record<string, number>;
}

export interface BankRowError {
  row_number: number;
  reason: string;
  raw_row: Record<string, unknown>;
}

export interface ImportSummary {
  import_batch_id: string;
  filename: string;
  total_rows: number;
  rows_imported: number;
  rows_rejected: number;
  rows_duplicated: number;
  rows_requiring_review: number;
  detected_columns: Record<string, string>;
  errors: BankRowError[];
}

export type ReconciliationStatus =
  | "MATCHED"
  | "EXPLAINED"
  | "NEEDS_REVIEW"
  | "FALSE_POSITIVE"
  | "RESOLVED";

export interface ReconciliationRunSummary {
  run_id: string;
  status: string;
  total_transactions: number;
  matched: number;
  explained: number;
  needs_review: number;
}

export interface ReconciliationCaseListItem {
  id: string;
  razorpay_settlement_id: string | null;
  status: ReconciliationStatus;
  match_rule: string | null;
  expected_amount: number | null;
  actual_amount: number | null;
  difference: number | null;
  updated_at: string;
}

export interface SettlementEvidence {
  utr: string | null;
  amount: number | null;
  fees: number | null;
  tax: number | null;
  status: string | null;
  settlement_date: string | null;
}

export interface PaymentEvidence {
  amount: number | null;
  fee: number | null;
  tax: number | null;
  method: string | null;
  status: string | null;
  payment_date: string | null;
}

export interface BankTxnEvidence {
  utr: string | null;
  reference_id: string | null;
  credit: number | null;
  debit: number | null;
  transaction_date: string | null;
  description: string | null;
}

export interface RefundEvidence {
  id: string;
  razorpay_refund_id: string;
  amount: number;
  status: string;
  refund_date: string | null;
}

export interface ReconciliationCaseDetail extends ReconciliationCaseListItem {
  razorpay_payment_id: string | null;
  bank_transaction_id: string | null;
  created_at: string;
  settlement_details?: SettlementEvidence | null;
  payment_details?: PaymentEvidence | null;
  bank_transaction_details?: BankTxnEvidence | null;
  refunds?: RefundEvidence[];
}

export interface EvidenceItem {
  source_type: string;
  source_id: string;
  description: string;
}

export type RootCause =
  | "FEE_TAX"
  | "REFUND"
  | "MISSING_BANK_CREDIT"
  | "DUPLICATE"
  | "TIMING_DIFFERENCE"
  | "AMOUNT_MISMATCH"
  | "UNKNOWN";

export type HumanDecision = "RESOLVED" | "NEEDS_REVIEW" | "REJECTED";

export interface Investigation {
  id: string;
  case_id: string;
  classification: ReconciliationStatus;
  root_cause: RootCause;
  explanation: string;
  confidence: number;
  recommended_action: string;
  requires_human_review: boolean;
  human_decision: HumanDecision | null;
  human_notes?: string | null;
  evidence: EvidenceItem[];
  created_at: string;
}

export interface DashboardSummary {
  total_transactions: number;
  processed_value: number;
  total_settlements: number;
  matched_count: number;
  explained_count: number;
  needs_review_count: number;
  reconciliation_rate: number;
  amount_requiring_investigation: number;
  last_run_at: string | null;
  last_run_status: string | null;
}

export interface RecentActivityItem {
  case_id: string;
  razorpay_settlement_id: string | null;
  status: ReconciliationStatus;
  root_cause: string | null;
  amount: number | null;
  updated_at: string;
}

export interface MismatchCategoryBreakdown {
  category: string;
  count: number;
  total_amount: number;
}

export interface AuditLogEntry {
  id: string;
  case_id: string | null;
  actor_type: "AI" | "HUMAN" | "SYSTEM";
  actor_id: string | null;
  action: string;
  previous_state: Record<string, unknown> | null;
  new_state: Record<string, unknown> | null;
  reason: string | null;
  created_at: string;
}

export interface ReconciliationRun {
  id: string;
  status: string;
  total_records: number;
  matched_records: number;
  explained_records: number;
  unresolved_records: number;
  failed_records: number;
  total_amount: number;
  matched_amount: number;
  unresolved_amount: number;
  match_rate: number;
  started_at: string;
  completed_at: string | null;
}

export interface ExceptionCase {
  case_id: string;
  razorpay_payment_id: string | null;
  razorpay_settlement_id: string | null;
  amount: number | null;
  status: string;
  mismatch_type: string | null;
  confidence: number | null;
  recommended_action: string | null;
  created_at: string;
}

export interface HealthCheck {
  status: string;
  app_env: string;
  config: {
    APP_ENV: string;
    API_V1_PREFIX: string;
    RAZORPAY_KEY_ID: string;
    RAZORPAY_KEY_SECRET: string;
    ANTHROPIC_API_KEY: string;
    GEMINI_API_KEY?: string;
    AI_PROVIDER?: string;
    JWT_SECRET_KEY: string;
    AI_MODEL: string;
    MATCH_DATE_WINDOW_DAYS: number;
  };
}
