"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { useActiveOrg } from "@/components/providers/org-provider";
import { generateTestPlan, exportTestPlanXray, generatePlaywrightTest, openAutomationPr } from "@/lib/api/endpoints";
import { ApiClientError } from "@/lib/api/client";
import type { GeneratedTest, TestCase, TestPlan } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type InputMode = "texto" | "jira_url" | "archivo";
type CaseFormat = "steps" | "gherkin";

function downloadMarkdown(plan: TestPlan, citations: string[]) {
  const lines: string[] = [
    `# Plan de Pruebas`,
    ``,
    `## Resumen`,
    plan.summary,
    ``,
    `## Sistemas`,
    ...plan.systems.map((s) => `- ${s}`),
    ``,
    `## Riesgos`,
    ...plan.risks.map((r) => `- ${r}`),
    ``,
    `## Precondiciones`,
    ...plan.preconditions.map((p) => `- ${p}`),
    ``,
    `## Datos de prueba`,
    ...plan.test_data.map((d) => `- ${d}`),
    ``,
    `## Casos de prueba`,
  ];

  plan.cases.forEach((c, idx) => {
    lines.push(``, `### ${idx + 1}. ${c.title}`);
    lines.push(`- **Nivel:** ${c.level}`);
    lines.push(`- **Prioridad:** ${c.priority}`);
    lines.push(`- **Automatizable:** ${c.automatable ? "Sí" : "No"}`);
    if (c.gherkin) {
      lines.push(``, `\`\`\`gherkin`, c.gherkin, `\`\`\``);
    } else {
      if (c.steps && c.steps.length > 0) {
        lines.push(``, `**Pasos:**`);
        c.steps.forEach((step, i) => lines.push(`${i + 1}. ${step}`));
      }
      if (c.expected) {
        lines.push(``, `**Resultado esperado:** ${c.expected}`);
      }
    }
  });

  if (plan.gaps.length > 0) {
    lines.push(``, `## Brechas`, ...plan.gaps.map((g) => `- ${g}`));
  }
  if (plan.open_questions.length > 0) {
    lines.push(``, `## Preguntas abiertas`, ...plan.open_questions.map((q) => `- ${q}`));
  }
  if (citations.length > 0) {
    lines.push(``, `## Citas`, ...citations.map((c) => `- ${c}`));
  }

  const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "plan-de-pruebas.md";
  a.click();
  URL.revokeObjectURL(url);
}

