import { getReservations, type Reservation } from "@/lib/api";

export const dynamic = "force-dynamic";

// ============================================================
// Heuristics — classify difficulty + detect problems
// ============================================================

type Difficulty = "easy" | "mid" | "hard";

type DifficultyReport = {
  level: Difficulty;
  reasons: string[];
};

function classify(r: Reservation): DifficultyReport {
  const reasons: string[] = [];

  // Time / date signals
  const d = new Date(r.requested_date + "T00:00:00");
  const dow = d.getDay(); // 0=Sun, 6=Sat
  if (dow === 0 || dow === 6) reasons.push("Weekend — needs police coverage");

  const startHour = parseInt(r.requested_start_time?.split(":")[0] ?? "12", 10);
  const endHour = parseInt(r.requested_end_time?.split(":")[0] ?? "12", 10);
  if (startHour < 6) reasons.push(`Early start (${r.requested_start_time})`);
  if (endHour >= 22) reasons.push(`Late end (${r.requested_end_time})`);

  const durationHrs = endHour - startHour;
  if (durationHrs >= 10) reasons.push(`Full-day event (${durationHrs}h)`);

  // Attendance signals
  const attendees = r.estimated_attendees ?? r.actual_attendance ?? 0;
  if (attendees >= 100) reasons.push(`Large attendance (${attendees})`);
  else if (attendees >= 50) reasons.push(`Medium-large attendance (${attendees})`);

  // Setup complexity from source_metadata
  if (r.meta_av && r.meta_av.trim() && r.meta_av.toLowerCase() !== "no") {
    reasons.push(`AV: ${r.meta_av}`);
  }
  if (r.meta_catering && r.meta_catering.trim() && r.meta_catering.toLowerCase() !== "no") {
    reasons.push(`Catering: ${r.meta_catering}`);
  }

  // External-org signals (best-effort)
  if (r.event_category === "monetization") reasons.push("External / paid event");

  // Decide level
  const hardSignals = [
    dow === 0 || dow === 6,
    startHour < 6,
    endHour >= 22,
    attendees >= 100,
    durationHrs >= 10,
  ].filter(Boolean).length;

  const midSignals = [
    attendees >= 50,
    r.meta_av && r.meta_av.trim() && r.meta_av.toLowerCase() !== "no",
    r.meta_catering && r.meta_catering.trim() && r.meta_catering.toLowerCase() !== "no",
    r.event_category === "monetization",
  ].filter(Boolean).length;

  let level: Difficulty = "easy";
  if (hardSignals >= 1) level = "hard";
  else if (midSignals >= 2) level = "mid";
  else if (midSignals >= 1) level = "mid";

  if (reasons.length === 0) reasons.push("Small daytime event, no special setup");

  return { level, reasons };
}

function toMinutes(t: string): number {
  const [hh, mm] = t.split(":").map((x) => parseInt(x, 10));
  return (hh || 0) * 60 + (mm || 0);
}

type Conflict = { a: Reservation; b: Reservation; date: string };

function findConflicts(rows: Reservation[]): Conflict[] {
  const byDate = new Map<string, Reservation[]>();
  for (const r of rows) {
    const k = r.requested_date;
    if (!byDate.has(k)) byDate.set(k, []);
    byDate.get(k)!.push(r);
  }
  const out: Conflict[] = [];
  for (const [date, group] of byDate) {
    if (group.length < 2) continue;
    for (let i = 0; i < group.length; i++) {
      for (let j = i + 1; j < group.length; j++) {
        const a = group[i];
        const b = group[j];
        const aStart = toMinutes(a.requested_start_time);
        const aEnd = toMinutes(a.requested_end_time);
        const bStart = toMinutes(b.requested_start_time);
        const bEnd = toMinutes(b.requested_end_time);
        const overlap = aStart < bEnd && bStart < aEnd;
        // Same room conflicts are worse, but ANY same-day time overlap is
        // worth surfacing since we share one venue.
        if (overlap) out.push({ a, b, date });
      }
    }
  }
  return out;
}

type Turnover = { from: Reservation; to: Reservation; gapMin: number };

function findTurnovers(rows: Reservation[], thresholdMin = 120): Turnover[] {
  const byDate = new Map<string, Reservation[]>();
  for (const r of rows) {
    const k = r.requested_date;
    if (!byDate.has(k)) byDate.set(k, []);
    byDate.get(k)!.push(r);
  }
  const out: Turnover[] = [];
  for (const group of byDate.values()) {
    if (group.length < 2) continue;
    const sorted = [...group].sort(
      (x, y) => toMinutes(x.requested_start_time) - toMinutes(y.requested_start_time),
    );
    for (let i = 0; i < sorted.length - 1; i++) {
      const a = sorted[i];
      const b = sorted[i + 1];
      const gap = toMinutes(b.requested_start_time) - toMinutes(a.requested_end_time);
      if (gap >= 0 && gap < thresholdMin) {
        out.push({ from: a, to: b, gapMin: gap });
      }
    }
  }
  return out;
}

