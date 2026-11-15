export type Severity = "INFO" | "MONITOR" | "REVIEW" | "URGENT";
export type MonitoringState = "URGENT" | "REVIEW" | "MONITOR" | "WITHIN_CRITERIA" | "INCOMPLETE";

export interface Profile {
  profile_id: string;
  display_name: string;
  role: string | null;
  mission_id: string;
  mission_name: string;
  environment: string;
  gravity_context: string;
  communication_mode: string;
  mission_day: number | null;
  has_mission: boolean;
  planned_duration_days?: number | null;
  mission_start: string;
  timezone: string;
  scenario: string | null;
  is_synthetic: boolean;
  settings: Record<string, any>;
  computed_baselines?: Record<string, Baseline>;
}

export interface Baseline {
  metric_code: string;
  label: string;
  unit: string;
  available: boolean;
  reason?: string;
  n_days: number;
  median?: number;
  robust_spread?: number;
  mean?: number;
  std?: number;
  min?: number;
  max?: number;
  p10?: number;
  p90?: number;
  ewma?: number;
  slope_per_day_14d?: number | null;
  confidence?: string;
  current?: number | null;
  robust_z?: number | null;
  pct_change?: number | null;
}

export interface Observation {
  observation_id: string;
  profile_id?: string;
  checkin_id?: string;
  metric_code: string;
  value: number | null;
  value_text: string | null;
  unit: string;
  normalized_value: number | null;
  normalized_unit: string | null;
  measured_at: string;
  recorded_at?: string;
  source: string;
  context: string | null;
  quality_status: string;
  quality_flags: string[];
  is_synthetic: boolean;
  status_note?: string | null;
  superseded_by?: string | null;
}

export interface KnowledgeRef {
  chunk_id: string;
  document_id: string;
  title: string;
  publisher: string;
  section: string;
  version?: string | null;
  publication_date?: string | null;
  passage: string;
  score: number;
  relevance_note: string;
}

export interface Finding {
  code: string;
  summary: string;
  statement_type: string;
  metric_codes: string[];
  evidence_observation_ids: string[];
  data: Record<string, any>;
  limitations: string[];
  severity: Severity;
  rule_ids: string[];
  next_steps: string[];
  requires_human_review: boolean;
  knowledge_references: KnowledgeRef[];
  evidence_status: "not_requested" | "found" | "unavailable";
  agent_id: string | null;
  certainty?: "strong" | "moderate" | "limited" | "self-reported" | null;
  certainty_reasons?: string[];
}

export interface AgentResult {
  run_id: string;
  agent_id: string;
  agent_name: string;
  agent_version: string;
  status: "completed" | "review" | "insufficient_data" | "failed" | "skipped";
  input_observation_ids: string[];
  findings: Finding[];
  assessments: { metric_code: string; assessment: string; detail: string }[];
  limitations: string[];
  activation_reason: string;
  method: string;
  output: Record<string, any>;
  error: string | null;
  duration_ms: number;
  requires_human_review: boolean;
}

export interface TraceEvent {
  stage: string;
  agent_id: string;
  name: string;
  status: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  summary: string;
  findings?: number;
  version?: string;
  input_observation_ids?: string[];
}

export interface NextAction {
  severity: Severity;
  text: string;
  rule_ids: string[];
  finding_code: string;
}

export interface Assessment {
  monitoring_state: MonitoringState;
  state_label: string;
  overall_severity: Severity;
  headline: string;
  requires_human_review: boolean;
  next_actions: NextAction[];
  coverage: {
    complete: boolean;
    routed_agents: string[];
    failed_agents: string[];
    insufficient_data_agents: string[];
    missing_core_metrics: string[];
  };
  evidence_retrieval: { available: boolean; reason?: string };
  ruleset: { version: string; status: string; checksum: string };
  finding_counts: Record<Severity, number>;
  findings: Finding[];
  agent_routes: Record<string, string>;
  versions: Record<string, any>;
}

