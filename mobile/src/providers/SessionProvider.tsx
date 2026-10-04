import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { login as cognitoLogin } from "../services/auth";
import {
  clearSession,
  getOrganizationId,
  getStoreId,
  getTokens,
  saveTokens,
  setOrganizationId,
  setStoreId,
} from "../services/storage";
import {
  getCurrentUser,
  getOrganizations,
  getStores,
  type CurrentUser,
  type Store,
  type UserOrganization,
} from "../services/workspace";

interface SessionContextValue {
  ready: boolean;
  authenticated: boolean;
  user: CurrentUser | null;
  organization: UserOrganization | null;
  stores: Store[];
  store: Store | null;
  permissions: string[];
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  selectStore: (storeId: number) => Promise<void>;
  reloadWorkspace: () => Promise<void>;
  can: (permission: string) => boolean;
}

const SessionContext = createContext<SessionContextValue | null>(
  null,
);

export function SessionProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [organization, setOrganization] =
    useState<UserOrganization | null>(null);
  const [stores, setStores] = useState<Store[]>([]);
  const [store, setStore] = useState<Store | null>(null);

  const reset = useCallback(() => {
    setAuthenticated(false);
    setUser(null);
    setOrganization(null);
    setStores([]);
    setStore(null);
  }, []);

  const loadWorkspace = useCallback(async () => {
    const tokens = await getTokens();

    if (!tokens.accessToken) {
      reset();
      return;
    }

    const [
      currentUser,
      organizationsResponse,
    ] = await Promise.all([
      getCurrentUser(),
      getOrganizations(),
    ]);

    const savedOrganizationId = await getOrganizationId();
    const nextOrganization =
      organizationsResponse.items.find(
        (item) => String(item.id) === savedOrganizationId,
      ) ||
      organizationsResponse.items[0] ||
      null;

    if (!nextOrganization) {
      throw new Error(
        "Tu cuenta no tiene una organización disponible.",
      );
    }

    await setOrganizationId(String(nextOrganization.id));

    const storesResponse = await getStores();
    const activeStores = storesResponse.items.filter(
      (item) => item.active,
    );
    const savedStoreId = await getStoreId();
    const nextStore =
      activeStores.find(
        (item) => String(item.id) === savedStoreId,
      ) ||
      activeStores[0] ||
      null;

    await setStoreId(
      nextStore ? String(nextStore.id) : null,
    );

    setUser(currentUser);
    setOrganization(nextOrganization);
    setStores(activeStores);
    setStore(nextStore);
    setAuthenticated(true);
  }, [reset]);

  const bootstrap = useCallback(async () => {
    setReady(false);
    try {
      await loadWorkspace();
    } catch {
      await clearSession();
      reset();
    } finally {
      setReady(true);
    }
  }, [loadWorkspace, reset]);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  const login = useCallback(
    async (email: string, password: string) => {
      const result = await cognitoLogin(email, password);
      await saveTokens(
        result.AccessToken,
        result.IdToken,
        result.RefreshToken,
      );
      await loadWorkspace();
      setReady(true);
    },
    [loadWorkspace],
  );

  const logout = useCallback(async () => {
    await clearSession();
    reset();
    setReady(true);
  }, [reset]);

  const selectStore = useCallback(
    async (storeId: number) => {
      const next = stores.find(
        (item) => item.id === storeId && item.active,
      );
      if (!next) return;

      await setStoreId(String(next.id));
      setStore(next);
    },
    [stores],
  );

  const permissions = useMemo(
    () => organization?.permissions || [],
    [organization],
  );

  const can = useCallback(
    (permission: string) =>
      permissions.includes(permission),
    [permissions],
  );

  const value = useMemo<SessionContextValue>(
    () => ({
      ready,
      authenticated,
      user,
      organization,
      stores,
      store,
      permissions,
      login,
      logout,
      selectStore,
      reloadWorkspace: loadWorkspace,
      can,
    }),
    [
      ready,
      authenticated,
      user,
      organization,
      stores,
      store,
      permissions,
      login,
      logout,
      selectStore,
      loadWorkspace,
      can,
    ],
  );

  return (
    <SessionContext.Provider value={value}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error(
      "useSession must be used inside SessionProvider",
    );
  }
  return context;
}
