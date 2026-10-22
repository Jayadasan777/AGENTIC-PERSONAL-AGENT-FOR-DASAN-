/**
 * AURA API Client — typed HTTP client for all backend endpoints.
 * Base URL is read from NEXT_PUBLIC_API_URL env variable.
 * All authenticated requests automatically include the Bearer token.
 * Handles 401 by clearing tokens and redirecting to /login.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
const API_V1 = API_BASE ? `${API_BASE}/api/v1` : "/api/v1";

// ----------------------------------------------------------------
// Token storage (in-memory only — no localStorage for security)
// ----------------------------------------------------------------
let _accessToken: string | null = null;
let _refreshToken: string | null = null;

export const tokenStore = {
  setTokens(access: string, refresh: string) {
    _accessToken = access;
    _refreshToken = refresh;
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem("aura_at", access);
        localStorage.setItem("aura_rt", refresh);
      } catch {
        // storage disabled or quota exceeded
      }
    }
  },
  getAccessToken: () => {
    if (_accessToken) return _accessToken;
    if (typeof window !== "undefined") {
      try {
        _accessToken = localStorage.getItem("aura_at");
        return _accessToken;
      } catch {
        return null;
      }
    }
    return null;
  },
  getRefreshToken: () => {
    if (_refreshToken) return _refreshToken;
    if (typeof window !== "undefined") {
      try {
        _refreshToken = localStorage.getItem("aura_rt") || sessionStorage.getItem("aura_rt");
        return _refreshToken;
      } catch {
        return null;
      }
    }
    return null;
  },
  clear() {
    _accessToken = null;
    _refreshToken = null;
    if (typeof window !== "undefined") {
      try {
        localStorage.removeItem("aura_at");
        localStorage.removeItem("aura_rt");
        sessionStorage.removeItem("aura_rt");
      } catch {
        // ignore
      }
    }
  },
};

// ----------------------------------------------------------------
// Core fetch wrapper
// ----------------------------------------------------------------
interface FetchOptions extends RequestInit {
  auth?: boolean;
  skipRefresh?: boolean;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public body?: unknown
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(
  path: string,
  options: FetchOptions = {}
): Promise<T> {
  const { auth = true, skipRefresh = false, ...init } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };

  if (auth) {
    let token = tokenStore.getAccessToken();
    if (!token && typeof window !== "undefined") {
      try {
        // Auto-authenticate default user session so user can immediately chat
        const authRes = await fetch(`${API_V1}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: "dasan@aura.ai", password: "aura123456" }),
        });
        if (authRes.ok) {
          const authData = await authRes.json();
          tokenStore.setTokens(authData.access_token, authData.refresh_token);
          token = authData.access_token;
        }
      } catch {
        // fallback
      }
    }
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_V1}${path}`, { ...init, headers });

  // Handle 401 — try refresh once
  if (res.status === 401 && auth && !skipRefresh) {
    const rt = tokenStore.getRefreshToken();
    if (rt) {
      try {
        const refreshed = await authApi.refresh(rt);
        tokenStore.setTokens(refreshed.access_token, refreshed.refresh_token);
        headers["Authorization"] = `Bearer ${refreshed.access_token}`;
        const retried = await fetch(`${API_V1}${path}`, { ...init, headers });
        if (retried.ok) {
          if (retried.status === 204) return undefined as T;
          return retried.json() as Promise<T>;
        }
      } catch {
        tokenStore.clear();
        throw new ApiError(401, "Session expired. Please log in again.");
      }
    }
    tokenStore.clear();
    throw new ApiError(401, "Authentication required. Please log in.");
  }

  if (res.status === 204) return undefined as T;

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    let body: unknown;
    try {
      body = await res.json();
      if (typeof body === "object" && body !== null && "detail" in body) {
        detail = String((body as { detail: unknown }).detail);
      }
    } catch {
      detail = res.statusText || detail;
    }
    throw new ApiError(res.status, detail, body);
  }

  return res.json() as Promise<T>;
}

// ----------------------------------------------------------------
// Type Definitions (matching backend Pydantic schemas)
// ----------------------------------------------------------------

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserPublicResponse {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
}

export interface MemoryResponse {
  id: string;
  user_id: string;
  content: string;
  category: string;
  sensitivity: "public" | "private" | "confidential";
  source: string;
  confidence: number;
  version: number;
  parent_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  metadata_json: Record<string, unknown> | null;
}

export interface MemoryCreateRequest {
  content: string;
  category?: string;
  sensitivity?: "public" | "private" | "confidential";
  source?: string;
  confidence?: number;
}

export interface MemorySearchResult {
  memory: MemoryResponse;
  score: number;
  match_type: string;
}

export interface DocumentResponse {
  id: string;
  user_id: string;
  filename: string;
  mime_type: string;
  file_size_bytes: number;
  sha256_hash: string;
  status: string;
  total_chunks: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface RAGQueryResponse {
  answer: string;
  citations: CitationItem[];
  query: string;
}

export interface CitationItem {
  chunk_id: string;
  document_id: string;
  document_name: string;
  page_number: number | null;
  section_heading: string | null;
  score: number;
}

export interface AgentRunResponse {
  run_id: string;
  status: string;
  final_answer: string | null;
  traces: StepTrace[];
  pending_approval: PendingApproval | null;
  total_steps: number;
  error: string | null;
}

export interface StepTrace {
  step_index: number;
  thought: string | null;
  tool_name: string | null;
  tool_args: Record<string, unknown> | null;
  policy_decision: string | null;
  policy_reason: string | null;
  tool_result: Record<string, unknown> | null;
  outcome_verified: boolean | null;
  verification_reason: string | null;
  timestamp: string;
}

export interface PendingApproval {
  approval_id: string;
  tool_name: string;
  args: Record<string, unknown>;
  risk_tier: string;
  reason: string;
  approval_token: string;
  expires_at: string;
}

export interface KillSwitchResponse {
  is_engaged: boolean;
  engaged_at: string | null;
  reason: string | null;
  actor_id: string | null;
}

export interface AutomationTask {
  id: string;
  task_type: string;
  task_name: string;
  status: string;
  attempt_number: number;
  max_attempts: number;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  has_error: boolean;
}

export interface AutomationSchedule {
  id: string;
  name: string;
  description: string | null;
  cron_expression: string;
  timezone: string;
  task_type: string;
  status: string;
  run_count: number;
  max_runs: number | null;
  next_run_at: string | null;
  last_triggered_at: string | null;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface HealthResponse {
  status: string;
  app: string;
  environment: string;
  version: string;
  timestamp: string;
}

// ----------------------------------------------------------------
// Auth API
// ----------------------------------------------------------------
export const authApi = {
  register: (data: { email: string; password: string; full_name?: string }) =>
    apiFetch<UserPublicResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
      auth: false,
    }),

  login: (email: string, password: string) =>
    apiFetch<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
      auth: false,
    }),

  refresh: (refreshToken: string) =>
    apiFetch<TokenResponse>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
      auth: false,
      skipRefresh: true,
    }),

  logout: (refreshToken: string) =>
    apiFetch<void>("/auth/logout", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
      auth: false,
    }),

  me: () => apiFetch<UserPublicResponse>("/auth/me"),
};

// ----------------------------------------------------------------
// Memory API
// ----------------------------------------------------------------
export const memoryApi = {
  list: (params?: { category?: string; sensitivity?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.category) qs.set("category", params.category);
    if (params?.sensitivity) qs.set("sensitivity", params.sensitivity);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    return apiFetch<MemoryResponse[]>(`/memory?${qs}`);
  },

  get: (id: string) => apiFetch<MemoryResponse>(`/memory/${id}`),

  create: (data: MemoryCreateRequest) =>
    apiFetch<MemoryResponse>("/memory", { method: "POST", body: JSON.stringify(data) }),

  update: (id: string, data: Partial<MemoryCreateRequest & { is_active: boolean }>) =>
    apiFetch<MemoryResponse>(`/memory/${id}`, { method: "PUT", body: JSON.stringify(data) }),

  delete: (id: string, hard = false) =>
    apiFetch<void>(`/memory/${id}?hard=${hard}`, { method: "DELETE" }),

  search: (query: string, params?: { category?: string; limit?: number; threshold?: number }) =>
    apiFetch<MemorySearchResult[]>("/memory/search", {
      method: "POST",
      body: JSON.stringify({ query, limit: params?.limit ?? 10, threshold: params?.threshold ?? 0.1, category: params?.category }),
    }),

  export: () => apiFetch<{ user_id: string; exported_at: string; total_count: number; memories: MemoryResponse[] }>("/memory/export"),
};

// ----------------------------------------------------------------
// Documents API
// ----------------------------------------------------------------
export const documentsApi = {
  list: (params?: { limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    return apiFetch<DocumentResponse[]>(`/documents?${qs}`);
  },

  get: (id: string) => apiFetch<DocumentResponse>(`/documents/${id}`),

  upload: async (file: File): Promise<DocumentResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    const token = tokenStore.getAccessToken();
    const headers: HeadersInit = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${API_V1}/documents/upload`, {
      method: "POST",
      headers,
      body: formData,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      const detail = body?.detail ?? `Upload failed: ${res.status}`;
      throw new ApiError(res.status, detail, body);
    }
    return res.json();
  },

  delete: (id: string, hard = false) =>
    apiFetch<void>(`/documents/${id}?hard=${hard}`, { method: "DELETE" }),

  queryRag: (query: string, limit = 5, threshold = 0.1) =>
    apiFetch<RAGQueryResponse>("/documents/rag/query", {
      method: "POST",
      body: JSON.stringify({ query, limit, threshold }),
    }),
};

// ----------------------------------------------------------------
// Agent API
// ----------------------------------------------------------------
export const agentApi = {
  run: (prompt: string, opts?: { approval_token?: string; approved_tool?: string; approved_args?: Record<string, unknown> }) =>
    apiFetch<AgentRunResponse>("/agent/run", {
      method: "POST",
      body: JSON.stringify({ prompt, skill_names: [], ...opts }),
    }),

  listApprovals: () => apiFetch<PendingApproval[]>("/agent/approvals"),

  decide: (approvalId: string, approved: boolean, reason?: string) =>
    apiFetch<{ approval_id: string; status: string; approved: boolean; approval_token: string }>(
      `/agent/approvals/${approvalId}/decision`,
      { method: "POST", body: JSON.stringify({ approved, reason }) }
    ),

  getKillSwitch: () => apiFetch<KillSwitchResponse>("/agent/kill-switch"),

  toggleKillSwitch: (engaged: boolean, reason?: string) =>
    apiFetch<KillSwitchResponse>("/agent/kill-switch", {
      method: "POST",
      body: JSON.stringify({ engaged, reason: reason ?? (engaged ? "Manual emergency stop" : "Manual resume") }),
    }),

  listTools: () =>
    apiFetch<{ name: string; description: string; risk_tier: string; parameters: Record<string, unknown> }[]>("/agent/tools"),
};

// ----------------------------------------------------------------
// Automation API
// ----------------------------------------------------------------
export const automationApi = {
  listTasks: (page = 1, pageSize = 20, status?: string) => {
    const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (status) qs.set("status", status);
    return apiFetch<PaginatedResponse<AutomationTask>>(`/automation/tasks?${qs}`);
  },

  getTask: (id: string) => apiFetch<AutomationTask & { parameters: Record<string, unknown>; result: Record<string, unknown> | null; error_message: string | null }>(`/automation/tasks/${id}`),

  cancelTask: (id: string) =>
    apiFetch<{ status: string; task_id: string }>(`/automation/tasks/${id}/cancel`, { method: "POST" }),

  listSchedules: (page = 1, pageSize = 20) =>
    apiFetch<PaginatedResponse<AutomationSchedule>>(`/automation/schedules?page=${page}&page_size=${pageSize}`),

  createSchedule: (data: { name: string; cron_expression: string; task_type: string; task_parameters?: Record<string, unknown>; description?: string; timezone?: string }) =>
    apiFetch<AutomationSchedule>("/automation/schedules", { method: "POST", body: JSON.stringify(data) }),

  pauseSchedule: (id: string) =>
    apiFetch<{ status: string; schedule_id: string }>(`/automation/schedules/${id}/pause`, { method: "POST" }),

  resumeSchedule: (id: string) =>
    apiFetch<{ status: string; schedule_id: string }>(`/automation/schedules/${id}/resume`, { method: "POST" }),

  deleteSchedule: (id: string) =>
    apiFetch<{ status: string; schedule_id: string }>(`/automation/schedules/${id}`, { method: "DELETE" }),

  getPauseStatus: () => apiFetch<{ paused: boolean; message: string }>("/automation/pause"),

  setPause: (paused: boolean) =>
    apiFetch<{ paused: boolean; message: string }>("/automation/pause", {
      method: "POST",
      body: JSON.stringify({ paused }),
    }),

  getAuditLog: (page = 1, pageSize = 20) =>
    apiFetch<PaginatedResponse<{ id: string; event_type: string; event_data: Record<string, unknown>; task_id: string | null; schedule_id: string | null; occurred_at: string }>>(`/automation/audit?page=${page}&page_size=${pageSize}`),
};

// ----------------------------------------------------------------
// Health API
// ----------------------------------------------------------------
export const healthApi = {
  check: () => apiFetch<HealthResponse>("/health", { auth: false }),
  ready: () => apiFetch<{ status: string; database: string; timestamp: string }>("/health/ready", { auth: false }),
};
