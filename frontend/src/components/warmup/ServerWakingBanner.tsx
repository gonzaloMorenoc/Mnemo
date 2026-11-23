"use client";

import { useQueryClient, type QueryCache } from "@tanstack/react-query";
import { useCallback, useSyncExternalStore } from "react";

import { isTransientError } from "@/lib/api/retry";

/** ¿Hay alguna consulta reintentando tras un 502/504/red caída? = el backend despierta. */
export function hasWakingQueries(cache: QueryCache): boolean {
  return cache.getAll().some(({ state }) => {
    return (
      state.fetchStatus === "fetching" &&
      state.fetchFailureCount > 0 &&
      isTransientError(state.fetchFailureReason)
    );
  });
}

/**
 * Un único aviso global mientras el servidor arranca, en lugar de una tarjeta
 * roja por consulta: las consultas siguen en «cargando» mientras reintentan.
 */
export function ServerWakingBanner() {
  const cache = useQueryClient().getQueryCache();
  const subscribe = useCallback((onChange: () => void) => cache.subscribe(onChange), [cache]);
  const waking = useSyncExternalStore(
    subscribe,
    () => hasWakingQueries(cache),
    () => false,
  );

  if (!waking) return null;
  return (
    <p
      role="status"
      className="mb-4 rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm text-zinc-600"
    >
      Despertando el servidor… La primera carga del día puede tardar hasta un minuto; los datos
      aparecerán solos.
    </p>
  );
}
