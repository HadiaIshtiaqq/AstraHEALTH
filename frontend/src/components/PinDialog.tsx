import { useEffect, useRef, useState } from "react";
import { Lock } from "lucide-react";

/** Modal PIN entry for actions reserved to the medical officer or admin. */
export function PinDialog({ title, description, onSubmit, onCancel, withNote = false, error }: {
  title: string; description: string; withNote?: boolean; error?: string | null;
  onSubmit: (pin: string, note: string) => void; onCancel: () => void;
}) {
  const [pin, setPin] = useState("");
  const [note, setNote] = useState("");
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="pin-title" className="fixed inset-0 z-50 grid place-items-center bg-navy/40 p-4"
      onKeyDown={(e) => { if (e.key === "Escape") onCancel(); }}>
      <form className="card fade-in w-full max-w-sm p-6" onSubmit={(e) => { e.preventDefault(); onSubmit(pin, note); }}>
        <h2 id="pin-title" className="flex items-center gap-2 text-lg font-semibold text-navy"><Lock size={18} aria-hidden /> {title}</h2>
        <p className="mt-1 text-sm text-muted">{description}</p>
        <label className="mt-4 block text-sm font-medium text-navy">PIN
          <input ref={ref} type="password" inputMode="numeric" autoComplete="off" value={pin} onChange={(e) => setPin(e.target.value)}
            className="mt-1 w-full rounded-xl border border-line px-3 py-2 tracking-[0.4em]" />
        </label>
        {withNote && (
          <label className="mt-3 block text-sm font-medium text-navy">Note (optional)
            <input value={note} onChange={(e) => setNote(e.target.value)} className="mt-1 w-full rounded-xl border border-line px-3 py-2" />
          </label>
        )}
        {error && <p role="alert" className="mt-3 text-sm font-semibold text-urgent">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={!pin}>Confirm</button>
        </div>
        <p className="mt-3 text-[11px] text-muted">PINs are generated on first start in backend/data/credentials.json.</p>
      </form>
    </div>
  );
}
