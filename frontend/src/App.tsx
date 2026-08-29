import {
  useEffect,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import {
  Activity,
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
  Package,
  Settings,
  ShoppingBag,
  Sparkles,
  Sun,
  Users,
  Workflow,
  X,
  Zap,
} from "lucide-react";
import ConversationsPage from "./pages/ConversationsPage";
import AgentsPage from "./pages/AgentsPage";
import TeamPage from "./pages/TeamPage";
import KnowledgeBasesPage from "./pages/KnowledgeBasesPage";
import StoresPage from "./pages/StoresPage";
import PlansPage from "./pages/PlansPage";
import CommercePage from "./pages/CommercePage";
import AutomationsPage from "./pages/AutomationsPage";
import AnalyticsPage from "./pages/AnalyticsPage";
import LoginPage from "./pages/LoginPage";
import { getStores, type Store } from "./services/stores";
import {
  getCurrentUser,
  getMyOrganizations,
  type CurrentUser,
  type UserOrganization,
} from "./services/session";
import { clearSession, hasSession } from "./services/authStorage";
import {
  getCountryFlag,
  getCountryName,
  getLanguageName,
} from "./utils/markets";
import "./App.css";

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

  const [storeScopeVersion, setStoreScopeVersion] = useState(0);

  const [storeListVersion, setStoreListVersion] = useState(0);

  const [
    planRequiredMessage,
    setPlanRequiredMessage,
  ] = useState<string | null>(null);

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
    function handlePlanRequired(
      event: Event,
    ) {
      const customEvent =
        event as CustomEvent<{
          message?: string;
        }>;

      setPlanRequiredMessage(
        customEvent.detail?.message ||
          t("planRequiredDefault"),
      );
    }

    window.addEventListener(
      "diaglob-plan-required",
      handlePlanRequired,
    );

    return () => {
      window.removeEventListener(
        "diaglob-plan-required",
        handlePlanRequired,
      );
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
  }, [organizationId, sessionReady, storeListVersion]);

  const changeStore = (storeId: string) => {
    if (storeId) {
      localStorage.setItem("diaglob-store-id", storeId);
    } else {
      localStorage.removeItem("diaglob-store-id");
    }

    setSelectedStoreId(storeId);
    setStoreMenuOpen(false);

    setStoreScopeVersion((current) => current + 1);
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

    setStoreScopeVersion(
      (current) => current + 1
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


  const handleMobileNavigation = (
    page: string,
  ) => {
    setActivePage(page);
    setMobileMenuOpen(false);
    setStoreMenuOpen(false);
  };


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

  if (!authenticated) {
    return <LoginPage onAuthenticated={handleAuthenticated} />;
  }

  if (authenticated && !sessionReady) {
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

  return (
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
              className={
                activePage === "settings"
                  ? "nav-item active"
                  : "nav-item"
              }
              onClick={() =>
                setActivePage("settings")
              }
            >
              <Settings size={18} />
              <span>{t("settings")}</span>
            </button>
          )}

          <div className="store-switcher">
            <button
              className="store-selector"
              onClick={() =>
                setStoreMenuOpen(
                  (current) => !current
                )
              }
              aria-expanded={storeMenuOpen}
              aria-label="Seleccionar tienda"
            >
              <span className="store-flag selected-market">
                {selectedStore
                  ? getCountryFlag(
                      selectedStore.country_code
                    )
                  : "🌎"}
              </span>

              <div className="store-selector-info">
                <span className="store-selector-label">
                  Tienda activa
                </span>

                <strong>
                  {selectedStore
                    ? selectedStore.name
                    : t("noActiveStore")}
                </strong>

                <small>
                  {selectedStore
                    ? `${getCountryName(
                        selectedStore.country_code
                      )} · ${selectedStore.currency} · ${getLanguageName(
                        selectedStore.default_language
                      )}`
                    : t("selectStore")}
                </small>
              </div>

              <ChevronDown
                size={16}
                className={
                  storeMenuOpen
                    ? "store-chevron open"
                    : "store-chevron"
                }
              />
            </button>

            {storeMenuOpen && (
              <div className="store-menu">
                <div className="store-menu-heading">
                  {t("selectStore")}
                </div>

                {stores
                  .filter((store) => store.active)
                  .map((store) => (
                  <button
                    key={store.id}
                    className={
                      selectedStoreId ===
                      String(store.id)
                        ? "active"
                        : ""
                    }
                    onClick={() =>
                      changeStore(
                        String(store.id)
                      )
                    }
                  >
                    <span className="store-flag">
                      {getCountryFlag(
                        store.country_code
                      )}
                    </span>

                    <span>
                      <strong>
                        {store.name}
                      </strong>

                      <small>
                        {getCountryName(
                          store.country_code
                        )}
                        {" · "}
                        {store.currency}
                      </small>

                      <small className="store-market-detail">
                        {getLanguageName(
                          store.default_language
                        )}
                        {" · "}
                        {store.timezone}
                      </small>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </aside>

      {planRequiredMessage && (
        <div
          className="plan-required-backdrop"
          onMouseDown={(event) => {
            if (
              event.target ===
              event.currentTarget
            ) {
              setPlanRequiredMessage(null);
            }
          }}
        >
          <div
            className="plan-required-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="plan-required-title"
          >
            <span className="eyebrow">
              {t("appI18nPlanRequiredEyebrow")}
            </span>

            <h2 id="plan-required-title">
              {t("appI18nPlanRequiredTitle")}
            </h2>

            <p>
              {planRequiredMessage}
            </p>

            <p className="plan-required-help">
              Puedes seguir navegando y consultando
              tu información, pero necesitas una
              suscripción activa para realizar
              cambios o utilizar las funciones
              operativas de DIAGLOB.
            </p>

            <div className="plan-required-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() =>
                  setPlanRequiredMessage(null)
                }
              >
                Ahora no
              </button>

              <button
                type="button"
                className="primary-button"
                onClick={() => {
                  setPlanRequiredMessage(null);
                  setActivePage("plans");
                }}
              >
                {t("appI18nViewPlans")}
              </button>
            </div>
          </div>
        </div>
      )}

      {mobileMenuOpen && (
        <>
          <button
            type="button"
            className="mobile-menu-backdrop"
            aria-label={t("mobileCloseMenu")}
            onClick={() =>
              setMobileMenuOpen(false)
            }
          />

          <aside
            className="mobile-navigation-drawer"
            aria-label={t("mobileNavigation")}
          >
            <div className="mobile-navigation-header">
              <div className="mobile-navigation-brand">
                <div className="brand-mark">
                  <Sparkles size={19} />
                </div>

                <div>
                  <strong>DIAGLOB</strong>
                  <small>AI COMMERCE</small>
                </div>
              </div>

              <button
                type="button"
                className="mobile-navigation-close"
                aria-label={t("mobileCloseMenu")}
                onClick={() =>
                  setMobileMenuOpen(false)
                }
              >
                <X size={20} />
              </button>
            </div>

            <nav className="mobile-navigation-links">
              {visibleNavigation.map(
                ({ key, icon: Icon }) => (
                  <button
                    type="button"
                    key={key}
                    onClick={() =>
                      handleMobileNavigation(key)
                    }
                    className={
                      activePage === key
                        ? "mobile-nav-item active"
                        : "mobile-nav-item"
                    }
                  >
                    <Icon size={19} />
                    <span>{t(key)}</span>
                  </button>
                ),
              )}

              {can("stores.read") && (
                <button
                  type="button"
                  className={
                    activePage === "settings"
                      ? "mobile-nav-item active"
                      : "mobile-nav-item"
                  }
                  onClick={() =>
                    handleMobileNavigation(
                      "settings"
                    )
                  }
                >
                  <Settings size={19} />
                  <span>{t("settings")}</span>
                </button>
              )}
            </nav>

            <div className="mobile-navigation-footer">
              <div className="mobile-language-switch">
                <button
                  type="button"
                  className={
                    i18n.language === "es"
                      ? "active"
                      : ""
                  }
                  onClick={() =>
                    changeLanguage("es")
                  }
                >
                  {t("spanish")}
                </button>

                <button
                  type="button"
                  className={
                    i18n.language === "en"
                      ? "active"
                      : ""
                  }
                  onClick={() =>
                    changeLanguage("en")
                  }
                >
                  {t("english")}
                </button>
              </div>

              <button
                type="button"
                className="mobile-theme-button"
                onClick={toggleTheme}
              >
                {theme === "dark"
                  ? <Sun size={18} />
                  : <Moon size={18} />}

                <span>
                  {theme === "dark"
                    ? t("lightMode")
                    : t("darkMode")}
                </span>
              </button>

              <button
                type="button"
                className="mobile-logout-button"
                onClick={handleLogout}
              >
                <LogOut size={18} />
                <span>{t("logout")}</span>
              </button>
            </div>
          </aside>
        </>
      )}

      <main className="main">
        <header className="topbar">
          <button
            type="button"
            className="mobile-menu-toggle"
            aria-label={t("mobileOpenMenu")}
            aria-expanded={mobileMenuOpen}
            onClick={() =>
              setMobileMenuOpen(
                (current) => !current
              )
            }
          >
            {mobileMenuOpen
              ? <X size={21} />
              : <Menu size={21} />}
          </button>

          <div className="mobile-topbar-brand">
            <div className="brand-mark">
              <Sparkles size={17} />
            </div>

            <div>
              <strong>DIAGLOB</strong>
              <small>AI COMMERCE</small>
            </div>
          </div>

          <div className="status">
            <span className="status-dot" />
            {t("systemOnline")}
          </div>

          <div className="topbar-actions">
            <div className="language-switch">
              <button
                className={i18n.language === "es" ? "selected" : ""}
                onClick={() => changeLanguage("es")}
              >
                {t("spanish")}
              </button>

              <button
                className={i18n.language === "en" ? "selected" : ""}
                onClick={() => changeLanguage("en")}
              >
                {t("english")}
              </button>
            </div>

            <button
              className="theme-button"
              onClick={toggleTheme}
              aria-label={t("appI18nChangeTheme")}
            >
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>

            <button
              className="logout-button"
              title={
                currentUser
                  ? `${t("logout")} · ${currentUser.name}`
                  : t("logout")
              }
              onClick={handleLogout}
            >
              <LogOut size={17} />
              <span>{t("logout")}</span>
            </button>
          </div>
        </header>

        {activePage === "overview" && <Dashboard t={t} />}

        {activePage === "conversations" && (
          <ConversationsPage
            key={`conversations-${storeScopeVersion}`}
            canWrite={can("conversations.write")}
          />
        )}

        {activePage === "team" && (
          <TeamPage
            canWrite={can("users.write")}
          />
        )}

        {activePage === "agents" && (
          <AgentsPage
            key={`agents-${storeScopeVersion}`}
            canWrite={can("agents.write")}
          />
        )}

        {activePage === "knowledge" && (
          <KnowledgeBasesPage
            key={`knowledge-${storeScopeVersion}`}
            canWrite={can("knowledge.write")}
          />
        )}

        {activePage === "settings" && (
          <StoresPage
            canWrite={can("stores.write")}
            onOpenPlans={() =>
              setActivePage("plans")
            }
            onStoresChanged={() => {
              setStoreListVersion(
                (current) =>
                  current + 1
              );

              setStoreScopeVersion(
                (current) =>
                  current + 1
              );
            }}
          />
        )}

        {activePage === "plans" && (
          <PlansPage />
        )}

        {activePage === "commerce" && (
          <CommercePage
            key={`commerce-${storeScopeVersion}`}
            canWrite={can("commerce.write")}
            storeId={
              selectedStore?.id ?? 0
            }
          />
        )}

        {activePage === "automations" && (
          <AutomationsPage
            key={`automations-${storeScopeVersion}`}
            canWrite={can("automations.write")}
          />
        )}

        {activePage === "analytics" && (
          <AnalyticsPage
            key={`analytics-${storeScopeVersion}`}
            canWrite={can("analytics.write")}
            storeId={
              selectedStore?.id ?? 0
            }
          />
        )}

        {![
          "overview",
          "conversations",
          "team",
          "agents",
          "knowledge",
          "settings",
          "plans",
          "commerce",
          "automations",
          "analytics",
        ].includes(
          activePage,
        ) && (
          <div className="content">
            <section className="page-heading">
              <div>
                <span className="eyebrow">DIAGLOB TECH</span>
                <h1>{t(activePage)}</h1>
                <p>Coming soon</p>
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

function Dashboard({ t }: { t: any }) {
  return (
    <div className="content">
      <section className="page-heading">
        <div>
          <span className="eyebrow">DIAGLOB TECH</span>
          <h1>{t("dashboardTitle")}</h1>
          <p>{t("dashboardSubtitle")}</p>
        </div>

        <button className="primary-button">
          <Zap size={17} />
          {t("createAgent")}
        </button>
      </section>

      <section className="stats-grid">
        <StatCard
          icon={<MessageSquareText size={20} />}
          label={t("activeConversations")}
          value="24"
          change="+12.5%"
        />

        <StatCard
          icon={<Bot size={20} />}
          label={t("aiResolved")}
          value="81%"
          change="+4.1%"
        />

        <StatCard
          icon={<Activity size={20} />}
          label={t("conversionRate")}
          value="18.4%"
          change="+2.8%"
        />

        <StatCard
          icon={<Package size={20} />}
          label={t("revenueInfluenced")}
          value="$4.8M"
          change="+16.2%"
        />
      </section>

      <section className="dashboard-grid">
        <div className="panel activity-panel">
          <div className="panel-header">
            <div>
              <h2>{t("liveActivity")}</h2>
              <p>{t("liveActivitySubtitle")}</p>
            </div>
          </div>

          <div className="activity-list">
            <ActivityItem
              icon={<MessageSquareText size={17} />}
              title="WhatsApp"
              detail={t("activityWhatsapp")}
              time={t("now")}
            />

            <ActivityItem
              icon={<ShoppingBag size={17} />}
              title="Shopify"
              detail={t("activityShopify")}
              time="4 min"
            />

            <ActivityItem
              icon={<BrainCircuit size={17} />}
              title={t("knowledge")}
              detail={t("activityKnowledge")}
              time="7 min"
            />

            <ActivityItem
              icon={<Bot size={17} />}
              title={t("salesAgent")}
              detail={t("activitySales")}
              time="12 min"
            />
          </div>
        </div>

        <div className="right-column">
          <div className="panel">
            <div className="panel-header">
              <h2>{t("agentStatus")}</h2>
            </div>

            <div className="agent-list">
              <Agent name={t("salesAgent")} t={t} />
              <Agent name={t("supportAgent")} t={t} />
              <Agent name={t("ordersAgent")} t={t} />
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2>{t("knowledgeStatus")}</h2>
            </div>

            <div className="knowledge-number">3</div>
            <span className="knowledge-label">14 {t("sourcesConnected")}</span>
          </div>
        </div>
      </section>

      <section className="welcome-card">
        <div className="welcome-icon">
          <Sparkles size={24} />
        </div>

        <div className="welcome-copy">
          <h2>{t("welcomeTitle")}</h2>
          <p>{t("welcomeText")}</p>
        </div>

        <button className="secondary-button">{t("connectStore")}</button>
      </section>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  change,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  change: string;
}) {
  return (
    <div className="stat-card">
      <div className="stat-top">
        <div className="stat-icon">{icon}</div>
        <span className="positive">{change}</span>
      </div>

      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function ActivityItem({
  icon,
  title,
  detail,
  time,
}: {
  icon: React.ReactNode;
  title: string;
  detail: string;
  time: string;
}) {
  return (
    <div className="activity-item">
      <div className="activity-icon">{icon}</div>

      <div className="activity-copy">
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>

      <span className="activity-time">{time}</span>
    </div>
  );
}

function Agent({ name, t }: { name: string; t: any }) {
  return (
    <div className="agent-item">
      <div className="agent-icon">
        <Bot size={18} />
      </div>

      <div className="agent-copy">
        <strong>{name}</strong>
        <span>
          <span className="mini-status" />
          {t("active")}
        </span>
      </div>
    </div>
  );
}

export default App;
