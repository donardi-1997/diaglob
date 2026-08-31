import { useTranslation } from "react-i18next";
import { useState, useEffect } from "react";
import {
  Sun,
  Moon,
  Menu,
  X,
  ChevronDown,
  Sparkles,
  MessageSquare,
  Bot,
  ShoppingBag,
  Workflow,
  BarChart3,
  Users,
  Globe,
  Check,
  Database,
  BrainCircuit,
  FileSpreadsheet,
  Table,
  Package,
  ArrowRight,
  LayoutDashboard,
} from "lucide-react";

interface PublicLandingPageProps {
  onNavigateToLogin: () => void;
  onNavigateToRegister: () => void;
}

const plans = [
  {
    id: "starter",
    name: "Starter",
    price: 19,
    stores: 1,
    features: [
      "landingPlanStarterFeature1",
      "landingPlanStarterFeature2",
      "landingPlanStarterFeature3",
      "landingPlanStarterFeature4",
      "landingPlanStarterFeature5",
      "landingPlanStarterFeature6",
    ],
  },
  {
    id: "growth",
    name: "Growth",
    price: 59,
    stores: 2,
    recommended: true,
    features: [
      "landingPlanGrowthFeature1",
      "landingPlanGrowthFeature2",
      "landingPlanGrowthFeature3",
      "landingPlanGrowthFeature4",
      "landingPlanGrowthFeature5",
      "landingPlanGrowthFeature6",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    price: 99,
    stores: 3,
    features: [
      "landingPlanProFeature1",
      "landingPlanProFeature2",
      "landingPlanProFeature3",
      "landingPlanProFeature4",
      "landingPlanProFeature5",
      "landingPlanProFeature6",
    ],
  },
  {
    id: "scale",
    name: "Scale",
    price: 179,
    stores: 5,
    features: [
      "landingPlanScaleFeature1",
      "landingPlanScaleFeature2",
      "landingPlanScaleFeature3",
      "landingPlanScaleFeature4",
      "landingPlanScaleFeature5",
      "landingPlanScaleFeature6",
    ],
  },
];

const features = [
  {
    icon: MessageSquare,
    title: "landingFeatureConversationsTitle",
    description: "landingFeatureConversationsDesc",
  },
  {
    icon: Bot,
    title: "landingFeatureAgentsTitle",
    description: "landingFeatureAgentsDesc",
  },
  {
    icon: ShoppingBag,
    title: "landingFeatureCommerceTitle",
    description: "landingFeatureCommerceDesc",
  },
  {
    icon: Workflow,
    title: "landingFeatureAutomationsTitle",
    description: "landingFeatureAutomationsDesc",
  },
  {
    icon: BarChart3,
    title: "landingFeatureAnalyticsTitle",
    description: "landingFeatureAnalyticsDesc",
  },
  {
    icon: Users,
    title: "landingFeatureMultiStoreTitle",
    description: "landingFeatureMultiStoreDesc",
  },
];

const howItWorks = [
  {
    step: 1,
    title: "landingHowStep1Title",
    description: "landingHowStep1Desc",
  },
  {
    step: 2,
    title: "landingHowStep2Title",
    description: "landingHowStep2Desc",
  },
  {
    step: 3,
    title: "landingHowStep3Title",
    description: "landingHowStep3Desc",
  },
  {
    step: 4,
    title: "landingHowStep4Title",
    description: "landingHowStep4Desc",
  },
];

const problemSolutions = [
  {
    problem: "landingProblem1",
    solution: "landingSolution1",
  },
  {
    problem: "landingProblem2",
    solution: "landingSolution2",
  },
  {
    problem: "landingProblem3",
    solution: "landingSolution3",
  },
  {
    problem: "landingProblem4",
    solution: "landingSolution4",
  },
];

const faqItems = [
  {
    question: "landingFaqWhatIs",
    answer: "landingFaqWhatIsAnswer",
  },
  {
    question: "landingFaqWhatsapp",
    answer: "landingFaqWhatsappAnswer",
  },
  {
    question: "landingFaqShopify",
    answer: "landingFaqShopifyAnswer",
  },
  {
    question: "landingFaqMultiStore",
    answer: "landingFaqMultiStoreAnswer",
  },
  {
    question: "landingFaqAi",
    answer: "landingFaqAiAnswer",
  },
  {
    question: "landingFaqDropi",
    answer: "landingFaqDropiAnswer",
  },
];

export default function PublicLandingPage({
  onNavigateToLogin,
  onNavigateToRegister,
}: PublicLandingPageProps) {
  const { t, i18n } = useTranslation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const [theme, setTheme] = useState(
    localStorage.getItem("diaglob-theme") || "dark"
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("diaglob-theme", theme);
  }, [theme]);

  useEffect(() => {
    document.title =
      i18n.language === "en"
        ? "Diaglob — Conversations, commerce and automation for ecommerce"
        : "Diaglob — Conversaciones, comercio y automatización para ecommerce";
  }, [i18n.language]);

  const toggleTheme = () =>
    setTheme((current) => (current === "dark" ? "light" : "dark"));

  const changeLanguage = (lang: string) => {
    i18n.changeLanguage(lang);
    localStorage.setItem("diaglob-language", lang);
  };

  const scrollTo = (id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    const navbarHeight = 64;
    const y = el.getBoundingClientRect().top + window.scrollY - navbarHeight;
    window.scrollTo({ top: y, behavior: "smooth" });
    setMobileMenuOpen(false);
  };

  const navLinks = [
    { label: t("landingNavProduct"), target: "problem" },
    { label: t("landingNavHow"), target: "how-it-works" },
    { label: t("landingNavFeatures"), target: "features" },
    { label: t("landingNavIntegrations"), target: "integrations" },
    { label: t("landingNavPricing"), target: "pricing" },
    { label: t("landingNavFaq"), target: "faq" },
  ];

  return (
    <div className="landing-page">
      {/* NAVBAR */}
      <header className="landing-navbar">
        <div className="landing-container">
          <div className="landing-navbar-inner">
            <button className="landing-brand" onClick={() => scrollTo("hero")}>
              <div className="brand-mark">
                <Sparkles size={20} />
              </div>
              <div>
                <div className="brand-name">DIAGLOB</div>
                <div className="brand-version">AI COMMERCE</div>
              </div>
            </button>

            <nav className="landing-nav-links">
              {navLinks.map((link) => (
                <button key={link.target + link.label} onClick={() => scrollTo(link.target)}>
                  {link.label}
                </button>
              ))}
            </nav>

            <div className="landing-nav-actions">
              <div className="landing-controls">
                <div className="landing-lang-switch">
                  <button
                    className={i18n.language === "es" ? "active" : ""}
                    onClick={() => changeLanguage("es")}
                    aria-label="Español"
                  >
                    ES
                  </button>
                  <button
                    className={i18n.language === "en" ? "active" : ""}
                    onClick={() => changeLanguage("en")}
                    aria-label="English"
                  >
                    EN
                  </button>
                </div>
                <button
                  className="theme-toggle"
                  onClick={toggleTheme}
                  aria-label={theme === "dark" ? t("themeSwitchLight") : t("themeSwitchDark")}
                >
                  {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
                </button>
              </div>
              <button className="landing-btn-ghost" onClick={onNavigateToLogin}>
                {t("landingNavLogin")}
              </button>
              <button className="landing-btn-primary" onClick={onNavigateToRegister}>
                {t("landingNavRegister")}
              </button>
            </div>

            <button
              className="landing-mobile-toggle"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-label="Menu"
            >
              {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </div>

        {mobileMenuOpen && (
          <div className="landing-mobile-menu">
            {navLinks.map((link) => (
              <button key={"m-" + link.target + link.label} onClick={() => scrollTo(link.target)}>
                {link.label}
              </button>
            ))}
            <div className="landing-mobile-actions">
              <div className="landing-controls">
                <div className="landing-lang-switch">
                  <button
                    className={i18n.language === "es" ? "active" : ""}
                    onClick={() => changeLanguage("es")}
                    aria-label="Español"
                  >
                    ES
                  </button>
                  <button
                    className={i18n.language === "en" ? "active" : ""}
                    onClick={() => changeLanguage("en")}
                    aria-label="English"
                  >
                    EN
                  </button>
                </div>
                <button
                  className="theme-toggle"
                  onClick={toggleTheme}
                  aria-label={theme === "dark" ? t("themeSwitchLight") : t("themeSwitchDark")}
                >
                  {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
                </button>
              </div>
              <button className="landing-btn-ghost" onClick={onNavigateToLogin}>
                {t("landingNavLogin")}
              </button>
              <button className="landing-btn-primary" onClick={onNavigateToRegister}>
                {t("landingNavRegister")}
              </button>
            </div>
          </div>
        )}
      </header>

      <main>
        {/* HERO */}
        <section className="landing-hero" id="hero">
          <div className="landing-container">
            <div className="landing-hero-content">
              <div className="landing-hero-eyebrow">
                <Sparkles size={14} />
                <span>{t("landingHeroEyebrow")}</span>
              </div>
              <h1 className="landing-hero-title">{t("landingHeroTitle")}</h1>
              <p className="landing-hero-subtitle">{t("landingHeroSubtitle")}</p>
              <div className="landing-hero-ctas">
                <button className="landing-btn-primary landing-btn-lg" onClick={onNavigateToRegister}>
                  {t("landingHeroCta")}
                </button>
                <button className="landing-btn-outline landing-btn-lg" onClick={() => scrollTo("how-it-works")}>
                  {t("landingHeroCtaSecondary")}
                </button>
              </div>
              <div className="landing-hero-pricing-note">{t("landingHeroPricingNote")}</div>
            </div>
            <div className="landing-hero-visual">
              <div className="landing-mock-ui">
                <div className="landing-mock-topbar">
                  <div className="landing-mock-dots">
                    <span></span><span></span><span></span>
                  </div>
                  <div className="landing-mock-title">Diaglob Dashboard</div>
                </div>
                <div className="landing-mock-body">
                  <div className="landing-mock-sidebar-mock">
                    <div className="landing-mock-nav-item active">
                      <BarChart3 size={14} /> {t("landingMockOverview")}
                    </div>
                    <div className="landing-mock-nav-item">
                      <MessageSquare size={14} /> {t("landingMockConversations")}
                    </div>
                    <div className="landing-mock-nav-item">
                      <ShoppingBag size={14} /> {t("landingMockCommerce")}
                    </div>
                    <div className="landing-mock-nav-item">
                      <Workflow size={14} /> {t("landingMockAutomations")}
                    </div>
                    <div className="landing-mock-nav-item">
                      <BarChart3 size={14} /> {t("landingMockAnalytics")}
                    </div>
                  </div>
                  <div className="landing-mock-content">
                    <div className="landing-mock-stats">
                      <div className="landing-mock-stat">
                        <div className="landing-mock-stat-value">24</div>
                        <div className="landing-mock-stat-label">{t("landingMockConversations")}</div>
                      </div>
                      <div className="landing-mock-stat">
                        <div className="landing-mock-stat-value">81%</div>
                        <div className="landing-mock-stat-label">{t("landingMockResolved")}</div>
                      </div>
                      <div className="landing-mock-stat">
                        <div className="landing-mock-stat-value">12</div>
                        <div className="landing-mock-stat-label">{t("landingMockOrders")}</div>
                      </div>
                    </div>
                    <div className="landing-mock-chart">
                      <div className="landing-mock-bar" style={{ height: "40%" }}></div>
                      <div className="landing-mock-bar" style={{ height: "65%" }}></div>
                      <div className="landing-mock-bar" style={{ height: "45%" }}></div>
                      <div className="landing-mock-bar" style={{ height: "80%" }}></div>
                      <div className="landing-mock-bar" style={{ height: "55%" }}></div>
                      <div className="landing-mock-bar" style={{ height: "70%" }}></div>
                      <div className="landing-mock-bar" style={{ height: "90%" }}></div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* PROBLEM / SOLUTION */}
        <section className="landing-section landing-problem" id="problem">
          <div className="landing-container">
            <h2 className="landing-section-title">{t("landingProblemTitle")}</h2>
            <div className="landing-problem-grid">
              {problemSolutions.map((item, i) => (
                <div key={i} className="landing-problem-card">
                  <div className="landing-problem-from">{t(item.problem)}</div>
                  <div className="landing-problem-arrow"><Check size={16} /></div>
                  <div className="landing-problem-to">{t(item.solution)}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* HOW IT WORKS */}
        <section className="landing-section landing-how" id="how-it-works">
          <div className="landing-container">
            <h2 className="landing-section-title">{t("landingHowTitle")}</h2>
            <p className="landing-section-subtitle">{t("landingHowSubtitle")}</p>
            <div className="landing-how-flow">
              {howItWorks.map((step, i) => (
                <div key={step.step} className="landing-how-step">
                  <div className="landing-how-step-number">{step.step}</div>
                  <h3 className="landing-how-step-title">{t(step.title)}</h3>
                  <p className="landing-how-step-desc">{t(step.description)}</p>
                  {i < howItWorks.length - 1 && (
                    <div className="landing-how-arrow">
                      <ChevronDown size={16} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* FEATURES */}
        <section className="landing-section landing-features" id="features">
          <div className="landing-container">
            <h2 className="landing-section-title">{t("landingFeaturesTitle")}</h2>
            <p className="landing-section-subtitle">{t("landingFeaturesSubtitle")}</p>
            <div className="landing-features-grid">
              {features.map((f) => (
                <div key={t(f.title)} className="landing-feature-card">
                  <div className="landing-feature-icon">
                    <f.icon size={24} />
                  </div>
                  <h3>{t(f.title)}</h3>
                  <p>{t(f.description)}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CONNECTED KNOWLEDGE + MULTI-COUNTRY */}
        <section className="landing-section landing-built" id="built">
          <div className="landing-container">
            <h2 className="landing-section-title">{t("landingBuiltTitle")}</h2>
            <p className="landing-section-subtitle">{t("landingBuiltSubtitle")}</p>

            <div className="landing-built-grid">
              {/* LEFT: Knowledge Flow */}
              <div className="landing-built-panel">
                <div className="landing-built-panel-label">{t("landingKnowledgeLabel")}</div>
                <div className="landing-knowledge-diagram">
                  {/* Sources column */}
                  <div className="landing-kb-sources">
                    <div className="landing-kb-source">
                      <div className="landing-kb-source-icon"><Table size={16} /></div>
                      <div className="landing-kb-source-info">
                        <span className="landing-kb-source-name">{t("landingSourceGoogleSheets")}</span>
                        <span className="landing-kb-badge coming-soon">{t("landingSourceGoogleSheetsStatus")}</span>
                      </div>
                    </div>
                    <div className="landing-kb-source">
                      <div className="landing-kb-source-icon"><FileSpreadsheet size={16} /></div>
                      <div className="landing-kb-source-info">
                        <span className="landing-kb-source-name">{t("landingSourceExcel")}</span>
                        <span className="landing-kb-badge available">{t("landingSourceExcelStatus")}</span>
                      </div>
                    </div>
                    <div className="landing-kb-source">
                      <div className="landing-kb-source-icon"><ShoppingBag size={16} /></div>
                      <div className="landing-kb-source-info">
                        <span className="landing-kb-source-name">{t("landingSourceShopify")}</span>
                        <span className="landing-kb-badge available">{t("landingSourceShopifyStatus")}</span>
                      </div>
                    </div>
                    <div className="landing-kb-source">
                      <div className="landing-kb-source-icon"><Package size={16} /></div>
                      <div className="landing-kb-source-info">
                        <span className="landing-kb-source-name">{t("landingSourceDropi")}</span>
                        <span className="landing-kb-badge coming-soon">{t("landingSourceDropiStatus")}</span>
                      </div>
                    </div>
                  </div>

                  {/* Connector */}
                  <div className="landing-kb-connector">
                    <div className="landing-kb-connector-line" />
                    <ArrowRight size={16} className="landing-kb-connector-arrow" />
                  </div>

                  {/* Knowledge Base node */}
                  <div className="landing-kb-central">
                    <div className="landing-kb-node">
                      <Database size={20} />
                      <span>Diaglob</span>
                    </div>
                    <p className="landing-kb-node-desc">{t("landingKnowledgeDesc")}</p>
                  </div>

                  {/* Connector */}
                  <div className="landing-kb-connector">
                    <div className="landing-kb-connector-line" />
                    <ArrowRight size={16} className="landing-kb-connector-arrow" />
                  </div>

                  {/* AI Agent */}
                  <div className="landing-kb-agent">
                    <div className="landing-kb-agent-icon">
                      <BrainCircuit size={20} />
                    </div>
                    <span className="landing-kb-agent-label">{t("landingAgentLabel")}</span>
                    <p className="landing-kb-agent-desc">{t("landingAgentDesc")}</p>
                  </div>
                </div>

                {/* Results row */}
                <div className="landing-kb-results">
                  <div className="landing-kb-result">
                    <Check size={14} />
                    <div>
                      <strong>{t("landingResultRespond")}</strong>
                      <span>{t("landingResultRespondDesc")}</span>
                    </div>
                  </div>
                  <div className="landing-kb-result">
                    <Check size={14} />
                    <div>
                      <strong>{t("landingResultRecommend")}</strong>
                      <span>{t("landingResultRecommendDesc")}</span>
                    </div>
                  </div>
                  <div className="landing-kb-result">
                    <Check size={14} />
                    <div>
                      <strong>{t("landingResultAutomate")}</strong>
                      <span>{t("landingResultAutomateDesc")}</span>
                    </div>
                  </div>
                </div>

                <p className="landing-kb-highlight">{t("landingKnowledgeHighlight")}</p>
              </div>

              {/* RIGHT: Multi-country */}
              <div className="landing-built-panel">
                <div className="landing-built-panel-label">{t("landingBuiltMultiTitle")}</div>
                <p className="landing-built-multi-sub">{t("landingBuiltMultiSubtitle")}</p>

                <div className="landing-country-diagram">
                  <div className="landing-country-stores">
                    <div className="landing-country-card">
                      <span className="landing-country-flag">🇨🇴</span>
                      <div className="landing-country-info">
                        <span className="landing-country-name">{t("landingStoreColombia")}</span>
                        <div className="landing-country-badges">
                          <span className="landing-country-badge">{t("landingStoreCurrencyCOP")}</span>
                          <span className="landing-country-badge">{t("landingStoreLangEs")}</span>
                        </div>
                        <div className="landing-country-integrations">
                          <span className="landing-ci"><MessageSquare size={12} /> WhatsApp</span>
                          <span className="landing-ci"><ShoppingBag size={12} /> Shopify</span>
                        </div>
                      </div>
                    </div>

                    <div className="landing-country-card">
                      <span className="landing-country-flag">🇲🇽</span>
                      <div className="landing-country-info">
                        <span className="landing-country-name">{t("landingStoreMexico")}</span>
                        <div className="landing-country-badges">
                          <span className="landing-country-badge">{t("landingStoreCurrencyMXN")}</span>
                          <span className="landing-country-badge">{t("landingStoreLangEs")}</span>
                        </div>
                        <div className="landing-country-integrations">
                          <span className="landing-ci"><MessageSquare size={12} /> WhatsApp</span>
                          <span className="landing-ci"><ShoppingBag size={12} /> Shopify</span>
                        </div>
                      </div>
                    </div>

                    <div className="landing-country-card">
                      <span className="landing-country-flag">🇺🇸</span>
                      <div className="landing-country-info">
                        <span className="landing-country-name">{t("landingStoreUsa")}</span>
                        <div className="landing-country-badges">
                          <span className="landing-country-badge">{t("landingStoreCurrencyUSD")}</span>
                          <span className="landing-country-badge">{t("landingStoreLangEn")}</span>
                        </div>
                        <div className="landing-country-integrations">
                          <span className="landing-ci"><MessageSquare size={12} /> WhatsApp</span>
                          <span className="landing-ci"><ShoppingBag size={12} /> Shopify</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Connector down to ops center */}
                  <div className="landing-country-connector">
                    <div className="landing-country-connector-lines" />
                  </div>

                  {/* Operations Center */}
                  <div className="landing-ops-node">
                    <LayoutDashboard size={18} />
                    <div>
                      <strong>{t("landingOpsCenter")}</strong>
                      <span>{t("landingOpsCenterDesc")}</span>
                    </div>
                  </div>
                </div>

                <p className="landing-built-each-store">{t("landingBuiltEachStore")}</p>
              </div>
            </div>
          </div>
        </section>

        {/* INTEGRATIONS */}
        <section className="landing-section landing-integrations" id="integrations">
          <div className="landing-container">
            <h2 className="landing-section-title">{t("landingIntegrationsTitle")}</h2>
            <p className="landing-section-subtitle">{t("landingIntegrationsSubtitle")}</p>
            <div className="landing-integrations-grid">
              <div className="landing-integration-card">
                <div className="landing-integration-icon">
                  <MessageSquare size={28} />
                </div>
                <h3>{t("landingIntegrationWhatsapp")}</h3>
                <div className="landing-integration-status available">
                  <Check size={14} /> {t("landingIntegrationAvailable")}
                </div>
              </div>
              <div className="landing-integration-card">
                <div className="landing-integration-icon">
                  <ShoppingBag size={28} />
                </div>
                <h3>{t("landingIntegrationShopify")}</h3>
                <div className="landing-integration-status available">
                  <Check size={14} /> {t("landingIntegrationAvailable")}
                </div>
              </div>
              <div className="landing-integration-card">
                <div className="landing-integration-icon">
                  <Globe size={28} />
                </div>
                <h3>{t("landingIntegrationDropi")}</h3>
                <div className="landing-integration-status coming-soon">
                  {t("landingIntegrationComingSoon")}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* PRICING */}
        <section className="landing-section landing-pricing" id="pricing">
          <div className="landing-container">
            <h2 className="landing-section-title">{t("landingPricingTitle")}</h2>
            <p className="landing-section-subtitle">{t("landingPricingSubtitle")}</p>
            <div className="landing-pricing-grid">
              {plans.map((plan) => (
                <div
                  key={plan.id}
                  className={`landing-pricing-card ${plan.recommended ? "recommended" : ""}`}
                >
                  {plan.recommended && (
                    <div className="landing-pricing-badge">{t("landingPricingRecommended")}</div>
                  )}
                  <h3>{plan.name}</h3>
                  <div className="landing-pricing-price">
                    <span className="landing-pricing-amount">${plan.price}</span>
                    <span className="landing-pricing-period">USD / {t("landingPricingMonth")}</span>
                  </div>
                  <div className="landing-pricing-stores">
                    {plan.stores}{" "}
                    {plan.stores === 1 ? t("landingPricingStore") : t("landingPricingStores")}
                  </div>
                  <ul className="landing-pricing-features">
                    {plan.features.map((f) => (
                      <li key={f}>
                        <Check size={14} /> {t(f)}
                      </li>
                    ))}
                  </ul>
                  <button
                    className={`landing-btn-primary landing-btn-full ${plan.recommended ? "recommended" : ""}`}
                    onClick={onNavigateToRegister}
                  >
                    {t("landingPricingCta")}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section className="landing-section landing-faq" id="faq">
          <div className="landing-container">
            <h2 className="landing-section-title">{t("landingFaqTitle")}</h2>
            <p className="landing-section-subtitle">{t("landingFaqSubtitle")}</p>
            <div className="landing-faq-list">
              {faqItems.map((item, i) => (
                <div
                  key={i}
                  className={`landing-faq-item ${openFaq === i ? "open" : ""}`}
                >
                  <button
                    className="landing-faq-question"
                    onClick={() => setOpenFaq(openFaq === i ? null : i)}
                    aria-expanded={openFaq === i}
                  >
                    <span>{t(item.question)}</span>
                    <ChevronDown size={18} className="landing-faq-chevron" />
                  </button>
                  {openFaq === i && (
                    <div className="landing-faq-answer">
                      <p>{t(item.answer)}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA FINAL */}
        <section className="landing-section landing-cta-final" id="cta-final">
          <div className="landing-container">
            <h2>{t("landingCtaFinalTitle")}</h2>
            <p>{t("landingCtaFinalSubtitle")}</p>
            <div className="landing-hero-ctas">
              <button className="landing-btn-primary landing-btn-lg" onClick={onNavigateToRegister}>
                {t("landingCtaFinalButton")}
              </button>
            </div>
          </div>
        </section>
      </main>

      {/* FOOTER */}
      <footer className="landing-footer">
        <div className="landing-container">
          <div className="landing-footer-grid">
            <div className="landing-footer-brand">
              <div className="landing-brand">
                <div className="brand-mark">
                  <Sparkles size={20} />
                </div>
                <div>
                  <div className="brand-name">DIAGLOB</div>
                  <div className="brand-version">AI COMMERCE</div>
                </div>
              </div>
              <p className="landing-footer-tagline">{t("landingFooterTagline")}</p>
            </div>
            <div className="landing-footer-col">
              <h4>{t("landingFooterProduct")}</h4>
              <button onClick={() => scrollTo("features")}>{t("landingFooterFeatures")}</button>
              <button onClick={() => scrollTo("integrations")}>{t("landingFooterIntegrations")}</button>
              <button onClick={() => scrollTo("pricing")}>{t("landingFooterPricing")}</button>
            </div>
            <div className="landing-footer-col">
              <h4>{t("landingFooterLegal")}</h4>
              <a href="/privacy">{t("landingFooterPrivacy")}</a>
              <a href="/terms">{t("landingFooterTerms")}</a>
            </div>
            <div className="landing-footer-col">
              <h4>{t("landingFooterAccount")}</h4>
              <button onClick={onNavigateToLogin}>{t("landingFooterLogin")}</button>
              <button onClick={onNavigateToRegister}>{t("landingFooterRegister")}</button>
            </div>
          </div>
          <div className="landing-footer-bottom">
            <span>&copy; {new Date().getFullYear()} Diaglob. {t("landingFooterRights")}</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
