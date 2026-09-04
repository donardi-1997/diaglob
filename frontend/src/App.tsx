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
import ConversationsPage from "./pages/ConversationsPage";
import AgentsPage from "./pages/AgentsPage";
import TeamPage from "./pages/TeamPage";
import KnowledgeBasesPage from "./pages/KnowledgeBasesPage";
import StoresPage from "./pages/StoresPage";
import PlansPage from "./pages/PlansPage";
import LoginPage from "./pages/LoginPage";
import PublicLandingPage from "./pages/PublicLandingPage";
import LegalPage from "./pages/LegalPage";
import DashboardPage from "./pages/DashboardPage";

const CommercePage = lazy(() => import("./pages/CommercePage"));
const AutomationsPage = lazy(() => import("./pages/AutomationsPage"));
const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage"));
const CustomersPage = lazy(() => import("./pages/CustomersPage"));
import { getStores, type Store } from "./services/stores";
import {
  getCurrentUser,
  getMyOrganizations,
  type CurrentUser,
  type UserOrganization,
} from "./services/session";
import { clearSession, hasSession } from "./services/authStorage";
import "./App.css";
import "./landing.css";

const navigation = [
  {
    key: "overview",
    icon: LayoutDashboard,
    permission: "dashboard.read",
  },

  {
    key: "plans",
    label: "plans",
    icon: CreditCard,
    permission: "stores.read",
  },
  {
    key: "conversations",
    icon: MessageSquareText,
    permission: "conversations.read",
  },
  {
    key: "customers",
    icon: Users,
    permission: "customers.read",
  },
  {
    key: "team",
    icon: Users,
    permission: "users.read",
  },
  {
    key: "agents",
    icon: Bot,
    permission: "agents.read",
  },
  {
    key: "knowledge",
    icon: BrainCircuit,
    permission: "knowledge.read",
  },
  {
    key: "commerce",
    icon: ShoppingBag,
    permission: "commerce.read",
  },
  {
    key: "automations",
    icon: Workflow,
    permission: "automations.read",
  },
  {
    key: "analytics",
    icon: BarChart3,
    permission: "analytics.read",
  },
];

