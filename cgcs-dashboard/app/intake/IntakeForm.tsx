"use client";

import { useState, useTransition } from "react";
import { processIntakeEmailAction, type IntakeResult } from "./actions";

const SAMPLE_BODY = `Submission Date: 11/14/2026
First Name: Jane
Last Name: Doe
Email: jane@example.org
Organization: Texas Housers
Event Name: Texas Housers 2026 Houser Awards
Event Date: 11/14/2026
Start Time: 7:00 AM
End Time: 4:00 PM
Attendees: 150
Room: 1311
Setup: Theater
A/V Needs: Microphone, Projector
Food: Outside catering
Notes: Annual awards luncheon`;

function tryExtractSubject(body: string): string {
  // Smartsheet emails usually have a "Subject:" line or the first
  // line looks like a subject. Heuristic best-effort.
  const subjMatch = body.match(/^Subject:\s*(.+)$/im);
  if (subjMatch) return subjMatch[1].trim();
  const firstLine = body.split("\n").find((l) => l.trim().length > 0);
  return firstLine?.trim().slice(0, 200) ?? "";
}

export function IntakeForm() {
  const [body, setBody] = useState("");
  const [subject, setSubject] = useState("");
  const [sender, setSender] = useState("automations@app.smartsheet.com");
  const [result, setResult] = useState<IntakeResult | null>(null);
  const [pending, startTransition] = useTransition();

  function handleAutoFillSubject() {
    setSubject(tryExtractSubject(body));
  }

  function handleSubmit(formData: FormData) {
    setResult(null);
    startTransition(async () => {
      const r = await processIntakeEmailAction(formData);
      setResult(r);
    });
  }

  function reset() {
    setBody("");
    setSubject("");
    setResult(null);
  }

  if (result?.ok) {
    return <IntakeResultView result={result} onReset={reset} />;
  }

  return (
    <form action={handleSubmit} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="block text-cgcs-mute mb-1">Subject *</span>
          <div className="flex gap-2">
            <input
              required
              name="subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Notice of Event Space Request — …"
              className="flex-1 rounded border border-cgcs-line px-3 py-2 text-sm focus:border-cgcs-ink outline-none"
            />
            <button
              type="button"
              onClick={handleAutoFillSubject}
              className="rounded border border-cgcs-line px-3 py-2 text-xs text-cgcs-mute hover:text-cgcs-ink"
              title="Try to pull subject from body"
            >
              Auto
            </button>
          </div>
        </label>
        <label className="block text-sm">
          <span className="block text-cgcs-mute mb-1">From</span>
          <input
            name="sender"
            value={sender}
            onChange={(e) => setSender(e.target.value)}
            className="w-full rounded border border-cgcs-line px-3 py-2 text-sm focus:border-cgcs-ink outline-none"
          />
        </label>
      </div>

      <label className="block text-sm">
        <span className="block text-cgcs-mute mb-1">Email body *</span>
        <textarea
          required
          name="body"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={18}
          placeholder="Paste the full Smartsheet intake email body here…"
          className="w-full rounded border border-cgcs-line px-3 py-2 font-mono text-xs focus:border-cgcs-ink outline-none"
        />
      </label>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={pending || !body || !subject}
          className="rounded bg-cgcs-ink px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {pending ? "Processing…" : "Run agent"}
        </button>
        <button
          type="button"
          onClick={() => {
            setBody(SAMPLE_BODY);
            setSubject("Notice of Event Space Request - CGCS RGC | Texas Housers 2026 Houser Awards | 11/14/26");
          }}
          className="text-xs text-cgcs-mute hover:text-cgcs-ink"
        >
          Load sample
        </button>
        {body && (
          <button
            type="button"
            onClick={() => setBody("")}
            className="text-xs text-cgcs-mute hover:text-cgcs-ink"
          >
            Clear
          </button>
        )}
        {pending && (
          <span className="text-xs text-cgcs-mute">
            Parsing email · classifying difficulty · drafting replies · writing to P.E.T. and calendar…
          </span>
        )}
      </div>

      {result && !result.ok && (
        <div className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
          {result.error ?? "Unknown error"}
        </div>
      )}
    </form>
  );
}

