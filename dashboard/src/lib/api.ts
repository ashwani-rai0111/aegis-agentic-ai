import type { HealthResponse, IncidentDetail, IncidentSummary } from "./types";

const API_URL =
  process.env.NEXT_PUBLIC_AEGIS_API_URL?.replace(/\/$/, "") ||
  "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
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
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export function getApiUrl() {
  return API_URL;
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