function downloadSpecTs(code: string, filename: string) {
  const blob = new Blob([code], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

interface CasePlaywrightSectionProps {
  tc: TestCase;
  accessToken: string;
  activeOrgId: string;
  styleSample: string;
}

function CasePlaywrightSection({ tc, accessToken, activeOrgId, styleSample }: CasePlaywrightSectionProps) {
  const [generated, setGenerated] = useState<GeneratedTest | null>(null);

  const generateMut = useMutation({
    mutationFn: () =>
      generatePlaywrightTest(accessToken, {
        case: tc,
        ...(styleSample.trim() ? { style_sample: styleSample.trim() } : {}),
      }),
    onSuccess: (data) => setGenerated(data),
    onError: (err: Error) => toast.error(err.message),
  });

  const prMut = useMutation({
    mutationFn: () => {
      if (!generated) throw new Error("Sin código generado");
      return openAutomationPr(accessToken, {
        org_id: activeOrgId,
        code: generated.code,
        filename: generated.filename,
      });
    },
    onSuccess: (data) => toast.success(data.pr_url),
    onError: (err: Error) => {
      const msg = err instanceof ApiClientError && err.status === 503 ? "Configura GitHub" : err.message;
      toast.error(msg);
    },
  });

  return (
    <div className="pt-2 space-y-2">
      <Button
        size="sm"
        variant="outline"
        onClick={() => generateMut.mutate()}
        disabled={generateMut.isPending}
      >
        {generateMut.isPending ? "Generando…" : "Generar test Playwright"}
      </Button>

      {generated && (
        <div className="space-y-2 rounded-lg border border-zinc-200 bg-white p-3">
          {generated.notes && (
            <p className="text-xs text-zinc-500">{generated.notes}</p>
          )}
          <pre className="rounded bg-zinc-900 text-zinc-100 p-3 text-xs overflow-x-auto whitespace-pre-wrap">
            {generated.code}
          </pre>
          <div className="flex gap-2 flex-wrap">
            <Button
              size="sm"
              variant="outline"
              onClick={() => downloadSpecTs(generated.code, generated.filename)}
            >
              Descargar
            </Button>
            <Button
              size="sm"
              onClick={() => prMut.mutate()}
              disabled={prMut.isPending}
            >
              {prMut.isPending ? "Abriendo PR…" : "Abrir draft PR"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function TestPlanPage() {
  const { accessToken } = useAuth();
  const { activeOrgId } = useActiveOrg();

  const [inputMode, setInputMode] = useState<InputMode>("texto");
  const [caseFormat, setCaseFormat] = useState<CaseFormat>("steps");
  const [huText, setHuText] = useState("");
  const [jiraUrl, setJiraUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const [plan, setPlan] = useState<TestPlan | null>(null);
  const [citations, setCitations] = useState<string[]>([]);

  // Playwright generation state
  const [styleSample, setStyleSample] = useState("");

  // Plan editable fields
  const [editSummary, setEditSummary] = useState("");
  const [editSystems, setEditSystems] = useState("");
  const [editRisks, setEditRisks] = useState("");
  const [editPreconditions, setEditPreconditions] = useState("");
  const [editTestData, setEditTestData] = useState("");
  const [editGaps, setEditGaps] = useState("");
  const [editOpenQuestions, setEditOpenQuestions] = useState("");

  function buildFormData(): FormData {
    const form = new FormData();
    form.append("org_id", activeOrgId ?? "");
    form.append("case_format", caseFormat);
    if (inputMode === "texto" && huText.trim()) {
      form.append("hu_text", huText.trim());
    } else if (inputMode === "jira_url" && jiraUrl.trim()) {
      form.append("jira_url", jiraUrl.trim());
    } else if (inputMode === "archivo" && file) {
      form.append("file", file);
    }
    return form;
  }

  function applyPlanToState(result: { plan: TestPlan; citations: string[] }) {
    const p = result.plan;
    setPlan(p);
    setCitations(result.citations);
    setEditSummary(p.summary);
    setEditSystems(p.systems.join("\n"));
    setEditRisks(p.risks.join("\n"));
    setEditPreconditions(p.preconditions.join("\n"));
    setEditTestData(p.test_data.join("\n"));
    setEditGaps(p.gaps.join("\n"));
    setEditOpenQuestions(p.open_questions.join("\n"));
  }

  const generateMutation = useMutation({
    mutationFn: () => {
      if (!accessToken) throw new Error("Sin sesión");
      return generateTestPlan(accessToken, buildFormData());
    },
    onSuccess: applyPlanToState,
    onError: (err: Error) => toast.error(err.message),
  });

  const xrayMutation = useMutation({
    mutationFn: () => {
      if (!accessToken) throw new Error("Sin sesión");
      if (!plan) throw new Error("No hay plan generado");
      const currentPlan: TestPlan = {
        ...plan,
        summary: editSummary,
        systems: editSystems.split("\n").filter(Boolean),
        risks: editRisks.split("\n").filter(Boolean),
        preconditions: editPreconditions.split("\n").filter(Boolean),
        test_data: editTestData.split("\n").filter(Boolean),
        gaps: editGaps.split("\n").filter(Boolean),
        open_questions: editOpenQuestions.split("\n").filter(Boolean),
        citations,
      };
      return exportTestPlanXray(accessToken, {
        org_id: activeOrgId ?? "",
        plan: currentPlan,
        case_format: caseFormat,
      });
    },
    onSuccess: (data) => {
      const keys = (data.keys ?? []).join(", ");
      if (keys.length > 0) {
        toast.success(`Importado a Xray: ${keys}`);
      } else {
        toast.success("Importado a Xray correctamente.");
      }
    },
    onError: () => toast.error("Configura Xray"),
  });

  function handleExportMarkdown() {
    if (!plan) return;
    const currentPlan: TestPlan = {
      ...plan,
      summary: editSummary,
      systems: editSystems.split("\n").filter(Boolean),
      risks: editRisks.split("\n").filter(Boolean),
      preconditions: editPreconditions.split("\n").filter(Boolean),
      test_data: editTestData.split("\n").filter(Boolean),
      gaps: editGaps.split("\n").filter(Boolean),
      open_questions: editOpenQuestions.split("\n").filter(Boolean),
      citations,
    };
    downloadMarkdown(currentPlan, citations);
  }

  if (!activeOrgId) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Plan de pruebas</h1>
          <p className="text-sm text-zinc-500">Genera un plan de pruebas a partir de historias de usuario o documentos.</p>
        </div>
        <Card className="max-w-xl p-5">
          <p className="text-sm text-zinc-500">Selecciona una organización para generar un plan de pruebas.</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Plan de pruebas</h1>
        <p className="text-sm text-zinc-500">Genera un plan de pruebas a partir de historias de usuario o documentos.</p>
      </div>

      {/* Input form */}
      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle className="text-base">Fuente de la historia de usuario</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Input mode selector */}
          <div className="space-y-1.5">
            <Label>Modo de entrada</Label>
            <div className="flex gap-4">
              {(["texto", "jira_url", "archivo"] as InputMode[]).map((mode) => (
                <label key={mode} className="flex items-center gap-1.5 cursor-pointer text-sm">
                  <input
                    type="radio"
                    name="inputMode"
                    value={mode}
                    checked={inputMode === mode}
                    onChange={() => setInputMode(mode)}
                    className="accent-zinc-900"
                  />
                  {mode === "texto" ? "Texto" : mode === "jira_url" ? "Jira URL" : "Subir archivo"}
                </label>
              ))}
            </div>
          </div>

          {/* Input field based on mode */}
          {inputMode === "texto" && (
            <div className="space-y-1.5">
              <Label htmlFor="hu-text">Historia de usuario</Label>
              <textarea
                id="hu-text"
                className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-zinc-400 min-h-[120px] resize-y"
                placeholder="Pega aquí la historia de usuario o el texto de los requisitos…"
                value={huText}
                onChange={(e) => setHuText(e.target.value)}
              />
            </div>
          )}

          {inputMode === "jira_url" && (
            <div className="space-y-1.5">
              <Label htmlFor="jira-url">URL de Jira</Label>
              <Input
                id="jira-url"
                placeholder="https://myorg.atlassian.net/browse/PROJ-123"
                value={jiraUrl}
                onChange={(e) => setJiraUrl(e.target.value)}
              />
            </div>
          )}

          {inputMode === "archivo" && (
            <div className="space-y-1.5">
              <Label htmlFor="hu-file">Archivo (PDF o Word)</Label>
              <Input
                id="hu-file"
                type="file"
                accept=".pdf,.doc,.docx"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </div>
          )}

          {/* Format selector */}
          <div className="space-y-1.5">
            <Label>Formato de casos</Label>
            <div className="flex gap-4">
              {(["steps", "gherkin"] as CaseFormat[]).map((fmt) => (
                <label key={fmt} className="flex items-center gap-1.5 cursor-pointer text-sm">
                  <input
                    type="radio"
                    name="caseFormat"
                    value={fmt}
                    checked={caseFormat === fmt}
                    onChange={() => setCaseFormat(fmt)}
                    className="accent-zinc-900"
                  />
                  {fmt === "steps" ? "Manual (pasos)" : "Gherkin"}
                </label>
              ))}
            </div>
          </div>

          <Button
            onClick={() => generateMutation.mutate()}
            disabled={generateMutation.isPending}
          >
            {generateMutation.isPending ? "Generando…" : "Generar"}
          </Button>
        </CardContent>
      </Card>

      {/* Plan result */}
      {plan && (
        <div className="space-y-6 max-w-3xl">
          {/* Action buttons */}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => generateMutation.mutate()}
              disabled={generateMutation.isPending}
            >
              {generateMutation.isPending ? "Re-generando…" : "Re-generar"}
            </Button>
            <Button variant="outline" onClick={handleExportMarkdown}>
              Exportar Markdown
            </Button>
            <Button
              onClick={() => xrayMutation.mutate()}
              disabled={xrayMutation.isPending}
            >
              {xrayMutation.isPending ? "Importando…" : "Importar a Jira (Xray)"}
            </Button>
          </div>

          {/* Style sample for Playwright generation */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Ejemplo de estilo (opcional)</CardTitle>
            </CardHeader>
            <CardContent>
              <textarea
                aria-label="Ejemplo de estilo Playwright"
                className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm font-mono shadow-sm focus:outline-none focus:ring-2 focus:ring-zinc-400 min-h-[80px] resize-y"
                placeholder="Pega aquí un test Playwright de referencia para que el generador siga tu estilo…"
                value={styleSample}
                onChange={(e) => setStyleSample(e.target.value)}
              />
            </CardContent>
          </Card>

          {/* Summary */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Resumen</CardTitle>
            </CardHeader>
            <CardContent>
              <textarea
                aria-label="Resumen del plan"
                className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-zinc-400 min-h-[80px] resize-y"
                value={editSummary}
                onChange={(e) => setEditSummary(e.target.value)}
              />
            </CardContent>
          </Card>

          {/* Metadata sections */}
          <div className="grid gap-4 sm:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Sistemas</CardTitle>
              </CardHeader>
              <CardContent>
                <textarea
                  aria-label="Sistemas"
                  className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-zinc-400 min-h-[80px] resize-y"
                  placeholder="Uno por línea"
                  value={editSystems}
                  onChange={(e) => setEditSystems(e.target.value)}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Riesgos</CardTitle>
              </CardHeader>
              <CardContent>
                <textarea
                  aria-label="Riesgos"
                  className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-zinc-400 min-h-[80px] resize-y"
                  placeholder="Uno por línea"
                  value={editRisks}
                  onChange={(e) => setEditRisks(e.target.value)}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Precondiciones</CardTitle>
              </CardHeader>
              <CardContent>
                <textarea
                  aria-label="Precondiciones"
                  className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-zinc-400 min-h-[80px] resize-y"
                  placeholder="Uno por línea"
                  value={editPreconditions}
                  onChange={(e) => setEditPreconditions(e.target.value)}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Datos de prueba</CardTitle>
              </CardHeader>
              <CardContent>
                <textarea
                  aria-label="Datos de prueba"
                  className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-zinc-400 min-h-[80px] resize-y"
                  placeholder="Uno por línea"
                  value={editTestData}
                  onChange={(e) => setEditTestData(e.target.value)}
                />
              </CardContent>
            </Card>
          </div>

          {/* Test cases */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Casos de prueba ({plan.cases.length})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {plan.cases.map((tc, idx) => (
                <div
                  key={idx}
                  className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 space-y-2"
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm text-zinc-900">{tc.title}</span>
                    <span className="rounded-full bg-zinc-200 px-2 py-0.5 text-xs text-zinc-600">{tc.level}</span>
                    <span className="rounded-full bg-zinc-200 px-2 py-0.5 text-xs text-zinc-600">{tc.priority}</span>
                    {tc.automatable && (
                      <span className="rounded-full bg-green-100 text-green-800 px-2 py-0.5 text-xs">automatizable</span>
                    )}
                  </div>

                  {tc.gherkin ? (
                    <pre className="rounded bg-zinc-900 text-zinc-100 p-3 text-xs overflow-x-auto whitespace-pre-wrap">
                      {tc.gherkin}
                    </pre>
                  ) : (
                    <>
                      {tc.steps && tc.steps.length > 0 && (
                        <div>
                          <p className="text-xs font-medium text-zinc-500 mb-1">Pasos</p>
                          <ol className="list-decimal list-inside space-y-0.5 text-sm text-zinc-700">
                            {tc.steps.map((step, si) => (
                              <li key={si}>{step}</li>
                            ))}
                          </ol>
                        </div>
                      )}
                      {tc.expected && (
                        <p className="text-sm text-zinc-700">
                          <span className="font-medium text-zinc-500">Esperado: </span>
                          {tc.expected}
                        </p>
                      )}
                    </>
                  )}

                  {accessToken && activeOrgId && (
                    <CasePlaywrightSection
                      tc={tc}
                      accessToken={accessToken}
                      activeOrgId={activeOrgId}
                      styleSample={styleSample}
                    />
                  )}
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Gaps & open questions */}
          <div className="grid gap-4 sm:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Brechas</CardTitle>
              </CardHeader>
              <CardContent>
                <textarea
                  aria-label="Brechas"
                  className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-zinc-400 min-h-[80px] resize-y"
                  placeholder="Uno por línea"
                  value={editGaps}
                  onChange={(e) => setEditGaps(e.target.value)}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Preguntas abiertas</CardTitle>
              </CardHeader>
              <CardContent>
                <textarea
                  aria-label="Preguntas abiertas"
                  className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-zinc-400 min-h-[80px] resize-y"
                  placeholder="Uno por línea"
                  value={editOpenQuestions}
                  onChange={(e) => setEditOpenQuestions(e.target.value)}
                />
              </CardContent>
            </Card>
          </div>

          {/* Citations */}
          {citations.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Citas</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1">
                  {citations.map((citation, idx) => (
                    <li key={idx} className="text-sm text-zinc-600">
                      · {citation}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
