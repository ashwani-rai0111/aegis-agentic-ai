export type IncidentSummary = {
  id: string;
  service: string;
  severity: string;
  status: string;
  summary: string | null;
  root_cause: string | null;
  confidence: number | null;
  scenario: string;
  agent_mode: string | null;
  detected_at: string;
  updated_at: string;
};

export type Observation = {
  id: string;
  source: string;
  name: string;
  value: string;
  evidence: Record<string, unknown> | null;
  timestamp: string;
};

export type Hypothesis = {
  id: string;
  hypothesis: string;
  evidence_for: string | null;
  evidence_against: string | null;
  score: number;
  selected: boolean;
};

export type Plan = {
  id: string;
  proposed_action: string;
  parameters: Record<string, unknown> | null;
  risk: string;
  rationale: string;
  approval_required: boolean;
  approved: boolean;
  approved_by: string | null;
};

export type Action = {
  id: string;
  tool: string;
  parameters: Record<string, unknown> | null;
  approved_by: string | null;
  started_at: string;
  completed_at: string | null;
  result: string | null;
  success: boolean;
};

export type Verification = {
  id: string;
  metric: string;
  before_value: string | null;
  after_value: string | null;
  success: boolean;
};

export type AuditLog = {
  id: string;
  actor: string;
  action: string;
  details: Record<string, unknown> | null;
  timestamp: string;
  result: string | null;
};

export type IncidentDetail = IncidentSummary & {
  observations: Observation[];
  hypotheses: Hypothesis[];
  plans: Plan[];
  actions: Action[];
  verifications: Verification[];
  audit_logs: AuditLog[];
};

export type HealthResponse = {
  status: string;
  database: string;
  agent_mode: string;
  tool_backend: string;
  aws_configured: boolean;
};