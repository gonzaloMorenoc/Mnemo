"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getDefects, getDefectLineage, getOrganizations } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

export default function DefectsPage() {
  const { accessToken } = useAuth();
  const [orgId, setOrgId] = useState<string>("");
  const [selected, setSelected] = useState<string | null>(null);

  const orgsQuery = useQuery({
    queryKey: ["orgs"],
    queryFn: () => getOrganizations(accessToken!),
    enabled: Boolean(accessToken),
  });

  const activeOrg = orgId || orgsQuery.data?.[0]?.id || "";

  const defectsQuery = useQuery({
    queryKey: ["defects", activeOrg],
    queryFn: () => getDefects(accessToken!, activeOrg),
    enabled: Boolean(accessToken && activeOrg),
  });

  const lineageQuery = useQuery({
    queryKey: ["lineage", selected],
    queryFn: () => getDefectLineage(accessToken!, selected!),
    enabled: Boolean(accessToken && selected),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Defect DNA</h1>
        <p className="text-sm text-zinc-500">Familias de defecto y su linaje a través de proyectos.</p>
      </div>

      {orgsQuery.data && orgsQuery.data.length > 1 && (
        <select
          className="rounded-lg border border-zinc-200 px-3 py-2 text-sm"
          value={activeOrg}
          onChange={(e) => setOrgId(e.target.value)}
        >
          {orgsQuery.data.map((o) => (
            <option key={o.id} value={o.id}>{o.name}</option>
          ))}
        </select>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <Card className="p-4">
          <h2 className="mb-3 text-sm font-medium text-zinc-700">Familias</h2>
          {defectsQuery.isLoading && <Skeleton className="h-24 w-full" />}
          {defectsQuery.data && defectsQuery.data.length === 0 && (
            <p className="text-sm text-zinc-500">No hay familias todavía. Sube un reporte en Assurance.</p>
          )}
          <ul className="space-y-2">
            {defectsQuery.data?.map((f) => (
              <li key={f.id}>
                <button
                  onClick={() => setSelected(f.id)}
                  className="flex w-full items-center justify-between rounded-lg border border-zinc-200 px-3 py-2 text-left text-sm hover:bg-zinc-50"
                >
                  <span className="font-medium text-zinc-900">{f.title}</span>
                  <span className="flex items-center gap-2">
                    <Badge>{f.occurrence_count}x</Badge>
                    {f.projects.length > 1 && <Badge>{f.projects.length} proyectos</Badge>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="p-4">
          <h2 className="mb-3 text-sm font-medium text-zinc-700">Linaje</h2>
          {!selected && <p className="text-sm text-zinc-500">Selecciona una familia.</p>}
          {lineageQuery.isLoading && <Skeleton className="h-24 w-full" />}
          {lineageQuery.data?.family && (
            <div className="space-y-3">
              <p className="text-sm font-medium text-zinc-900">{lineageQuery.data.family.title}</p>
              <ul className="space-y-1 text-sm text-zinc-600">
                {lineageQuery.data.failures.map((fl) => (
                  <li key={fl.id} className="flex items-center justify-between">
                    <span>{fl.test_name}</span>
                    <Badge>{fl.project}</Badge>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
