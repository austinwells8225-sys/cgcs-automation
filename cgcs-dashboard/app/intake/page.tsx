import { IntakeForm } from "./IntakeForm";

export const dynamic = "force-dynamic";

export default function IntakePage() {
  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <header className="mb-6">
        <h1 className="text-xl font-semibold text-cgcs-ink">New Intake</h1>
        <p className="text-sm text-cgcs-mute mt-1">
          Paste a Smartsheet intake email below. The agent parses 40+ fields,
          classifies difficulty, drafts replies, writes a P.E.T. row, and
          creates a calendar HOLD.
        </p>
      </header>
      <IntakeForm />
    </main>
  );
}
