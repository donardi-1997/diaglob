import { useCallback, useEffect, useMemo, useState } from "react";

import { clearSession, hasSession } from "../services/authStorage";
import { getStores, type Store } from "../services/stores";
import {
  getCurrentUser,
  getMyOrganizations,
  type CurrentUser,
  type UserOrganization,
} from "../services/session";
import {
  resolveOrganizationId,
  resolveStoreId,
} from "./workspaceSelection";

export function useWorkspace() {
  const [authenticated, setAuthenticated] = useState(hasSession());
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [organizations, setOrganizations] = useState<UserOrganization[]>([]);
  const [sessionReady, setSessionReady] = useState(false);
  const [organizationId, setOrganizationId] = useState(
    localStorage.getItem("diaglob-organization-id") || "",
  );
  const [stores, setStores] = useState<Store[]>([]);
  const [selectedStoreId, setSelectedStoreId] = useState(
    localStorage.getItem("diaglob-store-id") || "",
  );

  const resetWorkspace = useCallback(() => {
    setCurrentUser(null);
    setOrganizations([]);
    setStores([]);
    setOrganizationId("");
    setSelectedStoreId("");
    setSessionReady(false);
  }, []);

  const expireSession = useCallback(() => {
    clearSession();
    setAuthenticated(false);
    resetWorkspace();
  }, [resetWorkspace]);

  useEffect(() => {
    async function loadSession() {
      if (!authenticated) {
        resetWorkspace();
        return;
      }

      try {
        setSessionReady(false);

        const user = await getCurrentUser();
        const organizationsResponse = await getMyOrganizations();

        setCurrentUser(user);
        setOrganizations(organizationsResponse.items);

        const nextOrganizationId = resolveOrganizationId(
          organizationsResponse.items,
          localStorage.getItem("diaglob-organization-id"),
        );

        if (nextOrganizationId) {
          localStorage.setItem("diaglob-organization-id", nextOrganizationId);
        } else {
          localStorage.removeItem("diaglob-organization-id");
        }

        if (nextOrganizationId !== organizationId) {
          localStorage.removeItem("diaglob-store-id");
          setSelectedStoreId("");
        }

        setOrganizationId(nextOrganizationId);
        setSessionReady(true);
      } catch (error) {
        console.error("Unable to load session", error);
        expireSession();
      }
    }

    void loadSession();
  }, [authenticated, expireSession, organizationId, resetWorkspace]);

  useEffect(() => {
    const handleAuthExpired = () => expireSession();
    window.addEventListener("diaglob-auth-expired", handleAuthExpired);
    return () => window.removeEventListener("diaglob-auth-expired", handleAuthExpired);
  }, [expireSession]);

  const loadStores = useCallback(async () => {
    if (!sessionReady || !organizationId) {
      setStores([]);
      return;
    }

    try {
      const response = await getStores();
      setStores(response.items);

      const savedStoreId = localStorage.getItem("diaglob-store-id");
      if (
        savedStoreId &&
        !response.items.some((store) => String(store.id) === savedStoreId)
      ) {
        localStorage.removeItem("diaglob-store-id");
        setSelectedStoreId("");
      }
    } catch (error) {
      console.error("Unable to load stores", error);
      setStores([]);
      setSelectedStoreId("");
    }
  }, [organizationId, sessionReady]);

  useEffect(() => {
    void loadStores();
  }, [loadStores]);

  useEffect(() => {
    const nextStoreId = resolveStoreId(stores, selectedStoreId);

    if (nextStoreId === selectedStoreId) {
      return;
    }

    if (nextStoreId) {
      localStorage.setItem("diaglob-store-id", nextStoreId);
    } else {
      localStorage.removeItem("diaglob-store-id");
    }

    setSelectedStoreId(nextStoreId);
  }, [stores, selectedStoreId]);

  const changeStore = useCallback((storeId: string) => {
    if (storeId) {
      localStorage.setItem("diaglob-store-id", storeId);
    } else {
      localStorage.removeItem("diaglob-store-id");
    }
    setSelectedStoreId(storeId);
  }, []);

  const handleAuthenticated = useCallback(() => setAuthenticated(true), []);

  const handleLogout = useCallback(() => {
    clearSession();
    setAuthenticated(false);
    resetWorkspace();
  }, [resetWorkspace]);

  const selectedOrganization = useMemo(
    () =>
      organizations.find(
        (organization) => String(organization.id) === organizationId,
      ) || null,
    [organizationId, organizations],
  );

  const selectedStore = useMemo(
    () =>
      stores.find(
        (store) => store.active && String(store.id) === selectedStoreId,
      ) || null,
    [selectedStoreId, stores],
  );

  const permissions = useMemo(
    () => selectedOrganization?.permissions || [],
    [selectedOrganization],
  );
  const can = useCallback(
    (permission: string) => permissions.includes(permission),
    [permissions],
  );

  return {
    authenticated,
    currentUser,
    organizations,
    organizationId,
    sessionReady,
    stores,
    selectedStoreId,
    selectedOrganization,
    selectedStore,
    can,
    changeStore,
    handleAuthenticated,
    handleLogout,
    loadStores,
  };
}
