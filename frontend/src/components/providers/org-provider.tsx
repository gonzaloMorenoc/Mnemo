"use client";

import { createContext, useContext, useMemo, useState, type PropsWithChildren } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getOrganizations } from "@/lib/api/endpoints";
import type { OrganizationResponse } from "@/lib/api/types";

interface OrgContextValue {
  orgs: OrganizationResponse[];
  activeOrgId: string;
  setActiveOrgId: (id: string) => void;
}
const OrgContext = createContext<OrgContextValue | null>(null);
const STORAGE_KEY = "mnemo.activeOrgId";

export function OrgProvider({ children }: PropsWithChildren) {
  const { accessToken } = useAuth();
  const [explicitOrgId, setExplicitOrgId] = useState("");
  const orgsQuery = useQuery({
    queryKey: ["organizations", accessToken],
    queryFn: () => getOrganizations(accessToken!),
    enabled: Boolean(accessToken),
  });
  const orgs = useMemo(() => orgsQuery.data ?? [], [orgsQuery.data]);

  const activeOrgId = useMemo(() => {
    if (explicitOrgId) return explicitOrgId;
    if (!orgs.length) return "";
    const stored = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
    return stored && orgs.some((o) => o.id === stored) ? stored : orgs[0].id;
  }, [explicitOrgId, orgs]);

  function setActiveOrgId(id: string) {
    setExplicitOrgId(id);
    if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, id);
  }

  return <OrgContext.Provider value={{ orgs, activeOrgId, setActiveOrgId }}>{children}</OrgContext.Provider>;
}

export function useActiveOrg(): OrgContextValue {
  const ctx = useContext(OrgContext);
  if (!ctx) throw new Error("useActiveOrg must be used within OrgProvider");
  return ctx;
}
