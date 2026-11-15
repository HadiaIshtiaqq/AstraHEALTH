import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { PinDialog } from "../components/PinDialog";

/**
 * Admin-only controls (demo scenarios, fault injection, imports, reviewer pages) ask for the admin PIN once per
 * browser session. The PIN is kept only in memory (never in storage) and is cleared on any rejection.
 */
interface AdminApi { withAdmin: <T>(action: (pin: string) => Promise<T>, why: string) => Promise<T>; hasPin: boolean }
const Ctx = createContext<AdminApi | null>(null);

export function AdminProvider({ children }: { children: ReactNode }) {
  const pin = useRef<string | null>(null);
  const [prompt, setPrompt] = useState<{ why: string; resolve: (p: string | null) => void } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasPin, setHasPin] = useState(false);

  const ask = (why: string) => new Promise<string | null>((resolve) => { setError(null); setPrompt({ why, resolve }); });

  const withAdmin = useCallback(async <T,>(action: (p: string) => Promise<T>, why: string): Promise<T> => {
    for (let attempt = 0; attempt < 3; attempt++) {
      if (!pin.current) {
        const entered = await ask(why);
        if (!entered) throw new Error("Admin PIN required.");
        pin.current = entered;
      }
      try {
        const out = await action(pin.current);
        setHasPin(true);
        setPrompt(null);
        return out;
      } catch (e: any) {
        if (e?.status === 403 || e?.status === 429) {
          pin.current = null;
          setHasPin(false);
          setError(e.message);
          if (e.status === 429) throw e;
          continue;
        }
        throw e;
      }
    }
    throw new Error("Admin PIN rejected.");
  }, []);

  return (
    <Ctx.Provider value={{ withAdmin, hasPin }}>
      {children}
      {prompt && (
        <PinDialog title="Admin PIN" error={error} description={prompt.why}
          onCancel={() => { prompt.resolve(null); setPrompt(null); }}
          onSubmit={(p) => prompt.resolve(p)} />
      )}
    </Ctx.Provider>
  );
}

export function useAdmin(): AdminApi {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAdmin outside provider");
  return v;
}
