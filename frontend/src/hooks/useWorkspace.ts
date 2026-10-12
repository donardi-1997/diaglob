import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { clearSession, hasSession } from "../services/authStorage";
import { getStores, type Store } from "../services/stores";
import { createLatestRequestGuard } from "../services/latestRequestGuard";
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
  const [storesError, setStoresError] = useState(false);
  const [storesLoading, setStoresLoading] = useState(false);
  const [loadedStoresOrganizationId, setLoadedStoresOrganizationId] = useState("");
  const lastStoresOrganizationId = useRef("");
  const storesRequestGuard = useRef(createLatestRequestGuard());
  const [selectedStoreId, setSelectedStoreId] = useState(
    localStorage.getItem("diaglob-store-id") || "",
  );

  const resetWorkspace = useCallback(() => {
    // Logout must invalidate in-flight responses before clearing workspace state.
    storesRequestGuard.current.invalidate();
    lastStoresOrganizationId.current = "";
    setLoadedStoresOrganizationId("");
    setStoresLoading(false);
    setCurrentUser(null);
    setOrganizations([]);
    setStores([]);
    setStoresError(false);
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
    const requestId = storesRequestGuard.current.issue();

    if (!sessionReady || !organizationId) {
      setStores([]);
      setLoadedStoresOrganizationId("");
      setStoresError(false);
      setStoresLoading(false);
      return;
    }

    // Never retain one organization's stores after the active tenant changes.
    // Keep a saved selection only on the initial load of the same organization.
    if (lastStoresOrganizationId.current !== organizationId) {
      if (lastStoresOrganizationId.current) {
        localStorage.removeItem("diaglob-store-id");
        setSelectedStoreId("");
      }
      lastStoresOrganizationId.current = organizationId;
      setStores([]);
      setLoadedStoresOrganizationId("");
    }

    const isCurrent = () =>
      storesRequestGuard.current.isCurrent(requestId) &&
      localStorage.getItem("diaglob-organization-id") === organizationId;

    setStoresLoading(true);
    setStoresError(false);
    try {
      const response = await getStores();
      if (!isCurrent()) return;

      setStores(response.items);
      setLoadedStoresOrganizationId(organizationId);

      const savedStoreId = localStorage.getItem("diaglob-store-id");
      if (
        savedStoreId &&
        !response.items.some((store) => store.active && String(store.id) === savedStoreId)
      ) {
        localStorage.removeItem("diaglob-store-id");
        setSelectedStoreId("");
      }
    } catch (error) {
      if (!isCurrent()) return;
      console.error("Unable to load stores", error);
      setStoresError(true);
      // A same-organization retry retains its last known stores. A new tenant does not.
    } finally {
      if (isCurrent()) setStoresLoading(false);
    }
  }, [organizationId, sessionReady]);

  useEffect(() => {
    void loadStores();
    return () => storesRequestGuard.current.invalidate();
  }, [loadStores]);

  useEffect(() => {
    // Do not discard a persisted store before the first authorized store
    // response arrives, or select a store from a previous organization.
    if (!sessionReady || loadedStoresOrganizationId !== organizationId) {
      return;
    }

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
  }, [stores, selectedStoreId, organizationId, loadedStoresOrganizationId, sessionReady]);

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

  // Never render a previous tenant's stores while the new tenant loads.
  const availableStores = useMemo(
    () => loadedStoresOrganizationId === organizationId ? stores : [],
    [loadedStoresOrganizationId, organizationId, stores],
  );

  const selectedStore = useMemo(
    () =>
      availableStores.find(
        (store) => store.active && String(store.id) === selectedStoreId,
      ) || null,
    [selectedStoreId, availableStores],
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
    stores: availableStores,
    storesError,
    storesLoading,
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
