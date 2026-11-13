"use client";

import { useState } from "react";
import type { EntityOption, ParseResult } from "@/lib/types";

interface Props {
  onParse: (text: string) => Promise<ParseResult>;
  onApply: (result: ParseResult) => void;
  onPick: (polarity: "include" | "exclude", option: EntityOption) => void;
}

export function QueryBox({ onParse, onApply, onPick }: Props) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<ParseResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<Set<number>>(new Set());

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    setPicked(new Set());
    try {
      const r = await onParse(text);
      setResult(r);
      if (r.spec || r.draft_spec) onApply(r);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <form onSubmit={submit} className="space-y-2">
        <label htmlFor="query" className="text-sm font-medium">
          Describe what you want
        </label>
        <div className="flex gap-2">
          <input
            id="query"
            value={text}
            maxLength={500}
            onChange={(e) => setText(e.target.value)}
            placeholder="e.g. Marlo Vance and J. Calder except Overlook, no same artist back to back"
            className="min-w-0 flex-1 rounded-md border border-border bg-surface px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={busy || !text.trim()}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:text-black"
          >
            {busy ? "Reading…" : "Apply"}
          </button>
        </div>
        <p className="text-xs text-muted">
          Understood offline by fixed rules, matched only against this playlist. Nothing is sent to an AI model.
        </p>
      </form>

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      {result && (
        <div className="space-y-2 text-sm" aria-live="polite">
          {result.spec && !result.unrecognized.length && !result.unsupported.length && (
            <p className="text-accent">Applied. Check the rules below, then generate the preview.</p>
          )}
          {result.resolved.length > 0 && (
            <ul className="flex flex-wrap gap-2">
              {result.resolved.map((r, i) => (
                <li
                  key={i}
                  className={`rounded-full px-3 py-1 text-xs ${
                    r.polarity === "include" ? "bg-accent-soft text-accent" : "bg-danger-soft text-danger"
                  }`}
                >
                  {r.polarity === "include" ? "Only" : "Not"} {r.kind} {[...new Set(r.options.map((o) => o.name))].join(" + ")}
                </li>
              ))}
            </ul>
          )}
          {result.ambiguities.map((a, i) => (
            <div key={i} className="rounded-md border border-warn bg-warn-soft p-3 text-warn">
              <p className="font-medium">{a.question}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {a.options.map((o) => (
                  <button
                    key={o.id}
                    type="button"
                    disabled={picked.has(i)}
                    onClick={() => {
                      onPick(a.polarity, o);
                      setPicked(new Set(picked).add(i));
                    }}
                    className="rounded border border-warn bg-surface px-2 py-1 text-xs text-text disabled:opacity-50"
                  >
                    {o.name} ({o.kind}
                    {o.detail ? `, ${o.detail}` : ""}, {o.entry_count} songs)
                  </button>
                ))}
              </div>
              {result.draft_spec && !picked.has(i) && (
                <p className="mt-2 text-xs">Pick one to apply the rest of your request.</p>
              )}
            </div>
          ))}
          {result.contradictions.map((c) => (
            <p key={c} className="rounded-md bg-danger-soft p-2 text-danger">
              {c}
            </p>
          ))}
          {result.unrecognized.length > 0 && (
            <p className="rounded-md bg-surface-2 p-2">
              Not found in this playlist: {result.unrecognized.map((u) => `“${u}”`).join(", ")}. Only artists and
              albums already in the playlist can be used.
            </p>
          )}
          {result.unsupported.map((u) => (
            <p key={u} className="rounded-md bg-surface-2 p-2">
              {u}
            </p>
          ))}
          {result.notes.map((n) => (
            <p key={n} className="text-muted">
              {n}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
