import Link from "next/link";
import { getReservations, type Reservation } from "@/lib/api";
import { CategoryEditor } from "./CategoryEditor";
import { InlineText, InlineNumber, InlineDate, InlineSelect } from "./InlineEditor";
import { NewEventButton } from "./NewEventButton";

export const dynamic = "force-dynamic";

const STATUSES: { key: string; label: string }[] = [
  { key: "approved", label: "Upcoming" },
  { key: "completed", label: "Completed" },
  { key: "cancelled", label: "Cancelled" },
  { key: "rejected", label: "Declined" },
  { key: "", label: "All" },
];

const CATEGORY_LABEL: Record<string, string> = {
  cgcs: "CGCS",
  acc: "ACC",
  monetization: "Space rental",
};

const CATEGORY_COLOR: Record<string, string> = {
  cgcs: "bg-cgcs-good/10 text-cgcs-good ring-cgcs-good/30",
  acc: "bg-blue-50 text-blue-700 ring-blue-200",
  monetization: "bg-amber-50 text-amber-700 ring-amber-200",
};

const STATUS_COLOR: Record<string, string> = {
  completed: "bg-cgcs-good/10 text-cgcs-good ring-cgcs-good/30",
  approved: "bg-blue-50 text-blue-700 ring-blue-200",
  pending_review: "bg-amber-50 text-amber-700 ring-amber-200",
  cancelled: "bg-gray-100 text-gray-600 ring-gray-300",
  rejected: "bg-red-50 text-cgcs-bad ring-red-200",
};

function fmtDate(s: string): string {
  if (!s) return "—";
  const d = new Date(s + "T00:00:00Z");
  return d.toLocaleDateString("en-US", {
    year: "numeric", month: "short", day: "numeric", timeZone: "UTC",
  });
}

function fmtTimeRange(start: string, end: string): string {
  const tidy = (t: string) => (t === "00:00:00" ? "" : t.slice(0, 5));
  const s = tidy(start), e = tidy(end);
  if (!s && !e) return "—";
  return `${s} – ${e}`;
}

function fmtMoney(v: string | number | null | undefined): string {
  const n = typeof v === "string" ? parseFloat(v) : v ?? 0;
  if (!n) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: 0,
  }).format(n);
}

