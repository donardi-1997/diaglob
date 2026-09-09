export interface WorkspaceOrganizationLike {
  id: number | string;
}

export interface WorkspaceStoreLike {
  id: number | string;
  active: boolean;
}

export function resolveOrganizationId(
  organizations: WorkspaceOrganizationLike[],
  savedOrganizationId: string | null,
): string {
  if (
    savedOrganizationId &&
    organizations.some(
      (organization) => String(organization.id) === savedOrganizationId,
    )
  ) {
    return savedOrganizationId;
  }

  return organizations[0] ? String(organizations[0].id) : "";
}

export function resolveStoreId(
  stores: WorkspaceStoreLike[],
  selectedStoreId: string,
): string {
  const activeStores = stores.filter((store) => store.active);

  if (activeStores.length === 0) {
    return "";
  }

  if (
    activeStores.some(
      (store) => String(store.id) === selectedStoreId,
    )
  ) {
    return selectedStoreId;
  }

  return String(activeStores[0].id);
}
