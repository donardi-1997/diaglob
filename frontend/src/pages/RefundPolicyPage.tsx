import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Moon, Sparkles, Sun } from "lucide-react";

type RefundLocale = "es" | "en" | "pt-BR";

const copy = {
  es: {
    eyebrow: "LEGAL",
    title: "Política de reembolsos",
    updated: "Última actualización: 10 de septiembre de 2026",
    intro: "Esta política explica cuándo una compra de Diaglob puede ser elegible para reembolso. Las solicitudes se evalúan caso por caso, respetando siempre los derechos obligatorios del consumidor aplicables.",
    sections: [
      ["1. Operador del servicio", ["Diaglob es una marca operada por Adrian Felipe Restrepo Guerra, persona natural con operación principal en Bogotá, Colombia."]],
      ["2. Solicitudes de reembolso", ["Las solicitudes de reembolso se evalúan caso por caso. Consideraremos circunstancias como cobros duplicados, errores de facturación, imposibilidad técnica material de prestar el servicio y otros hechos razonables documentados por el cliente.", "La existencia de esta revisión caso por caso no limita derechos de retracto, garantía, reembolso u otros derechos irrenunciables que puedan corresponder conforme a la ley aplicable."]],
      ["3. Suscripciones iniciales", ["Las solicitudes relacionadas con una primera contratación pueden ser evaluadas caso por caso. Para solicitar revisión, contáctanos tan pronto como sea razonablemente posible e incluye el correo de la cuenta, la fecha del cobro y una descripción del motivo."]],
      ["4. Renovaciones", ["Las renovaciones de suscripción ya cobradas no son reembolsables, salvo cuando lo exija la ley aplicable o exista un error de cobro, duplicidad u otra circunstancia excepcional que justifique una revisión."]],
      ["5. Cancelación", ["Cancelar una suscripción detiene renovaciones futuras. Salvo que se indique lo contrario o la ley exija otra cosa, mantendrás acceso a Diaglob hasta finalizar el período que ya pagaste."]],
      ["6. Paquetes extra de IA", ["Los paquetes adicionales de respuestas o créditos de IA pueden ser elegibles para reembolso únicamente mientras no se haya utilizado ninguna parte del paquete. Una vez consumido total o parcialmente, el paquete no es reembolsable, salvo obligación legal aplicable o error atribuible al cobro."]],
      ["7. Compras procesadas por Paddle", ["Paddle puede actuar como Merchant of Record para las compras de Diaglob. En esos casos, Paddle procesa el pago, impuestos, comprobantes y determinadas operaciones de reembolso conforme a sus sistemas y términos. Podemos pedir información necesaria para localizar la transacción y tramitar la solicitud con Paddle."]],
      ["8. Cómo solicitar un reembolso", ["Escribe a adrianguerra9703@gmail.com desde el correo asociado a tu cuenta. Incluye, cuando sea posible, tu nombre, organización, fecha del cobro, importe, identificador o comprobante de la transacción y el motivo de la solicitud."]],
      ["9. Plazo y método de devolución", ["Si se aprueba un reembolso, se tramitará mediante el proveedor de pagos y normalmente al método de pago original. El tiempo para que aparezca el dinero depende del proveedor, banco, red de tarjetas y país del cliente."]],
      ["10. Cambios a esta política", ["Podemos actualizar esta política para reflejar cambios legales, comerciales o del servicio. La versión vigente se publicará en esta página con su fecha de actualización."]],
      ["11. Ley aplicable y contacto", ["Esta política se interpreta conforme a las leyes de la República de Colombia, sin perjuicio de normas imperativas de protección al consumidor aplicables en otras jurisdicciones.", "Contacto: adrianguerra9703@gmail.com."]],
    ],
  },
  en: {
    eyebrow: "LEGAL",
    title: "Refund Policy",
    updated: "Last updated: September 10, 2026",
    intro: "This policy explains when a Diaglob purchase may be eligible for a refund. Requests are reviewed on a case-by-case basis, while always respecting mandatory consumer rights under applicable law.",
    sections: [
      ["1. Service operator", ["Diaglob is a brand operated by Adrian Felipe Restrepo Guerra, an individual based in Bogotá, Colombia."]],
      ["2. Refund requests", ["Refund requests are reviewed case by case. We may consider circumstances such as duplicate charges, billing errors, a material technical inability to provide the service, and other reasonable circumstances documented by the customer.", "This case-by-case review does not limit any mandatory withdrawal, warranty, refund, or other non-waivable consumer rights under applicable law."]],
      ["3. Initial subscriptions", ["Requests related to an initial subscription may be reviewed case by case. Contact us as soon as reasonably possible and include the account email, charge date, and a description of the reason for the request."]],
      ["4. Renewals", ["Subscription renewals that have already been charged are non-refundable, except where required by applicable law or where there is a billing error, duplicate charge, or another exceptional circumstance that warrants review."]],
      ["5. Cancellation", ["Canceling a subscription stops future renewals. Unless otherwise stated or required by law, you retain access to Diaglob until the end of the billing period you already paid for."]],
      ["6. Extra AI packages", ["Additional AI response or credit packages may be eligible for a refund only while no part of the package has been used. Once used in whole or in part, the package is non-refundable except where required by applicable law or in case of a billing error."]],
      ["7. Purchases processed by Paddle", ["Paddle may act as Merchant of Record for Diaglob purchases. In those cases, Paddle processes payment, taxes, receipts, and certain refund operations through its systems and terms. We may request information needed to locate the transaction and process the request with Paddle."]],
      ["8. How to request a refund", ["Email adrianguerra9703@gmail.com from the address associated with your account. Where possible, include your name, organization, charge date, amount, transaction identifier or receipt, and the reason for the request."]],
      ["9. Refund timing and method", ["If a refund is approved, it will be processed through the payment provider and normally returned to the original payment method. The time for funds to appear depends on the provider, bank, card network, and customer country."]],
      ["10. Changes to this policy", ["We may update this policy to reflect legal, commercial, or service changes. The current version will be published on this page with its last-updated date."]],
      ["11. Governing law and contact", ["This policy is interpreted under the laws of the Republic of Colombia, without limiting mandatory consumer-protection rules that may apply in other jurisdictions.", "Contact: adrianguerra9703@gmail.com."]],
    ],
  },
  "pt-BR": {
    eyebrow: "LEGAL",
    title: "Política de reembolso",
    updated: "Última atualização: 10 de setembro de 2026",
    intro: "Esta política explica quando uma compra do Diaglob pode ser elegível para reembolso. As solicitações são avaliadas caso a caso, respeitando sempre os direitos obrigatórios do consumidor aplicáveis.",
    sections: [
      ["1. Operador do serviço", ["Diaglob é uma marca operada por Adrian Felipe Restrepo Guerra, pessoa física com operação principal em Bogotá, Colômbia."]],
      ["2. Solicitações de reembolso", ["As solicitações são avaliadas caso a caso. Podemos considerar cobranças duplicadas, erros de faturamento, impossibilidade técnica material de prestar o serviço e outras circunstâncias razoáveis documentadas pelo cliente."]],
      ["3. Assinaturas iniciais", ["Solicitações relacionadas à primeira contratação podem ser avaliadas caso a caso. Entre em contato o quanto antes e informe o e-mail da conta, a data da cobrança e o motivo da solicitação."]],
      ["4. Renovações", ["Renovações de assinatura já cobradas não são reembolsáveis, salvo quando exigido pela legislação aplicável ou em caso de erro de cobrança, duplicidade ou outra circunstância excepcional."]],
      ["5. Cancelamento", ["O cancelamento interrompe renovações futuras. Salvo indicação diferente ou exigência legal, o acesso permanece disponível até o fim do período já pago."]],
      ["6. Pacotes extras de IA", ["Pacotes adicionais de respostas ou créditos de IA só podem ser elegíveis para reembolso enquanto nenhuma parte tiver sido utilizada. Após uso total ou parcial, não são reembolsáveis, salvo obrigação legal ou erro de cobrança."]],
      ["7. Compras processadas pela Paddle", ["A Paddle pode atuar como Merchant of Record nas compras do Diaglob, processando pagamentos, impostos, recibos e determinadas operações de reembolso conforme seus sistemas e termos."]],
      ["8. Como solicitar", ["Envie um e-mail para adrianguerra9703@gmail.com a partir do endereço associado à sua conta e informe, quando possível, nome, organização, data e valor da cobrança, comprovante ou identificador e o motivo da solicitação."]],
      ["9. Prazo e método", ["Se aprovado, o reembolso será processado pelo provedor de pagamentos e normalmente devolvido ao método de pagamento original. O prazo depende do provedor, banco, bandeira e país do cliente."]],
      ["10. Alterações", ["Podemos atualizar esta política para refletir mudanças legais, comerciais ou do serviço. A versão vigente será publicada nesta página."]],
      ["11. Lei aplicável e contato", ["Esta política é interpretada conforme as leis da República da Colômbia, sem limitar normas obrigatórias de proteção ao consumidor aplicáveis em outras jurisdições.", "Contato: adrianguerra9703@gmail.com."]],
    ],
  },
} as const;

