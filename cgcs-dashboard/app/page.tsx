import Link from "next/link";
import { getImpact, getBudgetSummary } from "@/lib/api";
import { MetricCard } from "@/components/MetricCard";

function TierHeader({ title, href }: { title: string; href: string }) {
  return (
    <div className="mb-3 flex items-baseline justify-between">
      <h2 className="text-lg font-semibold text-cgcs-ink">{title}</h2>
      <Link
        href={href}
        className="text-xs text-cgcs-mute hover:text-cgcs-ink"
      >
        View events →
      </Link>
    </div>
  );
}

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
function moneyExact(n: number, withCents = false): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: withCents ? 2 : 0,
    maximumFractionDigits: withCents ? 2 : 0,
  }).format(n);
}

export const dynamic = "force-dynamic";

// Anchor Impact to the current academic fiscal year (Sep 1 – Aug 31).
// Determined by the current date: if we're past September, the FY starts this
// calendar year; otherwise it started the previous calendar year.
function fiscalYearStart(): string {
  const d = new Date();
  const y = d.getMonth() >= 8 ? d.getFullYear() : d.getFullYear() - 1;
  return `${y}-09-01`;
}

export default async function ImpactPage() {
  const [impact, budget] = await Promise.all([
    getImpact("year", fiscalYearStart()).catch((e) => ({ error: String(e) } as const)),
    getBudgetSummary().catch(() => null),
  ]);

  if ("error" in impact) {
    return (
      <div className="rounded-lg border border-cgcs-bad/40 bg-red-50 p-6 text-sm text-cgcs-bad">
        Failed to load impact data: {impact.error}
      </div>
    );
  }

  const { current } = impact;
  const fyLabel = budget && !("error" in budget) ? budget.fiscal_year.label : "Current fiscal year";

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-2xl font-semibold text-cgcs-ink">Impact</h1>
        <p className="text-sm text-cgcs-mute">
          {fyLabel} ·{" "}
          {new Date(impact.start + "T00:00:00Z").toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric",timeZone:"UTC"})}
          {" → "}
          {new Date(impact.end + "T00:00:00Z").toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric",timeZone:"UTC"})}
          {" · "}
          <Link
            href={`/reservations?date_from=${impact.start}&date_to=${impact.end}`}
            className="underline hover:text-cgcs-ink"
          >
            view all {fmt(current.community.total_events)} events in this window →
          </Link>
        </p>
      </header>

      {/* Budget snapshot — real numbers from the Fogg Ledger */}
      {budget && !("error" in budget) && (
        <section className="rounded-xl border border-amber-300/50 bg-gradient-to-r from-amber-50 to-yellow-50 p-6 ring-1 ring-amber-200">
          <div className="flex items-baseline justify-between">
            <div>
              <div className="text-xs uppercase tracking-wide text-amber-700">
                Fogg Ledger · {budget.fiscal_year.label}
              </div>
              <div className="mt-1 text-3xl font-semibold text-cgcs-ink">
                {moneyExact(budget.totals.current_balance, true)}
              </div>
              <div className="text-xs text-amber-700/80">
                current operating balance ·
                {" "}{moneyExact(budget.burn_rate.per_day, true)}/day allowance
                {" "}({budget.burn_rate.days_left} days left in FY)
              </div>
            </div>
            <div className="grid grid-cols-3 gap-6 text-right">
              <div>
                <div className="text-xs text-amber-700/80">YTD expense</div>
                <div className="text-xl font-semibold text-cgcs-bad">−{moneyExact(budget.totals.expense)}</div>
              </div>
              <div>
                <div className="text-xs text-amber-700/80">YTD revenue</div>
                <div className="text-xl font-semibold text-cgcs-good">+{moneyExact(budget.totals.revenue)}</div>
              </div>
              <div>
                <Link
                  href="/budget"
                  className="inline-block rounded-md bg-cgcs-ink px-3 py-1.5 text-sm text-white hover:opacity-90"
                >
                  View budget →
                </Link>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Tier 1: Community */}
      <section>
        <TierHeader title="Community (everything in the space)" href="/reservations" />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <MetricCard label="Total events" value={fmt(current.community.total_events)} />
          <MetricCard label="Total people" value={fmt(current.community.total_people)} />
          <MetricCard label="Total hours in use" value={fmt(current.community.total_hours)} />
          <MetricCard label="Total revenue" value={money(current.community.total_revenue)} />
        </div>
      </section>

      {/* Tier 2: Monetization */}
      <section>
        <TierHeader title="Monetization" href="/reservations?category=monetization" />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <MetricCard label="Events" value={fmt(current.monetization.total_events)} />
          <MetricCard label="People" value={fmt(current.monetization.total_people)} />
          <MetricCard label="Hours" value={fmt(current.monetization.total_hours)} />
          <MetricCard label="Revenue" value={money(current.monetization.total_revenue)} accent="good" />
        </div>
      </section>

      {/* Tier 3: ACC */}
      <section>
        <TierHeader title="ACC events" href="/reservations?category=acc" />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <MetricCard label="Events" value={fmt(current.acc.total_events)} />
          <MetricCard label="People" value={fmt(current.acc.total_people)} />
          <MetricCard label="Hours" value={fmt(current.acc.total_hours)} />
        </div>
      </section>

      {/* Tier 4: CGCS — the headline section */}
      <section>
        <TierHeader title="CGCS (designed / led / co-branded)" href="/reservations?category=cgcs" />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <MetricCard label="Events" value={fmt(current.cgcs.total_events)} />
          <MetricCard label="People" value={fmt(current.cgcs.total_people)} />
          <MetricCard label="Total hours" value={fmt(current.cgcs.total_hours)} />
          <MetricCard
            label="Training hours delivered"
            value={fmt(current.cgcs.training_hours)}
            sublabel={`${current.cgcs.training_events} training events`}
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
