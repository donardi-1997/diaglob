import { api } from "./api";


export interface TeamStore {
  id: number;
  name: string;
}


export type TeamRole =
  | "owner"
  | "manager"
  | "operator"
  | "analyst";


export interface TeamMember {
  id: number;
  user_id: number;
  name: string;
  email: string;
  role: TeamRole;
  all_stores: boolean;
  active: boolean;
  stores: TeamStore[];
  created_at: string;
}


export interface TeamUsage {
  used: number;
  limit: number;
  remaining: number;
}


export interface TeamResponse {
  items: TeamMember[];
  usage: TeamUsage;
  total: number;
}


export interface TeamInvitation {
  id: number;
  organization_id: number;
  email: string;
  role: Exclude<TeamRole, "owner">;
  all_stores: boolean;
  active: boolean;
  status:
    | "pending"
    | "accepted"
    | "cancelled"
    | "expired";
  stores: TeamStore[];
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
}


export interface InvitationsResponse {
  items: TeamInvitation[];
  total: number;
}


export interface TeamInvitationPayload {
  email: string;
  role:
    | "manager"
    | "operator"
    | "analyst";
  all_stores: boolean;
  store_ids: number[];
}


export interface TeamMemberUpdatePayload {
  role?: "manager" | "operator" | "analyst";
  all_stores?: boolean;
  store_ids?: number[];
  active?: boolean;
}


export async function getTeam() {
  const response =
    await api.get<TeamResponse>(
      "/api/team",
      {
        headers: {
          "X-Diaglob-Global-Scope": "1",
        },
      },
    );

  return response.data;
}


export async function getTeamInvitations() {
  const response =
    await api.get<InvitationsResponse>(
      "/api/team/invitations",
      {
        headers: {
          "X-Diaglob-Global-Scope": "1",
        },
      },
    );

  return response.data;
}


export async function createTeamInvitation(
  payload: TeamInvitationPayload,
) {
  const response =
    await api.post<TeamInvitation>(
      "/api/team/invitations",
      payload,
      {
        headers: {
          "X-Diaglob-Global-Scope": "1",
        },
      },
    );

  return response.data;
}


export async function cancelTeamInvitation(
  invitationId: number,
) {
  const response =
    await api.delete<TeamInvitation>(
      `/api/team/invitations/${invitationId}`,
      {
        headers: {
          "X-Diaglob-Global-Scope": "1",
        },
      },
    );

  return response.data;
}


export async function updateTeamMember(
  membershipId: number,
  payload: TeamMemberUpdatePayload,
) {
  const response =
    await api.patch<TeamMember>(
      `/api/team/${membershipId}`,
      payload,
      {
        headers: {
          "X-Diaglob-Global-Scope": "1",
        },
      },
    );

  return response.data;
}
