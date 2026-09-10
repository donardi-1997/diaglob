import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import {
  ChevronDown,
  HelpCircle,
  LogOut,
  Menu,
  Moon,
  Search,
  ShoppingBag,
  Sparkles,
  Sun,
  X,
  type LucideIcon,
} from "lucide-react";

import type { Store } from "../services/stores";
import "../app-shell-v2.css";
import "../onboarding-activation-polish.css";

export interface AppNavigationItem {
  key: string;
  label: string;
  group: "overview" | "operations" | "intelligence" | "workspace";
  icon: LucideIcon;
}

interface AppShellV2Props {
  children: ReactNode;
  navigation: AppNavigationItem[];
  activePage: string;
  onNavigate: (page: string) => void;
  stores: Store[];
  selectedStoreId: string;
  selectedStoreName?: string;
  onChangeStore: (storeId: string) => void;
  userEmail?: string;
  theme: string;
  onToggleTheme: () => void;
  language: string;
  onChangeLanguage: (language: string) => void;
  onLogout: () => void;
  supportUrl?: string;
}

const GROUP_LABELS: Record<string, Record<AppNavigationItem["group"], string>> = {
  es: {
    overview: "Resumen",
    operations: "Operación",
    intelligence: "IA & conocimiento",
    workspace: "Workspace",
  },
  en: {
    overview: "Overview",
    operations: "Operations",
    intelligence: "AI & knowledge",
    workspace: "Workspace",
  },
  "pt-BR": {
    overview: "Visão geral",
    operations: "Operação",
    intelligence: "IA & conhecimento",
    workspace: "Workspace",
  },
};

const SEARCH_LABELS: Record<string, string> = {
  es: "Buscar en Diaglob",
  en: "Search Diaglob",
  "pt-BR": "Buscar no Diaglob",
};

const STORE_LABELS: Record<string, string> = {
  es: "Tienda activa",
  en: "Active store",
  "pt-BR": "Loja ativa",
};

const SUPPORT_LABELS: Record<string, string> = {
  es: "Soporte",
  en: "Support",
  "pt-BR": "Suporte",
};

const GROUP_ORDER: AppNavigationItem["group"][] = [
  "overview",
  "operations",
  "intelligence",
  "workspace",
];

function initials(email?: string) {
  if (!email) return "DG";
  return email.slice(0, 2).toUpperCase();
}

