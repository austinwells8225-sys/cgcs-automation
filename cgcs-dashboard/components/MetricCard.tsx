type Props = {
  label: string;
  value: string | number;
  sublabel?: string;
  delta?: { current: number; previous: number };
  accent?: "default" | "good" | "bad";
};

function pct(curr: number, prev: number): string {
  if (!prev) return curr > 0 ? "+∞" : "—";
  const change = ((curr - prev) / prev) * 100;
  const sign = change > 0 ? "+" : "";
  return `${sign}${change.toFixed(1)}%`;
}

export function MetricCard({ label, value, sublabel, delta, accent }: Props) {
  const deltaColor =
    delta && delta.current >= delta.previous
      ? "text-cgcs-good"
      : "text-cgcs-bad";
  const accentRing =
    accent === "good" ? "ring-cgcs-good/20" : accent === "bad" ? "ring-cgcs-bad/20" : "ring-cgcs-line";

  return (
    <div className={`rounded-xl bg-white p-5 ring-1 ${accentRing}`}>
      <div className="text-xs uppercase tracking-wide text-cgcs-mute">{label}</div>
      <div className="mt-2 flex items-baseline justify-between">
        <div className="text-3xl font-semibold text-cgcs-ink">{value}</div>
        {delta ? (
          <div className={`text-sm font-medium ${deltaColor}`}>
            {pct(delta.current, delta.previous)} YoY
          </div>
        ) : null}
      </div>
      {sublabel ? <div className="mt-1 text-sm text-cgcs-mute">{sublabel}</div> : null}
    </div>
  );
}
