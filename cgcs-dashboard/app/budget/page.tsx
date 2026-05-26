import Link from "next/link";
import { getBudgetSummary, type BudgetSummary } from "@/lib/api";

export const dynamic = "force-dynamic";

function money(n: number, withCents = false): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: withCents ? 2 : 0,
    maximumFractionDigits: withCents ? 2 : 0,
  }).format(n);
}

function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s + "T00:00:00Z");
  return d.toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
  });
}

const CATEGORY_COLOR: Record<string, string> = {
  "Wage": "bg-purple-50 text-purple-700 ring-purple-200",
  "Event Income": "bg-cgcs-good/10 text-cgcs-good ring-cgcs-good/30",
  "Event Expenses": "bg-amber-50 text-amber-700 ring-amber-200",
  "Office Equipment": "bg-blue-50 text-blue-700 ring-blue-200",
  "Subscription": "bg-indigo-50 text-indigo-700 ring-indigo-200",
  "Food": "bg-orange-50 text-orange-700 ring-orange-200",
  "Police Coverage": "bg-red-50 text-red-700 ring-red-200",
  "Miscellaneous": "bg-gray-50 text-gray-600 ring-gray-200",
};

function CategoryPill({ name }: { name: string | null }) {
  if (!name) return <span className="text-cgcs-mute">—</span>;
  const cls = CATEGORY_COLOR[name] ?? "bg-gray-50 text-gray-600 ring-gray-200";
  return (
    <Link
      href={`/budget/ledger?category=${encodeURIComponent(name)}`}
      className={`inline-flex rounded-full px-2 py-0.5 text-xs ring-1 ${cls}`}
    >
      {name}
    </Link>
  );
}

