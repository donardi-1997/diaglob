import { useMemo, useState } from "react";
import { Cookie, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  getCookieConsent,
  saveCookieConsent,
  type CookieConsentPreferences,
} from "../services/cookieConsent";
import "./CookieConsent.css";

const copy = {
  es: {
    title: "Tu privacidad en Diaglob",
    body: "Usamos almacenamiento necesario para que Diaglob funcione. Con tu permiso, también podemos usar Meta Pixel y TikTok Pixel para medir campañas, atribuir registros y mejorar nuestra publicidad.",
    necessaryOnly: "Solo necesarias",
    acceptAll: "Aceptar todas",
    customize: "Personalizar",
    settings: "Cookies",
    modalTitle: "Preferencias de cookies",
    modalBody: "Puedes cambiar esta decisión cuando quieras. Las cookies y señales publicitarias permanecen desactivadas hasta que las autorices.",
    necessaryTitle: "Necesarias",
    necessaryDescription: "Sesión, seguridad, idioma, tema y almacenamiento de tu elección de privacidad. No se pueden desactivar.",
    advertisingTitle: "Publicidad y medición",
    advertisingDescription: "Permite Meta Pixel y TikTok Pixel para medir visitas, campañas y conversiones como registros. Puede incluir identificadores de campaña, datos técnicos del navegador y cookies publicitarias.",
    alwaysOn: "Siempre activas",
    save: "Guardar preferencias",
    privacy: "Ver Política de privacidad",
  },
  en: {
    title: "Your privacy at Diaglob",
    body: "We use necessary storage so Diaglob can work. With your permission, we may also use Meta Pixel and TikTok Pixel to measure campaigns, attribute sign-ups, and improve our advertising.",
    necessaryOnly: "Necessary only",
    acceptAll: "Accept all",
    customize: "Customize",
    settings: "Cookies",
    modalTitle: "Cookie preferences",
    modalBody: "You can change this decision at any time. Advertising cookies and signals remain disabled until you authorize them.",
    necessaryTitle: "Necessary",
    necessaryDescription: "Session, security, language, theme, and storage of your privacy choice. These cannot be disabled.",
    advertisingTitle: "Advertising and measurement",
    advertisingDescription: "Allows Meta Pixel and TikTok Pixel to measure visits, campaigns, and conversions such as sign-ups. This may include campaign identifiers, browser technical data, and advertising cookies.",
    alwaysOn: "Always on",
    save: "Save preferences",
    privacy: "View Privacy Policy",
  },
  "pt-BR": {
    title: "Sua privacidade no Diaglob",
    body: "Usamos armazenamento necessário para o funcionamento do Diaglob. Com sua permissão, também podemos usar Meta Pixel e TikTok Pixel para medir campanhas, atribuir cadastros e melhorar nossa publicidade.",
    necessaryOnly: "Somente necessárias",
    acceptAll: "Aceitar todas",
    customize: "Personalizar",
    settings: "Cookies",
    modalTitle: "Preferências de cookies",
    modalBody: "Você pode alterar esta decisão a qualquer momento. Cookies e sinais publicitários permanecem desativados até que você os autorize.",
    necessaryTitle: "Necessárias",
    necessaryDescription: "Sessão, segurança, idioma, tema e armazenamento da sua escolha de privacidade. Não podem ser desativadas.",
    advertisingTitle: "Publicidade e medição",
    advertisingDescription: "Permite Meta Pixel e TikTok Pixel para medir visitas, campanhas e conversões como cadastros. Pode incluir identificadores de campanha, dados técnicos do navegador e cookies publicitários.",
    alwaysOn: "Sempre ativas",
    save: "Salvar preferências",
    privacy: "Ver Política de Privacidade",
  },
} as const;

export default function CookieConsent() {
  const { i18n } = useTranslation();
  const locale = i18n.language.startsWith("pt") ? "pt-BR" : i18n.language.startsWith("en") ? "en" : "es";
  const labels = copy[locale];

  const initialConsent = useMemo(() => getCookieConsent(), []);
  const [consent, setConsent] = useState<CookieConsentPreferences | null>(initialConsent);
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [advertising, setAdvertising] = useState(initialConsent?.advertising ?? false);

  const persist = (allowAdvertising: boolean) => {
    const saved = saveCookieConsent(allowAdvertising);
    setConsent(saved);
    setAdvertising(saved.advertising);
    setPreferencesOpen(false);
  };

  const openPreferences = () => {
    setAdvertising(consent?.advertising ?? false);
    setPreferencesOpen(true);
  };

  return (
    <>
      {!consent && !preferencesOpen && (
        <aside className="cookie-consent-banner" role="dialog" aria-labelledby="cookie-consent-title">
          <div className="cookie-consent-icon" aria-hidden="true"><Cookie size={22} /></div>
          <div className="cookie-consent-copy">
            <strong id="cookie-consent-title">{labels.title}</strong>
            <p>{labels.body} <a href="/privacy">{labels.privacy}</a>.</p>
          </div>
          <div className="cookie-consent-actions">
            <button className="cookie-button secondary" type="button" onClick={() => persist(false)}>
              {labels.necessaryOnly}
            </button>
            <button className="cookie-button secondary" type="button" onClick={openPreferences}>
              <SlidersHorizontal size={16} />{labels.customize}
            </button>
            <button className="cookie-button primary" type="button" onClick={() => persist(true)}>
              {labels.acceptAll}
            </button>
          </div>
        </aside>
      )}

      {consent && !preferencesOpen && (
        <button className="cookie-settings-trigger" type="button" onClick={openPreferences}>
          <Cookie size={15} />{labels.settings}
        </button>
      )}

      {preferencesOpen && (
        <div className="cookie-preferences-backdrop" role="presentation">
          <section className="cookie-preferences" role="dialog" aria-modal="true" aria-labelledby="cookie-preferences-title">
            <div className="cookie-preferences-heading">
              <div className="cookie-consent-icon" aria-hidden="true"><ShieldCheck size={22} /></div>
              <div>
                <h2 id="cookie-preferences-title">{labels.modalTitle}</h2>
                <p>{labels.modalBody}</p>
              </div>
            </div>

            <div className="cookie-category">
              <div>
                <strong>{labels.necessaryTitle}</strong>
                <p>{labels.necessaryDescription}</p>
              </div>
              <span className="cookie-required-badge">{labels.alwaysOn}</span>
            </div>

            <label className="cookie-category cookie-category-toggle">
              <div>
                <strong>{labels.advertisingTitle}</strong>
                <p>{labels.advertisingDescription}</p>
              </div>
              <input
                type="checkbox"
                checked={advertising}
                onChange={(event) => setAdvertising(event.target.checked)}
                aria-label={labels.advertisingTitle}
              />
            </label>

            <div className="cookie-preferences-footer">
              <a href="/privacy">{labels.privacy}</a>
              <button className="cookie-button primary" type="button" onClick={() => persist(advertising)}>
                {labels.save}
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
