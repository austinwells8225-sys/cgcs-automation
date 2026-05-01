import { getImpact } from "@/lib/api";
import { MetricCard } from "@/components/MetricCard";

function fmt(n: number): string {
  return new Intl.NumberFormat("en-US").format(Math.round(n));
}
function money(n: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

export const dynamic = "force-dynamic";

export default async function ImpactPage() {
  const impact = await getImpact("year").catch((e) => ({ error: String(e) } as const));

  if ("error" in impact) {
    return (
      <div className="rounded-lg border border-cgcs-bad/40 bg-red-50 p-6 text-sm text-cgcs-bad">
        Failed to load impact data: {impact.error}
      </div>
    );
  }

  const { current, previous_year } = impact;

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-2xl font-semibold text-cgcs-ink">Impact</h1>
        <p className="text-sm text-cgcs-mute">
          {impact.start} – {impact.end} · year-over-year vs {previous_year.start}
        </p>
      </header>

      {/* Tier 1: Community */}
      <section>
        <h2 className="mb-3 text-lg font-semibold text-cgcs-ink">Community (everything in the space)</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <MetricCard
            label="Total events"
            value={fmt(current.community.total_events)}
            delta={{ current: current.community.total_events, previous: previous_year.community.total_events }}
          />
          <MetricCard
            label="Total people"
            value={fmt(current.community.total_people)}
            delta={{ current: current.community.total_people, previous: previous_year.community.total_people }}
          />
          <MetricCard
            label="Total hours in use"
            value={fmt(current.community.total_hours)}
            delta={{ current: current.community.total_hours, previous: previous_year.community.total_hours }}
          />
          <MetricCard
            label="Total revenue"
            value={money(current.community.total_revenue)}
            delta={{ current: current.community.total_revenue, previous: previous_year.community.total_revenue }}
          />
        </div>
      </section>

      {/* Tier 2: Monetization */}
      <section>
        <h2 className="mb-3 text-lg font-semibold text-cgcs-ink">Monetization</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <MetricCard label="Events" value={fmt(current.monetization.total_events)} delta={{ current: current.monetization.total_events, previous: previous_year.monetization.total_events }} />
          <MetricCard label="People" value={fmt(current.monetization.total_people)} delta={{ current: current.monetization.total_people, previous: previous_year.monetization.total_people }} />
          <MetricCard label="Hours" value={fmt(current.monetization.total_hours)} delta={{ current: current.monetization.total_hours, previous: previous_year.monetization.total_hours }} />
          <MetricCard label="Revenue" value={money(current.monetization.total_revenue)} delta={{ current: current.monetization.total_revenue, previous: previous_year.monetization.total_revenue }} accent="good" />
        </div>
      </section>

      {/* Tier 3: ACC */}
      <section>
        <h2 className="mb-3 text-lg font-semibold text-cgcs-ink">ACC events</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <MetricCard label="Events" value={fmt(current.acc.total_events)} delta={{ current: current.acc.total_events, previous: previous_year.acc.total_events }} />
          <MetricCard label="People" value={fmt(current.acc.total_people)} delta={{ current: current.acc.total_people, previous: previous_year.acc.total_people }} />
          <MetricCard label="Hours" value={fmt(current.acc.total_hours)} delta={{ current: current.acc.total_hours, previous: previous_year.acc.total_hours }} />
        </div>
      </section>

      {/* Tier 4: CGCS — the headline section */}
      <section>
        <h2 className="mb-3 text-lg font-semibold text-cgcs-ink">CGCS (designed / led / co-branded)</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <MetricCard label="Events" value={fmt(current.cgcs.total_events)} delta={{ current: current.cgcs.total_events, previous: previous_year.cgcs.total_events }} />
          <MetricCard label="People" value={fmt(current.cgcs.total_people)} delta={{ current: current.cgcs.total_people, previous: previous_year.cgcs.total_people }} />
          <MetricCard label="Total hours" value={fmt(current.cgcs.total_hours)} delta={{ current: current.cgcs.total_hours, previous: previous_year.cgcs.total_hours }} />
          <MetricCard
            label="Training hours delivered"
            value={fmt(current.cgcs.training_hours)}
            sublabel={`${current.cgcs.training_events} training events`}
            delta={{ current: current.cgcs.training_hours, previous: previous_year.cgcs.training_hours }}
            accent="good"
          />
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="rounded-xl bg-white p-5 ring-1 ring-cgcs-line">
            <div className="text-xs uppercase tracking-wide text-cgcs-mute">On-site vs off-site</div>
            <div className="mt-3 grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-2xl font-semibold text-cgcs-ink">{fmt(current.cgcs.on_site_events)}</div>
                <div className="text-cgcs-mute">on-site events · {fmt(current.cgcs.on_site_hours)} hrs</div>
              </div>
              <div>
                <div className="text-2xl font-semibold text-cgcs-ink">{fmt(current.cgcs.off_site_events)}</div>
                <div className="text-cgcs-mute">off-site events · {fmt(current.cgcs.off_site_hours)} hrs</div>
              </div>
            </div>
          </div>

          <div className="rounded-xl bg-white p-5 ring-1 ring-cgcs-line">
            <div className="text-xs uppercase tracking-wide text-cgcs-mute">Audience breakdown</div>
            <div className="mt-3 grid grid-cols-3 gap-4 text-sm">
              <div>
                <div className="text-2xl font-semibold text-cgcs-ink">{fmt(current.cgcs.audience.students)}</div>
                <div className="text-cgcs-mute">students</div>
              </div>
              <div>
                <div className="text-2xl font-semibold text-cgcs-ink">{fmt(current.cgcs.audience.staff)}</div>
                <div className="text-cgcs-mute">ACC staff/faculty</div>
              </div>
              <div>
                <div className="text-2xl font-semibold text-cgcs-ink">{fmt(current.cgcs.audience.community)}</div>
                <div className="text-cgcs-mute">community</div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
