import { api } from "./api";

export interface CurrentUser {
  id: number;
  name: string;
  email: string;
  active: boolean;
}

export interface UserOrganization {
  id: number;
  name: string;
  slug: string;
  role: string;
  all_stores: boolean;
  permissions: string[];
}

interface OrganizationsResponse {
  items: UserOrganization[];
  total: number;
}

export async function getCurrentUser() {
  const response =
    await api.get<CurrentUser>(
      "/api/me",
    );

  return response.data;
}

export async function getMyOrganizations() {
  const response =
    await api.get<OrganizationsResponse>(
      "/api/me/organizations",
    );

  return response.data;
}
