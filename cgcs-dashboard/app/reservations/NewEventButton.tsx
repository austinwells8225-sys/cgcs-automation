"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { createReservationAction } from "./actions";

const CATEGORIES = [
  { value: "monetization", label: "Monetization (paid, external)" },
  { value: "acc", label: "ACC (internal service)" },
  { value: "cgcs", label: "CGCS (designed / co-branded)" },
];

const STATUSES = [
  { value: "approved", label: "Upcoming (approved)" },
  { value: "pending_review", label: "Pending review" },
  { value: "completed", label: "Already completed" },
];

const ROOMS = [
  { value: "event_hall", label: "Event Hall (3340 — Big Room)" },
  { value: "classroom", label: "Classroom (3328)" },
  { value: "small_conference", label: "Small Conference (3346 / 3347 / 3348)" },
  { value: "large_conference", label: "Large Conference" },
  { value: "multipurpose", label: "Multipurpose" },
];

export function NewEventButton() {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const router = useRouter();

  const handleSubmit = (formData: FormData) => {
    setError(null);
    const payload: Record<string, unknown> = {
      event_name: formData.get("event_name") || "",
      requested_date: formData.get("requested_date") || "",
      requested_start_time: formData.get("requested_start_time") || "",
      requested_end_time: formData.get("requested_end_time") || "",
    };
    // Optional fields — only include if non-empty
    const optional: Record<string, string> = {
      cgcs_lead: "cgcs_lead",
      requester_organization: "org",
      event_category: "event_category",
      status: "status",
      room_requested: "room_requested",
      actual_revenue: "revenue",
      actual_attendance: "attendees",
      ad_astra: "ad_astra",
      floor_layout: "floor_layout",
      av: "av",
      catering: "catering",
    };
    for (const [field, formKey] of Object.entries(optional)) {
      const v = formData.get(formKey);
      if (v && String(v).trim()) payload[field] = v;
    }

    startTransition(async () => {
      const res = await createReservationAction(payload);
      if (res.ok) {
        setOpen(false);
        router.refresh();
      } else {
        setError(res.error);
      }
    });
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 rounded-md bg-cgcs-ink px-3 py-1.5 text-sm font-medium text-white hover:opacity-90"
      >
        <span>+</span> New event
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-16"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setOpen(false);
          }}
        >
          <div className="w-full max-w-3xl rounded-xl bg-white shadow-2xl ring-1 ring-cgcs-line">
            <div className="flex items-center justify-between border-b border-cgcs-line px-6 py-4">
              <h2 className="text-lg font-semibold text-cgcs-ink">Add new event to P.E.T.</h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-cgcs-mute hover:text-cgcs-ink"
                aria-label="Close"
              >
                ✕
              </button>
            </div>

            <form action={handleSubmit} className="space-y-5 p-6">
              <p className="text-xs text-cgcs-mute">
                Required fields are marked <span className="text-cgcs-bad">*</span>. Everything else can be filled in later by clicking the cells in the table.
              </p>

              {/* Required */}
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wide text-cgcs-mute">
                    Event name <span className="text-cgcs-bad">*</span>
                  </label>
                  <input
                    name="event_name"
                    required
                    autoFocus
                    placeholder="e.g. Texas Housers 2026 Houser Awards"
                    className="mt-1 w-full rounded border border-cgcs-line px-3 py-2 text-sm focus:border-cgcs-ink focus:outline-none"
                  />
                </div>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wide text-cgcs-mute">
                      Date <span className="text-cgcs-bad">*</span>
                    </label>
                    <input
                      name="requested_date"
                      type="date"
                      required
                      className="mt-1 w-full rounded border border-cgcs-line px-3 py-2 text-sm focus:border-cgcs-ink focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wide text-cgcs-mute">
                      Start time <span className="text-cgcs-bad">*</span>
                    </label>
                    <input
                      name="requested_start_time"
                      type="time"
                      required
                      className="mt-1 w-full rounded border border-cgcs-line px-3 py-2 text-sm focus:border-cgcs-ink focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wide text-cgcs-mute">
                      End time <span className="text-cgcs-bad">*</span>
                    </label>
                    <input
                      name="requested_end_time"
                      type="time"
                      required
                      className="mt-1 w-full rounded border border-cgcs-line px-3 py-2 text-sm focus:border-cgcs-ink focus:outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Common optional */}
              <div className="space-y-3 border-t border-cgcs-line pt-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-cgcs-mute">
                  Common fields (optional)
                </p>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <div>
                    <label className="block text-xs text-cgcs-mute">CGCS Lead</label>
                    <input
                      name="cgcs_lead"
                      placeholder="Austin, Bryan, Cate, Marisela…"
                      className="mt-1 w-full rounded border border-cgcs-line px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-cgcs-mute">Organization</label>
                    <input
                      name="org"
                      placeholder="Requesting org / dept"
                      className="mt-1 w-full rounded border border-cgcs-line px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-cgcs-mute">Tier</label>
                    <select
                      name="event_category"
                      defaultValue=""
                      className="mt-1 w-full rounded border border-cgcs-line px-3 py-2 text-sm"
                    >
                      <option value="">— Choose —</option>
                      {CATEGORIES.map((c) => (
                        <option key={c.value} value={c.value}>{c.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-cgcs-mute">Status</label>
                    <select
                      name="status"
                      defaultValue="approved"
                      className="mt-1 w-full rounded border border-cgcs-line px-3 py-2 text-sm"
                    >
                      {STATUSES.map((s) => (
                        <option key={s.value} value={s.value}>{s.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-cgcs-mute">Room</label>
                    <select
                      name="room_requested"
                      defaultValue=""
                      className="mt-1 w-full rounded border border-cgcs-line px-3 py-2 text-sm"
                    >
                      <option value="">— Choose —</option>
                      {ROOMS.map((r) => (
                        <option key={r.value} value={r.value}>{r.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-cgcs-mute">Expected attendees</label>
                    <input
                      name="attendees"
                      type="number"
                      placeholder="100"
                      className="mt-1 w-full rounded border border-cgcs-line px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-cgcs-mute">Revenue ($)</label>
                    <input
                      name="revenue"
                      type="number"
                      step="0.01"
                      placeholder="0.00"
                      className="mt-1 w-full rounded border border-cgcs-line px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-cgcs-mute">Ad Astra #</label>
                    <input
                      name="ad_astra"
                      placeholder="#20260101-00042"
                      className="mt-1 w-full rounded border border-cgcs-line px-3 py-2 text-sm"
                    />
                  </div>
                </div>
              </div>

              {/* Detail blob */}
              <div className="space-y-3 border-t border-cgcs-line pt-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-cgcs-mute">
                  Details (optional)
                </p>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                  <div>
                    <label className="block text-xs text-cgcs-mute">Floor layout</label>
                    <input
                      name="floor_layout"
                      placeholder="e.g. 10 Rounds with linens"
                      className="mt-1 w-full rounded border border-cgcs-line px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-cgcs-mute">AV needs</label>
                    <input
                      name="av"
                      placeholder="Projector, 2 mics, etc."
                      className="mt-1 w-full rounded border border-cgcs-line px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-cgcs-mute">Catering</label>
                    <input
                      name="catering"
                      placeholder="External / Internal / None"
                      className="mt-1 w-full rounded border border-cgcs-line px-3 py-2 text-sm"
                    />
                  </div>
                </div>
              </div>

              {error && (
                <div className="rounded-md border border-cgcs-bad/40 bg-red-50 px-3 py-2 text-sm text-cgcs-bad">
                  {error}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 border-t border-cgcs-line pt-4">
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  disabled={isPending}
                  className="rounded-md px-4 py-2 text-sm text-cgcs-mute hover:text-cgcs-ink disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isPending}
                  className="rounded-md bg-cgcs-ink px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                >
                  {isPending ? "Adding…" : "Add to P.E.T."}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
