import { getPendingEmails } from "@/lib/api";
import { approveAction, rejectAction } from "./actions";

export const dynamic = "force-dynamic";

export default async function InboxPage() {
  const data = await getPendingEmails().catch((e) => ({ error: String(e) } as const));

  if ("error" in data) {
    return (
      <div className="rounded-lg border border-cgcs-bad/40 bg-red-50 p-6 text-sm text-cgcs-bad">
        Failed to load pending emails: {data.error}
      </div>
    );
  }

  if (data.count === 0) {
    return (
      <div>
        <h1 className="text-2xl font-semibold text-cgcs-ink">Inbox</h1>
        <p className="mt-2 text-sm text-cgcs-mute">No pending drafts. Inbox zero.</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold text-cgcs-ink">Inbox</h1>
      <p className="mt-2 text-sm text-cgcs-mute">{data.count} drafts waiting for approval.</p>
      <div className="mt-6 space-y-4">
        {data.emails.map((e) => (
          <article key={e.id} className="rounded-xl bg-white p-5 ring-1 ring-cgcs-line">
            <header className="flex items-start justify-between gap-4">
              <div>
                <div className="text-xs uppercase tracking-wide text-cgcs-mute">{e.classification ?? "draft"}</div>
                <div className="mt-1 font-semibold text-cgcs-ink">{e.subject ?? "(no subject)"}</div>
                <div className="text-sm text-cgcs-mute">From: {e.from_email ?? "—"}</div>
              </div>
              <form className="flex gap-2">
                <input type="hidden" name="id" value={e.id} />
                <button
                  formAction={approveAction}
                  className="rounded-md bg-cgcs-good px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700"
                >
                  Approve & send
                </button>
                <button
                  formAction={rejectAction}
                  className="rounded-md bg-white px-3 py-1.5 text-sm font-medium text-cgcs-bad ring-1 ring-cgcs-bad/40 hover:bg-red-50"
                >
                  Reject
                </button>
              </form>
            </header>
            <pre className="mt-4 whitespace-pre-wrap rounded-lg bg-slate-50 p-4 text-sm text-cgcs-ink">
{e.draft_body ?? "(no draft body)"}
            </pre>
          </article>
        ))}
      </div>
    </div>
  );
}
