import type {
  AuditLogEntry,
  CopilotChatResponse,
  DashboardSummary,
  DemoSeedResponse,
  ExceptionCase,
  HealthCheck,
  ImportSummary,
  Investigation,
  MerchantAccount,
  MismatchCategoryBreakdown,
  ReconciliationCaseDetail,
  ReconciliationCaseListItem,
  ReconciliationRun,
  ReconciliationRunSummary,
  RecentActivityItem,
  SyncResult,
  TokenResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_V1 = `${API_BASE}/api/v1`;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("ri_token");
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem("ri_token", token);
  else localStorage.removeItem("ri_token");
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  { auth = true, isForm = false }: { auth?: boolean; isForm?: boolean } = {}
): Promise<T> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string>) };
  if (!isForm) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_V1}${path}`, { ...options, headers });

  if (res.status === 204) return undefined as T;

  const contentType = res.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json") ? await res.json() : await res.text();

  if (!res.ok) {
    const rawDetail = typeof body === "object" && body !== null && "detail" in body
      ? (body as { detail: unknown }).detail
      : null;
    const detail = rawDetail != null
      ? Array.isArray(rawDetail)
        ? (rawDetail as { msg: string }[]).map(e => e.msg).join("; ")
        : String(rawDetail)
      : `Request failed with status ${res.status}`;
    throw new ApiError(res.status, detail);
  }

  return body as T;
}

// ── Health (no /api/v1 prefix, no auth) ──────────────────────────────────
export async function getHealth(): Promise<HealthCheck> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new ApiError(res.status, "Backend health check failed");
  return res.json();
}

// ── Auth ─────────────────────────────────────────────────────────────────
export function register(email: string, password: string, full_name: string) {
  return request<TokenResponse>(
    "/auth/register",
    { method: "POST", body: JSON.stringify({ email, password, full_name }) },
    { auth: false }
  );
}

export function login(email: string, password: string) {
  return request<TokenResponse>(
    "/auth/login",
    { method: "POST", body: JSON.stringify({ email, password }) },
    { auth: false }
  );
}

// ── Merchant accounts ────────────────────────────────────────────────────
export function getMyMerchantAccount() {
  return request<MerchantAccount | null>("/merchant-accounts/me");
}

export function createMerchantAccount(
  business_name: string,
  razorpay_key_id: string,
  is_test_mode: boolean
) {
  return request<MerchantAccount>("/merchant-accounts", {
    method: "POST",
    body: JSON.stringify({ business_name, razorpay_key_id, is_test_mode }),
  });
}

// ── Razorpay sync ────────────────────────────────────────────────────────
export function syncRazorpayData() {
  return request<SyncResult[]>("/razorpay/sync", { method: "POST" });
}

// ── Bank statements ──────────────────────────────────────────────────────
export function uploadBankStatement(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return request<ImportSummary>(
    "/bank-statements/upload",
    { method: "POST", body: formData },
    { isForm: true }
  );
}

// ── Reconciliation ───────────────────────────────────────────────────────
export function seedDemoData() {
  return request<DemoSeedResponse>("/reconciliation/seed-demo", { method: "POST" });
}

export function runReconciliation() {
  return request<ReconciliationRunSummary>("/reconciliation/run", { method: "POST" });
}

export function listCases(statusFilter?: string, runId?: string) {
  const params = new URLSearchParams();
  if (statusFilter) params.set("status_filter", statusFilter);
  if (runId) params.set("run_id", runId);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return request<ReconciliationCaseListItem[]>(`/reconciliation/cases${qs}`);
}

export function getCase(caseId: string) {
  return request<ReconciliationCaseDetail>(`/reconciliation/cases/${caseId}`);
}

// Real, already-tested backend endpoints (Track 04 batch reconciliation) that
// this frontend fork hadn't wired up yet -- added here (read-only GETs) so
// the Overview dashboard can show real run history and exceptions instead
// of inventing chart data.
export function listReconciliationRuns(limit = 10) {
  return request<ReconciliationRun[]>(`/reconciliation/runs?limit=${limit}`);
}

export function listExceptions(runId?: string) {
  const qs = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return request<ExceptionCase[]>(`/reconciliation/exceptions${qs}`);
}

// ── AI Copilot ──────────────────────────────────────────────────────────
export function copilotChat(message: string, history: { role: "user" | "assistant"; text: string }[]) {
  return request<CopilotChatResponse>("/copilot/chat", {
    method: "POST",
    body: JSON.stringify({ message, history }),
  });
}

// ── Investigations ───────────────────────────────────────────────────────
export function getLatestInvestigation(caseId: string) {
  return request<Investigation | null>(`/investigations/cases/${caseId}`);
}

export function triggerInvestigation(caseId: string) {
  return request<Investigation>(`/investigations/cases/${caseId}/investigate`, { method: "POST" });
}

export function submitDecision(investigationId: string, decision: string, notes?: string) {
  return request<Investigation>(`/investigations/${investigationId}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision, notes: notes || null }),
  });
}

// ── Dashboard ─────────────────────────────────────────────────────────────
export function getDashboardSummary() {
  return request<DashboardSummary>("/dashboard/summary");
}

export function getRecentActivity(limit = 10) {
  return request<RecentActivityItem[]>(`/dashboard/recent-activity?limit=${limit}`);
}

export function getMismatchBreakdown() {
  return request<MismatchCategoryBreakdown[]>("/dashboard/mismatch-breakdown");
}

// ── Audit log ─────────────────────────────────────────────────────────────
export function listAuditLogs(caseId?: string, limit = 100) {
  const params = new URLSearchParams();
  if (caseId) params.set("case_id", caseId);
  params.set("limit", String(limit));
  return request<AuditLogEntry[]>(`/audit-logs?${params.toString()}`);
}
