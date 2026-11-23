import { apiRequest } from "@/lib/api/client";

export type OrgRole = "owner" | "admin" | "member" | "viewer";

export interface OrgMember {
  user_id: string;
  role: string;
  email: string | null;
  display_name: string | null;
  created_at: string | null;
}

export interface JoinCodeResult {
  join_code: string;
  join_code_expires_at: string | null;
}

const base = (orgId: string) => `/api/v2/orgs/${encodeURIComponent(orgId)}`;

export function listMembers(token: string, orgId: string) {
  return apiRequest<OrgMember[]>(`${base(orgId)}/members`, "GET", { token });
}

export function changeMemberRole(token: string, orgId: string, userId: string, role: OrgRole) {
  return apiRequest<{ user_id: string; role: string }>(
    `${base(orgId)}/members/${encodeURIComponent(userId)}`,
    "PATCH",
    { token, body: { role } },
  );
}

export function removeMember(token: string, orgId: string, userId: string) {
  return apiRequest<{ removed: boolean }>(
    `${base(orgId)}/members/${encodeURIComponent(userId)}`,
    "DELETE",
    { token },
  );
}

export function rotateJoinCode(token: string, orgId: string) {
  return apiRequest<JoinCodeResult>(`${base(orgId)}/join-code/rotate`, "POST", { token });
}
