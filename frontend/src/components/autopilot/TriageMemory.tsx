"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getFamilyMemory } from "@/lib/api/endpoints";
import type { FamilyMemory } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";

/**
 * Memoria en el flujo, en el triaje: qué dejó escrito el equipo sobre la familia de
 * este fallo (etiqueta y su porqué, lecciones, dónde más apareció). Se carga al
 * desplegar, para no pedir N memorias al pintar un run con muchos fallos.
 */
export function TriageMemory({ familyId }: { familyId: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="w-full">
      <button
        type="button"
        className="text-xs font-medium text-primary hover:underline"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? "Ocultar memoria del equipo" : "Memoria del equipo"}
      </button>
      {open && <MemoryBody familyId={familyId} />}
    </div>
  );
}

function MemoryBody({ familyId }: { familyId: string }) {
  const { accessToken } = useAuth();
  const query = useQuery({
    queryKey: ["family-memory-full", familyId],
    queryFn: () => getFamilyMemory(accessToken!, familyId),
    enabled: Boolean(accessToken && familyId),
    retry: false,
  });

  if (query.isLoading) return <p className="mt-2 text-xs text-zinc-500">Cargando memoria…</p>;
  if (query.isError || !query.data)
    return <p className="mt-2 text-xs text-red-600">No se pudo cargar la memoria de esta familia.</p>;
  return <MemoryView memory={query.data} />;
}

function author(memory: FamilyMemory): string {
  const who = memory.reason_by || memory.reason_by_email || "alguien del equipo";
  const gone = memory.reason_by_active ? "" : " (ya no está en la organización)";
  const when = memory.reason_at ? `, ${memory.reason_at.slice(0, 10)}` : "";
  return `${who}${gone}${when}`;
}

export function MemoryView({ memory }: { memory: FamilyMemory }) {
  const seen = memory.runs > 0
    ? `Vista en ${memory.runs} run${memory.runs === 1 ? "" : "s"}` +
      (memory.projects.length > 1 ? ` · proyectos: ${memory.projects.join(", ")}` : "")
    : null;
  return (
    <div className="mt-2 space-y-2 rounded-lg border border-zinc-100 bg-zinc-50 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        {memory.label_text && (
          <Badge className="bg-primary/10 text-primary">Etiqueta del equipo: {memory.label_text}</Badge>
        )}
        {seen && <span className="text-xs text-zinc-500">{seen}</span>}
      </div>

      {!memory.has_memory && (
        <p className="text-zinc-500">
          El equipo aún no ha dejado nada escrito sobre esta familia. Etiquetarla con una razón
          o documentar una lección hará que la próxima vez aparezca aquí y en el check del PR.
        </p>
      )}

      {memory.reason && (
        <blockquote className="border-l-2 border-primary/40 pl-3 text-zinc-700">
          <p>“{memory.reason}”</p>
          <footer className="mt-1 text-xs text-zinc-500">— {author(memory)}</footer>
        </blockquote>
      )}

      {memory.lessons.length > 0 && (
        <ul className="space-y-1">
          {memory.lessons.map((l) => (
            <li key={l.id}>
              <Badge className="mr-2 bg-emerald-100 text-emerald-800">Lección</Badge>
              <span className="font-medium text-zinc-900">{l.title}</span>
              {l.summary && <p className="mt-0.5 line-clamp-2 text-zinc-600">{l.summary}</p>}
            </li>
          ))}
        </ul>
      )}

      {memory.related.length > 0 && (
        <div>
          <p className="text-xs font-medium text-zinc-500">Conocimiento relacionado</p>
          <ul className="mt-1 list-disc pl-5 text-zinc-700">
            {memory.related.map((r) => (
              <li key={r.id}>{r.title || "(sin título)"}</li>
            ))}
          </ul>
        </div>
      )}

      <Link
        href={`/app/defects?family=${encodeURIComponent(memory.family_id)}`}
        className="inline-block text-xs font-medium text-primary hover:underline"
      >
        Abrir la familia →
      </Link>
    </div>
  );
}
