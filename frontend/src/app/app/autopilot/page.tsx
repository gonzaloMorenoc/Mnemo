"use client";

import { useLayoutEffect, useState } from "react";

import { useActiveOrg } from "@/components/providers/org-provider";
import { RunSelector } from "@/components/autopilot/RunSelector";
import { TriageVerdictList } from "@/components/autopilot/TriageVerdictList";
import { ActionsPanel } from "@/components/autopilot/ActionsPanel";
import { CertificateCard } from "@/components/autopilot/CertificateCard";
import { GateCard } from "@/components/autopilot/GateCard";
import { BriefingCard } from "@/components/autopilot/BriefingCard";
import { RoiPanel } from "@/components/autopilot/RoiPanel";

export default function AutopilotPage() {
  const { activeOrgId: orgId } = useActiveOrg();
  const [runId, setRunId] = useState<string | null>(null);
  // Enlace directo a un run (?run=<id>) desde el Dashboard. window.location en vez
  // de useSearchParams para no forzar Suspense (mismo patrón que /app/knowledge).
  useLayoutEffect(() => {
    const r = new URLSearchParams(window.location.search).get("run");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (r) setRunId(r);
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Autopilot</h1>
        <p className="text-sm text-zinc-500">
          Analiza un run: clasifica cada fallo, propone acciones correctivas y emite el acta firmada.
        </p>
      </div>
      <RunSelector orgId={orgId} onRunId={setRunId} />
      {runId && (
        <div key={runId} className="space-y-4">
          <BriefingCard runId={runId} />
          <TriageVerdictList runId={runId} />
          <ActionsPanel runId={runId} orgId={orgId} />
          <CertificateCard runId={runId} />
          <GateCard runId={runId} />
          <RoiPanel runId={runId} />
        </div>
      )}
    </div>
  );
}