function Chip({
  label, count, active, href,
}: { label: string; count?: number; active: boolean; href: string }) {
  return (
    <Link
      href={href}
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm ring-1 transition ${
        active
          ? "bg-cgcs-ink text-white ring-cgcs-ink"
          : "bg-white text-cgcs-ink ring-cgcs-line hover:bg-cgcs-bg"
      }`}
    >
      <span>{label}</span>
      {count !== undefined && (
        <span
          className={`rounded-full px-1.5 text-xs ${
            active ? "bg-white/20" : "bg-cgcs-bg text-cgcs-mute"
          }`}
        >
          {count}
        </span>
      )}
    </Link>
  );
}

type SortKey = "date" | "event" | "org" | "lead" | "category" | "status" | "revenue" | "attendees";
type SortDir = "asc" | "desc";
const SORT_KEYS: SortKey[] = ["date", "event", "org", "lead", "category", "status", "revenue", "attendees"];

function SortableHeader({
  label, sortKey, activeSort, activeDir, baseParams, align = "left",
}: {
  label: string;
  sortKey: SortKey;
  activeSort: SortKey;
  activeDir: SortDir;
  baseParams: URLSearchParams;
  align?: "left" | "right";
}) {
  const isActive = activeSort === sortKey;
  // Toggle direction if clicking the active column, otherwise default to asc for
  // text-y columns and desc for date/numbers.
  const numericDefault: SortKey[] = ["date", "revenue", "attendees"];
  const nextDir: SortDir = isActive
    ? activeDir === "asc" ? "desc" : "asc"
    : numericDefault.includes(sortKey) ? "desc" : "asc";

  const q = new URLSearchParams(baseParams);
  q.set("sort", sortKey);
  q.set("dir", nextDir);

  const arrow = isActive ? (activeDir === "asc" ? "↑" : "↓") : "";
  return (
    <th className={`px-4 py-3 ${align === "right" ? "text-right" : "text-left"}`}>
      <Link
        href={`/reservations?${q.toString()}`}
        className={`inline-flex items-center gap-1 hover:text-cgcs-ink ${
          isActive ? "text-cgcs-ink" : ""
        }`}
      >
        <span>{label}</span>
        <span className="text-cgcs-mute">{arrow || "↕"}</span>
      </Link>
    </th>
  );
}

const CATEGORY_TITLE: Record<string, string> = {
  cgcs: "CGCS (designed / led / co-branded)",
  acc: "ACC events",
  monetization: "Monetization (paid space rentals)",
};

// Austin's spreadsheet uses S/A/C single-letter codes. Map them to category.
const CATEGORY_LETTER: Record<string, string> = {
  cgcs: "C",
  acc: "S",
  monetization: "A",
};

// Season tinting from the original P.E.T. spreadsheet color key.
function seasonTint(dateISO: string): string {
  if (!dateISO) return "";
  const month = parseInt(dateISO.slice(5, 7), 10); // 1-12
  if (month >= 3 && month <= 5) return "bg-green-50/60";    // Spring
  if (month >= 6 && month <= 8) return "bg-yellow-50/70";   // Summer
  if (month >= 9 && month <= 11) return "bg-amber-100/50";  // Fall (light brown)
  return ""; // Winter — no tint
}

function fmtDateUS(s: string): string {
  if (!s) return "";
  const d = new Date(s + "T00:00:00Z");
  return d.toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
  });
}

export default async function ReservationsPage({
  searchParams,
}: {
  searchParams: Promise<{
    status?: string; category?: string; sort?: string; dir?: string;
    date_from?: string; date_to?: string;
  }>;
}) {
  const { status, category, sort, dir, date_from, date_to } = await searchParams;
  const activeStatus = status ?? "";
  const activeCategory = category ?? "";
  const activeDateFrom = date_from ?? "";
  const activeDateTo = date_to ?? "";
  const activeSort: SortKey =
    SORT_KEYS.includes((sort as SortKey)) ? (sort as SortKey) : "date";
  const activeDir: SortDir = dir === "asc" ? "asc" : "desc";

  const [filtered, all] = await Promise.all([
    getReservations(
      activeStatus || undefined, 500, activeSort, activeDir,
      activeCategory || undefined,
      activeDateFrom || undefined,
      activeDateTo || undefined,
    ).catch((e) => ({ error: String(e) } as const)),
    getReservations(undefined, 2000).catch(() => null),
  ]);

  if ("error" in filtered) {
    return (
      <div className="rounded-lg border border-cgcs-bad/40 bg-red-50 p-6 text-sm text-cgcs-bad">
        Failed to load reservations: {filtered.error}
      </div>
    );
  }

  const counts: Record<string, number> = { "": all?.count ?? 0 };
  if (all) {
    for (const r of all.reservations) {
      counts[r.status] = (counts[r.status] ?? 0) + 1;
    }
  }

  const rows = filtered.reservations;

  // Preserve sort + category + date state when status chips switch the filter.
  const sortParams = new URLSearchParams();
  if (activeSort !== "date") sortParams.set("sort", activeSort);
  if (activeDir !== "desc") sortParams.set("dir", activeDir);
  if (activeCategory) sortParams.set("category", activeCategory);
  if (activeDateFrom) sortParams.set("date_from", activeDateFrom);
  if (activeDateTo) sortParams.set("date_to", activeDateTo);
  const sortSuffix = sortParams.toString() ? `&${sortParams.toString()}` : "";

  // Header links preserve the active status + category + date filters.
  const headerBaseParams = new URLSearchParams();
  if (activeStatus) headerBaseParams.set("status", activeStatus);
  if (activeCategory) headerBaseParams.set("category", activeCategory);
  if (activeDateFrom) headerBaseParams.set("date_from", activeDateFrom);
  if (activeDateTo) headerBaseParams.set("date_to", activeDateTo);

  // Build a clear-date URL that drops the date filters but keeps the rest.
  const noDate = new URLSearchParams();
  if (activeStatus) noDate.set("status", activeStatus);
  if (activeCategory) noDate.set("category", activeCategory);
  if (activeSort !== "date") noDate.set("sort", activeSort);
  if (activeDir !== "desc") noDate.set("dir", activeDir);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-cgcs-ink">P.E.T. — Proposed Events Tracker</h1>
        <p className="text-sm text-cgcs-mute">
          {filtered.count} {activeStatus || "total"} record
          {filtered.count === 1 ? "" : "s"}
          {activeCategory && (
            <>
              {" · filtered to "}
              <span className="font-medium text-cgcs-ink">
                {CATEGORY_TITLE[activeCategory] ?? activeCategory}
              </span>{" "}
              <Link
                href={`/reservations${
                  activeStatus ? `?status=${activeStatus}` : ""
                }`}
                className="text-cgcs-mute underline hover:text-cgcs-ink"
              >
                clear
              </Link>
            </>
          )}
          {(activeDateFrom || activeDateTo) && (
            <>
              {" · "}
              <span className="font-medium text-cgcs-ink">
                {activeDateFrom ? fmtDateUS(activeDateFrom) : "earliest"}
                {" → "}
                {activeDateTo ? fmtDateUS(activeDateTo) : "latest"}
              </span>{" "}
              <Link
                href={`/reservations${noDate.toString() ? "?" + noDate.toString() : ""}`}
                className="text-cgcs-mute underline hover:text-cgcs-ink"
              >
                clear dates
              </Link>
            </>
          )}
        </p>
        </div>
        <NewEventButton />
      </header>

      <div className="flex flex-wrap gap-2">
        {STATUSES.map((s) => (
          <Chip
            key={s.key || "all"}
            label={s.label}
            count={counts[s.key]}
            active={activeStatus === s.key}
            href={
              s.key
                ? `/reservations?status=${s.key}${sortSuffix}`
                : `/reservations${sortSuffix ? "?" + sortSuffix.slice(1) : ""}`
            }
          />
        ))}
      </div>

      <p className="text-xs text-cgcs-mute">
        Click any cell to edit. Changes save instantly. Click the event name to open the full detail page.
      </p>

      <div className="overflow-x-auto rounded-xl bg-white ring-1 ring-cgcs-line">
        <table className="w-full min-w-[1600px] text-sm">
          <thead className="bg-cgcs-bg text-xs uppercase tracking-wide text-cgcs-mute">
            <tr>
              <SortableHeader label="Date" sortKey="date" activeSort={activeSort} activeDir={activeDir} baseParams={headerBaseParams} />
              <SortableHeader label="Event" sortKey="event" activeSort={activeSort} activeDir={activeDir} baseParams={headerBaseParams} />
              <SortableHeader label="Lead" sortKey="lead" activeSort={activeSort} activeDir={activeDir} baseParams={headerBaseParams} />
              <SortableHeader label="Org" sortKey="org" activeSort={activeSort} activeDir={activeDir} baseParams={headerBaseParams} />
              <SortableHeader label="Tier" sortKey="category" activeSort={activeSort} activeDir={activeDir} baseParams={headerBaseParams} />
              <SortableHeader label="Status" sortKey="status" activeSort={activeSort} activeDir={activeDir} baseParams={headerBaseParams} />
              <SortableHeader label="Revenue" sortKey="revenue" activeSort={activeSort} activeDir={activeDir} baseParams={headerBaseParams} align="right" />
              <SortableHeader label="Attendees" sortKey="attendees" activeSort={activeSort} activeDir={activeDir} baseParams={headerBaseParams} align="right" />
              <th className="px-3 py-3 text-left">Ad Astra</th>
              <th className="px-3 py-3 text-left">Layout</th>
              <th className="px-3 py-3 text-left">Walkthrough</th>
              <th className="px-3 py-3 text-left">AV</th>
              <th className="px-3 py-3 text-left">Catering</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-cgcs-line">
            {rows.length === 0 && (
              <tr>
                <td colSpan={13} className="px-4 py-8 text-center text-cgcs-mute">
                  No reservations match this filter.
                </td>
              </tr>
            )}
            {rows.map((r: Reservation) => {
              const cellCls = "px-2 py-2 align-top";
              const tint = seasonTint(r.requested_date);
              return (
                <tr key={r.id} className={`${tint} hover:bg-cgcs-bg/40`}>
                  {/* Date — inline editable */}
                  <td className={cellCls}>
                    <InlineDate
                      id={r.id}
                      field="requested_date"
                      value={r.requested_date}
                      display={
                        <div>
                          <div className="font-medium">{fmtDate(r.requested_date)}</div>
                          <div className="text-xs text-cgcs-mute">
                            {fmtTimeRange(r.requested_start_time, r.requested_end_time)}
                          </div>
                        </div>
                      }
                    />
                  </td>
                  {/* Event — clickable to detail */}
                  <td className={cellCls}>
                    <Link
                      href={`/reservations/${r.id}`}
                      className="block rounded px-1.5 py-0.5 text-cgcs-ink hover:bg-cgcs-bg/70"
                    >
                      <div className="font-medium">{r.event_name}</div>
                      {r.room_requested && (
                        <div className="text-xs text-cgcs-mute">{r.room_requested}</div>
                      )}
                    </Link>
                  </td>
                  {/* Lead — inline editable text */}
                  <td className={cellCls}>
                    <InlineText id={r.id} field="cgcs_lead" value={r.cgcs_lead} placeholder="Assign…" />
                  </td>
                  {/* Org — inline editable */}
                  <td className={cellCls}>
                    <InlineText
                      id={r.id}
                      field="requester_organization"
                      value={r.requester_organization}
                      className="text-cgcs-mute"
                    />
                  </td>
                  {/* Tier — category editor with S/A/C letter prefix */}
                  <td className={cellCls}>
                    <div className="flex items-center gap-1.5">
                      {r.event_category && (
                        <span
                          className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-cgcs-ink text-[10px] font-bold text-white"
                          title={`Letter code: ${CATEGORY_LETTER[r.event_category] ?? "?"}`}
                        >
                          {CATEGORY_LETTER[r.event_category] ?? "?"}
                        </span>
                      )}
                      <CategoryEditor id={r.id} current={r.event_category} />
                    </div>
                  </td>
                  {/* Status — inline editable dropdown */}
                  <td className={cellCls}>
                    <InlineSelect
                      id={r.id}
                      field="status"
                      value={r.status}
                      options={[
                        { value: "approved", label: "Upcoming" },
                        { value: "completed", label: "Completed" },
                        { value: "cancelled", label: "Cancelled" },
                        { value: "rejected", label: "Declined" },
                        { value: "pending_review", label: "Pending" },
                      ]}
                      display={
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-xs ring-1 ${
                            STATUS_COLOR[r.status] ?? "bg-gray-50 text-gray-600 ring-gray-200"
                          }`}
                        >
                          {r.status === "pending_review" ? "pending" : r.status}
                        </span>
                      }
                    />
                  </td>
                  {/* Revenue — inline number */}
                  <td className={cellCls}>
                    <InlineNumber
                      id={r.id}
                      field="actual_revenue"
                      value={r.actual_revenue as number | null | undefined}
                      display={<span className="text-cgcs-ink">{fmtMoney(r.actual_revenue)}</span>}
                    />
                  </td>
                  {/* Attendees — inline number */}
                  <td className={cellCls}>
                    <InlineNumber
                      id={r.id}
                      field="actual_attendance"
                      value={r.actual_attendance}
                    />
                  </td>
                  {/* Ad Astra — metadata text */}
                  <td className={cellCls}>
                    <InlineText id={r.id} field="ad_astra" value={r.meta_ad_astra} />
                  </td>
                  {/* Layout — metadata text */}
                  <td className={cellCls}>
                    <InlineText id={r.id} field="floor_layout" value={r.meta_layout} />
                  </td>
                  {/* Walkthrough — metadata text */}
                  <td className={cellCls}>
                    <InlineText id={r.id} field="walkthrough" value={r.meta_walkthrough} />
                  </td>
                  {/* AV — metadata text */}
                  <td className={cellCls}>
                    <InlineText id={r.id} field="av" value={r.meta_av} />
                  </td>
                  {/* Catering — metadata text */}
                  <td className={cellCls}>
                    <InlineText id={r.id} field="catering" value={r.meta_catering} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
