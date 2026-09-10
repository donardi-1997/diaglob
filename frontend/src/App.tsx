import {
  Suspense,
  lazy,
  useEffect,
  useState,
} from "react";
import {
  Routes,
  Route,
  Navigate,
  useNavigate,
} from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  CreditCard,
  BarChart3,
  Bot,
  BrainCircuit,
  ChevronDown,
  HelpCircle,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquareText,
  Moon,
  Settings,
  ShoppingBag,
  Sparkles,
  Sun,
  Users,
  Workflow,
  X,
} from "lucide-react";
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
const CustomersPage = lazy(() => import("./pages/CustomersPage"));

const navigation = [
  { key: "overview", icon: LayoutDashboard, permission: "dashboard.read" },
  { key: "plans", label: "plans", icon: CreditCard, permission: "stores.read" },
  { key: "conversations", icon: MessageSquareText, permission: "conversations.read" },
  { key: "customers", icon: Users, permission: "customers.read" },
  { key: "team", icon: Users, permission: "users.read" },
  { key: "agents", icon: Bot, permission: "agents.read" },
  { key: "knowledge", icon: BrainCircuit, permission: "knowledge.read" },
  { key: "commerce", icon: ShoppingBag, permission: "commerce.read" },
  { key: "automations", icon: Workflow, permission: "automations.read" },
  { key: "analytics", icon: BarChart3, permission: "analytics.read" },
];

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
  const [storeMenuOpen, setStoreMenuOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("diaglob-theme", theme);
  }, [theme]);

  const visibleNavigation = navigation.filter((item) => can(item.permission));

  useEffect(() => {
    if (!sessionReady || visibleNavigation.length === 0) {
      return;
    }

    const allowed =
      activePage === "settings"
        ? can("stores.read")
        : activePage === "plans"
          ? true
          : visibleNavigation.some((item) => item.key === activePage);

    if (!allowed) {
      setActivePage(visibleNavigation[0].key);
    }
  }, [activePage, can, sessionReady, visibleNavigation]);

  useEffect(() => {
    if (!mobileMenuOpen) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileMenuOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [mobileMenuOpen]);

  const selectStore = (storeId: string) => {
    changeStore(storeId);
    setStoreMenuOpen(false);
  };

  const logout = () => {
    handleLogout();
    setStoreMenuOpen(false);
    setMobileMenuOpen(false);
  };

  const toggleTheme = () => {
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  };

  const changeLanguage = (language: string) => {
    void i18n.changeLanguage(language);
    localStorage.setItem("diaglob-language", language);
  };

  return (
    <Routes>
      <Route
        path="/"
        element={
          authenticated ? (
            <Navigate to="/app" replace />
          ) : (
            <Suspense fallback={<div className="page-loading">Cargando...</div>}>
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
            <LoginPage onAuthenticated={handleAuthenticated} initialMode="login" />
          )
        }
      />
      <Route
        path="/register"
        element={
          authenticated ? (
            <Navigate to="/app" replace />
          ) : (
            <LoginPage onAuthenticated={handleAuthenticated} initialMode="register" />
          )
        }
      />
      <Route
        path="/privacy"
        element={
          <Suspense fallback={<div className="page-loading">Cargando...</div>}>
            <LegalPage kind="privacy" />
          </Suspense>
        }
      />
      <Route
        path="/terms"
        element={
          <Suspense fallback={<div className="page-loading">Cargando...</div>}>
            <LegalPage kind="terms" />
          </Suspense>
        }
      />
      <Route
        path="/refund-policy"
        element={
          <Suspense fallback={<div className="page-loading">Cargando...</div>}>
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
            <div className="session-loading">
              <div className="session-loading-card">
                <div className="brand-mark">
                  <Sparkles size={22} />
                </div>
                <strong>DIAGLOB</strong>
                <span>Cargando tu espacio...</span>
              </div>
            </div>
          ) : (
            <div className="app-shell">
              <aside className="sidebar">
                <div>
                  <div className="brand">
                    <div className="brand-mark">
                      <Sparkles size={20} />
                    </div>
                    <div>
                      <div className="brand-name">DIAGLOB</div>
                      <div className="brand-version">AI COMMERCE</div>
                    </div>
                  </div>
                  <nav className="navigation">
                    {visibleNavigation.map(({ key, icon: Icon }) => (
                      <button
                        key={key}
                        onClick={() => setActivePage(key)}
                        className={`nav-item ${activePage === key ? "active" : ""}`}
                      >
                        <Icon size={18} />
                        <span>{t(key)}</span>
                      </button>
                    ))}
                  </nav>
                </div>
                <div className="sidebar-bottom">
                  {can("stores.read") && (
                    <button
                      className={activePage === "settings" ? "nav-item active" : "nav-item"}
                      onClick={() => setActivePage("settings")}
                    >
                      <Settings size={18} />
                      <span>{t("settings")}</span>
                    </button>
                  )}
                  <a
                    href={import.meta.env.VITE_SUPPORT_URL || "#"}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="nav-item support-link"
                  >
                    <HelpCircle size={18} />
                    <span>{t("supportLabel") || "Soporte"}</span>
                  </a>
                  <div className="store-switcher">
                    <button
                      className="workspace-card"
                      onClick={() => setStoreMenuOpen(!storeMenuOpen)}
                    >
                      <ShoppingBag size={16} />
                      <span className="workspace-name">
                        {selectedStore?.name || "Sin tienda"}
                      </span>
                      <ChevronDown size={14} />
                    </button>
                    {storeMenuOpen && (
                      <div className="store-menu">
                        {stores.filter((store) => store.active).map((store) => (
                          <button
                            key={store.id}
                            onClick={() => selectStore(String(store.id))}
                            className={String(store.id) === selectedStoreId ? "active" : ""}
                          >
                            {store.name}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <button className="nav-item" onClick={logout}>
                    <LogOut size={18} />
                    <span>{t("logout")}</span>
                  </button>
                </div>
              </aside>

              {mobileMenuOpen && (
                <div className="mobile-drawer-overlay" onClick={() => setMobileMenuOpen(false)}>
                  <div className="mobile-drawer" onClick={(event) => event.stopPropagation()}>
                    <div className="mobile-drawer-header">
                      <div className="brand">
                        <div className="brand-mark">
                          <Sparkles size={20} />
                        </div>
                        <div>
                          <div className="brand-name">DIAGLOB</div>
                          <div className="brand-version">AI COMMERCE</div>
                        </div>
                      </div>
                      <button
                        className="mobile-drawer-close"
                        onClick={() => setMobileMenuOpen(false)}
                        aria-label="Cerrar menú"
                      >
                        <X size={20} />
                      </button>
                    </div>
                    <nav className="mobile-drawer-nav">
                      {visibleNavigation.map(({ key, icon: Icon }) => (
                        <button
                          key={key}
                          onClick={() => {
                            setActivePage(key);
                            setMobileMenuOpen(false);
                          }}
                          className={`nav-item ${activePage === key ? "active" : ""}`}
                        >
                          <Icon size={18} />
                          <span>{t(key)}</span>
                        </button>
                      ))}
                    </nav>
                    <div className="mobile-drawer-bottom">
                      {can("stores.read") && (
                        <button
                          className={activePage === "settings" ? "nav-item active" : "nav-item"}
                          onClick={() => {
                            setActivePage("settings");
                            setMobileMenuOpen(false);
                          }}
                        >
                          <Settings size={18} />
                          <span>{t("settings")}</span>
                        </button>
                      )}
                      <div className="store-switcher">
                        <button
                          className="workspace-card"
                          onClick={() => setStoreMenuOpen(!storeMenuOpen)}
                        >
                          <ShoppingBag size={16} />
                          <span className="workspace-name">
                            {selectedStore?.name || "Sin tienda"}
                          </span>
                          <ChevronDown size={14} />
                        </button>
                        {storeMenuOpen && (
                          <div className="store-menu">
                            {stores.filter((store) => store.active).map((store) => (
                              <button
                                key={store.id}
                                onClick={() => selectStore(String(store.id))}
                                className={String(store.id) === selectedStoreId ? "active" : ""}
                              >
                                {store.name}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                      <button className="nav-item" onClick={logout}>
                        <LogOut size={18} />
                        <span>{t("logout")}</span>
                      </button>
                    </div>
                  </div>
                </div>
              )}

              <main className="main">
                <div className="topbar">
                  <button
                    className="mobile-menu-button"
                    onClick={() => setMobileMenuOpen(true)}
                    aria-label="Abrir menú"
                  >
                    <Menu size={20} />
                  </button>
                  <div className="status">
                    <span className="status-dot"></span>
                    {currentUser?.email}
                  </div>
                  <div className="topbar-actions">
                    <div className="language-switch">
                      <button
                        className={i18n.language === "es" ? "active" : ""}
                        onClick={() => changeLanguage("es")}
                      >
                        ES
                      </button>
                      <button
                        className={i18n.language === "en" ? "active" : ""}
                        onClick={() => changeLanguage("en")}
                      >
                        EN
                      </button>
                      <button
                        className={i18n.language === "pt-BR" ? "active" : ""}
                        onClick={() => changeLanguage("pt-BR")}
                      >
                        PT-BR
                      </button>
                    </div>
                    <button className="theme-button" onClick={toggleTheme}>
                      {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
                    </button>
                  </div>
                </div>
                <div className="content">
                  <Suspense fallback={<div className="page-loading">Cargando...</div>}>
                    {activePage === "overview" && (
                      <DashboardPage
                        stores={stores}
                        storeId={selectedStoreId ? Number(selectedStoreId) : null}
                        onNavigateToStores={() => setActivePage("settings")}
                        onNavigateToCommerce={() => setActivePage("commerce")}
                        onNavigateToWhatsApp={() => setActivePage("settings")}
                        onNavigateToKnowledge={() => setActivePage("knowledge")}
                        onNavigateToAutomations={() => setActivePage("automations")}
                      />
                    )}
                    {activePage === "plans" && <PlansPage />}
                    {activePage === "conversations" && (
                      <ConversationsPage stores={stores} canWrite={can("conversations.write")} />
                    )}
                    {activePage === "customers" && (
                      <CustomersPage canWrite={can("customers.write")} storeId={Number(selectedStoreId) || 0} />
                    )}
                    {activePage === "team" && (
                      <TeamPage stores={stores} canWrite={can("users.write")} />
                    )}
                    {activePage === "agents" && (
                      <AgentsPage stores={stores} canWrite={can("agents.write")} />
                    )}
                    {activePage === "knowledge" && (
                      <KnowledgeBasesPage stores={stores} canWrite={can("knowledge.write")} />
                    )}
                    {activePage === "settings" && (
                      <StoresPage canWrite={can("stores.write")} onStoresChanged={loadStores} />
                    )}
                    {activePage === "commerce" && (
                      <CommercePage canWrite={can("commerce.write")} storeId={Number(selectedStoreId) || 0} />
                    )}
                    {activePage === "automations" && (
                      <AutomationsPage canWrite={can("automations.write")} storeId={Number(selectedStoreId) || 0} />
                    )}
                    {activePage === "analytics" && (
                      <AnalyticsPage
                        canWrite={can("analytics.write")}
                        storeId={Number(selectedStoreId) || 0}
                        currency={selectedStore?.currency || "COP"}
                      />
                    )}
                  </Suspense>
                </div>
              </main>
            </div>
          )
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
