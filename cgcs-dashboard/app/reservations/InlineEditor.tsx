"use client";

import { useState, useTransition, useRef, useEffect } from "react";
import { updateFieldsAction } from "./actions";

type Common = {
  id: string;
  field: string;
  /** What's currently shown when not editing */
  display?: React.ReactNode;
  /** Class applied to the trigger / display element */
  className?: string;
  /** Placeholder shown when empty */
  placeholder?: string;
};

/** Click → text input. Enter/blur saves. Esc cancels. */
export function InlineText({
  id, field, value, display, className = "", placeholder = "—",
}: Common & { value: string | null | undefined }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const [isPending, startTransition] = useTransition();
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => { setDraft(value ?? ""); }, [value]);
  useEffect(() => { if (editing) ref.current?.focus(); }, [editing]);

  const save = () => {
    setEditing(false);
    if (draft === (value ?? "")) return;
    startTransition(() => updateFieldsAction(id, { [field]: draft }));
  };
  const cancel = () => { setEditing(false); setDraft(value ?? ""); };

  if (editing) {
    return (
      <input
        ref={ref}
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); save(); }
          if (e.key === "Escape") { e.preventDefault(); cancel(); }
        }}
        className={`w-full rounded border border-cgcs-ink bg-white px-1.5 py-0.5 text-sm outline-none ${className}`}
      />
    );
  }
  return (
    <button
      type="button"
      disabled={isPending}
      onClick={() => setEditing(true)}
      className={`block w-full cursor-text rounded px-1.5 py-0.5 text-left text-sm hover:bg-cgcs-bg/70 disabled:opacity-50 ${className}`}
      title="Click to edit"
    >
      {display ?? (value ?? <span className="text-cgcs-mute">{placeholder}</span>)}
    </button>
  );
}

/** Click → number input. */
export function InlineNumber({
  id, field, value, display, className = "", placeholder = "—",
}: Common & { value: number | string | null | undefined }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value == null ? "" : String(value));
  const [isPending, startTransition] = useTransition();
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => { setDraft(value == null ? "" : String(value)); }, [value]);
  useEffect(() => { if (editing) ref.current?.focus(); }, [editing]);

  const save = () => {
    setEditing(false);
    const cur = value == null ? "" : String(value);
    if (draft === cur) return;
    const send = draft === "" ? null : draft;
    startTransition(() => updateFieldsAction(id, { [field]: send }));
  };
  const cancel = () => { setEditing(false); setDraft(value == null ? "" : String(value)); };

  if (editing) {
    return (
      <input
        ref={ref}
        type="number"
        step="any"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); save(); }
          if (e.key === "Escape") { e.preventDefault(); cancel(); }
        }}
        className={`w-full rounded border border-cgcs-ink bg-white px-1.5 py-0.5 text-right text-sm outline-none ${className}`}
      />
    );
  }
  return (
    <button
      type="button"
      disabled={isPending}
      onClick={() => setEditing(true)}
      className={`block w-full cursor-text rounded px-1.5 py-0.5 text-right text-sm hover:bg-cgcs-bg/70 disabled:opacity-50 ${className}`}
      title="Click to edit"
    >
      {display ?? (value != null ? value : <span className="text-cgcs-mute">{placeholder}</span>)}
    </button>
  );
}

/** Click → date input (YYYY-MM-DD). */
export function InlineDate({
  id, field, value, display, className = "", placeholder = "—",
}: Common & { value: string | null | undefined }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const [isPending, startTransition] = useTransition();
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => { setDraft(value ?? ""); }, [value]);
  useEffect(() => { if (editing) ref.current?.focus(); }, [editing]);

  const save = () => {
    setEditing(false);
    if (draft === (value ?? "")) return;
    startTransition(() => updateFieldsAction(id, { [field]: draft || null }));
  };
  const cancel = () => { setEditing(false); setDraft(value ?? ""); };

  if (editing) {
    return (
      <input
        ref={ref}
        type="date"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); save(); }
          if (e.key === "Escape") { e.preventDefault(); cancel(); }
        }}
        className={`w-full rounded border border-cgcs-ink bg-white px-1.5 py-0.5 text-sm outline-none ${className}`}
      />
    );
  }
  return (
    <button
      type="button"
      disabled={isPending}
      onClick={() => setEditing(true)}
      className={`block w-full cursor-text rounded px-1.5 py-0.5 text-left text-sm hover:bg-cgcs-bg/70 disabled:opacity-50 ${className}`}
      title="Click to edit"
    >
      {display ?? (value ?? <span className="text-cgcs-mute">{placeholder}</span>)}
    </button>
  );
}

/** Click → dropdown. */
export function InlineSelect({
  id, field, value, options, display, className = "",
}: Common & {
  value: string | null | undefined;
  options: { value: string; label: string }[];
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function click(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", click);
    return () => document.removeEventListener("mousedown", click);
  }, [open]);

  const pick = (v: string) => {
    setOpen(false);
    if (v === (value ?? "")) return;
    startTransition(() => updateFieldsAction(id, { [field]: v }));
  };

  return (
    <div ref={wrapRef} className="relative inline-block w-full">
      <button
        type="button"
        disabled={isPending}
        onClick={() => setOpen((o) => !o)}
        className={`block w-full cursor-pointer rounded px-1.5 py-0.5 text-left text-sm hover:bg-cgcs-bg/70 disabled:opacity-50 ${className}`}
      >
        {display ?? (value ?? <span className="text-cgcs-mute">—</span>)}
      </button>
      {open && (
        <div className="absolute left-0 top-full z-20 mt-0.5 min-w-full overflow-hidden rounded-md bg-white shadow-lg ring-1 ring-cgcs-line">
          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => pick(opt.value)}
              className={`block w-full whitespace-nowrap px-3 py-1.5 text-left text-xs hover:bg-cgcs-bg ${
                opt.value === value ? "font-semibold text-cgcs-ink" : "text-cgcs-mute"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
