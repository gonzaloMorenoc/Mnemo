"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getOrganizations } from "@/lib/api/endpoints";
import { RunSelector } from "@/components/autopilot/RunSelector";
import { TriageVerdictList } from "@/components/autopilot/TriageVerdictList";
import { ActionsPanel } from "@/components/autopilot/ActionsPanel";
import { CertificateCard } from "@/components/autopilot/CertificateCard";
import { GateCard } from "@/components/autopilot/GateCard";
import { BriefingCard } from "@/components/autopilot/BriefingCard";

export default function AutopilotPage() {
  const { accessToken } = useAuth();
  const [runId, setRunId] = useState<string | null>(null);

  const orgsQuery = useQuery({
    queryKey: ["organizations", accessToken],
    queryFn: () => getOrganizations(accessToken!),
    enabled: Boolean(accessToken),
  });
  const orgId = orgsQuery.data?.[0]?.id ?? "";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Autopilot</h1>
        <p className="text-sm text-zinc-500">Triaje, acción Nivel 2, certificado y gate de un run.</p>
      </div>
      <RunSelector orgId={orgId} onRunId={setRunId} />
      {runId && (
        <div key={runId} className="space-y-4">
          <BriefingCard runId={runId} />
          <TriageVerdictList runId={runId} />
          <ActionsPanel runId={runId} orgId={orgId} />
          <CertificateCard runId={runId} />
          <GateCard runId={runId} />
        </div>
      )}
    </div>
  );
}
