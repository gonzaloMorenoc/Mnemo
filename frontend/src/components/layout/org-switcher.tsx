"use client";
import { useActiveOrg } from "@/components/providers/org-provider";

export function OrgSwitcher() {
  const { orgs, activeOrgId, setActiveOrgId } = useActiveOrg();
  if (orgs.length === 0) return null;
  if (orgs.length === 1) return <span className="text-sm text-zinc-600">{orgs[0].name}</span>;
  return (
    <select
      aria-label="Organización"
      className="rounded-lg border border-zinc-200 px-2 py-1 text-sm"
      value={activeOrgId}
      onChange={(e) => setActiveOrgId(e.target.value)}
    >
      {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
    </select>
  );
}
