"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { useActiveOrg } from "@/components/providers/org-provider";
import {
  createKnowledge,
  askKnowledge,
  searchKnowledge,
} from "@/lib/api/endpoints";
import type { KnowledgeAnswer, KnowledgeSource } from "@/lib/api/types";
import { KnowledgeBrowser } from "@/components/knowledge/KnowledgeBrowser";
import { KnowledgeProposalsPanel } from "@/components/knowledge/KnowledgeProposalsPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const KIND_OPTIONS = [
  { value: "regla_negocio", label: "Regla de negocio" },
  { value: "flujo", label: "Flujo" },
  { value: "riesgo", label: "Riesgo" },
  { value: "glosario", label: "Glosario" },
  { value: "leccion", label: "Lección" },
  { value: "reto", label: "Reto" },
  { value: "patron", label: "Patrón" },
] as const;

type KindValue = (typeof KIND_OPTIONS)[number]["value"];

const EMPTY_FORM = {
  kind: "regla_negocio" as KindValue,
  title: "",
  challenge: "",
  approach: "",
  outcome: "",
  domain: "",
  project: "",
  tags: "",
};

export default function KnowledgePage() {
  const { accessToken } = useAuth();
  const { activeOrgId, isLoading } = useActiveOrg();

  // Capture form state
  const [form, setForm] = useState(EMPTY_FORM);

  // Ask/Search state
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<KnowledgeAnswer | null>(null);
  const [sources, setSources] = useState<KnowledgeSource[]>([]);

  const captureMutation = useMutation({
    mutationFn: () => {
      if (!accessToken) throw new Error("Sin sesión");
      const tags = form.tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      return createKnowledge(accessToken, {
        org_id: activeOrgId,
        kind: form.kind,
        title: form.title,
        ...(form.challenge ? { challenge: form.challenge } : {}),
        ...(form.approach ? { approach: form.approach } : {}),
        ...(form.outcome ? { outcome: form.outcome } : {}),
        ...(form.domain ? { domain: form.domain } : {}),
        ...(form.project ? { project: form.project } : {}),
        tags,
      });
    },
    onSuccess: () => {
      toast.success("Conocimiento capturado.");
      setForm(EMPTY_FORM);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const askMutation = useMutation({
    mutationFn: () => {
      if (!accessToken) throw new Error("Sin sesión");
      return askKnowledge(accessToken, { org_id: activeOrgId, question });
    },
    onSuccess: (data) => {
      setAnswer(data);
      // Also fire a search to get sources
      if (accessToken && activeOrgId) {
        searchKnowledge(accessToken, { org_id: activeOrgId, query: question })
          .then(setSources)
          .catch(() => {
            // degrade silently — sources are optional
          });
      }
    },
    onError: (err: Error) => toast.error(err.message),
  });

  function handleFormChange(
    field: keyof typeof EMPTY_FORM,
    value: string,
  ) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  if (isLoading) {
    return (
      <div className="space-y-6" data-testid="knowledge-loading-skeleton">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Conocimiento</h1>
          <p className="text-sm text-zinc-500">Base de conocimiento institucional del equipo de QA.</p>
        </div>
        <Skeleton className="h-40 max-w-xl rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (!activeOrgId && !isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Conocimiento</h1>
          <p className="text-sm text-zinc-500">Base de conocimiento institucional del equipo de QA.</p>
        </div>
        <Card className="max-w-xl p-5">
          <p className="text-sm text-zinc-500">Selecciona una organización para ver y capturar conocimiento.</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Conocimiento</h1>
        <p className="text-sm text-zinc-500">Base de conocimiento institucional del equipo de QA.</p>
      </div>

      {/* Capture zone */}
      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle className="text-base">Capturar conocimiento</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              captureMutation.mutate();
            }}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="kind">Tipo</Label>
                <Select value={form.kind} onValueChange={(v) => handleFormChange("kind", v)}>
                  <SelectTrigger id="kind" aria-label="Tipo">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {KIND_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="domain">Dominio</Label>
                <Input
                  id="domain"
                  placeholder="p.ej. pagos, auth…"
                  value={form.domain}
                  onChange={(e) => handleFormChange("domain", e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="project">Proyecto / cliente</Label>
                <Input
                  id="project"
                  placeholder="p.ej. checkout-suite"
                  value={form.project}
                  onChange={(e) => handleFormChange("project", e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="title">Título *</Label>
              <Input
                id="title"
                placeholder="Nombre corto del conocimiento"
                required
                value={form.title}
                onChange={(e) => handleFormChange("title", e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="challenge">Reto / problema</Label>
              <Input
                id="challenge"
                placeholder="¿Qué problema o reto describe?"
                value={form.challenge}
                onChange={(e) => handleFormChange("challenge", e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="approach">Enfoque / solución</Label>
              <Input
                id="approach"
                placeholder="¿Cómo se abordó?"
                value={form.approach}
                onChange={(e) => handleFormChange("approach", e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="outcome">Resultado</Label>
              <Input
                id="outcome"
                placeholder="¿Qué resultado se obtuvo?"
                value={form.outcome}
                onChange={(e) => handleFormChange("outcome", e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="tags">Etiquetas (separadas por coma)</Label>
              <Input
                id="tags"
                placeholder="p.ej. crítico, regresión, pago"
                value={form.tags}
                onChange={(e) => handleFormChange("tags", e.target.value)}
              />
            </div>

            <Button type="submit" disabled={captureMutation.isPending || !form.title.trim()}>
              {captureMutation.isPending ? "Guardando…" : "Guardar conocimiento"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Hojeo + curación: explorar, editar, obsoletar, borrar */}
      <KnowledgeBrowser orgId={activeOrgId} />

      {/* Proposals tray — IA propone / humano aprueba */}
      <KnowledgeProposalsPanel orgId={activeOrgId} />

      {/* Ask / Search zone */}
      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle className="text-base">Preguntar a la base de conocimiento</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Input
              placeholder="¿Qué quieres saber? p.ej. ¿Cómo gestionamos errores de pago?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && question.trim()) {
                  e.preventDefault();
                  askMutation.mutate();
                }
              }}
            />
            <Button
              onClick={() => askMutation.mutate()}
              disabled={askMutation.isPending || !question.trim()}
            >
              {askMutation.isPending ? "Consultando…" : "Preguntar"}
            </Button>
          </div>

          {answer && (
            <div className="space-y-3 rounded-xl border border-zinc-200 bg-zinc-50 p-4">
              <p className="text-sm font-medium text-zinc-800">Respuesta</p>
              <p className="text-sm text-zinc-700">{answer.answer}</p>

              {answer.citations.length > 0 && (
                <div>
                  <p className="mb-1.5 text-xs font-medium text-zinc-500">Fuentes citadas</p>
                  <ul className="space-y-1">
                    {answer.citations.map((citation, idx) => (
                      <li key={idx} className="text-xs text-zinc-600">
                        · {citation}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {sources.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-zinc-500">Fuentes encontradas</p>
              {sources.map((src) => (
                <div
                  key={src.id}
                  className="rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm"
                >
                  <div className="flex items-center gap-2">
                    <Badge variant={src.type === "knowledge" ? "default" : "user"}>
                      {src.type}
                    </Badge>
                    {src.confidence && (
                      <span className="text-xs text-zinc-500">confianza: {src.confidence}</span>
                    )}
                  </div>
                  {src.title && (
                    <p className="mt-1 font-medium text-zinc-800">{src.title}</p>
                  )}
                  <p className="mt-0.5 text-zinc-600 line-clamp-2">{src.content}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
