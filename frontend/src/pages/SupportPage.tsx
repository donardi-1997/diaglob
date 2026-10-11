import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Mail, ArrowLeft, LifeBuoy, ShieldCheck, CreditCard, Store } from "lucide-react";

type Language = "es" | "en" | "pt-BR";

const copy: Record<Language, {
  title: string;
  intro: string;
  general: string;
  billing: string;
  description: string;
  writeUs: string;
  include: string;
  shopifyTitle: string;
  shopifyBody: string;
  billingTitle: string;
  billingBody: string;
  privacyTitle: string;
  privacyBody: string;
  privacyLink: string;
  refundLink: string;
  back: string;
  caution: string;
}> = {
  es: {
    title: "Centro de ayuda de Diaglob",
    intro: "¿Necesitas ayuda con tu cuenta, una tienda conectada o un problema técnico? Escríbenos y cuéntanos qué ocurrió.",
    general: "Soporte general",
    billing: "Consultas de facturación",
    description: "Para problemas de acceso, errores e integraciones de tiendas.",
    writeUs: "Escribir al equipo de soporte",
    include: "Indica tu correo de cuenta, el nombre de tu organización, la tienda afectada (si aplica), los pasos para reproducir el problema y una captura sin datos sensibles.",
    shopifyTitle: "Conectar una tienda Shopify",
    shopifyBody: "Inicia sesión en Diaglob y utiliza la integración Shopify para autorizar la conexión. No envíes contraseñas, tokens ni códigos de acceso por correo.",
    billingTitle: "Planes, cargos o cancelaciones",
    billingBody: "Para una compra realizada dentro de Shopify, revisa primero los detalles de suscripción de Shopify. Si te suscribiste directamente a Diaglob, escribe al equipo de facturación e incluye el identificador del recibo (nunca datos de tarjeta).",
    privacyTitle: "Privacidad y datos",
    privacyBody: "Consulta nuestras políticas o contáctanos para plantear una solicitud de privacidad. Los plazos y posibles excepciones legales se rigen por la política vigente.",
    privacyLink: "Política de privacidad",
    refundLink: "Política de reembolsos",
    back: "Volver a Diaglob",
    caution: "No incluyas contraseñas, claves de API, números completos de tarjeta ni datos personales de clientes en tu solicitud.",
  },
  en: {
    title: "DIAGLOB Support Center",
    intro: "Need help with your account, connected store, or a technical issue? Contact us and describe what happened.",
    general: "General support",
    billing: "Billing inquiries",
    description: "For account access, errors, and store integrations.",
    writeUs: "Email our support team",
    include: "Include your account email, organization name, affected store (if applicable), steps to reproduce the issue, and a screenshot without sensitive information.",
    shopifyTitle: "Connect a Shopify store",
    shopifyBody: "Sign in to DIAGLOB and use the Shopify integration to authorize the connection. Never email passwords, tokens, or access codes.",
    billingTitle: "Plans, charges, or cancellation",
    billingBody: "For subscriptions purchased through Shopify, start with the subscription details in Shopify. For direct DIAGLOB purchases, contact the billing team with a receipt reference, never credit card information.",
    privacyTitle: "Privacy and data",
    privacyBody: "Read our policies or contact us with a privacy-related request. Applicable response periods and any lawful exceptions are governed by our current privacy policy.",
    privacyLink: "Privacy policy",
    refundLink: "Refund policy",
    back: "Back to DIAGLOB",
    caution: "Do not send passwords, API keys, full payment-card numbers, or customers' personal information in support requests.",
  },
  "pt-BR": {
    title: "Central de ajuda da Diaglob",
    intro: "Precisa de ajuda com sua conta, loja conectada ou um problema técnico? Entre em contato e descreva o ocorrido.",
    general: "Suporte geral",
    billing: "Questões de faturamento",
    description: "Para acesso à conta, erros e integrações de lojas.",
    writeUs: "Enviar e-mail ao suporte",
    include: "Informe o e-mail da conta, nome da organização, loja afetada (se aplicável), etapas para reproduzir o problema e uma imagem sem dados sensíveis.",
    shopifyTitle: "Conectar uma loja Shopify",
    shopifyBody: "Acesse a Diaglob e use a integração Shopify para autorizar a conexão. Nunca envie senhas, tokens ou códigos de acesso por e-mail.",
    billingTitle: "Planos, cobranças ou cancelamentos",
    billingBody: "Para assinaturas feitas pela Shopify, consulte primeiro os detalhes na Shopify. Para compras diretas na Diaglob, contate faturamento com a referência do recibo, nunca os dados do cartão.",
    privacyTitle: "Privacidade e dados",
    privacyBody: "Consulte nossas políticas ou entre em contato com uma solicitação sobre privacidade. Os prazos e exceções legais seguem a política vigente.",
    privacyLink: "Política de privacidade",
    refundLink: "Política de reembolso",
    back: "Voltar à Diaglob",
    caution: "Não envie senhas, chaves de API, números completos de cartão ou dados pessoais de clientes na solicitação.",
  },
};

