"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { generateKnowledgeProposals, listKnowledge } from "@/lib/api/endpoints";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

/**
 * Memoria en el flujo: al mirar una familia de defectos, la lección vinculada
 * aparece al lado — sin ir a buscarla. Si no existe, un clic deja el borrador
 * en la bandeja de propuestas (IA propone / humano aprueba).
 */
export function FamilyMemoryPanel({
  token,
  orgId,
  familyId,
}: {
  token: string;
  orgId: string;
  familyId: string;
}) {
  const qc = useQueryClient();

  const lessons = useQuery({
    queryKey: ["family-memory", familyId],
    queryFn: () =>
      listKnowledge(token, orgId, { defect_family_id: familyId, status: "activo" }),
    enabled: Boolean(token && orgId && familyId),
  });

  const propose = useMutation({
    mutationFn: () => generateKnowledgeProposals(token, orgId, { cap: 1, familyIds: [familyId] }),
    onSuccess: (r) => {
      if (r.created > 0) {
        toast.success("Propuesta creada — revísala en Conocimiento.");
        qc.invalidateQueries({ queryKey: ["knowledge-proposals", orgId] });
      } else {
        toast.error("No se generó: la familia ya tiene propuesta pendiente o el LLM no respondió.");
      }
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const items = lessons.data ?? [];

  return (
    <div className="mt-3 space-y-2 border-t border-zinc-100 pt-3">
      <p className="text-xs font-medium text-zinc-500">Memoria del equipo</p>
      {lessons.isLoading ? null : items.length === 0 ? (
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm text-zinc-500">Esta familia aún no tiene lección documentada.</p>
          <Button
            size="sm"
            variant="ghost"
            disabled={propose.isPending}
            onClick={() => propose.mutate()}
          >
            {propose.isPending ? "Proponiendo…" : "Proponer lección (IA)"}
          </Button>
        </div>
      ) : (
        items.map((l) => (
          <div key={l.id} className="rounded-lg border border-emerald-100 bg-emerald-50/50 p-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className="bg-emerald-100 text-emerald-800">Lección</Badge>
              <span className="text-sm font-medium text-zinc-900">{l.title}</span>
            </div>
            {l.approach && (
              <p className="mt-1 text-sm text-zinc-600 line-clamp-3">{l.approach}</p>
            )}
            <Link
              href="/app/knowledge?tab=explorar"
              className="mt-1 inline-block text-xs font-medium text-emerald-700 hover:text-emerald-900"
            >
              Ver en Conocimiento →
            </Link>
          </div>
        ))
      )}
    </div>
  );
}
