import {
  Suspense,
  lazy,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  Navigate,
  Route,
  Routes,
  useNavigate,
} from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  BarChart3,
  Bot,
  BrainCircuit,
  CreditCard,
  LayoutDashboard,
  MessageSquareText,
  Plug,
  ShoppingBag,
  Sparkles,
  Store,
  Users,
  Workflow,
} from "lucide-react";

import AppShellV2, {
  type AppNavigationItem,
} from "./components/AppShellV2";
import type { GlobalSearchResult } from "./services/globalSearch";
import LoginPage from "./pages/LoginPage";
import { useWorkspace } from "./hooks/useWorkspace";
import "./App.css";
import "./landing.css";

const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const ConversationsPage = lazy(() => import("./pages/ConversationsPage"));
const AgentsPage = lazy(() => import("./pages/AgentsPage"));
const TeamPage = lazy(() => import("./pages/TeamPage"));
const KnowledgeBasesPage = lazy(() => import("./pages/KnowledgeBasesPage"));
const StoresPage = lazy(() => import("./pages/StoresPage"));
const PlansPage = lazy(() => import("./pages/PlansPage"));
const PublicLandingPage = lazy(() => import("./pages/PublicLandingPage"));
const LegalPage = lazy(() => import("./pages/LegalPage"));
const RefundPolicyPage = lazy(() => import("./pages/RefundPolicyPage"));
const CommercePage = lazy(() => import("./pages/CommercePage"));
const AutomationsPage = lazy(() => import("./pages/AutomationsPage"));
const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage"));
const CustomersWorkspacePage = lazy(() => import("./pages/CustomersWorkspacePage"));
const IntegrationsHubPage = lazy(() => import("./pages/IntegrationsHubPage"));

interface NavigationDefinition {
  key: string;
  labelKey: string;
  fallback: string;
  group: AppNavigationItem["group"];
  icon: AppNavigationItem["icon"];
  permission: string;
}

interface SearchTarget {
  result: GlobalSearchResult;
  requestKey: number;
}

const navigation: NavigationDefinition[] = [
  {
    key: "overview",
    labelKey: "overview",
    fallback: "Overview",
    group: "overview",
    icon: LayoutDashboard,
    permission: "dashboard.read",
  },
  {
    key: "analytics",
    labelKey: "analytics",
    fallback: "Analytics",
    group: "overview",
    icon: BarChart3,
    permission: "analytics.read",
  },
  {
    key: "conversations",
    labelKey: "conversations",
    fallback: "Conversaciones",
    group: "operations",
    icon: MessageSquareText,
    permission: "conversations.read",
  },
  {
    key: "customers",
    labelKey: "customers",
    fallback: "Clientes",
    group: "operations",
    icon: Users,
    permission: "customers.read",
  },
  {
    key: "commerce",
    labelKey: "commerce",
    fallback: "Comercio",
    group: "operations",
    icon: ShoppingBag,
    permission: "commerce.read",
  },
  {
    key: "integrations",
    labelKey: "integrations",
    fallback: "Integraciones",
    group: "operations",
    icon: Plug,
    permission: "stores.read",
  },
  {
    key: "automations",
    labelKey: "automations",
    fallback: "Automatizaciones",
    group: "operations",
    icon: Workflow,
    permission: "automations.read",
  },
  {
    key: "agents",
    labelKey: "agents",
    fallback: "Agentes IA",
    group: "intelligence",
    icon: Bot,
    permission: "agents.read",
  },
  {
    key: "knowledge",
    labelKey: "knowledge",
    fallback: "Knowledge",
    group: "intelligence",
    icon: BrainCircuit,
    permission: "knowledge.read",
  },
  {
    key: "settings",
    labelKey: "stores",
    fallback: "Tiendas",
    group: "workspace",
    icon: Store,
    permission: "stores.read",
  },
  {
    key: "team",
    labelKey: "team",
    fallback: "Equipo",
    group: "workspace",
    icon: Users,
    permission: "users.read",
  },
  {
    key: "plans",
    labelKey: "plans",
    fallback: "Planes y facturación",
    group: "workspace",
    icon: CreditCard,
    permission: "stores.read",
  },
];

