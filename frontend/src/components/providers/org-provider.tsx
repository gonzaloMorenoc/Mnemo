"use client";

import { createContext, useContext, useMemo, useState, type PropsWithChildren } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getOrganizations } from "@/lib/api/endpoints";
import type { OrganizationResponse } from "@/lib/api/types";

interface OrgContextValue {
  orgs: OrganizationResponse[];
  activeOrgId: string;
  isLoading: boolean;
  /** La lista de organizaciones no se pudo cargar (no confundir con «no hay ninguna»). */
  isError: boolean;
  /** La lista cargó bien y el usuario no pertenece a ninguna organización. */
  hasNoOrgs: boolean;
  refetchOrgs: () => void;
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
    staleTime: 5 * 60_000,
  });
  const orgs = useMemo(() => orgsQuery.data ?? [], [orgsQuery.data]);
  const hasNoOrgs = orgsQuery.isSuccess && orgs.length === 0;

  const storedOrgId =
    typeof window !== "undefined"
      ? (window.localStorage.getItem(STORAGE_KEY) ?? "")
      : "";

  const activeOrgId = useMemo(() => {
    if (explicitOrgId) return explicitOrgId;
    if (orgs.length) {
      return orgs.some((o) => o.id === storedOrgId) ? storedOrgId : orgs[0].id;
    }
    // Lista cargada y vacía: el id guardado es de otra cuenta o de una org que ya no existe.
    if (hasNoOrgs) return "";
    return storedOrgId; // optimistic: list not yet loaded
  }, [explicitOrgId, orgs, storedOrgId, hasNoOrgs]);

  function setActiveOrgId(id: string) {
    setExplicitOrgId(id);
    if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, id);
  }

  const value: OrgContextValue = {
    orgs,
    activeOrgId,
    isLoading: orgsQuery.isLoading,
    isError: orgsQuery.isError,
    hasNoOrgs: hasNoOrgs && !explicitOrgId,
    refetchOrgs: () => void orgsQuery.refetch(),
    setActiveOrgId,
  };

  return <OrgContext.Provider value={value}>{children}</OrgContext.Provider>;
}

export function useActiveOrg(): OrgContextValue {
  const ctx = useContext(OrgContext);
  if (!ctx) throw new Error("useActiveOrg must be used within OrgProvider");
  return ctx;
}
