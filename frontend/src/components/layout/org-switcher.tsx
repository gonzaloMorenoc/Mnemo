"use client";
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
  if (orgs.length === 1) return <span className="text-sm text-zinc-600">{orgs[0].name}</span>;
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
