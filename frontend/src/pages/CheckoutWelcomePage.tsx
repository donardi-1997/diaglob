import { CheckCircle2 } from "lucide-react";
import { useTranslation } from "react-i18next";

export default function CheckoutWelcomePage() {
  const { i18n } = useTranslation();
  const language = i18n.resolvedLanguage || i18n.language;
  const copy = language.startsWith("pt")
    ? {
        title: "Obrigado pela sua compra",
        description: "Estamos confirmando sua assinatura. Seu plano será ativado após a confirmação segura de Paddle.",
        action: "Ir para o aplicativo",
      }
    : language.startsWith("en")
      ? {
          title: "Thanks for your purchase",
          description: "We are confirming your subscription. Your plan will activate after Paddle confirms it securely.",
          action: "Go to the app",
        }
      : {
          title: "Gracias por tu compra",
          description: "Estamos confirmando tu suscripción. Tu plan se activará cuando Paddle la confirme de forma segura.",
          action: "Ir a la aplicación",
        };

  return (
    <main className="content plans-page" aria-labelledby="checkout-welcome-title">
      <section className="page-heading">
        <div>
          <span className="eyebrow">DIAGLOB</span>
          <h1 id="checkout-welcome-title">
            <CheckCircle2 aria-hidden="true" size={25} /> {copy.title}
          </h1>
          <p>{copy.description}</p>
          <a className="plan-button" href="/app/plans">{copy.action}</a>
        </div>
      </section>
    </main>
  );
}