function App() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();

  const [theme, setTheme] = useState(
    localStorage.getItem("diaglob-theme") || "dark",
  );

  const [activePage, setActivePage] = useState("overview");

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

  const [storeMenuOpen, setStoreMenuOpen] = useState(false);

  const [
    mobileMenuOpen,
    setMobileMenuOpen,
  ] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("diaglob-theme", theme);
  }, [theme]);

  useEffect(() => {
    async function loadSession() {
      if (!authenticated) {
        setCurrentUser(null);
        setOrganizations([]);
        setStores([]);
        setSessionReady(false);
        return;
      }

      try {
        setSessionReady(false);

        // Primero validamos/refrescamos la sesión.
        // Después cargamos datos dependientes del usuario.
        const user = await getCurrentUser();

        setCurrentUser(user);

        const organizationsResponse = await getMyOrganizations();

        setOrganizations(organizationsResponse.items);

        const savedOrganizationId = localStorage.getItem(
          "diaglob-organization-id",
        );

        const savedIsAllowed = Boolean(
          savedOrganizationId &&
          organizationsResponse.items.some(
            (organization) => String(organization.id) === savedOrganizationId,
          ),
        );

        const nextOrganizationId = savedIsAllowed
          ? savedOrganizationId!
          : organizationsResponse.items[0]
            ? String(organizationsResponse.items[0].id)
            : "";

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

        clearSession();

        setAuthenticated(false);
        setCurrentUser(null);
        setOrganizations([]);
        setStores([]);
        setOrganizationId("");
        setSelectedStoreId("");
        setSessionReady(false);
      }
    }

    loadSession();
  }, [authenticated]);

  useEffect(() => {
    const handleAuthExpired = () => {
      clearSession();

      setAuthenticated(false);
      setCurrentUser(null);
      setOrganizations([]);
      setStores([]);
      setOrganizationId("");
      setSelectedStoreId("");
      setSessionReady(false);
    };

    window.addEventListener("diaglob-auth-expired", handleAuthExpired);

    return () => {
      window.removeEventListener("diaglob-auth-expired", handleAuthExpired);
    };
  }, []);


  useEffect(() => {
    async function loadStores() {
      if (!sessionReady || !organizationId) {
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
    }

    loadStores();
  }, [organizationId, sessionReady]);

  const changeStore = (storeId: string) => {
    if (storeId) {
      localStorage.setItem("diaglob-store-id", storeId);
    } else {
      localStorage.removeItem("diaglob-store-id");
    }

    setSelectedStoreId(storeId);
    setStoreMenuOpen(false);
  };

  const selectedOrganization =
    organizations.find(
      (organization) => String(organization.id) === organizationId,
    ) || null;

  const permissions = selectedOrganization?.permissions || [];

  const can = (permission: string) => permissions.includes(permission);

  const visibleNavigation = navigation.filter((item) => can(item.permission));

  useEffect(() => {
    if (!selectedOrganization || visibleNavigation.length === 0) {
      return;
    }

    const allowed =
      activePage === "settings"
        ? can("stores.read")
        : activePage === "plans"
          ? true
          : visibleNavigation.some(
              (item) =>
                item.key === activePage
            );

    if (!allowed) {
      setActivePage(visibleNavigation[0].key);
    }
  }, [selectedOrganization, activePage]);

  const selectedStore =
    stores.find(
      (store) =>
        store.active &&
        String(store.id) === selectedStoreId
    ) || null;

  useEffect(() => {
    const activeStores =
      stores.filter(
        (store) => store.active
      );

    if (activeStores.length === 0) {
      if (selectedStoreId !== "") {
        localStorage.removeItem(
          "diaglob-store-id"
        );

        setSelectedStoreId("");
      }

      return;
    }

    const currentStoreIsValid =
      activeStores.some(
        (store) =>
          String(store.id) === selectedStoreId
      );

    if (currentStoreIsValid) {
      return;
    }

    const firstStoreId =
      String(activeStores[0].id);

    localStorage.setItem(
      "diaglob-store-id",
      firstStoreId,
    );

    setSelectedStoreId(
      firstStoreId,
    );
  }, [stores, selectedStoreId]);


  const handleAuthenticated = () => {
    setAuthenticated(true);
  };

  useEffect(() => {
    if (!mobileMenuOpen) {
      return;
    }

    const previousOverflow =
      document.body.style.overflow;

    document.body.style.overflow = "hidden";

    const handleKeyDown = (
      event: KeyboardEvent,
    ) => {
      if (event.key === "Escape") {
        setMobileMenuOpen(false);
      }
    };

    window.addEventListener(
      "keydown",
      handleKeyDown,
    );

    return () => {
      document.body.style.overflow =
        previousOverflow;

      window.removeEventListener(
        "keydown",
        handleKeyDown,
      );
    };
  }, [mobileMenuOpen]);


  const handleLogout = () => {
    clearSession();

    setAuthenticated(false);
    setCurrentUser(null);
    setOrganizations([]);
    setStores([]);
    setOrganizationId("");
    setSelectedStoreId("");
    setSessionReady(false);
    setStoreMenuOpen(false);
    setMobileMenuOpen(false);
  };

  const toggleTheme = () => {
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  };

  const changeLanguage = (language: string) => {
    i18n.changeLanguage(language);
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
            <PublicLandingPage
              onNavigateToLogin={() => {
                navigate("/login");
              }}
              onNavigateToRegister={() => {
                navigate("/register");
              }}
            />
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
      <Route path="/privacy" element={<LegalPage kind="privacy" />} />
      <Route path="/terms" element={<LegalPage kind="terms" />} />
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
                        {stores.filter((s) => s.active).map((s) => (
                          <button
                            key={s.id}
                            onClick={() => {
                              changeStore(String(s.id));
                              setStoreMenuOpen(false);
                            }}
                            className={String(s.id) === selectedStoreId ? "active" : ""}
                          >
                            {s.name}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <button className="nav-item" onClick={handleLogout}>
                    <LogOut size={18} />
                    <span>{t("logout")}</span>
                  </button>
                </div>
              </aside>

              {mobileMenuOpen && (
                <div className="mobile-drawer-overlay" onClick={() => setMobileMenuOpen(false)}>
                  <div className="mobile-drawer" onClick={(e) => e.stopPropagation()}>
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
                            {stores.filter((s) => s.active).map((s) => (
                              <button
                                key={s.id}
                                onClick={() => {
                                  changeStore(String(s.id));
                                  setStoreMenuOpen(false);
                                }}
                                className={String(s.id) === selectedStoreId ? "active" : ""}
                              >
                                {s.name}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                      <button className="nav-item" onClick={handleLogout}>
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
                    </div>
                    <button className="theme-button" onClick={toggleTheme}>
                      {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
                    </button>
                  </div>
                </div>
                <div className="content">
                  {activePage === "overview" && (
                    <DashboardPage storeId={selectedStoreId ? Number(selectedStoreId) : null} />
                  )}
                  {activePage === "plans" && <PlansPage />}
                  {activePage === "conversations" && <ConversationsPage canWrite={can("conversations.write")} />}
                  {activePage === "customers" && (
                    <Suspense fallback={<div className="page-loading">Cargando...</div>}>
                      <CustomersPage canWrite={can("customers.write")} storeId={Number(selectedStoreId) || 0} />
                    </Suspense>
                  )}
                  {activePage === "team" && <TeamPage canWrite={can("users.write")} />}
                  {activePage === "agents" && <AgentsPage canWrite={can("agents.write")} />}
                  {activePage === "knowledge" && <KnowledgeBasesPage canWrite={can("knowledge.write")} />}
                  {activePage === "settings" && <StoresPage canWrite={can("stores.write")} />}
                  {activePage === "commerce" && (
                    <Suspense fallback={<div className="page-loading">Cargando...</div>}>
                      <CommercePage canWrite={can("commerce.write")} storeId={Number(selectedStoreId) || 0} />
                    </Suspense>
                  )}
                  {activePage === "automations" && (
                    <Suspense fallback={<div className="page-loading">Cargando...</div>}>
                       <AutomationsPage canWrite={can("automations.write")} storeId={Number(selectedStoreId) || 0} />
                    </Suspense>
                  )}
                  {activePage === "analytics" && (
                    <Suspense fallback={<div className="page-loading">Cargando...</div>}>
                      <AnalyticsPage canWrite={can("analytics.write")} storeId={Number(selectedStoreId) || 0} />
                    </Suspense>
                  )}
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
