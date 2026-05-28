"use server";

import { revalidatePath } from "next/cache";

const AGENT_URL = process.env.AGENT_API_URL ?? "http://langgraph-agent:8000";
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET ?? "";

export type IntakeResult = {
  ok: boolean;
  request_id?: string;
  status?: string;
  difficulty?: string | null;
  auto_send?: boolean;
  parsed?: Record<string, unknown>;
  draft_emails?: Array<{
    to: string;
    cc?: string;
    subject: string;
    body: string;
    auto_send?: boolean;
    classification?: Record<string, unknown>;
  }>;
  acknowledgment?: { subject: string; body: string } | null;
  reason?: string;
  error?: string;
};

export async function processIntakeEmailAction(
  formData: FormData,
): Promise<IntakeResult> {
  const subject = String(formData.get("subject") ?? "").trim();
  const sender = String(formData.get("sender") ?? "automations@app.smartsheet.com").trim();
  const body = String(formData.get("body") ?? "").trim();

  if (!body) return { ok: false, error: "Body is required" };
  if (!subject) return { ok: false, error: "Subject is required" };

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 90_000); // intake graph can take ~30s
    const res = await fetch(`${AGENT_URL}/webhook/smartsheet-new-entry`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Webhook-Secret": WEBHOOK_SECRET,
      },
      body: JSON.stringify({ subject, sender, body, force: true }),
      cache: "no-store",
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      return { ok: false, error: `Agent ${res.status}: ${text || res.statusText}` };
    }
    const data = (await res.json()) as IntakeResult & { status?: string; reason?: string };

    // Successful intake — refresh the P.E.T. + homepage so the new reservation shows up.
    revalidatePath("/reservations");
    revalidatePath("/");
    return { ...data, ok: true };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, error: msg };
  }
}
