"use client";

import { useEffect, useState } from "react";

import { WAKING_NOTICE_AFTER_MS, warmBackend } from "@/lib/warmup";

type Phase = "checking" | "waking" | "ready" | "unreachable";

/**
 * Lanza el ping de calentamiento al montar (landing, login, registro) y, si se
 * pide, avisa con amabilidad mientras el servidor despierta en vez de dejar que
 * el primer intento acabe en un error rojo.
 */
export function BackendWarmup({ showNotice = false }: { showNotice?: boolean }) {
  const [phase, setPhase] = useState<Phase>("checking");

  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      if (active) setPhase((p) => (p === "checking" ? "waking" : p));
    }, WAKING_NOTICE_AFTER_MS);
    void warmBackend().then((result) => {
      if (active) setPhase(result);
    });
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);

  if (!showNotice) return null;
  if (phase === "waking") {
    return (
      <p role="status" className="rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm text-zinc-600">
        Despertando el servidor… La primera conexión del día puede tardar hasta un minuto. Puedes
        ir escribiendo mientras tanto.
      </p>
    );
  }
  if (phase === "unreachable") {
    return (
      <p role="status" className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
        El servidor aún no responde. Puede seguir arrancando: inténtalo de nuevo en unos segundos.
      </p>
    );
  }
  return null;
}
