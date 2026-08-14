import type {
  FixJob,
  FixRepo,
  HealthResponse,
  IncidentDetail,
  IncidentSummary,
} from "./types";
import { getSessionToken } from "./auth";

const API_URL =
  process.env.NEXT_PUBLIC_AEGIS_API_URL?.replace(/\/$/, "") ||
  "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = getSessionToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // keep statusText
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  return response.json() as Promise<T>;
}

export function getApiUrl() {
  return API_URL;
}

export function login(username: string, password: string) {
  return request<{ token: string; username: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function verifySession(token: string) {
  return request<{ ok: boolean; username: string | null }>("/auth/session", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function fetchHealth() {
  return request<HealthResponse>("/health");
}

export function fetchIncidents() {
  return request<IncidentSummary[]>("/incidents");
}

export function fetchIncident(id: string) {
  return request<IncidentDetail>(`/incidents/${id}`);
}

export function simulateIncident(payload?: {
  scenario?: string;
  service?: string;
  severity?: string;
}) {
  return request<IncidentDetail>("/incidents/simulate", {
    method: "POST",
    body: JSON.stringify({
      scenario: payload?.scenario ?? "api_memory_pressure",
      service: payload?.service ?? "production-api",
      severity: payload?.severity ?? "HIGH",
    }),
  });
}

export function runLiveIncident(payload?: { service?: string; severity?: string }) {
  return request<IncidentDetail>("/incidents/live", {
    method: "POST",
    body: JSON.stringify({
      service: payload?.service ?? "production-api",
      severity: payload?.severity ?? "HIGH",
    }),
  });
}

export function investigateIssue(payload: {
  message: string;
  service?: string;
  severity?: string;
}) {
  return request<IncidentDetail>("/incidents/investigate", {
    method: "POST",
    body: JSON.stringify({
      message: payload.message,
      service: payload.service ?? "signyn",
      severity: payload.severity ?? "HIGH",
    }),
  });
}

export function approveIncident(id: string, approvedBy = "dashboard-operator") {
  return request<IncidentDetail>(`/incidents/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ approved_by: approvedBy }),
  });
}

export function rejectIncident(
  id: string,
  rejectedBy = "dashboard-operator",
  reason = "Operator rejected remediation plan",
) {
  return request<IncidentDetail>(`/incidents/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ rejected_by: rejectedBy, reason }),
  });
}

export function fetchFixRepos() {
  return request<FixRepo[]>("/fixes/repos");
}

export function fetchFixJobs() {
  return request<FixJob[]>("/fixes");
}

export function fetchFixJob(id: string) {
  return request<FixJob>(`/fixes/${id}`);
}

export function createFixJob(payload: {
  repo_key: string;
  error_text: string;
  notes?: string;
  fix_password: string;
}) {
  return request<FixJob>("/fixes", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
