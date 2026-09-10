import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  BarChart3,
  Bot,
  BrainCircuit,
  Check,
  ChevronDown,
  CreditCard,
  Database,
  Globe,
  Megaphone,
  Menu,
  MessageSquare,
  Moon,
  Package,
  ShoppingBag,
  Sparkles,
  Store,
  Sun,
  TrendingUp,
  Workflow,
  X,
} from "lucide-react";

import { getMarketingCopy, resolveMarketingLocale } from "../marketingCopy";

interface PublicLandingPageProps {
  onNavigateToLogin: () => void;
  onNavigateToRegister: () => void;
}

const plans = [
  { id: "starter", name: "Starter", price: 19, stores: 1, ai: "1K" },
  { id: "growth", name: "Growth", price: 49, stores: 2, ai: "5K" },
  { id: "pro", name: "Pro", price: 99, stores: 5, ai: "20K", recommended: true },
  { id: "scale", name: "Scale", price: 199, stores: 10, ai: "50K" },
];

const productIcons = [BrainCircuit, ShoppingBag, BarChart3, Workflow, Store, Bot];
const problemIcons = [Database, Workflow, TrendingUp];
const outcomeIcons = [MessageSquare, Globe, BarChart3];

const landingUi = {
  es: {
    live: "EN VIVO",
    aiAgent: "Agente IA",
    knowledgeSynced: "Conocimiento sincronizado",
    countries: "3 países",
    oneWorkspace: "Un solo workspace",
    commerce: "Comercio",
    messaging: "Mensajería",
    knowledge: "Conocimiento",
    growthPayments: "Crecimiento y pagos",
    localPayments: "Pagos locales",
    operationsOs: "Sistema operativo",
    coreOpsAnalytics: "Operación central + analítica",
    primaryNav: "Navegación principal",
    language: "Idioma",
    capabilities: "Capacidades",
    lightMode: "Modo claro",
    darkMode: "Modo oscuro",
  },
  en: {
    live: "LIVE",
    aiAgent: "AI Agent",
    knowledgeSynced: "Knowledge synced",
    countries: "3 countries",
    oneWorkspace: "One workspace",
    commerce: "Commerce",
    messaging: "Messaging",
    knowledge: "Knowledge",
    growthPayments: "Growth & payments",
    localPayments: "Local payments",
    operationsOs: "Operations OS",
    coreOpsAnalytics: "Core operations + analytics",
    primaryNav: "Primary navigation",
    language: "Language",
    capabilities: "Capabilities",
    lightMode: "Light mode",
    darkMode: "Dark mode",
  },
  "pt-BR": {
    live: "AO VIVO",
    aiAgent: "Agente IA",
    knowledgeSynced: "Conhecimento sincronizado",
    countries: "3 países",
    oneWorkspace: "Um workspace",
    commerce: "Comércio",
    messaging: "Mensagens",
    knowledge: "Conhecimento",
    growthPayments: "Crescimento e pagamentos",
    localPayments: "Pagamentos locais",
    operationsOs: "Sistema operacional",
    coreOpsAnalytics: "Operação central + analytics",
    primaryNav: "Navegação principal",
    language: "Idioma",
    capabilities: "Recursos",
    lightMode: "Modo claro",
    darkMode: "Modo escuro",
  },
} as const;

