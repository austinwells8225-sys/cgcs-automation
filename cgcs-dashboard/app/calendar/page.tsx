import Link from "next/link";
import { getCalendarEvents, type CalendarEvent } from "@/lib/api";
import { syncCalendarAction } from "./actions";
import { SyncButton } from "./SyncButton";

export const dynamic = "force-dynamic";

// month math, UTC-anchored so SSR == client render
function parseMonth(s: string | undefined): { year: number; month: number } {
  // month is 0-indexed in Date but we accept 1-12 in URL
  if (s && /^\d{4}-\d{2}$/.test(s)) {
    const [y, m] = s.split("-").map(Number);
    return { year: y, month: m - 1 };
  }
  const now = new Date();
  return { year: now.getUTCFullYear(), month: now.getUTCMonth() };
}

function monthName(year: number, month: number): string {
  return new Date(Date.UTC(year, month, 1)).toLocaleString("en-US", {
    month: "long", year: "numeric", timeZone: "UTC",
  });
}

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function shiftMonth(year: number, month: number, delta: number): string {
  const d = new Date(Date.UTC(year, month + delta, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

function eventDateKey(ev: CalendarEvent): string {
  // For all-day: start is already YYYY-MM-DD; for timed: take date portion.
  return ev.start.slice(0, 10);
}

function fmtTime(iso: string): string {
  // "2026-07-15T13:00:00-06:00" -> "1:00 PM"
  const m = iso.match(/T(\d{2}):(\d{2})/);
  if (!m) return "";
  let h = parseInt(m[1], 10);
  const ap = h >= 12 ? "PM" : "AM";
  if (h > 12) h -= 12;
  if (h === 0) h = 12;
  return `${h}:${m[2]} ${ap}`;
}

export default async function CalendarPage({
  searchParams,
}: {
  searchParams: Promise<{ m?: string }>;
}) {
  const { m } = await searchParams;
  const { year, month } = parseMonth(m);

  // Range: first day of selected month through first day of next month.
  const startDate = new Date(Date.UTC(year, month, 1));
  const endDate = new Date(Date.UTC(year, month + 1, 1));
  const startISO = isoDate(startDate);
  const endISO = isoDate(endDate);

  const data = await getCalendarEvents(startISO, endISO).catch((e) => ({
    error: String(e),
  } as const));

  if ("error" in data) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold text-cgcs-ink">Calendar</h1>
        <div className="rounded-lg border border-cgcs-bad/40 bg-red-50 p-6 text-sm text-cgcs-bad">
          Failed to load calendar events: {data.error}
        </div>
      </div>
    );
  }

  // Bucket events by YYYY-MM-DD
  const byDay = new Map<string, CalendarEvent[]>();
  for (const ev of data.events) {
    const k = eventDateKey(ev);
    const list = byDay.get(k) ?? [];
    list.push(ev);
    byDay.set(k, list);
  }

  // Build the 6x7 grid: start from the Sunday on/before the first of the month
  const firstWeekday = startDate.getUTCDay(); // 0 = Sun
  const gridStart = new Date(Date.UTC(year, month, 1 - firstWeekday));
  const cells: { date: Date; inMonth: boolean }[] = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(gridStart.getTime() + i * 24 * 60 * 60 * 1000);
    cells.push({ date: d, inMonth: d.getUTCMonth() === month });
  }

  const todayISO = isoDate(new Date());
  const prevMonth = shiftMonth(year, month, -1);
  const nextMonth = shiftMonth(year, month, 1);

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-cgcs-ink">Calendar</h1>
          <p className="text-sm text-cgcs-mute">
            {data.count} event{data.count === 1 ? "" : "s"} this month · CGCS Events calendar (live)
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <form action={syncCalendarAction}>
            <SyncButton />
          </form>
          <Link
            href={`/calendar?m=${prevMonth}`}
            className="rounded-md bg-white px-3 py-1 ring-1 ring-cgcs-line hover:bg-cgcs-bg"
          >
            ← Prev
          </Link>
          <div className="px-2 font-medium text-cgcs-ink">{monthName(year, month)}</div>
          <Link
            href={`/calendar?m=${nextMonth}`}
            className="rounded-md bg-white px-3 py-1 ring-1 ring-cgcs-line hover:bg-cgcs-bg"
          >
            Next →
          </Link>
        </div>
      </header>

      <div className="overflow-hidden rounded-xl bg-white ring-1 ring-cgcs-line">
        <div className="grid grid-cols-7 border-b border-cgcs-line bg-cgcs-bg text-xs uppercase tracking-wide text-cgcs-mute">
          {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
            <div key={d} className="px-2 py-2 text-center">{d}</div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {cells.map(({ date, inMonth }) => {
            const key = isoDate(date);
            const events = byDay.get(key) ?? [];
            const isToday = key === todayISO;
            return (
              <div
                key={key}
                className={`min-h-[110px] border-b border-r border-cgcs-line p-2 ${
                  inMonth ? "bg-white" : "bg-cgcs-bg/40"
                }`}
              >
                <div
                  className={`mb-1 inline-flex h-6 min-w-6 items-center justify-center rounded-full px-1 text-xs ${
                    isToday
                      ? "bg-cgcs-ink font-semibold text-white"
                      : inMonth ? "text-cgcs-ink" : "text-cgcs-mute"
                  }`}
                >
                  {date.getUTCDate()}
                </div>
                <div className="space-y-1">
                  {events.slice(0, 3).map((ev) => (
                    <a
                      key={ev.id}
                      href={ev.html_link || "#"}
                      target="_blank"
                      rel="noreferrer"
                      title={ev.summary}
                      className="block truncate rounded px-1.5 py-0.5 text-[11px] bg-cgcs-good/10 text-cgcs-ink hover:bg-cgcs-good/20"
                    >
                      {!ev.all_day && (
                        <span className="mr-1 text-cgcs-mute">{fmtTime(ev.start)}</span>
                      )}
                      {ev.summary}
                    </a>
                  ))}
                  {events.length > 3 && (
                    <div className="text-[11px] text-cgcs-mute">+{events.length - 3} more</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
