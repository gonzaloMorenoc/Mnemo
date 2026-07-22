"use client";
import Link from "next/link";
import { Building2 } from "lucide-react";

import { useActiveOrg } from "@/components/providers/org-provider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function OrgSwitcher() {
  const { orgs, activeOrgId, setActiveOrgId } = useActiveOrg();
  if (orgs.length === 0) return null;
  if (orgs.length === 1) {
    // Una sola org: el nombre sigue siendo útil — lleva a gestionarla.
    return (
      <Link
        href="/app/org"
        aria-label={`${orgs[0].name} — gestionar organización`}
        className="flex min-w-0 items-center gap-1.5 rounded-lg px-2 py-1 text-sm font-medium text-zinc-700 transition hover:bg-zinc-100 hover:text-zinc-900"
      >
        <Building2 size={14} className="shrink-0 text-zinc-400" />
        <span className="max-w-[35vw] truncate">{orgs[0].name}</span>
      </Link>
    );
  }
  return (
    <Select value={activeOrgId} onValueChange={setActiveOrgId}>
      <SelectTrigger
        aria-label="Organización"
        className="h-8 max-w-[35vw] rounded-lg px-2 text-sm [&>span]:truncate"
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {orgs.map((o) => (
          <SelectItem key={o.id} value={o.id}>{o.name}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
