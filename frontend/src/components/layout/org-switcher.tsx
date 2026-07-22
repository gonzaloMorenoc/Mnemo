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
        title="Gestionar organización"
        className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm font-medium text-zinc-700 transition hover:bg-zinc-100 hover:text-zinc-900"
      >
        <Building2 size={14} className="text-zinc-400" />
        {orgs[0].name}
      </Link>
    );
  }
  return (
    <Select value={activeOrgId} onValueChange={setActiveOrgId}>
      <SelectTrigger aria-label="Organización" className="h-8 rounded-lg px-2 text-sm">
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