function IntakeResultView({
  result,
  onReset,
}: {
  result: IntakeResult;
  onReset: () => void;
}) {
  const p = result.parsed ?? {};
  const drafts = result.draft_emails ?? [];
  const ack = result.acknowledgment;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 rounded border border-emerald-300 bg-emerald-50 px-4 py-3">
        <div>
          <div className="text-sm font-medium text-emerald-800">
            Processed · status: {result.status ?? "ok"}
            {result.difficulty && (
              <span className="ml-2 rounded bg-emerald-200 px-2 py-0.5 text-xs uppercase tracking-wide">
                {result.difficulty}
              </span>
            )}
          </div>
          {result.request_id && (
            <div className="text-xs text-emerald-700 mt-1">
              request_id: {result.request_id}
            </div>
          )}
          {result.reason && (
            <div className="text-xs text-emerald-700 mt-1">{result.reason}</div>
          )}
        </div>
        <button
          onClick={onReset}
          className="rounded bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-800"
        >
          Process another
        </button>
      </div>

      <Section title="Parsed event">
        <ParsedTable parsed={p} />
      </Section>

      {ack && (
        <Section title="Acknowledgment (sent to requester)">
          <EmailCard label="Auto-ack" to={String(p.contact_email ?? "")} subject={ack.subject} body={ack.body} />
        </Section>
      )}

      {drafts.length > 0 && (
        <Section title={`Drafted emails (${drafts.length})`}>
          <div className="space-y-3">
            {drafts.map((d, i) => (
              <EmailCard
                key={i}
                label={String(d.classification?.recipient_role ?? `Draft ${i + 1}`)}
                to={d.to}
                cc={d.cc}
                subject={d.subject}
                body={d.body}
              />
            ))}
          </div>
        </Section>
      )}

      <div className="text-xs text-cgcs-mute">
        Reservation written to P.E.T. ·{" "}
        <a href="/reservations" className="underline">
          open the table
        </a>
        .
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2 text-sm font-medium text-cgcs-ink">{title}</div>
      {children}
    </div>
  );
}

function ParsedTable({ parsed }: { parsed: Record<string, unknown> }) {
  const entries = Object.entries(parsed).filter(([_, v]) => v !== null && v !== "" && v !== undefined);
  if (entries.length === 0) {
    return <div className="text-xs text-cgcs-mute">No fields parsed.</div>;
  }
  return (
    <div className="rounded border border-cgcs-line">
      <table className="w-full text-xs">
        <tbody>
          {entries.map(([k, v]) => (
            <tr key={k} className="border-t border-cgcs-line first:border-t-0">
              <td className="bg-gray-50 px-3 py-1.5 font-mono text-cgcs-mute w-1/3">{k}</td>
              <td className="px-3 py-1.5">
                {typeof v === "object" ? (
                  <pre className="whitespace-pre-wrap">{JSON.stringify(v, null, 2)}</pre>
                ) : (
                  String(v)
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EmailCard({
  label,
  to,
  cc,
  subject,
  body,
}: {
  label: string;
  to: string;
  cc?: string;
  subject: string;
  body: string;
}) {
  const [copied, setCopied] = useState<"" | "subject" | "body" | "all">("");
  const all = `To: ${to}\n${cc ? `Cc: ${cc}\n` : ""}Subject: ${subject}\n\n${body}`;

  async function copy(text: string, which: "subject" | "body" | "all") {
    await navigator.clipboard.writeText(text);
    setCopied(which);
    setTimeout(() => setCopied(""), 1500);
  }

  return (
    <div className="rounded border border-cgcs-line">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cgcs-line bg-gray-50 px-3 py-2">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded bg-cgcs-ink px-2 py-0.5 font-medium text-white">{label}</span>
          <span className="text-cgcs-mute">to</span>
          <span className="font-mono">{to || "—"}</span>
          {cc && (
            <>
              <span className="text-cgcs-mute">cc</span>
              <span className="font-mono">{cc}</span>
            </>
          )}
        </div>
        <button
          onClick={() => copy(all, "all")}
          className="rounded border border-cgcs-line px-2 py-0.5 text-xs hover:bg-white"
        >
          {copied === "all" ? "Copied" : "Copy all"}
        </button>
      </div>
      <div className="px-3 py-2 text-sm">
        <div className="mb-2 flex items-start justify-between gap-2">
          <div>
            <span className="text-cgcs-mute text-xs">Subject:</span>{" "}
            <span className="font-medium">{subject}</span>
          </div>
          <button
            onClick={() => copy(subject, "subject")}
            className="rounded border border-cgcs-line px-2 py-0.5 text-xs hover:bg-gray-50"
          >
            {copied === "subject" ? "Copied" : "Copy"}
          </button>
        </div>
        <div className="flex items-start justify-between gap-2">
          <pre className="whitespace-pre-wrap font-sans text-xs leading-relaxed flex-1">{body}</pre>
          <button
            onClick={() => copy(body, "body")}
            className="rounded border border-cgcs-line px-2 py-0.5 text-xs hover:bg-gray-50"
          >
            {copied === "body" ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
    </div>
  );
}
