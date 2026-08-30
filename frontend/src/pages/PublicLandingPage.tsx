import { useTranslation } from "react-i18next";
import { useState, useEffect } from "react";
import {
  MessageSquareText,
  Bot,
  ShoppingBag,
  Workflow,
  BarChart3,
  LayoutDashboard,
  Users,
  Sparkles,
  Zap,
  Check,
  ArrowRight,
  ChevronDown,
  Menu,
  X,
  Clock,
  TrendingUp,
  AlertTriangle,
  Globe,
  Phone,
  Package,
  ShoppingCart,
  Store,
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
      "1 tienda activa",
      "Conversaciones WhatsApp",
      "AI Agents",
      "Commerce básico",
      "Analytics esencial",
    ],
  },
  {
    id: "growth",
    name: "Growth",
    price: 59,
    stores: 2,
    recommended: true,
    features: [
      "2 tiendas activas",
      "Todo de Starter",
      "Automations",
      "Operations Center",
      "Multi-store",
      "Soporte prioritario",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    price: 99,
    stores: 3,
    features: [
      "3 tiendas activas",
      "Todo de Growth",
      "Team & permisos avanzados",
      "Knowledge Bases",
      "Analytics avanzado",
    ],
  },
  {
    id: "scale",
    name: "Scale",
    price: 179,
    stores: 5,
    features: [
      "5 tiendas activas",
      "Todo de Pro",
      "Capacidad extendida",
      "Soporte dedicado",
    ],
  },
];

const features = [
  {
    icon: MessageSquareText,
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
    icon: LayoutDashboard,
    title: "landingFeatureOperationsTitle",
    description: "landingFeatureOperationsDesc",
  },
  {
    icon: Store,
    title: "landingFeatureMultiStoreTitle",
    description: "landingFeatureMultiStoreDesc",
  },
  {
    icon: Users,
    title: "landingFeatureTeamTitle",
    description: "landingFeatureTeamDesc",
  },
];

const howItWorks = [
  {
    step: 1,
    icon: Phone,
    title: "landingHowStep1Title",
    description: "landingHowStep1Desc",
  },
  {
    step: 2,
    icon: MessageSquareText,
    title: "landingHowStep2Title",
    description: "landingHowStep2Desc",
  },
  {
    step: 3,
    icon: Bot,
    title: "landingHowStep3Title",
    description: "landingHowStep3Desc",
  },
  {
    step: 4,
    icon: ShoppingCart,
    title: "landingHowStep4Title",
    description: "landingHowStep4Desc",
  },
  {
    step: 5,
    icon: Workflow,
    title: "landingHowStep5Title",
    description: "landingHowStep5Desc",
  },
  {
    step: 6,
    icon: BarChart3,
    title: "landingHowStep6Title",
    description: "landingHowStep6Desc",
  },
];

const targetUsers = [
  {
    icon: ShoppingBag,
    title: "landingTargetEcommerceTitle",
    description: "landingTargetEcommerceDesc",
  },
  {
    icon: Globe,
    title: "landingTargetDropshippingTitle",
    description: "landingTargetDropshippingDesc",
  },
  {
    icon: Zap,
    title: "landingTargetDtcTitle",
    description: "landingTargetDtcDesc",
  },
  {
    icon: Phone,
    title: "landingTargetWhatsappTitle",
    description: "landingTargetWhatsappDesc",
  },
  {
    icon: Store,
    title: "landingTargetMultiStoreTitle",
    description: "landingTargetMultiStoreDesc",
  },
];

const faqItems = [
  {
    question: "landingFaqWhatIs",
    answer: "landingFaqWhatIsAnswer",
  },
  {
    question: "landingFaqShopify",
    answer: "landingFaqShopifyAnswer",
  },
  {
    question: "landingFaqWhatsapp",
    answer: "landingFaqWhatsappAnswer",
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
    question: "landingFaqAutomations",
    answer: "landingFaqAutomationsAnswer",
  },
  {
    question: "landingFaqMetrics",
    answer: "landingFaqMetricsAnswer",
  },
  {
    question: "landingFaqDropi",
    answer: "landingFaqDropiAnswer",
  },
  {
    question: "landingFaqPricing",
    answer: "landingFaqPricingAnswer",
  },
  {
    question: "landingFaqChangePlan",
    answer: "landingFaqChangePlanAnswer",
  },
  {
    question: "landingFaqDataSeparation",
    answer: "landingFaqDataSeparationAnswer",
  },
];