function LoadingScreen({ session = false }: { session?: boolean }) {
  if (!session) {
    return <div className="page-loading">Cargando...</div>;
  }

  return (
    <div className="session-loading">
      <div className="session-loading-card">
        <div className="brand-mark">
          <Sparkles size={22} />
        </div>
        <strong>DIAGLOB</strong>
        <span>Cargando tu espacio...</span>
      </div>
    </div>
  );
}

function App() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const {
    authenticated,
    currentUser,
    sessionReady,
    stores,
    selectedStoreId,
    selectedStore,
    can,
    changeStore,
    handleAuthenticated,
    handleLogout,
    loadStores,
  } = useWorkspace();

  const [theme, setTheme] = useState(
    localStorage.getItem("diaglob-theme") || "dark",
  );
  const [activePage, setActivePage] = useState("overview");
  const [searchTarget, setSearchTarget] = useState<SearchTarget | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("diaglob-theme", theme);
  }, [theme]);

  const visibleNavigation = useMemo<AppNavigationItem[]>(
    () =>
      navigation
        .filter((item) => can(item.permission))
        .map((item) => ({
          key: item.key,
          label: t(item.labelKey) || item.fallback,
          group: item.group,
          icon: item.icon,
        })),
    [can, t],
  );

  useEffect(() => {
    if (!sessionReady || visibleNavigation.length === 0) {
      return;
    }

    if (!visibleNavigation.some((item) => item.key === activePage)) {
      setActivePage(visibleNavigation[0].key);
    }
  }, [activePage, sessionReady, visibleNavigation]);

  const toggleTheme = () => {
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  };

  const changeLanguage = (language: string) => {
    void i18n.changeLanguage(language);
    localStorage.setItem("diaglob-language", language);
  };

  const handleNavigate = (page: string) => {
    setSearchTarget(null);
    setActivePage(page);
  };

  const handleSearchResult = (result: GlobalSearchResult) => {
    if (result.storeId && String(result.storeId) !== selectedStoreId) {
      changeStore(String(result.storeId));
    }

    setSearchTarget((current) => ({
      result,
      requestKey: (current?.requestKey || 0) + 1,
    }));
    setActivePage(result.page);
  };

  const selectedSearchResult = searchTarget?.result;
  const searchRequestKey = searchTarget?.requestKey;
  const commerceSearchKind =
    selectedSearchResult?.kind === "product"
    || selectedSearchResult?.kind === "order"
      ? selectedSearchResult.kind
      : undefined;

  const appContent = (
    <Suspense fallback={<LoadingScreen />}>
      {activePage === "overview" && (
        <DashboardPage
          stores={stores}
          storeId={selectedStoreId ? Number(selectedStoreId) : null}
          onNavigateToStores={() => handleNavigate("settings")}
          onNavigateToCommerce={() => handleNavigate("commerce")}
          onNavigateToWhatsApp={() => handleNavigate("integrations")}
          onNavigateToKnowledge={() => handleNavigate("knowledge")}
          onNavigateToAutomations={() => handleNavigate("automations")}
        />
      )}
      {activePage === "plans" && <PlansPage />}
      {activePage === "conversations" && (
        <ConversationsPage
          stores={stores}
          canWrite={can("conversations.write")}
          initialConversationId={
            selectedSearchResult?.kind === "conversation"
              ? selectedSearchResult.entityId
              : undefined
          }
          initialStoreId={
            selectedSearchResult?.kind === "conversation"
              ? selectedSearchResult.storeId
              : undefined
          }
          searchRequestKey={
            selectedSearchResult?.kind === "conversation"
              ? searchRequestKey
              : undefined
          }
        />
      )}
      {activePage === "customers" && (
        <CustomersWorkspacePage
          canWrite={can("customers.write")}
          storeId={Number(selectedStoreId) || 0}
          initialCustomerId={
            selectedSearchResult?.kind === "customer"
              ? selectedSearchResult.entityId
              : undefined
          }
          searchRequestKey={
            selectedSearchResult?.kind === "customer"
              ? searchRequestKey
              : undefined
          }
        />
      )}
      {activePage === "team" && (
        <TeamPage stores={stores} canWrite={can("users.write")} />
      )}
      {activePage === "agents" && (
        <AgentsPage stores={stores} canWrite={can("agents.write")} />
      )}
      {activePage === "knowledge" && (
        <KnowledgeBasesPage
          stores={stores}
          canWrite={can("knowledge.write")}
        />
      )}
      {activePage === "settings" && (
        <StoresPage
          canWrite={can("stores.write")}
          onStoresChanged={loadStores}
        />
      )}
      {activePage === "commerce" && (
        <CommercePage
          canWrite={can("commerce.write")}
          storeId={Number(selectedStoreId) || 0}
          searchKind={commerceSearchKind}
          searchEntityId={commerceSearchKind ? selectedSearchResult?.entityId : undefined}
          searchQuery={commerceSearchKind ? selectedSearchResult?.query : undefined}
          searchRequestKey={commerceSearchKind ? searchRequestKey : undefined}
        />
      )}
      {activePage === "integrations" && (
        <IntegrationsHubPage
          storeId={Number(selectedStoreId) || 0}
          storeName={selectedStore?.name}
          shopDomain={selectedStore?.shopify_domain}
          canWrite={can("stores.write")}
          onNavigateToKnowledge={() => handleNavigate("knowledge")}
          onNavigateToStores={() => handleNavigate("settings")}
        />
      )}
      {activePage === "automations" && (
        <AutomationsPage
          canWrite={can("automations.write")}
          storeId={Number(selectedStoreId) || 0}
        />
      )}
      {activePage === "analytics" && (
        <AnalyticsPage
          canWrite={can("analytics.write")}
          storeId={Number(selectedStoreId) || 0}
          currency={selectedStore?.currency || "COP"}
        />
      )}
    </Suspense>
  );

  return (
    <Routes>
      <Route
        path="/"
        element={
          authenticated ? (
            <Navigate to="/app" replace />
          ) : (
            <Suspense fallback={<LoadingScreen />}>
              <PublicLandingPage
                onNavigateToLogin={() => navigate("/login")}
                onNavigateToRegister={() => navigate("/register")}
              />
            </Suspense>
          )
        }
      />
      <Route
        path="/login"
        element={
          authenticated ? (
            <Navigate to="/app" replace />
          ) : (
            <LoginPage
              onAuthenticated={handleAuthenticated}
              initialMode="login"
            />
          )
        }
      />
      <Route
        path="/register"
        element={
          authenticated ? (
            <Navigate to="/app" replace />
          ) : (
            <LoginPage
              onAuthenticated={handleAuthenticated}
              initialMode="register"
            />
          )
        }
      />
      <Route
        path="/privacy"
        element={
          <Suspense fallback={<LoadingScreen />}>
            <LegalPage kind="privacy" />
          </Suspense>
        }
      />
      <Route
        path="/terms"
        element={
          <Suspense fallback={<LoadingScreen />}>
            <LegalPage kind="terms" />
          </Suspense>
        }
      />
      <Route
        path="/refund-policy"
        element={
          <Suspense fallback={<LoadingScreen />}>
            <RefundPolicyPage />
          </Suspense>
        }
      />
      <Route path="/refund" element={<Navigate to="/refund-policy" replace />} />
      <Route
        path="/app/*"
        element={
          !authenticated ? (
            <Navigate to="/login" replace />
          ) : !sessionReady ? (
            <LoadingScreen session />
          ) : (
            <AppShellV2
              navigation={visibleNavigation}
              activePage={activePage}
              onNavigate={handleNavigate}
              onSearchResult={handleSearchResult}
              stores={stores}
              selectedStoreId={selectedStoreId}
              selectedStoreName={selectedStore?.name}
              onChangeStore={changeStore}
              userEmail={currentUser?.email}
              theme={theme}
              onToggleTheme={toggleTheme}
              language={i18n.resolvedLanguage || i18n.language}
              onChangeLanguage={changeLanguage}
              onLogout={handleLogout}
              supportUrl={import.meta.env.VITE_SUPPORT_URL}
            >
              {appContent}
            </AppShellV2>
          )
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
