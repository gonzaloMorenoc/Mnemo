"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import {
  approveKnowledgeProposal,
  generateKnowledgeProposals,
  listKnowledgeProposals,
  refineKnowledgeProposal,
  rejectKnowledgeProposal,
} from "@/lib/api/endpoints";
import type { KnowledgeProposal } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export function KnowledgeProposalsPanel({ orgId }: { orgId: string }) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const key = ["knowledge-proposals", orgId];

  const query = useQuery({
    queryKey: key,
    queryFn: () => listKnowledgeProposals(accessToken!, orgId),
    enabled: Boolean(accessToken && orgId),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: key });

  const generate = useMutation({
    mutationFn: () => generateKnowledgeProposals(accessToken!, orgId),
    onSuccess: (r) => {
      const parts = [`${r.created} propuesta(s) generada(s)`];
      if (r.failed) parts.push(`${r.failed} fallo(s) — reintenta`);
      if (r.remaining) parts.push(`${r.remaining} defecto(s) sin cubrir`);
      toast.success(parts.join(" · "));
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const proposals = query.data ?? [];

  return (
    <Card className="max-w-2xl">
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2 text-base">
          Propuestas de la IA
          {proposals.length > 0 && <Badge>{proposals.length}</Badge>}
        </CardTitle>
        <Button
          size="sm"
          variant="ghost"
          disabled={generate.isPending}
          onClick={() => generate.mutate()}
        >
          {generate.isPending ? "Generando…" : "Generar propuestas"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-zinc-500">
          Mnemo redacta lecciones a partir de los defectos que aún no están documentados.
          Revísalas (y edítalas si hace falta) antes de que entren en la memoria.
        </p>
        {proposals.length === 0 ? (
          <p className="text-sm text-zinc-500">No hay propuestas pendientes.</p>
        ) : (
          proposals.map((p) => (
            <ProposalCard key={p.id} proposal={p} token={accessToken!} onDone={invalidate} />
          ))
        )}
      </CardContent>
    </Card>
  );
}

// Los 7 tipos del esquema (check de kind en BD) con su etiqueta en español.
const KIND_OPTIONS: [string, string][] = [
  ["leccion", "Lección"],
  ["regla_negocio", "Regla de negocio"],
  ["flujo", "Flujo"],
  ["riesgo", "Riesgo"],
  ["glosario", "Glosario"],
  ["reto", "Reto"],
  ["patron", "Patrón"],
];

const SOURCE_BADGE: Record<string, { label: string; className: string }> = {
  auto_triage: { label: "Triaje", className: "" },
  jira: { label: "Jira", className: "border-blue-200 bg-blue-50 text-blue-700" },
  confluence: { label: "Confluence", className: "border-teal-200 bg-teal-50 text-teal-700" },
};

function ProposalCard({
  proposal,
  token,
  onDone,
}: {
  proposal: KnowledgeProposal;
  token: string;
  onDone: () => void;
}) {
  const [form, setForm] = useState({
    kind: proposal.kind,
    title: proposal.title ?? "",
    challenge: proposal.challenge ?? "",
    approach: proposal.approach ?? "",
    domain: proposal.domain ?? "",
    outcome: proposal.outcome ?? "",
    tags: (proposal.tags ?? []).join(", "),
  });
  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const refine = useMutation({
    mutationFn: () => refineKnowledgeProposal(token, proposal.id),
    onSuccess: (p) => {
      setForm((f) => ({
        ...f,
        kind: p.kind ?? f.kind,
        title: p.title ?? f.title,
        challenge: p.challenge ?? f.challenge,
        approach: p.approach ?? f.approach,
        domain: p.domain ?? f.domain,
        outcome: p.outcome ?? f.outcome,
      }));
      toast.success("Propuesta refinada — revisa antes de aprobar.");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const approve = useMutation({
    mutationFn: () =>
      approveKnowledgeProposal(token, proposal.id, {
        kind: form.kind,
        title: form.title,
        challenge: form.challenge || null,
        approach: form.approach || null,
        domain: form.domain || null,
        outcome: form.outcome || null,
        tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
      }),
    onSuccess: () => {
      toast.success("Lección añadida a la memoria.");
      onDone();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const reject = useMutation({
    mutationFn: () => rejectKnowledgeProposal(token, proposal.id),
    onSuccess: () => {
      toast.success("Propuesta descartada.");
      onDone();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const badge = SOURCE_BADGE[proposal.source] ?? SOURCE_BADGE.auto_triage;

  return (
    <div className="space-y-3 rounded-xl border border-zinc-200 bg-zinc-50 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge className={badge.className}>{badge.label}</Badge>
        <span className="text-xs text-zinc-500">
          {proposal.source === "auto_triage"
            ? "inferida del triaje · revisa antes de aprobar"
            : "importada — revisa y destila antes de aprobar"}
        </span>
        {proposal.external_url && (
          <a
            href={proposal.external_url}
            target="_blank"
            rel="noreferrer"
            className="text-xs font-medium text-zinc-600 underline underline-offset-2 hover:text-zinc-900"
          >
            Ver original ↗
          </a>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
        <div className="space-y-1.5">
          <Label htmlFor={`t-${proposal.id}`}>Título</Label>
          <Input id={`t-${proposal.id}`} maxLength={300} value={form.title} onChange={(e) => set("title", e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`k-${proposal.id}`}>Tipo</Label>
          {/* El tipo decide qué detectores de gaps ven el item (regla_sin_test solo
              mira regla_negocio/flujo/riesgo) → editable, no congelado */}
          <select
            id={`k-${proposal.id}`}
            value={form.kind}
            onChange={(e) => set("kind", e.target.value)}
            className="h-10 rounded-xl border border-zinc-300 bg-white px-3 text-sm text-zinc-900"
          >
            {KIND_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Reto y enfoque son multilínea (causa raíz + pasos numerados) → Textarea */}
      <div className="space-y-1.5">
        <Label htmlFor={`c-${proposal.id}`}>Reto / problema</Label>
        <Textarea id={`c-${proposal.id}`} rows={3} maxLength={4000} value={form.challenge} onChange={(e) => set("challenge", e.target.value)} />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`a-${proposal.id}`}>Enfoque / solución</Label>
        <Textarea id={`a-${proposal.id}`} rows={4} maxLength={4000} value={form.approach} onChange={(e) => set("approach", e.target.value)} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={`d-${proposal.id}`}>Dominio</Label>
          <Input id={`d-${proposal.id}`} maxLength={300} placeholder="p.ej. pagos" value={form.domain} onChange={(e) => set("domain", e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`g-${proposal.id}`}>Etiquetas (separadas por coma)</Label>
          <Input id={`g-${proposal.id}`} value={form.tags} onChange={(e) => set("tags", e.target.value)} />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`o-${proposal.id}`}>Resultado (a completar)</Label>
        <Textarea id={`o-${proposal.id}`} rows={2} maxLength={4000} placeholder="¿Qué resultado se obtuvo?" value={form.outcome} onChange={(e) => set("outcome", e.target.value)} />
      </div>

      <div className="flex justify-end gap-2">
        <Button
          size="sm"
          variant="ghost"
          disabled={approve.isPending || reject.isPending || refine.isPending}
          onClick={() => refine.mutate()}
        >
          {refine.isPending ? "Refinando…" : "Refinar con IA"}
        </Button>
        <Button size="sm" variant="ghost" disabled={approve.isPending || reject.isPending || refine.isPending} onClick={() => reject.mutate()}>
          Descartar
        </Button>
        <Button size="sm" disabled={approve.isPending || reject.isPending || refine.isPending || !form.title.trim()} onClick={() => approve.mutate()}>
          {approve.isPending ? "Aprobando…" : "Aprobar"}
        </Button>
      </div>
    </div>
  );
}