export default function PublicLandingPage({
  onNavigateToLogin,
  onNavigateToRegister,
}: PublicLandingPageProps) {
  const { i18n } = useTranslation();
  const copy = useMemo(() => getMarketingCopy(i18n.language), [i18n.language]);
  const locale = resolveMarketingLocale(i18n.language);
  const ui = landingUi[locale];
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(0);
  const [theme, setTheme] = useState(() => localStorage.getItem("diaglob-theme") || "dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("diaglob-theme", theme);
  }, [theme]);

  useEffect(() => {
    const title =
      locale === "en"
        ? "Diaglob — Dropshipping operations, AI and analytics"
        : locale === "pt-BR"
          ? "Diaglob — Operação, IA e analytics para dropshipping"
          : "Diaglob — Operación, IA y analítica para dropshipping";
    const description = copy.hero.subtitle;

    document.title = title;
    let meta = document.querySelector('meta[name="description"]');
    if (!meta) {
      meta = document.createElement("meta");
      meta.setAttribute("name", "description");
      document.head.appendChild(meta);
    }
    meta.setAttribute("content", description);
  }, [copy.hero.subtitle, locale]);

  const changeLanguage = (language: string) => {
    void i18n.changeLanguage(language);
    localStorage.setItem("diaglob-language", language);
  };

  const scrollTo = (id: string) => {
    const element = document.getElementById(id);
    if (!element) return;
    const top = element.getBoundingClientRect().top + window.scrollY - 76;
    window.scrollTo({ top, behavior: "smooth" });
    setMobileMenuOpen(false);
  };

  const navLinks = [
    { label: copy.nav.product, target: "product" },
    { label: copy.nav.outcomes, target: "outcomes" },
    { label: copy.nav.integrations, target: "integrations" },
    { label: copy.nav.pricing, target: "pricing" },
  ];

  const integrationGroups = [
    {
      label: ui.commerce,
      icon: ShoppingBag,
      items: ["Shopify", "Nuvemshop", "Dropi"],
    },
    {
      label: ui.messaging,
      icon: MessageSquare,
      items: ["WhatsApp", "Telegram"],
    },
    {
      label: ui.knowledge,
      icon: BrainCircuit,
      items: ["Google Drive", "Google Sheets", "Google Docs"],
    },
    {
      label: ui.growthPayments,
      icon: CreditCard,
      items: ["Meta Ads", ui.localPayments],
    },
  ];

  return (
    <div className="marketing-page">
      <header className="marketing-nav">
        <div className="marketing-shell marketing-nav-inner">
          <button className="marketing-brand" onClick={() => scrollTo("hero")} aria-label="Diaglob">
            <span className="marketing-brand-mark"><Sparkles size={19} /></span>
            <span className="marketing-brand-copy">
              <strong>DIAGLOB</strong>
              <small>AI COMMERCE OS</small>
            </span>
          </button>

          <nav className="marketing-nav-links" aria-label={ui.primaryNav}>
            {navLinks.map((link) => (
              <button key={link.target} onClick={() => scrollTo(link.target)}>{link.label}</button>
            ))}
          </nav>

          <div className="marketing-nav-actions">
            <div className="marketing-language" aria-label={ui.language}>
              {(["es", "en", "pt-BR"] as const).map((language) => (
                <button
                  key={language}
                  className={locale === language ? "active" : ""}
                  onClick={() => changeLanguage(language)}
                >
                  {language === "pt-BR" ? "PT" : language.toUpperCase()}
                </button>
              ))}
            </div>
            <button
              className="marketing-icon-button"
              onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")}
              aria-label={theme === "dark" ? ui.lightMode : ui.darkMode}
            >
              {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <button className="marketing-login-button" onClick={onNavigateToLogin}>{copy.nav.login}</button>
            <button className="marketing-primary-button compact" onClick={onNavigateToRegister}>
              {copy.nav.start}<ArrowRight size={16} />
            </button>
          </div>

          <button
            className="marketing-mobile-toggle"
            onClick={() => setMobileMenuOpen((open) => !open)}
            aria-label="Menu"
            aria-expanded={mobileMenuOpen}
          >
            {mobileMenuOpen ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>

        {mobileMenuOpen && (
          <div className="marketing-mobile-menu">
            {navLinks.map((link) => (
              <button key={link.target} onClick={() => scrollTo(link.target)}>{link.label}</button>
            ))}
            <div className="marketing-mobile-language">
              {(["es", "en", "pt-BR"] as const).map((language) => (
                <button key={language} className={locale === language ? "active" : ""} onClick={() => changeLanguage(language)}>
                  {language === "pt-BR" ? "PT-BR" : language.toUpperCase()}
                </button>
              ))}
            </div>
            <button className="marketing-login-button" onClick={onNavigateToLogin}>{copy.nav.login}</button>
            <button className="marketing-primary-button" onClick={onNavigateToRegister}>{copy.nav.start}</button>
          </div>
        )}
      </header>

      <main>
        <section className="marketing-hero" id="hero">
          <div className="marketing-orb orb-one" />
          <div className="marketing-orb orb-two" />
          <div className="marketing-shell marketing-hero-grid">
            <div className="marketing-hero-copy">
              <div className="marketing-eyebrow"><Sparkles size={15} />{copy.hero.eyebrow}</div>
              <h1>
                {copy.hero.titleLead}
                <span>{copy.hero.titleAccent}</span>
              </h1>
              <p className="marketing-hero-subtitle">{copy.hero.subtitle}</p>
              <div className="marketing-hero-actions">
                <button className="marketing-primary-button large" onClick={onNavigateToRegister}>
                  {copy.hero.primary}<ArrowRight size={18} />
                </button>
                <button className="marketing-secondary-button large" onClick={() => scrollTo("workflow")}>
                  {copy.hero.secondary}
                </button>
              </div>
              <p className="marketing-hero-note"><Check size={15} />{copy.hero.note}</p>
              <div className="marketing-trust-row">
                {copy.hero.trust.map((item) => <span key={item}>{item}</span>)}
              </div>
            </div>

            <div className="marketing-product-demo" aria-label={copy.dashboard.label}>
              <div className="demo-window">
                <div className="demo-topbar">
                  <div className="demo-dots"><span /><span /><span /></div>
                  <span>{copy.dashboard.label}</span>
                  <span className="demo-live"><i />{ui.live}</span>
                </div>
                <div className="demo-toolbar">
                  <div>
                    <small>{copy.dashboard.store}</small>
                    <strong>{copy.dashboard.period}</strong>
                  </div>
                  <span className="demo-health"><Check size={13} />{copy.dashboard.healthy}</span>
                </div>
                <div className="demo-metric-grid">
                  <div className="demo-metric featured">
                    <span>{copy.dashboard.revenue}</span><strong>$42.8K</strong><small>+18.4%</small>
                  </div>
                  <div className="demo-metric">
                    <span>{copy.dashboard.profit}</span><strong>$12.6K</strong><small>29.4%</small>
                  </div>
                  <div className="demo-metric">
                    <span>{copy.dashboard.delivery}</span><strong>84.7%</strong><small>+4.2%</small>
                  </div>
                  <div className="demo-metric">
                    <span>{copy.dashboard.conversations}</span><strong>1,284</strong><small>IA</small>
                  </div>
                </div>
                <div className="demo-chart-card">
                  <div className="demo-chart-heading">
                    <div><small>{copy.dashboard.orders}</small><strong>386</strong></div>
                    <div className="demo-chart-legend"><span /><span /></div>
                  </div>
                  <div className="demo-chart-bars">
                    {[42, 58, 49, 72, 64, 83, 76, 92, 80, 96].map((height, index) => (
                      <i key={index} style={{ height: `${height}%` }} />
                    ))}
                  </div>
                </div>
                <div className="demo-automation-row">
                  <Workflow size={17} />
                  <div><strong>8</strong><span>{copy.dashboard.automation}</span></div>
                  <span className="demo-pulse" />
                </div>
              </div>
              <div className="demo-floating-card floating-ai"><Bot size={18} /><div><strong>{ui.aiAgent}</strong><span>{ui.knowledgeSynced}</span></div><Check size={16} /></div>
              <div className="demo-floating-card floating-store"><Globe size={18} /><div><strong>{ui.countries}</strong><span>{ui.oneWorkspace}</span></div></div>
            </div>
          </div>
        </section>

        <section className="marketing-proof-strip" aria-label={ui.capabilities}>
          <div className="marketing-shell marketing-proof-inner">
            {[
              ["Shopify", ShoppingBag], ["WhatsApp", MessageSquare], ["Google Knowledge", BrainCircuit],
              ["Dropi", Package], ["Meta Ads", Megaphone], ["Analytics", BarChart3],
            ].map(([label, Icon]) => {
              const IconComponent = Icon as typeof ShoppingBag;
              return <div key={label as string}><IconComponent size={18} /><span>{label as string}</span></div>;
            })}
          </div>
        </section>

        <section className="marketing-section marketing-problem" id="outcomes">
          <div className="marketing-shell">
            <div className="marketing-section-heading centered">
              <span className="marketing-kicker">{copy.problem.eyebrow}</span>
              <h2>{copy.problem.title}</h2>
              <p>{copy.problem.subtitle}</p>
            </div>
            <div className="marketing-problem-grid">
              {copy.problem.items.map((item, index) => {
                const Icon = problemIcons[index];
                return (
                  <article key={item.title} className="marketing-problem-card">
                    <span className="marketing-card-icon muted"><Icon size={22} /></span>
                    <h3>{item.title}</h3><p>{item.text}</p>
                  </article>
                );
              })}
            </div>
          </div>
        </section>

        <section className="marketing-section marketing-outcomes">
          <div className="marketing-shell">
            <div className="marketing-section-heading">
              <span className="marketing-kicker">{copy.outcomes.eyebrow}</span>
              <h2>{copy.outcomes.title}</h2>
              <p>{copy.outcomes.subtitle}</p>
            </div>
            <div className="marketing-outcome-grid">
              {copy.outcomes.items.map((item, index) => {
                const Icon = outcomeIcons[index];
                return (
                  <article key={item.title} className="marketing-outcome-card">
                    <div className="marketing-outcome-top"><span className="marketing-card-icon"><Icon size={23} /></span><span className="marketing-proof-pill">{item.proof}</span></div>
                    <h3>{item.title}</h3><p>{item.text}</p>
                  </article>
                );
              })}
            </div>
          </div>
        </section>

        <section className="marketing-section marketing-product" id="product">
          <div className="marketing-shell">
            <div className="marketing-section-heading centered narrow">
              <span className="marketing-kicker">{copy.product.eyebrow}</span>
              <h2>{copy.product.title}</h2>
              <p>{copy.product.subtitle}</p>
            </div>
            <div className="marketing-product-grid">
              {copy.product.cards.map((card, index) => {
                const Icon = productIcons[index];
                return (
                  <article key={card.title} className={`marketing-product-card product-${index + 1}`}>
                    <div className="marketing-product-card-head">
                      <span className="marketing-card-icon"><Icon size={24} /></span>
                      <span className="marketing-product-tag">{card.tag}</span>
                    </div>
                    <h3>{card.title}</h3>
                    <p>{card.text}</p>
                    <ul>{card.bullets.map((bullet) => <li key={bullet}><Check size={14} />{bullet}</li>)}</ul>
                  </article>
                );
              })}
            </div>
          </div>
        </section>

        <section className="marketing-section marketing-integrations" id="integrations">
          <div className="marketing-shell marketing-integrations-layout">
            <div className="marketing-section-heading">
              <span className="marketing-kicker">{copy.integrations.eyebrow}</span>
              <h2>{copy.integrations.title}</h2>
              <p>{copy.integrations.subtitle}</p>
              <small>{copy.integrations.note}</small>
            </div>
            <div className="marketing-integration-board">
              <div className="integration-core"><Sparkles size={22} /><strong>DIAGLOB</strong><span>{ui.operationsOs}</span></div>
              {integrationGroups.map((group) => {
                const Icon = group.icon;
                return (
                  <div className="integration-group" key={group.label}>
                    <div className="integration-group-label"><Icon size={16} />{group.label}</div>
                    <div className="integration-chips">{group.items.map((item) => <span key={item}>{item}</span>)}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section className="marketing-section marketing-workflow" id="workflow">
          <div className="marketing-shell">
            <div className="marketing-section-heading centered narrow">
              <span className="marketing-kicker">{copy.workflow.eyebrow}</span>
              <h2>{copy.workflow.title}</h2>
              <p>{copy.workflow.subtitle}</p>
            </div>
            <div className="marketing-steps">
              {copy.workflow.steps.map((step, index) => (
                <article key={step.title} className="marketing-step">
                  <span className="marketing-step-number">0{index + 1}</span>
                  <div><h3>{step.title}</h3><p>{step.text}</p></div>
                  {index < copy.workflow.steps.length - 1 && <ArrowRight className="marketing-step-arrow" size={22} />}
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="marketing-section marketing-pricing" id="pricing">
          <div className="marketing-shell">
            <div className="marketing-section-heading centered narrow">
              <span className="marketing-kicker">{copy.pricing.eyebrow}</span>
              <h2>{copy.pricing.title}</h2>
              <p>{copy.pricing.subtitle}</p>
            </div>
            <div className="marketing-pricing-grid">
              {plans.map((plan) => (
                <article key={plan.id} className={`marketing-price-card ${plan.recommended ? "recommended" : ""}`}>
                  {plan.recommended && <span className="marketing-recommended">{copy.pricing.recommended}</span>}
                  <div className="marketing-price-name"><span>{plan.name}</span>{plan.id === "scale" && <Sparkles size={18} />}</div>
                  <div className="marketing-price"><strong>${plan.price}</strong><span>{copy.pricing.perMonth}</span></div>
                  <div className="marketing-price-divider" />
                  <div className="marketing-price-feature"><Store size={17} /><span><strong>{plan.stores}</strong> {plan.stores === 1 ? copy.pricing.store : copy.pricing.stores}</span></div>
                  <div className="marketing-price-feature"><Bot size={17} /><span><strong>{plan.ai}</strong> {copy.pricing.includedAi}</span></div>
                  <div className="marketing-price-feature"><Check size={17} /><span>{ui.coreOpsAnalytics}</span></div>
                  <button className={plan.recommended ? "marketing-primary-button full" : "marketing-secondary-button full"} onClick={onNavigateToRegister}>
                    {copy.pricing.cta}<ArrowRight size={16} />
                  </button>
                </article>
              ))}
            </div>
            <div className="marketing-ai-addon"><Sparkles size={20} /><div><strong>{copy.pricing.extraAi}</strong><span>{copy.pricing.footer}</span></div></div>
          </div>
        </section>

        <section className="marketing-section marketing-faq">
          <div className="marketing-shell marketing-faq-layout">
            <div className="marketing-section-heading">
              <span className="marketing-kicker">{copy.faq.eyebrow}</span>
              <h2>{copy.faq.title}</h2>
            </div>
            <div className="marketing-faq-list">
              {copy.faq.items.map((item, index) => (
                <article className={`marketing-faq-item ${openFaq === index ? "open" : ""}`} key={item.q}>
                  <button onClick={() => setOpenFaq(openFaq === index ? null : index)} aria-expanded={openFaq === index}>
                    <span>{item.q}</span><ChevronDown size={19} />
                  </button>
                  {openFaq === index && <p>{item.a}</p>}
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="marketing-final-cta">
          <div className="marketing-shell marketing-final-card">
            <div className="marketing-final-glow" />
            <span className="marketing-kicker light">{copy.final.eyebrow}</span>
            <h2>{copy.final.title}</h2>
            <p>{copy.final.subtitle}</p>
            <div className="marketing-hero-actions centered-actions">
              <button className="marketing-primary-button large inverse" onClick={onNavigateToRegister}>{copy.final.cta}<ArrowRight size={18} /></button>
              <button className="marketing-final-login" onClick={onNavigateToLogin}>{copy.final.login}</button>
            </div>
          </div>
        </section>
      </main>

      <footer className="marketing-footer">
        <div className="marketing-shell marketing-footer-grid">
          <div className="marketing-footer-brand">
            <div className="marketing-brand static"><span className="marketing-brand-mark"><Sparkles size={19} /></span><span className="marketing-brand-copy"><strong>DIAGLOB</strong><small>AI COMMERCE OS</small></span></div>
            <p>{copy.footer.tagline}</p>
          </div>
          <div><strong>{copy.footer.product}</strong><button onClick={() => scrollTo("product")}>{copy.nav.product}</button><button onClick={() => scrollTo("integrations")}>{copy.nav.integrations}</button><button onClick={() => scrollTo("pricing")}>{copy.nav.pricing}</button></div>
          <div><strong>{copy.footer.legal}</strong><a href="/privacy">{copy.footer.privacy}</a><a href="/terms">{copy.footer.terms}</a></div>
          <div><strong>{copy.footer.account}</strong><button onClick={onNavigateToLogin}>{copy.nav.login}</button><button onClick={onNavigateToRegister}>{copy.nav.start}</button></div>
        </div>
        <div className="marketing-shell marketing-footer-bottom">© {new Date().getFullYear()} Diaglob. {copy.footer.rights}</div>
      </footer>
    </div>
  );
}
