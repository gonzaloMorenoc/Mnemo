"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import {
  changeMemberRole,
  listMembers,
  removeMember,
  rotateJoinCode,
  type JoinCodeResult,
  type OrgMember,
  type OrgRole,
} from "@/lib/api/members";
import type { OrganizationResponse } from "@/lib/api/types";

// Espejo de src/orgs/permissions.py SOLO para no ofrecer opciones imposibles;
// quien decide es el backend.
const ROLE_RANK: Record<OrgRole, number> = { viewer: 0, member: 1, admin: 2, owner: 3 };
const ROLES_DESC: OrgRole[] = ["owner", "admin", "member", "viewer"];

export const ROLE_LABEL: Record<OrgRole, string> = {
  owner: "Propietario/a",
  admin: "Admin",
  member: "Miembro",
  viewer: "Solo lectura",
};

function rankOf(role: string | null | undefined): number {
  return role && role in ROLE_RANK ? ROLE_RANK[role as OrgRole] : -1;
}

export function isOrgAdmin(role: string | null | undefined): boolean {
  return rankOf(role) >= ROLE_RANK.admin;
}

function canEdit(actorRole: string | null, target: OrgMember): boolean {
  return actorRole === "owner" || (isOrgAdmin(actorRole) && target.role !== "owner");
}

function roleOptions(actorRole: string | null, target: OrgMember, isSelf: boolean): OrgRole[] {
  const ceiling = isSelf ? Math.min(rankOf(actorRole), rankOf(target.role)) : rankOf(actorRole);
  return ROLES_DESC.filter((r) => ROLE_RANK[r] <= ceiling);
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("es-ES");
}

function isPast(value: string | null | undefined): boolean {
  if (!value) return false;
  const t = new Date(value).getTime();
  return !Number.isNaN(t) && t <= Date.now();
}

interface MemberRowProps {
  member: OrgMember;
  actorRole: string | null;
  isSelf: boolean;
  busy: boolean;
  onRoleChange: (role: OrgRole) => void;
  onRemove: () => void;
}

function MemberRow({ member, actorRole, isSelf, busy, onRoleChange, onRemove }: MemberRowProps) {
  const [confirming, setConfirming] = useState(false);
  const name = member.display_name || member.email || member.user_id;
  const editable = canEdit(actorRole, member);
  const label = ROLE_LABEL[member.role as OrgRole] ?? member.role;

  return (
    <li className="grid gap-2 rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm md:grid-cols-[1fr_auto_auto] md:items-center">
      <div className="min-w-0">
        <p className="truncate font-medium text-zinc-800">
          {name}
          {isSelf && <span className="ml-1 text-xs font-normal text-zinc-500">(tú)</span>}
        </p>
        {member.display_name && member.email && (
          <p className="truncate text-xs text-zinc-500">{member.email}</p>
        )}
      </div>

      {editable ? (
        <select
          aria-label={`Rol de ${name}`}
          className="h-9 rounded-lg border border-zinc-300 bg-white px-2 text-sm text-zinc-900 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/60"
          value={member.role}
          disabled={busy}
          onChange={(e) => onRoleChange(e.target.value as OrgRole)}
        >
          {roleOptions(actorRole, member, isSelf).map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </select>
      ) : (
        <span className="text-xs text-zinc-500">{label}</span>
      )}

      <div className="flex justify-end gap-2">
        {editable && !isSelf && !confirming && (
          <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => setConfirming(true)}>
            Expulsar
          </Button>
        )}
        {confirming && (
          <>
            <span className="self-center text-xs text-zinc-600">¿Seguro?</span>
            <Button
              type="button"
              size="sm"
              variant="destructive"
              disabled={busy}
              onClick={() => {
                setConfirming(false);
                onRemove();
              }}
            >
              Sí, expulsar
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => setConfirming(false)}>
              Cancelar
            </Button>
          </>
        )}
      </div>
    </li>
  );
}

function JoinCodeBox({ org, token }: { org: OrganizationResponse; token: string }) {
  const queryClient = useQueryClient();
  const [rotated, setRotated] = useState<JoinCodeResult | null>(null);
  const code = rotated?.join_code ?? org.join_code;
  const expires = rotated?.join_code_expires_at ?? org.join_code_expires_at;
  const expired = isPast(expires);

  const rotate = useMutation({
    mutationFn: () => rotateJoinCode(token, org.id),
    onSuccess: (result) => {
      setRotated(result);
      toast.success("Código rotado: el anterior ya no sirve.");
      void queryClient.invalidateQueries({ queryKey: ["organizations"] });
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-600">
      <span>Código de invitación:</span>
      <code className="rounded bg-zinc-100 px-2 py-1 text-xs text-zinc-800">{code ?? "—"}</code>
      {expires && (
        <span className={expired ? "text-red-600" : undefined}>
          {expired ? "caducado" : `caduca el ${formatDate(expires)}`}
        </span>
      )}
      <Button type="button" variant="outline" size="sm" disabled={rotate.isPending} onClick={() => rotate.mutate()}>
        <RefreshCw size={14} className="mr-1" />
        {rotate.isPending ? "Rotando…" : "Rotar código"}
      </Button>
      <span className="w-full text-zinc-500">Quien entra con el código lo hace con rol de solo lectura.</span>
    </div>
  );
}

export function OrgMembersPanel({ org }: { org: OrganizationResponse }) {
  const { accessToken, user } = useAuth();
  const queryClient = useQueryClient();
  const admin = isOrgAdmin(org.role);
  const membersKey = ["org-members", org.id, accessToken];

  const membersQuery = useQuery({
    queryKey: membersKey,
    queryFn: () => listMembers(accessToken!, org.id),
    enabled: Boolean(accessToken) && admin,
  });

  const refresh = () => void queryClient.invalidateQueries({ queryKey: membersKey });

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: OrgRole }) =>
      changeMemberRole(accessToken!, org.id, userId, role),
    onSuccess: () => {
      toast.success("Rol actualizado.");
      refresh();
    },
    onError: (error) => toast.error(error.message),
  });

  const removeMutation = useMutation({
    mutationFn: (userId: string) => removeMember(accessToken!, org.id, userId),
    onSuccess: () => {
      toast.success("Miembro expulsado.");
      refresh();
    },
    onError: (error) => toast.error(error.message),
  });

  if (!admin) {
    return (
      <p className="text-xs text-zinc-500">
        {org.role === "viewer"
          ? "Tienes acceso de solo lectura. Pide a un admin que te suba a miembro para trabajar."
          : "Solo owners y admins gestionan los miembros y el código de invitación."}
      </p>
    );
  }

  const busy = roleMutation.isPending || removeMutation.isPending;

  return (
    <div className="space-y-3">
      {accessToken && <JoinCodeBox org={org} token={accessToken} />}
      {membersQuery.isLoading && <p className="text-xs text-zinc-500">Cargando miembros…</p>}
      {membersQuery.isError && <p className="text-xs text-red-600">No se pudieron cargar los miembros.</p>}
      <ul className="space-y-2">
        {membersQuery.data?.map((member) => (
          <MemberRow
            key={member.user_id}
            member={member}
            actorRole={org.role}
            isSelf={member.user_id === user?.id}
            busy={busy}
            onRoleChange={(role) => roleMutation.mutate({ userId: member.user_id, role })}
            onRemove={() => removeMutation.mutate(member.user_id)}
          />
        ))}
      </ul>
    </div>
  );
}
