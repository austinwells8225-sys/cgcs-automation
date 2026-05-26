import Link from "next/link";
import { getReservationFull, type ReservationFull } from "@/lib/api";
import { CategoryEditor } from "../CategoryEditor";

export const dynamic = "force-dynamic";

const CATEGORY_LABEL: Record<string, string> = {
  cgcs: "CGCS",
  acc: "ACC",
  monetization: "Space rental",
};

const STATUS_COLOR: Record<string, string> = {
  completed: "bg-cgcs-good/10 text-cgcs-good ring-cgcs-good/30",
  approved: "bg-blue-50 text-blue-700 ring-blue-200",
  pending_review: "bg-amber-50 text-amber-700 ring-amber-200",
  cancelled: "bg-gray-100 text-gray-600 ring-gray-300",
  rejected: "bg-red-50 text-cgcs-bad ring-red-200",
};

const SOURCE_LABEL: Record<string, string> = {
  smartsheet: "Smartsheet intake",
  manual_backfill: "Manual backfill (spreadsheet)",
  manual_backfill_declined: "Manual backfill — declined tab",
  calendar_sync: "Google Calendar sync",
  manual: "Manual entry",
};

function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s + (s.length === 10 ? "T00:00:00Z" : ""));
  return d.toLocaleDateString("en-US", {
    year: "numeric", month: "long", day: "numeric", timeZone: "UTC",
  });
}

function fmtTime(s: string | null | undefined): string {
  if (!s || s === "00:00:00") return "";
  return s.slice(0, 5);
}

function fmtMoney(v: string | number | null | undefined): string {
  const n = typeof v === "string" ? parseFloat(v) : v ?? 0;
  if (!n) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: 0,
  }).format(n);
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-cgcs-mute">{label}</div>
      <div className="mt-1 text-sm text-cgcs-ink">{value || <span className="text-cgcs-mute">—</span>}</div>
    </div>
  );
}

// Format an arbitrary source_metadata value for human display.
function fmtMetaValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "object") return JSON.stringify(v, null, 2);
  return String(v);
}

// Pretty-label common source_metadata keys.
const META_LABELS: Record<string, string> = {
  ad_astra: "Ad Astra #",
  tdx: "TDX / Smartsheet #",
  cgcs_lead: "CGCS Lead (raw)",
  contact_info: "Event lead / contact",
  poc: "POC",
  poc_name: "POC name",
  poc_email: "POC email",
  poc_phone: "POC phone",
  organization: "Organization",
  host: "Host",
  event_title: "Event title (from calendar)",
  date_blob: "Date (verbatim)",
  time_block: "Time block reserved",
  floor_layout: "Floor layout / setup",
  stage: "Stage",
  av: "A/V needs",
  catering: "Catering",
  staffing: "Staffing & volunteers",
  additional_needs: "Additional needs",
  walkthrough: "Walkthrough date",
  invoice_generated: "Invoice generated",
  agreement_sent: "Agreement sent",
  agreement: "Agreement / paperwork",
  billing: "Billing",
  rooms: "Rooms",
  attendance: "Attendance",
  money_expected: "Money expected",
  cgcs_labor: "CGCS labor",
  cal_status: "Status (per calendar)",
  internal_notes: "Internal notes",
  location: "Calendar location",
  raw_title: "Calendar title (raw)",
  is_hold: "Tentative HOLD",
  calendar_event_id: "Calendar event ID",
  calendar_html_link: "Calendar event link",
};

