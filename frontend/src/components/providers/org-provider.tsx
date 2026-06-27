"use client";

import { createContext, useContext, useEffect, useState, type PropsWithChildren } from "react";
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
  const [activeOrgId, setActive] = useState("");
  const orgsQuery = useQuery({
    queryKey: ["organizations"],
    queryFn: () => getOrganizations(accessToken!),
    enabled: Boolean(accessToken),
  });
  const orgs = orgsQuery.data ?? [];

  useEffect(() => {
    if (!orgs.length || activeOrgId) return;
    const stored = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
    const valid = stored && orgs.some((o) => o.id === stored) ? stored : orgs[0].id;
    setActive(valid);
  }, [orgs, activeOrgId]);

  function setActiveOrgId(id: string) {
    setActive(id);
    if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, id);
  }

  return <OrgContext.Provider value={{ orgs, activeOrgId, setActiveOrgId }}>{children}</OrgContext.Provider>;
}

export function useActiveOrg(): OrgContextValue {
  const ctx = useContext(OrgContext);
  if (!ctx) throw new Error("useActiveOrg must be used within OrgProvider");
  return ctx;
}