export default function AppShellV2({
  children,
  navigation,
  activePage,
  onNavigate,
  stores,
  selectedStoreId,
  selectedStoreName,
  onChangeStore,
  userEmail,
  theme,
  onToggleTheme,
  language,
  onChangeLanguage,
  onLogout,
  supportUrl,
}: AppShellV2Props) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [storeMenuOpen, setStoreMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  const locale = language === "pt-BR" ? "pt-BR" : language === "en" ? "en" : "es";
  const labels = GROUP_LABELS[locale];
  const currentItem = navigation.find((item) => item.key === activePage);
  const supportHref =
    supportUrl?.trim() ||
    "mailto:adrianguerra9703@gmail.com?subject=Diaglob%20Support";

  const groupedNavigation = useMemo(
    () =>
      GROUP_ORDER.map((group) => ({
        group,
        items: navigation.filter((item) => item.group === group),
      })).filter((section) => section.items.length > 0),
    [navigation],
  );

  useEffect(() => {
    if (!mobileOpen) return;

    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [mobileOpen]);

  const navigate = (page: string) => {
    onNavigate(page);
    setMobileOpen(false);
  };

  const renderNavigation = () => (
    <nav className="dg-nav" aria-label="Main navigation">
      {groupedNavigation.map(({ group, items }) => (
        <section className="dg-nav-group" key={group}>
          <div className="dg-nav-group-label">{labels[group]}</div>
          <div className="dg-nav-group-items">
            {items.map(({ key, label, icon: Icon }) => (
              <button
                type="button"
                key={key}
                className={`dg-nav-item ${activePage === key ? "is-active" : ""}`}
                onClick={() => navigate(key)}
                aria-current={activePage === key ? "page" : undefined}
              >
                <span className="dg-nav-icon"><Icon size={18} /></span>
                <span>{label}</span>
                {activePage === key && <span className="dg-nav-active-dot" />}
              </button>
            ))}
          </div>
        </section>
      ))}
    </nav>
  );

  const renderSupport = () => (
    <>
      <a
        className="dg-support-link"
        href={supportHref}
        target={supportHref.startsWith("mailto:") ? undefined : "_blank"}
        rel={supportHref.startsWith("mailto:") ? undefined : "noopener noreferrer"}
      >
        <HelpCircle size={17} />
        <span>{SUPPORT_LABELS[locale]}</span>
      </a>
      <div className="dg-powered-by">
        <span>Powered by</span>
        <strong>Diaglob</strong>
      </div>
    </>
  );

  return (
    <div className="dg-shell">
      <aside className="dg-sidebar">
        <div className="dg-sidebar-brand">
          <div className="dg-brand-mark"><Sparkles size={19} /></div>
          <div className="dg-brand-copy">
            <strong>DIAGLOB</strong>
            <span>Commerce OS</span>
          </div>
        </div>

        <div className="dg-sidebar-scroll">{renderNavigation()}</div>

        <div className="dg-sidebar-footer">
          {renderSupport()}
          <div className="dg-sidebar-user">
            <div className="dg-avatar">{initials(userEmail)}</div>
            <div className="dg-user-copy">
              <strong>{userEmail?.split("@")[0] || "Diaglob"}</strong>
              <span>{userEmail || "Workspace"}</span>
            </div>
          </div>
        </div>
      </aside>

      {mobileOpen && (
        <div className="dg-mobile-overlay" onClick={() => setMobileOpen(false)}>
          <aside className="dg-mobile-drawer" onClick={(event) => event.stopPropagation()}>
            <div className="dg-mobile-drawer-header">
              <div className="dg-sidebar-brand">
                <div className="dg-brand-mark"><Sparkles size={19} /></div>
                <div className="dg-brand-copy"><strong>DIAGLOB</strong><span>Commerce OS</span></div>
              </div>
              <button className="dg-icon-button" onClick={() => setMobileOpen(false)} aria-label="Cerrar menú">
                <X size={20} />
              </button>
            </div>
            <div className="dg-mobile-nav-scroll">{renderNavigation()}</div>
            <div className="dg-mobile-support-footer">{renderSupport()}</div>
          </aside>
        </div>
      )}

      <div className="dg-workspace">
        <header className="dg-topbar">
          <div className="dg-topbar-left">
            <button className="dg-icon-button dg-mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Abrir menú">
              <Menu size={20} />
            </button>
            <div className="dg-page-context">
              <span>{currentItem ? labels[currentItem.group] : "Diaglob"}</span>
              <strong>{currentItem?.label || "Diaglob"}</strong>
            </div>
          </div>

          <div className="dg-topbar-center">
            <button type="button" className="dg-search-trigger" aria-label={SEARCH_LABELS[locale]}>
              <Search size={16} />
              <span>{SEARCH_LABELS[locale]}</span>
              <kbd>⌘ K</kbd>
            </button>
          </div>

          <div className="dg-topbar-actions">
            <div className="dg-store-switcher">
              <button
                type="button"
                className="dg-store-trigger"
                onClick={() => setStoreMenuOpen((open) => !open)}
              >
                <span className="dg-store-icon"><ShoppingBag size={16} /></span>
                <span className="dg-store-copy">
                  <small>{STORE_LABELS[locale]}</small>
                  <strong>{selectedStoreName || "Sin tienda"}</strong>
                </span>
                <ChevronDown size={15} />
              </button>
              {storeMenuOpen && (
                <div className="dg-popover dg-store-menu">
                  {stores.filter((store) => store.active).map((store) => (
                    <button
                      key={store.id}
                      type="button"
                      className={String(store.id) === selectedStoreId ? "is-active" : ""}
                      onClick={() => {
                        onChangeStore(String(store.id));
                        setStoreMenuOpen(false);
                      }}
                    >
                      <span>{store.name}</span>
                      <small>{store.country_code || store.currency || ""}</small>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <button type="button" className="dg-icon-button" onClick={onToggleTheme} aria-label="Cambiar tema">
              {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </button>

            <div className="dg-profile-menu-wrap">
              <button type="button" className="dg-profile-trigger" onClick={() => setProfileOpen((open) => !open)}>
                <span className="dg-avatar dg-avatar-small">{initials(userEmail)}</span>
                <ChevronDown size={14} />
              </button>
              {profileOpen && (
                <div className="dg-popover dg-profile-menu">
                  <div className="dg-profile-meta">
                    <strong>{userEmail || "Diaglob"}</strong>
                    <span>Workspace</span>
                  </div>
                  <div className="dg-language-row">
                    {(["es", "en", "pt-BR"] as const).map((item) => (
                      <button
                        key={item}
                        type="button"
                        className={locale === item ? "is-active" : ""}
                        onClick={() => onChangeLanguage(item)}
                      >
                        {item === "pt-BR" ? "PT" : item.toUpperCase()}
                      </button>
                    ))}
                  </div>
                  <button type="button" className="dg-logout-action" onClick={onLogout}>
                    <LogOut size={16} />
                    <span>Cerrar sesión</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="dg-main-content">{children}</main>
      </div>
    </div>
  );
}
