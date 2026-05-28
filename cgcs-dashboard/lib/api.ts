// Server-side API client for the CGCS LangGraph agent.
// All calls go from the dashboard's server to the agent — the API key
// never reaches the browser.

const AGENT_URL = process.env.AGENT_API_URL ?? "http://langgraph-agent:8000";
const API_KEY = process.env.LANGGRAPH_API_KEY ?? "";

// At build time the agent isn't running, so fetches would hang forever.
// 5s is plenty at runtime; 5s also lets the build fail fast and render error
// state, which pages handle gracefully with .catch().
const FETCH_TIMEOUT_MS = 5000;

type FetchOpts = RequestInit & { revalidate?: number };

async function agentFetch<T>(path: string, opts: FetchOpts = {}): Promise<T> {
  const { revalidate, ...rest } = opts;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(`${AGENT_URL}${path}`, {
      ...rest,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${API_KEY}`,
        ...(rest.headers ?? {}),
      },
      next: revalidate ? { revalidate } : undefined,
      cache: rest.cache ?? "no-store",
      signal: controller.signal,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`Agent ${res.status} on ${path}: ${text}`);
    }
    return res.json() as Promise<T>;
  } catch (e) {
    if ((e as Error)?.name === "AbortError") {
      throw new Error(`Agent fetch timed out (${FETCH_TIMEOUT_MS}ms) on ${path}`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
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

// --- Reservations ---------------------------------------------------------

export type Reservation = {
  id: string;
  request_id: string;
  event_name: string;
  requester_organization?: string | null;
  requested_date: string;
  requested_start_time: string;
  requested_end_time: string;
  room_requested?: string | null;
  status: string;
  event_category?: string | null;
  event_subtype?: string | null;
  actual_revenue?: string | number | null;
  actual_attendance?: number | null;
  estimated_attendees?: number | null;
  source?: string | null;
  cgcs_lead?: string | null;
  created_at?: string | null;
  // Source metadata fields extracted for the P.E.T. view
  meta_ad_astra?: string | null;
  meta_tdx?: string | null;
  meta_layout?: string | null;
  meta_walkthrough?: string | null;
  meta_invoice?: string | null;
  meta_av?: string | null;
  meta_catering?: string | null;
  meta_poc_email?: string | null;
  meta_poc_phone?: string | null;
};

export type ReservationFull = Reservation & {
  requester_name?: string | null;
  requester_email?: string | null;
  event_description?: string | null;
  admin_notes?: string | null;
  event_category?: string | null;
  event_subtype?: string | null;
  event_location?: string | null;
  estimated_attendees?: number | null;
  attendance_students?: number | null;
  attendance_staff?: number | null;
  attendance_community?: number | null;
  training_hours_delivered?: string | number | null;
  estimated_cost?: string | number | null;
  is_eligible?: boolean | null;
  eligibility_reason?: string | null;
  calendar_available?: boolean | null;
  ai_decision?: string | null;
  pricing_tier?: string | null;
  completed_at?: string | null;
  cancelled_at?: string | null;
  cancellation_reason?: string | null;
  source_metadata?: Record<string, unknown> | null;
};

export function getReservationFull(id: string): Promise<ReservationFull> {
  return agentFetch(`/api/v1/reservations/${id}/full`);
}

export function updateReservationCategory(
  id: string,
  category: "cgcs" | "acc" | "monetization",
): Promise<{ id: string; event_name: string; event_category: string }> {
  const q = new URLSearchParams({ category });
  return agentFetch(`/api/v1/reservations/${id}/category?${q.toString()}`, {
    method: "PATCH",
  });
}

export function updateReservationFields(
  id: string,
  updates: Record<string, unknown>,
): Promise<{ id: string; event_name: string }> {
  return agentFetch(`/api/v1/reservations/${id}`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
}

export function createReservation(
  payload: Record<string, unknown>,
): Promise<{ id: string; request_id: string; event_name: string }> {
  return agentFetch(`/api/v1/reservations`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getReservations(
  status?: string,
  limit = 500,
  sort?: string,
  direction?: "asc" | "desc",
  category?: string,
  date_from?: string,
  date_to?: string,
): Promise<{ count: number; reservations: Reservation[] }> {
  const q = new URLSearchParams({ limit: String(limit) });
  if (status) q.set("status", status);
  if (category) q.set("category", category);
  if (date_from) q.set("date_from", date_from);
  if (date_to) q.set("date_to", date_to);
  if (sort) q.set("sort", sort);
  if (direction) q.set("direction", direction);
  return agentFetch(`/api/v1/reservations?${q.toString()}`);
}

// --- Budget ---------------------------------------------------------------

export type BudgetCategoryRow = {
  category: string;
  row_count: number;
  expense_total: number;
  revenue_total: number;
  net: number;
};

export type BudgetTxnRow = {
  id: string;
  date: string | null;
  description: string;
  category: string | null;
  payment_method: string | null;
  expense: number;
  revenue: number;
  running_balance: number;
  linked_reservation_id: string | null;
  notes: string | null;
};

export type BudgetSummary = {
  fiscal_year: {
    label: string;
    start_date: string;
    end_date: string;
    starting_balance: number;
    holdover_to_next: number;
  };
  totals: {
    expense: number;
    revenue: number;
    wage_expense: number;
    non_wage_expense: number;
    current_balance: number;
    txn_count: number;
  };
  burn_rate: {
    days_left: number;
    weeks_left: number;
    months_left: number;
    per_day: number;
    per_week: number;
    per_month: number;
  };
  categories: BudgetCategoryRow[];
  recent_transactions: BudgetTxnRow[];
};

export function getBudgetSummary(fy?: string): Promise<BudgetSummary> {
  const q = new URLSearchParams();
  if (fy) q.set("fy", fy);
  return agentFetch(`/api/v1/budget/summary?${q.toString()}`);
}

export type BudgetTransaction = {
  id: string;
  fy_label: string;
  transaction_date: string | null;
  description: string;
  category: string | null;
  payment_method: string | null;
  expense: number | null;
  revenue: number | null;
  running_balance: number | null;
  transfer_required: boolean | null;
  transfer_confirmed: boolean | null;
  notes: string | null;
  source_tag: string | null;
  linked_reservation_id: string | null;
  created_at: string | null;
};

export function getBudgetTransactions(
  fy?: string,
  category?: string,
  sort?: string,
  direction?: "asc" | "desc",
  limit = 500,
): Promise<{ count: number; transactions: BudgetTransaction[] }> {
  const q = new URLSearchParams({ limit: String(limit) });
  if (fy) q.set("fy", fy);
  if (category) q.set("category", category);
  if (sort) q.set("sort", sort);
  if (direction) q.set("direction", direction);
  return agentFetch(`/api/v1/budget/transactions?${q.toString()}`);
}

// --- Calendar -------------------------------------------------------------

export type CalendarEvent = {
  id: string;
  summary: string;
  description?: string;
  location?: string;
  start: string;            // ISO datetime (or YYYY-MM-DD if all-day)
  end: string;
  all_day: boolean;
  html_link?: string;
  status?: string;
};

export function getCalendarEvents(
  start: string,
  end: string,
): Promise<{ count: number; events: CalendarEvent[] }> {
  const q = new URLSearchParams({ start, end });
  return agentFetch(`/api/v1/calendar/events?${q.toString()}`);
}

export type CalendarSyncResult = {
  range: { start: string; end: string };
  fetched: number;
  inserted: number;
  skipped_dedup: number;
  skipped_other: number;
  errors: string[];
};

export function syncCalendar(): Promise<CalendarSyncResult> {
  return agentFetch(`/api/v1/calendar/sync`, { method: "POST" });
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