export default function RefundPolicyPage() {
  const { i18n } = useTranslation();
  const locale: RefundLocale = i18n.language.toLowerCase().startsWith("en")
    ? "en"
    : i18n.language.toLowerCase().startsWith("pt")
      ? "pt-BR"
      : "es";
  const documentContent = useMemo(() => copy[locale], [locale]);
  const [theme, setTheme] = useState(localStorage.getItem("diaglob-theme") || "dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("diaglob-theme", theme);
  }, [theme]);

  useEffect(() => {
    document.title = `${documentContent.title} | Diaglob`;
    let meta = document.head.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (!meta) {
      meta = document.createElement("meta");
      meta.name = "description";
      document.head.appendChild(meta);
    }
    meta.content = documentContent.intro;

    let canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!canonical) {
      canonical = document.createElement("link");
      canonical.rel = "canonical";
      document.head.appendChild(canonical);
    }
    canonical.href = "https://diaglob.tech/refund-policy";
  }, [documentContent]);

  const changeLanguage = (language: RefundLocale) => {
    void i18n.changeLanguage(language);
    localStorage.setItem("diaglob-language", language);
  };

  return (
    <div className="landing-page legal-page">
      <header className="landing-navbar">
        <div className="landing-container">
<div className="landing-navbar-inner">
  <Link className="landing-brand" to="/" aria-label="Diaglob home">
    <div className="brand-mark"><Sparkles size={20} /></div>
    <div><div className="brand-name">DIAGLOB</div><div className="brand-version">AI COMMERCE</div></div>
  </Link>
  <div className="landing-controls">
    <div className="landing-lang-switch" aria-label="Language">
      <button className={locale === "es" ? "active" : ""} onClick={() => changeLanguage("es")}>ES</button>
      <button className={locale === "en" ? "active" : ""} onClick={() => changeLanguage("en")}>EN</button>
      <button className={locale === "pt-BR" ? "active" : ""} onClick={() => changeLanguage("pt-BR")}>PT-BR</button>
    </div>
    <button className="theme-toggle" onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")} aria-label="Toggle theme">
      {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  </div>
</div>
        </div>
      </header>
      <main className="legal-main">
        <article className="legal-document">
<div className="legal-intro">
  <span className="landing-hero-eyebrow">{documentContent.eyebrow}</span>
  <h1>{documentContent.title}</h1>
  <p className="legal-updated">{documentContent.updated}</p>
  <p className="legal-lede">{documentContent.intro}</p>
</div>
<div className="legal-sections">
  {documentContent.sections.map(([title, paragraphs]) => (
    <section key={title} className="legal-section">
      <h2>{title}</h2>
      {paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
    </section>
  ))}
</div>
        </article>
      </main>
    </div>
  );
}
