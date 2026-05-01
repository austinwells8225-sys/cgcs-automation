// Server-side API client for the CGCS LangGraph agent.
// All calls go from the dashboard's server to the agent — the API key
// never reaches the browser.

const AGENT_URL = process.env.AGENT_API_URL ?? "http://langgraph-agent:8000";
const API_KEY = process.env.LANGGRAPH_API_KEY ?? "";

type FetchOpts = RequestInit & { revalidate?: number };

async function agentFetch<T>(path: string, opts: FetchOpts = {}): Promise<T> {
  const { revalidate, ...rest } = opts;
  const res = await fetch(`${AGENT_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${API_KEY}`,
      ...(rest.headers ?? {}),
    },
    next: revalidate ? { revalidate } : undefined,
    cache: rest.cache ?? "no-store",
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Agent ${res.status} on ${path}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// --- Impact ---------------------------------------------------------------

export type ImpactTier = {
  total_events: number;
  total_people: number;
  total_hours: number;
  total_revenue: number;
};

export type CgcsImpactTier = ImpactTier & {
  training_hours: number;
  training_events: number;
  on_site_events: number;
  off_site_events: number;
  on_site_hours: number;
  off_site_hours: number;
  audience: { students: number; staff: number; community: number };
};

export type ImpactReport = {
  period: string;
  start: string;
  end: string;
  current: {
    community: ImpactTier;
    monetization: ImpactTier;
    acc: ImpactTier;
    cgcs: CgcsImpactTier;
  };
  previous_year: {
    start: string;
    end: string;
    community: ImpactTier;
    monetization: ImpactTier;
    acc: ImpactTier;
    cgcs: CgcsImpactTier;
  };
};

export function getImpact(period = "year", start = ""): Promise<ImpactReport> {
  const q = new URLSearchParams({ period, ...(start ? { start } : {}) });
  return agentFetch<ImpactReport>(`/api/v1/impact?${q.toString()}`);
}

// --- Inbox (pending email drafts) ----------------------------------------

export type PendingEmail = {
  id: string;
  thread_id?: string;
  from_email?: string;
  subject?: string;
  draft_body?: string;
  classification?: string;
  created_at?: string;
};

export function getPendingEmails(): Promise<{ count: number; emails: PendingEmail[] }> {
  return agentFetch(`/api/v1/email/pending`);
}

export function approveEmail(id: string, edits?: string) {
  return agentFetch(`/api/v1/email/approve/${id}`, {
    method: "POST",
    body: JSON.stringify({ approve: true, edited_body: edits }),
  });
}

export function rejectEmail(id: string) {
  return agentFetch(`/api/v1/email/approve/${id}`, {
    method: "POST",
    body: JSON.stringify({ approve: false }),
  });
}

// --- Alerts ---------------------------------------------------------------

export type Alert = {
  id: string;
  reservation_id?: string | null;
  alert_type: string;
  title: string;
  detail?: string | null;
  status: string;
  created_at?: string | null;
};

export function getActiveAlerts(): Promise<{ count: number; alerts: Alert[] }> {
  return agentFetch(`/api/v1/alerts/active`);
}

// --- Manual event entry ---------------------------------------------------

export type ManualEventInput = {
  event_name: string;
  requested_date: string;
  requested_start_time: string;
  requested_end_time: string;
  event_subtype?: string;
  event_location?: string;
  estimated_attendees?: number;
  actual_attendance?: number;
  attendance_students?: number;
  attendance_staff?: number;
  attendance_community?: number;
  training_hours_delivered?: number;
  notes?: string;
};

export function createManualEvent(input: ManualEventInput) {
  return agentFetch(`/api/v1/events/manual`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}
