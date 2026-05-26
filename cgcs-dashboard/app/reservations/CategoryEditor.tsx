"use client";

import { useState, useTransition, useRef, useEffect } from "react";
import { updateCategoryAction } from "./actions";

type Category = "cgcs" | "acc" | "monetization";

const LABEL: Record<Category, string> = {
  cgcs: "CGCS",
  acc: "ACC",
  monetization: "Space rental",
};

const PILL_COLOR: Record<Category | "_none", string> = {
  cgcs: "bg-cgcs-good/10 text-cgcs-good ring-cgcs-good/30",
  acc: "bg-blue-50 text-blue-700 ring-blue-200",
  monetization: "bg-amber-50 text-amber-700 ring-amber-200",
  _none: "bg-gray-50 text-gray-600 ring-gray-200",
};

const OPTIONS: Category[] = ["cgcs", "acc", "monetization"];

export function CategoryEditor({
  id,
  current,
}: {
  id: string;
  current: string | null | undefined;
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const wrapRef = useRef<HTMLDivElement>(null);

  // close on outside click
  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const cat = (current ?? "") as Category | "";
  const pillColor = cat ? PILL_COLOR[cat] : PILL_COLOR._none;
  const pillLabel = cat ? LABEL[cat] : "—";

  function handleSelect(next: Category) {
    setOpen(false);
    if (next === cat) return;
    startTransition(async () => {
      await updateCategoryAction(id, next);
    });
  }

  return (
    <div ref={wrapRef} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={isPending}
        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ring-1 transition hover:brightness-95 disabled:opacity-50 ${pillColor}`}
        title="Click to change category"
      >
        <span>{pillLabel}</span>
        <span className="text-[10px] opacity-60">▾</span>
      </button>
      {open && (
        <div className="absolute left-0 z-20 mt-1 w-36 overflow-hidden rounded-md bg-white shadow-lg ring-1 ring-cgcs-line">
          {OPTIONS.map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => handleSelect(opt)}
              className={`flex w-full items-center justify-between px-3 py-2 text-left text-xs hover:bg-cgcs-bg ${
                opt === cat ? "font-semibold text-cgcs-ink" : "text-cgcs-mute"
              }`}
            >
              <span>{LABEL[opt]}</span>
              {opt === cat && <span className="text-cgcs-good">✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
