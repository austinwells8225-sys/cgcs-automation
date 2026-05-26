import Link from "next/link";
import { getBudgetTransactions, type BudgetTransaction } from "@/lib/api";

export const dynamic = "force-dynamic";

function money(n: number | null, withCents = true): string {
  if (!n) return "";
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: withCents ? 2 : 0,
  }).format(n);
}

function fmtDate(s: string | null): string {
  if (!s) return "—";
  const d = new Date(s + "T00:00:00Z");
  return d.toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
  });
}

const CATEGORIES = [
  "Wage", "Event Income", "Event Expenses", "Office Equipment",
  "Subscription", "Food", "Police Coverage", "Miscellaneous",
];

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
        <span className={`rounded-full px-1.5 text-xs ${active ? "bg-white/20" : "bg-cgcs-bg text-cgcs-mute"}`}>
          {count}
        </span>
      )}
    </Link>
  );
}

export default async function LedgerPage({
  searchParams,
}: {
  searchParams: Promise<{ category?: string; sort?: string; dir?: string }>;
}) {
  const { category, sort, dir } = await searchParams;
  const activeCategory = category ?? "";
  const activeSort = sort ?? "date";
  const activeDir = (dir === "asc" ? "asc" : "desc") as "asc" | "desc";

  const [filtered, all] = await Promise.all([
    getBudgetTransactions(undefined, activeCategory || undefined, activeSort, activeDir).catch(
      (e) => ({ error: String(e) } as const),
    ),
    getBudgetTransactions(undefined, undefined, "date", "desc", 2000).catch(() => null),
  ]);

  if ("error" in filtered) {
    return (
      <div className="rounded-lg border border-cgcs-bad/40 bg-red-50 p-6 text-sm text-cgcs-bad">
        Failed to load ledger: {filtered.error}
      </div>
    );
  }

  const counts: Record<string, number> = { "": all?.count ?? 0 };
  if (all) {
    for (const t of all.transactions) {
      if (t.category) counts[t.category] = (counts[t.category] ?? 0) + 1;
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <Link href="/budget" className="text-sm text-cgcs-mute hover:text-cgcs-ink">
          ← Back to budget dashboard
        </Link>
      </div>

      <header>
        <h1 className="text-2xl font-semibold text-cgcs-ink">Transaction Ledger</h1>
        <p className="text-sm text-cgcs-mute">
          {filtered.count} {activeCategory || "total"} transaction{filtered.count === 1 ? "" : "s"}
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        <Chip label="All" count={counts[""]} active={activeCategory === ""} href="/budget/ledger" />
        {CATEGORIES.map((cat) => (
          <Chip
            key={cat}
            label={cat}
            count={counts[cat]}
            active={activeCategory === cat}
            href={`/budget/ledger?category=${encodeURIComponent(cat)}`}
          />
        ))}
      </div>

      <div className="overflow-hidden rounded-xl bg-white ring-1 ring-cgcs-line">
        <table className="w-full text-sm">
          <thead className="bg-cgcs-bg text-left text-xs uppercase tracking-wide text-cgcs-mute">
            <tr>
              <th className="px-4 py-3">Date</th>
              <th className="px-4 py-3">Description</th>
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Pmt</th>
              <th className="px-4 py-3 text-right">Expense</th>
              <th className="px-4 py-3 text-right">Revenue</th>
              <th className="px-4 py-3 text-right">Running</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-cgcs-line">
            {filtered.transactions.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-cgcs-mute">
                  No transactions match this filter.
                </td>
              </tr>
            )}
            {filtered.transactions.map((t: BudgetTransaction) => (
              <tr key={t.id} className="hover:bg-cgcs-bg/50">
                <td className="px-4 py-3 align-top text-cgcs-mute">{fmtDate(t.transaction_date)}</td>
                <td className="px-4 py-3 align-top text-cgcs-ink">
                  {t.linked_reservation_id ? (
                    <Link href={`/reservations/${t.linked_reservation_id}`} className="hover:underline">
                      {t.description}
                    </Link>
                  ) : t.description}
                  {t.notes && <div className="mt-0.5 text-xs text-cgcs-mute">{t.notes}</div>}
                </td>
                <td className="px-4 py-3 align-top">
                  {t.category && (
                    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs ring-1 ${
                      CATEGORY_COLOR[t.category] ?? "bg-gray-50 text-gray-600 ring-gray-200"
                    }`}>{t.category}</span>
                  )}
                </td>
                <td className="px-4 py-3 align-top text-xs text-cgcs-mute">{t.payment_method ?? "—"}</td>
                <td className="px-4 py-3 align-top text-right text-cgcs-bad">
                  {t.expense ? `−${money(t.expense)}` : <span className="text-cgcs-mute">—</span>}
                </td>
                <td className="px-4 py-3 align-top text-right text-cgcs-good">
                  {t.revenue ? `+${money(t.revenue)}` : <span className="text-cgcs-mute">—</span>}
                </td>
                <td className="px-4 py-3 align-top text-right text-cgcs-mute">
                  {money(t.running_balance, false)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
