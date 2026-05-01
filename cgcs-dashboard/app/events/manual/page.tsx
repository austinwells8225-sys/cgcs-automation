import { redirect } from "next/navigation";
import { createManualEvent } from "@/lib/api";

export const dynamic = "force-dynamic";

async function submit(formData: FormData) {
  "use server";
  const get = (k: string) => {
    const v = formData.get(k);
    return v ? String(v) : undefined;
  };
  const num = (k: string) => {
    const v = get(k);
    return v ? Number(v) : undefined;
  };

  await createManualEvent({
    event_name: String(formData.get("event_name") ?? ""),
    requested_date: String(formData.get("requested_date") ?? ""),
    requested_start_time: String(formData.get("requested_start_time") ?? ""),
    requested_end_time: String(formData.get("requested_end_time") ?? ""),
    event_subtype: get("event_subtype"),
    event_location: get("event_location"),
    estimated_attendees: num("estimated_attendees"),
    actual_attendance: num("actual_attendance"),
    attendance_students: num("attendance_students"),
    attendance_staff: num("attendance_staff"),
    attendance_community: num("attendance_community"),
    training_hours_delivered: num("training_hours_delivered"),
    notes: get("notes"),
  });

  redirect("/?logged=1");
}

const labelClass = "block text-xs uppercase tracking-wide text-cgcs-mute";
const inputClass =
  "mt-1 w-full rounded-md border border-cgcs-line bg-white px-3 py-2 text-sm text-cgcs-ink focus:border-cgcs-accent focus:outline-none";

export default function ManualEventPage() {
  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-semibold text-cgcs-ink">Log an off-site CGCS event</h1>
      <p className="mt-2 text-sm text-cgcs-mute">
        For events CGCS designed/led/co-branded that didn't flow through Smartsheet — typically off-site at other ACC campuses or partner venues.
      </p>

      <form action={submit} className="mt-6 space-y-4">
        <div>
          <label className={labelClass}>Event name</label>
          <input className={inputClass} name="event_name" required />
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className={labelClass}>Date</label>
            <input className={inputClass} type="date" name="requested_date" required />
          </div>
          <div>
            <label className={labelClass}>Start</label>
            <input className={inputClass} type="time" name="requested_start_time" required />
          </div>
          <div>
            <label className={labelClass}>End</label>
            <input className={inputClass} type="time" name="requested_end_time" required />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelClass}>Subtype</label>
            <select className={inputClass} name="event_subtype" defaultValue="convening">
              <option value="training">Training</option>
              <option value="convening">Convening</option>
              <option value="co_branded">Co-branded</option>
              <option value="other">Other</option>
            </select>
          </div>
          <div>
            <label className={labelClass}>Location</label>
            <select className={inputClass} name="event_location" defaultValue="off_site">
              <option value="on_site">On-site (CGCS center)</option>
              <option value="off_site">Off-site</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelClass}>Estimated attendees</label>
            <input className={inputClass} type="number" min="0" name="estimated_attendees" />
          </div>
          <div>
            <label className={labelClass}>Actual attendance</label>
            <input className={inputClass} type="number" min="0" name="actual_attendance" />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className={labelClass}>Students</label>
            <input className={inputClass} type="number" min="0" name="attendance_students" />
          </div>
          <div>
            <label className={labelClass}>Staff/faculty</label>
            <input className={inputClass} type="number" min="0" name="attendance_staff" />
          </div>
          <div>
            <label className={labelClass}>Community</label>
            <input className={inputClass} type="number" min="0" name="attendance_community" />
          </div>
        </div>

        <div>
          <label className={labelClass}>Training hours delivered (if training)</label>
          <input className={inputClass} type="number" step="0.25" min="0" name="training_hours_delivered" />
        </div>

        <div>
          <label className={labelClass}>Notes</label>
          <textarea className={inputClass} name="notes" rows={3} />
        </div>

        <button
          type="submit"
          className="rounded-md bg-cgcs-accent px-4 py-2 text-sm font-medium text-white hover:bg-sky-800"
        >
          Log event
        </button>
      </form>
    </div>
  );
}