export default async function ReservationDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let data: ReservationFull | { error: string };
  try {
    data = await getReservationFull(id);
  } catch (e) {
    data = { error: String(e) };
  }

  if ("error" in data) {
    return (
      <div className="space-y-4">
        <Link href="/reservations" className="text-sm text-cgcs-mute hover:text-cgcs-ink">
          ← Back to reservations
        </Link>
        <div className="rounded-lg border border-cgcs-bad/40 bg-red-50 p-6 text-sm text-cgcs-bad">
          Failed to load: {data.error}
        </div>
      </div>
    );
  }

  const r = data;
  const meta = (r.source_metadata ?? {}) as Record<string, unknown>;
  // Prefer the HTML-stripped plain text; fall back to raw description / event_description.
  const description =
    (meta.description_plain as string) ||
    (meta.event_description as string) ||
    (meta.description as string) ||
    r.event_description ||
    "";
  const calLink = (meta.calendar_html_link as string) || "";

  // Keys we render in their own dedicated section (Description) — skip in the
  // metadata grid below so we don't duplicate.
  const HIDDEN_IN_META = new Set([
    "description", "description_plain", "event_description",
  ]);

  // Render meta keys in a friendlier order, putting things we know about first.
  const knownOrder = [
    "cgcs_lead", "ad_astra", "tdx", "organization", "host", "poc", "poc_name",
    "poc_email", "poc_phone", "contact_info", "date_blob", "time_block",
    "attendance", "money_expected", "floor_layout", "stage", "av", "catering",
    "staffing", "additional_needs", "walkthrough", "rooms", "invoice_generated",
    "agreement_sent", "agreement", "billing", "cgcs_labor", "cal_status",
    "internal_notes", "is_hold", "location", "raw_title", "event_title",
    "calendar_event_id", "calendar_html_link",
  ];
  const metaKeys = Object.keys(meta).filter((k) => !HIDDEN_IN_META.has(k));
  const orderedKeys = [
    ...knownOrder.filter((k) => k in meta && !HIDDEN_IN_META.has(k)),
    ...metaKeys.filter((k) => !knownOrder.includes(k)),
  ];

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/reservations"
          className="text-sm text-cgcs-mute hover:text-cgcs-ink"
        >
          ← Back to reservations
        </Link>
      </div>

      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold text-cgcs-ink">{r.event_name}</h1>
          <span
            className={`inline-flex rounded-full px-2 py-0.5 text-xs ring-1 ${
              STATUS_COLOR[r.status] ?? "bg-gray-50 text-gray-600 ring-gray-200"
            }`}
          >
            {r.status === "pending_review" ? "pending" : r.status}
          </span>
          <CategoryEditor id={r.id} current={r.event_category} />
        </div>
        <p className="text-sm text-cgcs-mute">
          {fmtDate(r.requested_date)}
          {fmtTime(r.requested_start_time) && (
            <> · {fmtTime(r.requested_start_time)} – {fmtTime(r.requested_end_time)}</>
          )}
          {r.requester_organization && <> · {r.requester_organization}</>}
        </p>
      </header>

      {/* Core fields grid */}
      <section className="grid grid-cols-1 gap-4 rounded-xl bg-white p-6 ring-1 ring-cgcs-line md:grid-cols-2 lg:grid-cols-3">
        <Field label="CGCS Lead" value={r.cgcs_lead} />
        <Field label="Tier" value={r.event_category ? CATEGORY_LABEL[r.event_category] : null} />
        <Field label="Subtype" value={r.event_subtype} />
        <Field label="Room" value={r.room_requested} />
        <Field label="Location" value={r.event_location} />
        <Field
          label="Attendance"
          value={
            r.actual_attendance ?? r.estimated_attendees
              ? `${r.actual_attendance ?? r.estimated_attendees}${
                  r.actual_attendance ? "" : " (est.)"
                }`
              : null
          }
        />
        <Field label="Revenue" value={fmtMoney(r.actual_revenue)} />
        <Field label="Pricing tier" value={r.pricing_tier} />
        <Field label="Source" value={r.source ? SOURCE_LABEL[r.source] ?? r.source : null} />
        <Field label="Request ID" value={<code className="text-xs">{r.request_id}</code>} />
        <Field
          label="Requester"
          value={r.requester_name && <>{r.requester_name}{r.requester_email && <> · {r.requester_email}</>}</>}
        />
        <Field label="Created" value={fmtDate(r.created_at)} />
      </section>

      {/* Description (calendar / Smartsheet) */}
      {description && (
        <section className="rounded-xl bg-white p-6 ring-1 ring-cgcs-line">
          <div className="mb-2 text-xs uppercase tracking-wide text-cgcs-mute">
            Description
          </div>
          <pre className="whitespace-pre-wrap font-sans text-sm text-cgcs-ink">{description}</pre>
          {calLink && (
            <a
              href={calLink}
              target="_blank"
              rel="noreferrer"
              className="mt-3 inline-block text-xs text-cgcs-mute underline hover:text-cgcs-ink"
            >
              Open in Google Calendar →
            </a>
          )}
        </section>
      )}

      {/* Admin notes */}
      {r.admin_notes && (
        <section className="rounded-xl bg-white p-6 ring-1 ring-cgcs-line">
          <div className="mb-2 text-xs uppercase tracking-wide text-cgcs-mute">Admin notes</div>
          <pre className="whitespace-pre-wrap font-sans text-sm text-cgcs-ink">{r.admin_notes}</pre>
        </section>
      )}

      {/* Source metadata — everything else captured from the original row */}
      {orderedKeys.length > 0 && (
        <section className="rounded-xl bg-white p-6 ring-1 ring-cgcs-line">
          <div className="mb-3 text-xs uppercase tracking-wide text-cgcs-mute">
            Source metadata
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {orderedKeys
              .filter((k) => k !== "description") // already shown above
              .map((k) => (
                <Field
                  key={k}
                  label={META_LABELS[k] ?? k}
                  value={
                    k === "calendar_html_link" ? (
                      <a
                        href={String(meta[k] || "")}
                        target="_blank"
                        rel="noreferrer"
                        className="text-cgcs-mute underline hover:text-cgcs-ink"
                      >
                        Open →
                      </a>
                    ) : (
                      fmtMetaValue(meta[k])
                    )
                  }
                />
              ))}
          </div>
        </section>
      )}
    </div>
  );
}
