"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { useActiveOrg } from "@/components/providers/org-provider";
import {
  domainSummary,
  learningPath,
  askKnowledge,
} from "@/lib/api/endpoints";
import type { DomainSummary, KnowledgeAnswer, LearningPath } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function OnboardingPage() {
  const { accessToken } = useAuth();
  const { activeOrgId } = useActiveOrg();

  const [topic, setTopic] = useState("");

  // Domain summary state
  const [summary, setSummary] = useState<DomainSummary | null>(null);

  // Learning path state
  const [path, setPath] = useState<LearningPath | null>(null);

  // Chat state
  const [question, setQuestion] = useState("");
  const [chatAnswer, setChatAnswer] = useState<KnowledgeAnswer | null>(null);

  const summaryMutation = useMutation({
    mutationFn: () => {
      if (!accessToken) throw new Error("Sin sesión");
      return domainSummary(accessToken, { org_id: activeOrgId ?? "", topic: topic.trim() });
    },
    onSuccess: setSummary,
    onError: (err: Error) => toast.error(err.message),
  });

  const pathMutation = useMutation({
    mutationFn: () => {
      if (!accessToken) throw new Error("Sin sesión");
      return learningPath(accessToken, { org_id: activeOrgId ?? "", topic: topic.trim() });
    },
    onSuccess: setPath,
    onError: (err: Error) => toast.error(err.message),
  });

  const askMutation = useMutation({
    mutationFn: () => {
      if (!accessToken) throw new Error("Sin sesión");
      return askKnowledge(accessToken, { org_id: activeOrgId ?? "", question });
    },
    onSuccess: setChatAnswer,
    onError: (err: Error) => toast.error(err.message),
  });

  if (!activeOrgId) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Onboarding</h1>
          <p className="text-sm text-zinc-500">Ponte al día rápidamente con el dominio y los sistemas de QA del proyecto.</p>
        </div>
        <Card className="max-w-xl p-5">
          <p className="text-sm text-zinc-500">Selecciona una organización para comenzar el onboarding.</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Onboarding</h1>
        <p className="text-sm text-zinc-500">Ponte al día rápidamente con el dominio y los sistemas de QA del proyecto.</p>
      </div>

      {/* Topic input */}
      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle className="text-base">Tema / Dominio</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="topic">¿Sobre qué área quieres aprender?</Label>
            <Input
              id="topic"
              placeholder="p.ej. pagos, autenticación, checkout…"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && topic.trim()) {
                  e.preventDefault();
                  summaryMutation.mutate();
                }
              }}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() => summaryMutation.mutate()}
              disabled={summaryMutation.isPending || !topic.trim()}
            >
              {summaryMutation.isPending ? "Analizando…" : "¿Qué sabe el proyecto?"}
            </Button>
            <Button
              variant="outline"
              onClick={() => pathMutation.mutate()}
              disabled={pathMutation.isPending || !topic.trim()}
            >
              {pathMutation.isPending ? "Generando ruta…" : "Ruta de aprendizaje"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Domain summary result */}
      {summary && (
        <Card className="max-w-2xl">
          <CardHeader>
            <CardTitle className="text-base">Resumen del dominio: {topic}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {summary.rules.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-zinc-500">Reglas de negocio</p>
                <ul className="space-y-1">
                  {summary.rules.map((rule, idx) => (
                    <li key={idx} className="text-sm text-zinc-700">· {rule}</li>
                  ))}
                </ul>
              </div>
            )}
            {summary.systems.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-zinc-500">Sistemas</p>
                <ul className="space-y-1">
                  {summary.systems.map((sys, idx) => (
                    <li key={idx} className="text-sm text-zinc-700">· {sys}</li>
                  ))}
                </ul>
              </div>
            )}
            {summary.existing_tests.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-zinc-500">Tests existentes</p>
                <ul className="space-y-1">
                  {summary.existing_tests.map((t, idx) => (
                    <li key={idx} className="text-sm text-zinc-700">· {t}</li>
                  ))}
                </ul>
              </div>
            )}
            {summary.historical_bugs.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-zinc-500">Bugs históricos</p>
                <ul className="space-y-1">
                  {summary.historical_bugs.map((bug, idx) => (
                    <li key={idx} className="text-sm text-zinc-700">· {bug}</li>
                  ))}
                </ul>
              </div>
            )}
            {summary.risks.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-zinc-500">Riesgos</p>
                <ul className="space-y-1">
                  {summary.risks.map((risk, idx) => (
                    <li key={idx} className="text-sm text-zinc-700">· {risk}</li>
                  ))}
                </ul>
              </div>
            )}
            {summary.citations.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-zinc-500">Fuentes citadas</p>
                <ul className="space-y-1">
                  {summary.citations.map((citation, idx) => (
                    <li key={idx} className="text-xs text-zinc-500">· {citation}</li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Learning path result */}
      {path && (
        <Card className="max-w-2xl">
          <CardHeader>
            <CardTitle className="text-base">Ruta de aprendizaje: {topic}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {path.days.map((day) => (
              <div key={day.day} className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 space-y-2">
                <p className="text-sm font-semibold text-zinc-800">Día {day.day}</p>
                <ul className="space-y-1">
                  {day.items.map((item, idx) => (
                    <li key={idx} className="text-sm text-zinc-700">· {item}</li>
                  ))}
                </ul>
              </div>
            ))}
            {path.citations.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-zinc-500">Fuentes citadas</p>
                <ul className="space-y-1">
                  {path.citations.map((citation, idx) => (
                    <li key={idx} className="text-xs text-zinc-500">· {citation}</li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Chat section */}
      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle className="text-base">Preguntar al equipo</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Input
              placeholder="¿Cómo funciona el flujo de checkout? ¿Qué hacer si el pago falla?"
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

          {chatAnswer && (
            <div className="space-y-3 rounded-xl border border-zinc-200 bg-zinc-50 p-4">
              <p className="text-sm font-medium text-zinc-800">Respuesta</p>
              <p className="text-sm text-zinc-700">{chatAnswer.answer}</p>

              {chatAnswer.citations.length > 0 && (
                <div>
                  <p className="mb-1.5 text-xs font-medium text-zinc-500">Fuentes citadas</p>
                  <ul className="space-y-1">
                    {chatAnswer.citations.map((citation, idx) => (
                      <li key={idx} className="text-xs text-zinc-600">
                        · {citation}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