function resolveLanguage(language: string): Language {
  if (language.toLowerCase().startsWith("en")) return "en";
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  return "es";
}

export default function SupportPage() {
  const { i18n } = useTranslation();
  const language = resolveLanguage(i18n.resolvedLanguage || i18n.language);
  const t = copy[language];

  useEffect(() => {
    document.title = `${t.title} | Diaglob`;
    let description = document.head.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (!description) {
      description = document.createElement("meta");
      description.name = "description";
      document.head.appendChild(description);
    }
    description.content = t.intro;
    let canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!canonical) {
      canonical = document.createElement("link");
      canonical.rel = "canonical";
      document.head.appendChild(canonical);
    }
    canonical.href = "https://diaglob.tech/support";
  }, [t]);

  return (
    <div className="landing-page legal-page">
      <header className="landing-navbar">
        <div className="landing-container">
          <div className="landing-navbar-inner">
            <Link className="landing-brand" to="/" aria-label="Diaglob home">
              <span className="marketing-brand-mark"><img src="/brand/diaglob-mark.svg" alt="" width={32} height={32} /></span>
              <span className="brand-name">DIAGLOB</span>
            </Link>
            <div className="landing-controls" aria-label="Language">
              {(["es", "en", "pt-BR"] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  className={language === value ? "active" : ""}
                  onClick={() => void i18n.changeLanguage(value)}
                  aria-pressed={language === value}
                  style={{ padding: "8px 12px" }}
                >
                  {value === "pt-BR" ? "PT" : value.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>
      <main className="legal-main" id="main">
        <article className="legal-document">
          <div className="legal-intro">
            <span className="landing-hero-eyebrow"><LifeBuoy size={18} aria-hidden="true" /> DIAGLOB</span>
            <h1>{t.title}</h1>
            <p className="legal-lede">{t.intro}</p>
          </div>
          <div className="legal-sections">
            <section className="legal-section">
              <h2><Mail size={20} aria-hidden="true" /> {t.general}</h2>
              <p>{t.description}</p>
              <p><a href="mailto:support@diaglob.tech?subject=DIAGLOB%20Support">support@diaglob.tech</a></p>
              <p><a href="mailto:support@diaglob.tech?subject=DIAGLOB%20Support">{t.writeUs}</a></p>
              <p>{t.include}</p>
            </section>
            <section className="legal-section">
              <h2><Store size={20} aria-hidden="true" /> {t.shopifyTitle}</h2>
              <p>{t.shopifyBody}</p>
            </section>
            <section className="legal-section">
              <h2><CreditCard size={20} aria-hidden="true" /> {t.billingTitle}</h2>
              <p>{t.billingBody}</p>
              <p><a href="mailto:billing@diaglob.tech?subject=DIAGLOB%20Billing">{t.billing}: billing@diaglob.tech</a></p>
              <p><Link to="/refund-policy">{t.refundLink}</Link></p>
            </section>
            <section className="legal-section">
              <h2><ShieldCheck size={20} aria-hidden="true" /> {t.privacyTitle}</h2>
              <p>{t.privacyBody}</p>
              <p><Link to="/privacy">{t.privacyLink}</Link></p>
              <p><strong>{t.caution}</strong></p>
            </section>
            <section className="legal-section">
              <p><Link to="/"><ArrowLeft size={16} aria-hidden="true" /> {t.back}</Link></p>
              <p><Link to="/terms">Terms / Términos</Link></p>
            </section>
          </div>
        </article>
      </main>
    </div>
  );
}