export default async function BudgetPage() {
  let data: BudgetSummary | { error: string };
  try {
    data = await getBudgetSummary();
  } catch (e) {
    data = { error: String(e) };
  }
  if ("error" in data) {
    return (
      <div className="rounded-lg border border-cgcs-bad/40 bg-red-50 p-6 text-sm text-cgcs-bad">
        Failed to load budget: {data.error}
      </div>
    );
  }

  const { fiscal_year: fy, totals, burn_rate: br, categories, recent_transactions } = data;
  const net = totals.revenue - totals.expense;

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold text-cgcs-ink">Budget — Fogg Ledger</h1>
        <p className="text-sm text-cgcs-mute">
          {fy.label} · {fmtDate(fy.start_date)} – {fmtDate(fy.end_date)} · {totals.txn_count} transactions
        </p>
      </header>

      {/* Burn rate gold banner */}
      <section className="rounded-xl border border-amber-300/50 bg-gradient-to-r from-amber-50 to-yellow-50 p-6 ring-1 ring-amber-200">
        <div className="text-xs uppercase tracking-wide text-amber-700">
          Burn rate · spending allowance for {fy.label}
        </div>
        <div className="mt-2 flex items-baseline justify-between gap-6">
          <div>
            <div className="text-xs text-amber-700/80">Current balance</div>
            <div className="text-4xl font-semibold text-cgcs-ink">{money(totals.current_balance, true)}</div>
          </div>
          <div className="grid grid-cols-3 gap-6 text-right">
            <div>
              <div className="text-xs text-amber-700/80">Per day · {br.days_left} days left</div>
              <div className="text-2xl font-semibold text-cgcs-ink">{money(br.per_day, true)}</div>
            </div>
            <div>
              <div className="text-xs text-amber-700/80">Per week · {br.weeks_left} weeks</div>
              <div className="text-2xl font-semibold text-cgcs-ink">{money(br.per_week)}</div>
            </div>
            <div>
              <div className="text-xs text-amber-700/80">Per month · {br.months_left} months</div>
              <div className="text-2xl font-semibold text-cgcs-ink">{money(br.per_month)}</div>
            </div>
          </div>
        </div>
        <div className="mt-3 text-xs text-amber-700/80">
          Updates daily. Calculated as current balance ÷ time remaining until {fmtDate(fy.end_date)}.
        </div>
      </section>

      {/* FY totals grid */}
      <section className="grid grid-cols-1 gap-4 md:grid-cols-5">
        <div className="rounded-xl bg-white p-5 ring-1 ring-cgcs-line">
          <div className="text-xs uppercase tracking-wide text-cgcs-mute">Starting balance</div>
          <div className="mt-2 text-2xl font-semibold text-cgcs-ink">{money(fy.starting_balance)}</div>
        </div>
        <div className="rounded-xl bg-white p-5 ring-1 ring-cgcs-line">
          <div className="text-xs uppercase tracking-wide text-cgcs-mute">Total expense</div>
          <div className="mt-2 text-2xl font-semibold text-cgcs-bad">−{money(totals.expense)}</div>
          <div className="mt-1 text-xs text-cgcs-mute">
            Wages {money(totals.wage_expense)} · Other {money(totals.non_wage_expense)}
          </div>
        </div>
        <div className="rounded-xl bg-white p-5 ring-1 ring-cgcs-line">
          <div className="text-xs uppercase tracking-wide text-cgcs-mute">Revenue earned</div>
          <div className="mt-2 text-2xl font-semibold text-cgcs-good">+{money(totals.revenue)}</div>
        </div>
        <div className="rounded-xl bg-white p-5 ring-1 ring-cgcs-line">
          <div className="text-xs uppercase tracking-wide text-cgcs-mute">Net change</div>
          <div className={`mt-2 text-2xl font-semibold ${net < 0 ? "text-cgcs-bad" : "text-cgcs-good"}`}>
            {net < 0 ? "−" : "+"}{money(Math.abs(net))}
          </div>
        </div>
        <div className="rounded-xl bg-white p-5 ring-1 ring-cgcs-line">
          <div className="text-xs uppercase tracking-wide text-cgcs-mute">Holdover → next FY</div>
          <div className="mt-2 text-2xl font-semibold text-cgcs-ink">{money(fy.holdover_to_next)}</div>
        </div>
      </section>

      {/* Category breakdown */}
      <section className="rounded-xl bg-white p-6 ring-1 ring-cgcs-line">
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="text-lg font-semibold text-cgcs-ink">FY spend by category</h2>
          <Link
            href="/budget/ledger"
            className="text-xs text-cgcs-mute hover:text-cgcs-ink"
          >
            View all transactions →
          </Link>
        </div>
        <table className="w-full text-sm">
          <thead className="text-xs uppercase tracking-wide text-cgcs-mute">
            <tr>
              <th className="pb-3 text-left">Category</th>
              <th className="pb-3 text-right">Expense</th>
              <th className="pb-3 text-right">Revenue</th>
              <th className="pb-3 text-right">Net</th>
              <th className="pb-3 text-right text-cgcs-mute/60">Rows</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-cgcs-line">
            {categories.map((c) => (
              <tr key={c.category} className="hover:bg-cgcs-bg/50">
                <td className="py-3"><CategoryPill name={c.category} /></td>
                <td className="py-3 text-right text-cgcs-ink">
                  {c.expense_total ? money(c.expense_total) : <span className="text-cgcs-mute">—</span>}
                </td>
                <td className="py-3 text-right text-cgcs-ink">
                  {c.revenue_total ? money(c.revenue_total) : <span className="text-cgcs-mute">—</span>}
                </td>
                <td className={`py-3 text-right font-medium ${c.net < 0 ? "text-cgcs-bad" : "text-cgcs-good"}`}>
                  {c.net < 0 ? "−" : "+"}{money(Math.abs(c.net))}
                </td>
                <td className="py-3 text-right text-xs text-cgcs-mute">{c.row_count}</td>
              </tr>
            ))}
            <tr className="border-t-2 border-cgcs-ink font-semibold">
              <td className="py-3 text-cgcs-ink">Total</td>
              <td className="py-3 text-right text-cgcs-bad">−{money(totals.expense)}</td>
              <td className="py-3 text-right text-cgcs-good">+{money(totals.revenue)}</td>
              <td className={`py-3 text-right ${net < 0 ? "text-cgcs-bad" : "text-cgcs-good"}`}>
                {net < 0 ? "−" : "+"}{money(Math.abs(net))}
              </td>
              <td className="py-3 text-right text-xs text-cgcs-mute">{totals.txn_count}</td>
            </tr>
          </tbody>
        </table>
      </section>

      {/* Recent transactions */}
      <section className="rounded-xl bg-white p-6 ring-1 ring-cgcs-line">
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="text-lg font-semibold text-cgcs-ink">Recent transactions</h2>
          <Link href="/budget/ledger" className="text-xs text-cgcs-mute hover:text-cgcs-ink">
            View full ledger →
          </Link>
        </div>
        <table className="w-full text-sm">
          <thead className="text-xs uppercase tracking-wide text-cgcs-mute">
            <tr>
              <th className="pb-3 text-left">Date</th>
              <th className="pb-3 text-left">Description</th>
              <th className="pb-3 text-left">Category</th>
              <th className="pb-3 text-right">Expense</th>
              <th className="pb-3 text-right">Revenue</th>
              <th className="pb-3 text-right">Running</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-cgcs-line">
            {recent_transactions.map((t) => (
              <tr key={t.id} className="hover:bg-cgcs-bg/50">
                <td className="py-2 text-cgcs-mute">{fmtDate(t.date)}</td>
                <td className="py-2 text-cgcs-ink">
                  {t.linked_reservation_id ? (
                    <Link
                      href={`/reservations/${t.linked_reservation_id}`}
                      className="hover:underline"
                    >
                      {t.description}
                    </Link>
                  ) : t.description}
                  {t.notes && <div className="text-xs text-cgcs-mute">{t.notes.slice(0, 80)}</div>}
                </td>
                <td className="py-2"><CategoryPill name={t.category} /></td>
                <td className="py-2 text-right text-cgcs-bad">
                  {t.expense ? `−${money(t.expense, true)}` : <span className="text-cgcs-mute">—</span>}
                </td>
                <td className="py-2 text-right text-cgcs-good">
                  {t.revenue ? `+${money(t.revenue, true)}` : <span className="text-cgcs-mute">—</span>}
                </td>
                <td className="py-2 text-right text-cgcs-mute">{money(t.running_balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
