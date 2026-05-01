export const dynamic = "force-dynamic";

export default function SurveysPage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-cgcs-ink">Surveys</h1>
      <p className="mt-2 text-sm text-cgcs-mute">
        Post-event survey responses — coming next. The <code className="rounded bg-slate-100 px-1">cgcs.event_surveys</code>{" "}
        table is in place; needs the Google Form → webhook ingestion path next.
      </p>
    </div>
  );
}
