"use client";

import { useFormStatus } from "react-dom";

export function SyncButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded-md bg-cgcs-ink px-3 py-1 text-sm text-white ring-1 ring-cgcs-ink hover:opacity-90 disabled:opacity-50"
    >
      {pending ? "Syncing…" : "Sync now"}
    </button>
  );
}