export interface Statement {
  type: "observation" | "interpretation" | "recommendation" | "limitation";
  text: string;
  finding_codes: string[];
  citations: string[];
  source: "llm" | "template";
}

export interface Explanation {
  status: string;
  statements: Statement[];
  rejected: { text: string; reason: string }[];
  model?: string | null;
  latency_ms?: number;
  prompt_version?: string | null;
  note?: string;
}

export interface Alert {
  alert_id: string;
  run_id: string;
  profile_id: string;
  severity: Severity;
  title: string;
  reason: string;
  next_step: string;
  rule_ids: string[];
  evidence_ids: string[];
  state: "open" | "acknowledged" | "superseded";
  created_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  occurrences?: number;
  last_seen_at?: string | null;
}

export interface AnalysisRun {
  run_id: string;
  profile_id: string;
  checkin_id: string;
  status: string;
  overall_status: MonitoringState;
  coverage: string;
  model_version: string;
  ruleset_version: string;
  agent_versions: Record<string, string>;
  trace: TraceEvent[];
  assessment: Assessment;
  explanation_status: string;
  explanation: Explanation | null;
  started_at: string;
  completed_at: string;
  agent_results: AgentResult[];
  alerts: Alert[];
}

export interface Task {
  task_id: string;
  profile_id: string;
  title: string;
  category: string;
  description: string;
  scheduled_for: string;
  completed_at: string | null;
  completion_note: string | null;
}

export interface MetricDef {
  code: string;
  label: string;
  system: string;
  normalized_unit: string;
  units: string[];
  value_type: "numeric" | "scale" | "boolean" | "categorical";
  plausible_range: [number, number] | null;
  scale_labels: string[];
  description: string;
  agents: string[];
}

export interface SymptomDef {
  code: string;
  label: string;
  system: string;
}

export interface AgentDescription {
  agent_id: string;
  name: string;
  version: string;
  scope: string;
  metrics: string[];
  method: string;
  must_not: string;
}

export interface SystemHealth {
  app_version: string;
  mode: string;
  offline: { allow_external_network: boolean; guard_installed: boolean; blocked_attempts: number; last_blocked: string | null };
  database: { ok: boolean; path: string; size_kb: number; engine: string };
  llm: { provider: string; model: string; enabled: boolean; reachable: boolean; model_available: boolean; detail?: string; prompt_version: string };
  knowledge_index: { ready: boolean; error: string | null; documents: number; chunks: number; index_version: string };
  ruleset: { version: string; status: string; checksum: string; rules: number };
  anomaly_model: { name: string; version: string };
  synthetic_data: boolean;
  access_control?: { initial_secrets_file_present: boolean; key_protection?: string };
  server_time: string;
}

export interface ObservationDraft {
  metric_code: string;
  value: number | string | null;
  unit: string | null;
  measured_at: string;
  source: string;
  context?: string | null;
  confirmed?: boolean;
  label?: string;
  evidence_text?: string | null;
  onset?: string | null;
  time_note?: string;
}

export interface ParseResult {
  intents: string[];
  observations: ObservationDraft[];
  negated_symptoms: string[];
  clarifications: { metric_code: string; field: string; question: string; options: string[] }[];
  requires_confirmation: boolean;
  method: string;
}

export interface ValidationPreview {
  ok: boolean;
  checkin_errors: string[];
  observations: {
    index: number;
    metric_code: string;
    label: string;
    quality_status: string;
    errors: string[];
    flags: string[];
    messages: string[];
    normalized_value: number | null;
    normalized_unit: string | null;
  }[];
}

export interface Overview {
  profile: Profile;
  latest_values: Record<string, Observation>;
  latest_run: AnalysisRun | null;
  open_alerts: Alert[];
  checkin_due: boolean;
  tasks_today: Task[];
  checkin_streak: number;
  computed_baselines?: Record<string, Baseline>;
  urgent_acknowledged?: { alert_id: string; acknowledged_at: string; acknowledged_note: string | null } | null;
}
