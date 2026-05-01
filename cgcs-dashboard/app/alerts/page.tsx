import { getActiveAlerts } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AlertsPage() {
  const data = await getActiveAlerts().catch((e) => ({ error: String(e) } as const));

  if ("error" in data) {
    return (
      <div className="rounded-lg border border-cgcs-bad/40 bg-red-50 p-6 text-sm text-cgcs-bad">
        Failed to load alerts: {data.error}
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold text-cgcs-ink">Alerts</h1>
      <p className="mt-2 text-sm text-cgcs-mute">{data.count} active.</p>
      <div className="mt-6 space-y-3">
        {data.alerts.map((a) => (
          <div key={a.id} className="rounded-xl bg-white p-5 ring-1 ring-cgcs-line">
            <div className="text-xs uppercase tracking-wide text-cgcs-mute">{a.alert_type}</div>
            <div className="mt-1 font-semibold text-cgcs-ink">{a.title}</div>
            {a.detail ? <div className="mt-1 text-sm text-cgcs-mute">{a.detail}</div> : null}
          </div>
        ))}
        {data.alerts.length === 0 ? <p className="text-sm text-cgcs-mute">No active alerts.</p> : null}
      </div>
    </div>
  );
}