type Flag = { reservation: Reservation; flags: string[] };

function findMissingData(rows: Reservation[]): Flag[] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const out: Flag[] = [];
  for (const r of rows) {
    const flags: string[] = [];
    const eventDate = new Date(r.requested_date + "T00:00:00");
    const daysOut = Math.round((eventDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));

    if (r.status === "approved" && !r.cgcs_lead) flags.push("No CGCS lead assigned");

    const attendees = r.estimated_attendees ?? r.actual_attendance ?? 0;
    if (attendees >= 50 && !r.meta_ad_astra) flags.push("Large event but no Ad Astra reservation");

    if (daysOut >= 0 && daysOut <= 14 && !r.meta_walkthrough)
      flags.push(`Event in ${daysOut} days — no walkthrough scheduled`);

    if (attendees >= 25 && !r.meta_layout) flags.push("Layout not specified");

    if (flags.length > 0) out.push({ reservation: r, flags });
  }
  return out;
}

// ============================================================
// Page
// ============================================================

export default async function DiagnosticsPage() {
  const today = new Date();
  const horizon = new Date();
  horizon.setDate(horizon.getDate() + 90);
  const date_from = today.toISOString().slice(0, 10);
  const date_to = horizon.toISOString().slice(0, 10);

  let rows: Reservation[] = [];
  let fetchError: string | null = null;
  try {
    const r = await getReservations(undefined, 500, "requested_date", "asc", undefined, date_from, date_to);
    rows = r.reservations.filter((x) => x.status !== "cancelled" && x.status !== "rejected");
  } catch (e) {
    fetchError = e instanceof Error ? e.message : String(e);
  }

  if (fetchError) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-8">
        <h1 className="text-xl font-semibold mb-4">Diagnostics</h1>
        <div className="rounded border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
          Couldn't load reservations: {fetchError}
        </div>
      </main>
    );
  }

  const classified = rows.map((r) => ({ r, c: classify(r) }));
  const byLevel = {
    hard: classified.filter((x) => x.c.level === "hard"),
    mid: classified.filter((x) => x.c.level === "mid"),
    easy: classified.filter((x) => x.c.level === "easy"),
  };
  const conflicts = findConflicts(rows);
  const turnovers = findTurnovers(rows);
  const flagged = findMissingData(rows);

  return (
    <main className="mx-auto max-w-6xl px-6 py-8 space-y-8">
      <header>
        <h1 className="text-xl font-semibold text-cgcs-ink">Diagnostics</h1>
        <p className="text-sm text-cgcs-mute mt-1">
          Looking at {rows.length} active event{rows.length === 1 ? "" : "s"} over the next 90 days
          (through {date_to}).
        </p>
      </header>

      {/* Difficulty distribution */}
      <section>
        <h2 className="text-base font-semibold text-cgcs-ink mb-3">Difficulty distribution</h2>
        <div className="grid gap-3 md:grid-cols-3">
          <TierCard
            level="hard"
            label="Hard"
            count={byLevel.hard.length}
            blurb="Weekend, after-hours, large attendance, or full-day."
          />
          <TierCard
            level="mid"
            label="Medium"
            count={byLevel.mid.length}
            blurb="Catering or AV needed, medium attendance, or external/paid."
          />
          <TierCard
            level="easy"
            label="Easy"
            count={byLevel.easy.length}
            blurb="Small daytime event, minimal setup."
          />
        </div>
      </section>

      {/* Hard events list */}
      {byLevel.hard.length > 0 && (
        <section>
          <h2 className="text-base font-semibold text-cgcs-ink mb-3">
            Hard events ({byLevel.hard.length})
          </h2>
          <div className="space-y-2">
            {byLevel.hard.slice(0, 25).map(({ r, c }) => (
              <EventReasonRow key={r.id} r={r} reasons={c.reasons} level="hard" />
            ))}
          </div>
        </section>
      )}

      {/* Medium events */}
      {byLevel.mid.length > 0 && (
        <section>
          <h2 className="text-base font-semibold text-cgcs-ink mb-3">
            Medium events ({byLevel.mid.length})
          </h2>
          <div className="space-y-2">
            {byLevel.mid.slice(0, 15).map(({ r, c }) => (
              <EventReasonRow key={r.id} r={r} reasons={c.reasons} level="mid" />
            ))}
          </div>
        </section>
      )}

      {/* Conflicts */}
      <section>
        <h2 className="text-base font-semibold text-cgcs-ink mb-3">
          Calendar conflicts ({conflicts.length})
        </h2>
        {conflicts.length === 0 ? (
          <p className="text-sm text-cgcs-mute">No overlapping events detected.</p>
        ) : (
          <div className="space-y-2">
            {conflicts.slice(0, 25).map((c, i) => (
              <ConflictRow key={i} c={c} />
            ))}
          </div>
        )}
      </section>

      {/* Turnovers */}
      <section>
        <h2 className="text-base font-semibold text-cgcs-ink mb-3">
          Tight turnovers ({turnovers.length})
        </h2>
        <p className="text-xs text-cgcs-mute mb-2">
          Same-day events with less than 2 hours between one ending and the next starting.
        </p>
        {turnovers.length === 0 ? (
          <p className="text-sm text-cgcs-mute">Nothing tight in the next 90 days.</p>
        ) : (
          <div className="space-y-2">
            {turnovers.slice(0, 25).map((t, i) => (
              <TurnoverRow key={i} t={t} />
            ))}
          </div>
        )}
      </section>

      {/* Missing data flags */}
      <section>
        <h2 className="text-base font-semibold text-cgcs-ink mb-3">
          Missing-data flags ({flagged.length})
        </h2>
        {flagged.length === 0 ? (
          <p className="text-sm text-cgcs-mute">Everything has what it needs.</p>
        ) : (
          <div className="space-y-2">
            {flagged.slice(0, 25).map((f) => (
              <FlagRow key={f.reservation.id} f={f} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

// ============================================================
// UI bits
// ============================================================

const TIER_BG: Record<Difficulty, string> = {
  hard: "bg-red-50 border-red-300",
  mid: "bg-amber-50 border-amber-300",
  easy: "bg-emerald-50 border-emerald-300",
};
const TIER_PILL: Record<Difficulty, string> = {
  hard: "bg-red-600 text-white",
  mid: "bg-amber-500 text-white",
  easy: "bg-emerald-600 text-white",
};

function TierCard({
  level,
  label,
  count,
  blurb,
}: {
  level: Difficulty;
  label: string;
  count: number;
  blurb: string;
}) {
  return (
    <div className={`rounded border p-4 ${TIER_BG[level]}`}>
      <div className="flex items-baseline justify-between mb-1">
        <span className={`rounded px-2 py-0.5 text-xs uppercase tracking-wide ${TIER_PILL[level]}`}>
          {label}
        </span>
        <span className="text-2xl font-semibold text-cgcs-ink">{count}</span>
      </div>
      <p className="text-xs text-cgcs-mute mt-2">{blurb}</p>
    </div>
  );
}

function EventReasonRow({
  r,
  reasons,
  level,
}: {
  r: Reservation;
  reasons: string[];
  level: Difficulty;
}) {
  return (
    <div className={`rounded border px-3 py-2 ${TIER_BG[level]}`}>
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-medium text-cgcs-ink truncate">{r.event_name}</div>
          <div className="text-xs text-cgcs-mute">
            {r.requested_date} · {r.requested_start_time}–{r.requested_end_time}
            {r.requester_organization ? ` · ${r.requester_organization}` : ""}
          </div>
        </div>
        <span className={`shrink-0 rounded px-2 py-0.5 text-[10px] uppercase ${TIER_PILL[level]}`}>
          {level}
        </span>
      </div>
      <ul className="mt-1 text-xs text-cgcs-ink space-y-0.5">
        {reasons.map((reason, i) => (
          <li key={i}>· {reason}</li>
        ))}
      </ul>
    </div>
  );
}

function ConflictRow({ c }: { c: Conflict }) {
  return (
    <div className="rounded border border-red-300 bg-red-50 px-3 py-2">
      <div className="text-xs font-medium text-red-800 mb-1">
        {c.date} — time overlap
      </div>
      <div className="text-sm text-cgcs-ink">
        <span className="font-medium">{c.a.event_name}</span>{" "}
        ({c.a.requested_start_time}–{c.a.requested_end_time}) ↔{" "}
        <span className="font-medium">{c.b.event_name}</span>{" "}
        ({c.b.requested_start_time}–{c.b.requested_end_time})
      </div>
    </div>
  );
}

function TurnoverRow({ t }: { t: Turnover }) {
  const hrs = Math.floor(t.gapMin / 60);
  const mins = t.gapMin % 60;
  const gapStr = hrs > 0 ? `${hrs}h ${mins}m` : `${mins}m`;
  return (
    <div className="rounded border border-amber-300 bg-amber-50 px-3 py-2">
      <div className="text-xs font-medium text-amber-800 mb-1">
        {t.from.requested_date} — {gapStr} gap
      </div>
      <div className="text-sm text-cgcs-ink">
        <span className="font-medium">{t.from.event_name}</span> ends {t.from.requested_end_time}{" "}
        → <span className="font-medium">{t.to.event_name}</span> starts {t.to.requested_start_time}
      </div>
    </div>
  );
}

function FlagRow({ f }: { f: Flag }) {
  return (
    <div className="rounded border border-cgcs-line bg-white px-3 py-2">
      <div className="text-sm font-medium text-cgcs-ink">
        {f.reservation.event_name}{" "}
        <span className="text-xs text-cgcs-mute font-normal">· {f.reservation.requested_date}</span>
      </div>
      <ul className="mt-1 text-xs text-amber-700 space-y-0.5">
        {f.flags.map((flag, i) => (
          <li key={i}>· {flag}</li>
        ))}
      </ul>
    </div>
  );
}