export default function PublicLandingPage({
  onNavigateToLogin,
  onNavigateToRegister,
}: PublicLandingPageProps) {
  const { t } = useTranslation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  useEffect(() => {
    document.title = "Diaglob — Conversaciones, comercio y automatización para ecommerce";
  }, []);

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
    setMobileMenuOpen(false);
  };

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
              <button onClick={() => scrollTo("features")}>{t("landingNavProduct")}</button>
              <button onClick={() => scrollTo("how-it-works")}>{t("landingNavHow")}</button>
              <button onClick={() => scrollTo("features")}>{t("landingNavFeatures")}</button>
              <button onClick={() => scrollTo("integrations")}>{t("landingNavIntegrations")}</button>
              <button onClick={() => scrollTo("pricing")}>{t("landingNavPricing")}</button>
              <button onClick={() => scrollTo("faq")}>{t("landingNavFaq")}</button>
            </nav>

            <div className="landing-nav-actions">
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
            <button onClick={() => scrollTo("features")}>{t("landingNavProduct")}</button>
            <button onClick={() => scrollTo("how-it-works")}>{t("landingNavHow")}</button>
            <button onClick={() => scrollTo("features")}>{t("landingNavFeatures")}</button>
            <button onClick={() => scrollTo("integrations")}>{t("landingNavIntegrations")}</button>
            <button onClick={() => scrollTo("pricing")}>{t("landingNavPricing")}</button>
            <button onClick={() => scrollTo("faq")}>{t("landingNavFaq")}</button>
            <div className="landing-mobile-actions">
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
                <ArrowRight size={18} />
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
                    <LayoutDashboard size={14} /> {t("landingMockOverview")}
                  </div>
                  <div className="landing-mock-nav-item">
                    <MessageSquareText size={14} /> {t("landingMockConversations")}
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

      {/* PROBLEM */}
      <section className="landing-section landing-problem" id="problem">
        <div className="landing-container">
          <h2 className="landing-section-title">{t("landingProblemTitle")}</h2>
          <div className="landing-problem-grid">
            <div className="landing-problem-card">
              <MessageSquareText size={20} />
              <span>{t("landingProblem1")}</span>
            </div>
            <div className="landing-problem-card">
              <Clock size={20} />
              <span>{t("landingProblem2")}</span>
            </div>
            <div className="landing-problem-card">
              <ShoppingCart size={20} />
              <span>{t("landingProblem3")}</span>
            </div>
            <div className="landing-problem-card">
              <Workflow size={20} />
              <span>{t("landingProblem4")}</span>
            </div>
            <div className="landing-problem-card">
              <Store size={20} />
              <span>{t("landingProblem5")}</span>
            </div>
            <div className="landing-problem-card">
              <BarChart3 size={20} />
              <span>{t("landingProblem6")}</span>
            </div>
          </div>
          <div className="landing-problem-resolution">
            <Sparkles size={24} />
            <h3>{t("landingProblemResolution")}</h3>
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
                <div className="landing-how-step-icon">
                  <step.icon size={24} />
                </div>
                <h3 className="landing-how-step-title">{t(step.title)}</h3>
                <p className="landing-how-step-desc">{t(step.description)}</p>
                {i < howItWorks.length - 1 && (
                  <div className="landing-how-arrow">
                    <ArrowRight size={16} />
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

      {/* WHATSAPP */}
      <section className="landing-section landing-highlight" id="whatsapp">
        <div className="landing-container">
          <div className="landing-highlight-content">
            <div className="landing-highlight-icon">
              <Phone size={32} />
            </div>
            <h2>{t("landingWhatsappTitle")}</h2>
            <p>{t("landingWhatsappDesc")}</p>
            <ul className="landing-highlight-list">
              <li><Check size={16} /> {t("landingWhatsapp1")}</li>
              <li><Check size={16} /> {t("landingWhatsapp2")}</li>
              <li><Check size={16} /> {t("landingWhatsapp3")}</li>
              <li><Check size={16} /> {t("landingWhatsapp4")}</li>
              <li><Check size={16} /> {t("landingWhatsapp5")}</li>
              <li><Check size={16} /> {t("landingWhatsapp6")}</li>
            </ul>
          </div>
        </div>
      </section>

      {/* COMMERCE */}
      <section className="landing-section landing-commerce" id="commerce">
        <div className="landing-container">
          <div className="landing-highlight-content">
            <div className="landing-highlight-icon">
              <ShoppingBag size={32} />
            </div>
            <h2>{t("landingCommerceTitle")}</h2>
            <p>{t("landingCommerceDesc")}</p>
            <ul className="landing-highlight-list">
              <li><Check size={16} /> {t("landingCommerce1")}</li>
              <li><Check size={16} /> {t("landingCommerce2")}</li>
              <li><Check size={16} /> {t("landingCommerce3")}</li>
              <li><Check size={16} /> {t("landingCommerce4")}</li>
              <li><Check size={16} /> {t("landingCommerce5")}</li>
            </ul>
          </div>
        </div>
      </section>

      {/* AUTOMATIONS */}
      <section className="landing-section landing-automations" id="automations">
        <div className="landing-container">
          <div className="landing-highlight-content">
            <div className="landing-highlight-icon">
              <Workflow size={32} />
            </div>
            <h2>{t("landingAutomationsTitle")}</h2>
            <p>{t("landingAutomationsDesc")}</p>
            <div className="landing-automation-examples">
              <div className="landing-automation-example">
                <div className="landing-auto-trigger">{t("landingAutoTrigger1")}</div>
                <ArrowRight size={14} />
                <div className="landing-auto-action">{t("landingAutoAction1")}</div>
              </div>
              <div className="landing-automation-example">
                <div className="landing-auto-trigger">{t("landingAutoTrigger2")}</div>
                <ArrowRight size={14} />
                <div className="landing-auto-action">{t("landingAutoAction2")}</div>
              </div>
              <div className="landing-automation-example">
                <div className="landing-auto-trigger">{t("landingAutoTrigger3")}</div>
                <ArrowRight size={14} />
                <div className="landing-auto-action">{t("landingAutoAction3")}</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ANALYTICS */}
      <section className="landing-section landing-analytics" id="analytics">
        <div className="landing-container">
          <div className="landing-highlight-content">
            <div className="landing-highlight-icon">
              <BarChart3 size={32} />
            </div>
            <h2>{t("landingAnalyticsTitle")}</h2>
            <p>{t("landingAnalyticsDesc")}</p>
            <ul className="landing-highlight-list">
              <li><Check size={16} /> {t("landingAnalytics1")}</li>
              <li><Check size={16} /> {t("landingAnalytics2")}</li>
              <li><Check size={16} /> {t("landingAnalytics3")}</li>
              <li><Check size={16} /> {t("landingAnalytics4")}</li>
              <li><Check size={16} /> {t("landingAnalytics5")}</li>
              <li><Check size={16} /> {t("landingAnalytics6")}</li>
            </ul>
          </div>
        </div>
      </section>

      {/* OPERATIONS CENTER */}
      <section className="landing-section landing-operations" id="operations">
        <div className="landing-container">
          <div className="landing-highlight-content">
            <div className="landing-highlight-icon">
              <LayoutDashboard size={32} />
            </div>
            <h2>{t("landingOperationsTitle")}</h2>
            <p>{t("landingOperationsDesc")}</p>
            <ul className="landing-highlight-list">
              <li><Check size={16} /> {t("landingOperations1")}</li>
              <li><Check size={16} /> {t("landingOperations2")}</li>
              <li><Check size={16} /> {t("landingOperations3")}</li>
              <li><Check size={16} /> {t("landingOperations4")}</li>
              <li><Check size={16} /> {t("landingOperations5")}</li>
            </ul>
          </div>
        </div>
      </section>

      {/* MULTI-STORE */}
      <section className="landing-section landing-multistore" id="multistore">
        <div className="landing-container">
          <div className="landing-highlight-content">
            <div className="landing-highlight-icon">
              <Store size={32} />
            </div>
            <h2>{t("landingMultiStoreTitle")}</h2>
            <p>{t("landingMultiStoreDesc")}</p>
            <ul className="landing-highlight-list">
              <li><Check size={16} /> {t("landingMultiStore1")}</li>
              <li><Check size={16} /> {t("landingMultiStore2")}</li>
              <li><Check size={16} /> {t("landingMultiStore3")}</li>
              <li><Check size={16} /> {t("landingMultiStore4")}</li>
              <li><Check size={16} /> {t("landingMultiStore5")}</li>
            </ul>
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
                <MessageSquareText size={28} />
              </div>
              <h3>WhatsApp</h3>
              <p>{t("landingIntegrationWhatsapp")}</p>
              <div className="landing-integration-status available">
                <Check size={14} /> {t("landingIntegrationAvailable")}
              </div>
            </div>
            <div className="landing-integration-card">
              <div className="landing-integration-icon">
                <ShoppingBag size={28} />
              </div>
              <h3>Shopify</h3>
              <p>{t("landingIntegrationShopify")}</p>
              <div className="landing-integration-status available">
                <Check size={14} /> {t("landingIntegrationAvailable")}
              </div>
            </div>
            <div className="landing-integration-card">
              <div className="landing-integration-icon">
                <Package size={28} />
              </div>
              <h3>Dropi</h3>
              <p>{t("landingIntegrationDropi")}</p>
              <div className="landing-integration-status coming-soon">
                {t("landingIntegrationComingSoon")}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* TARGET USERS */}
      <section className="landing-section landing-target" id="target">
        <div className="landing-container">
          <h2 className="landing-section-title">{t("landingTargetTitle")}</h2>
          <p className="landing-section-subtitle">{t("landingTargetSubtitle")}</p>
          <div className="landing-target-grid">
            {targetUsers.map((u) => (
              <div key={t(u.title)} className="landing-target-card">
                <u.icon size={24} />
                <h3>{t(u.title)}</h3>
                <p>{t(u.description)}</p>
              </div>
            ))}
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
                  {plan.stores} {plan.stores === 1 ? t("landingPricingStore") : t("landingPricingStores")}
                </div>
                <ul className="landing-pricing-features">
                  {plan.features.map((f) => (
                    <li key={f}>
                      <Check size={14} /> {f}
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

      {/* BENEFITS */}
      <section className="landing-section landing-benefits" id="benefits">
        <div className="landing-container">
          <h2 className="landing-section-title">{t("landingBenefitsTitle")}</h2>
          <div className="landing-benefits-grid">
            <div className="landing-benefit-card">
              <Clock size={24} />
              <h3>{t("landingBenefit1Title")}</h3>
              <p>{t("landingBenefit1Desc")}</p>
            </div>
            <div className="landing-benefit-card">
              <Zap size={24} />
              <h3>{t("landingBenefit2Title")}</h3>
              <p>{t("landingBenefit2Desc")}</p>
            </div>
            <div className="landing-benefit-card">
              <ShoppingCart size={24} />
              <h3>{t("landingBenefit3Title")}</h3>
              <p>{t("landingBenefit3Desc")}</p>
            </div>
            <div className="landing-benefit-card">
              <Store size={24} />
              <h3>{t("landingBenefit4Title")}</h3>
              <p>{t("landingBenefit4Desc")}</p>
            </div>
            <div className="landing-benefit-card">
              <AlertTriangle size={24} />
              <h3>{t("landingBenefit5Title")}</h3>
              <p>{t("landingBenefit5Desc")}</p>
            </div>
            <div className="landing-benefit-card">
              <TrendingUp size={24} />
              <h3>{t("landingBenefit6Title")}</h3>
              <p>{t("landingBenefit6Desc")}</p>
            </div>
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

      {/* FINAL CTA */}
      <section className="landing-section landing-cta-final" id="cta-final">
        <div className="landing-container">
          <h2>{t("landingCtaFinalTitle")}</h2>
          <p>{t("landingCtaFinalSubtitle")}</p>
          <div className="landing-hero-ctas">
            <button className="landing-btn-primary landing-btn-lg" onClick={onNavigateToRegister}>
              {t("landingCtaFinalButton")}
              <ArrowRight size={18} />
            </button>
            <button className="landing-btn-outline landing-btn-lg" onClick={onNavigateToLogin}>
              {t("landingNavLogin")}
            </button>
          </div>
          <div className="landing-hero-pricing-note">{t("landingHeroPricingNote")}</div>
        </div>
      </section>

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
              <button onClick={() => scrollTo("features")}>{t("landingNavFeatures")}</button>
              <button onClick={() => scrollTo("integrations")}>{t("landingNavIntegrations")}</button>
              <button onClick={() => scrollTo("pricing")}>{t("landingNavPricing")}</button>
            </div>

            <div className="landing-footer-col">
              <h4>{t("landingFooterLegal")}</h4>
              <a href="/privacy">{t("landingFooterPrivacy")}</a>
              <a href="/terms">{t("landingFooterTerms")}</a>
            </div>

            <div className="landing-footer-col">
              <h4>{t("landingFooterAccount")}</h4>
              <button onClick={onNavigateToLogin}>{t("landingNavLogin")}</button>
              <button onClick={onNavigateToRegister}>{t("landingNavRegister")}</button>
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
