import { apiRequest } from "./api";

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

export interface Store {
  id: number;
  name: string;
  slug: string;
  country_code: string;
  currency: string;
  timezone: string;
  default_language: string;
  shopify_domain: string | null;
  active: boolean;
}

export async function getCurrentUser() {
  return apiRequest<CurrentUser>("/api/me");
}

export async function getOrganizations() {
  return apiRequest<{
    items: UserOrganization[];
    total: number;
  }>("/api/me/organizations");
}

export async function getStores() {
  return apiRequest<{
    items: Store[];
    total: number;
  }>("/api/stores", {
    globalScope: true,
  });
}
