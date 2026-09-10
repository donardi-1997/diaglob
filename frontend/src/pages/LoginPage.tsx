import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  BarChart3,
  Bot,
  Building2,
  Check,
  KeyRound,
  LockKeyhole,
  Mail,
  Moon,
  Sparkles,
  Sun,
  UserRound,
  Workflow,
} from "lucide-react";

import {
  confirmSignUp,
  login,
  provisionAccount,
  resendConfirmationCode,
  signUp,
} from "../services/auth";
import { saveSession } from "../services/authStorage";
import { getMarketingCopy, resolveMarketingLocale } from "../marketingCopy";
import "../onboarding-activation-polish.css";

interface LoginPageProps {
  onAuthenticated: () => void;
  initialMode?: AuthMode;
  onNavigateHome?: () => void;
}

type AuthMode = "login" | "register" | "confirm";

export default function LoginPage({
  onAuthenticated,
  initialMode,
  onNavigateHome = () => window.location.assign("/"),
}: LoginPageProps) {
  const { t, i18n } = useTranslation();
  const copy = useMemo(() => getMarketingCopy(i18n.language), [i18n.language]);
  const locale = resolveMarketingLocale(i18n.language);
  const legalCopy = useMemo(() => {
    if (locale === "en") {
      return {
        prefix: "I agree to the",
        terms: "Terms of Service",
        join: "and the",
        privacy: "Privacy Policy",
        required: "You must accept the Terms of Service and Privacy Policy to create your account.",
        refunds: "Refund policy",
      };
    }
    if (locale === "pt-BR") {
      return {
        prefix: "Aceito os",
        terms: "Termos de Serviço",
        join: "e a",
        privacy: "Política de Privacidade",
        required: "Você precisa aceitar os Termos de Serviço e a Política de Privacidade para criar sua conta.",
        refunds: "Política de reembolso",
      };
    }
    return {
      prefix: "Acepto los",
      terms: "Términos de servicio",
      join: "y la",
      privacy: "Política de privacidad",
      required: "Debes aceptar los Términos de servicio y la Política de privacidad para crear tu cuenta.",
      refunds: "Política de reembolsos",
    };
  }, [locale]);

  const [mode, setMode] = useState<AuthMode>(initialMode || "login");
  const [name, setName] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmationCode, setConfirmationCode] = useState("");
  const [acceptedLegal, setAcceptedLegal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [theme, setTheme] = useState(() => localStorage.getItem("diaglob-theme") || "dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("diaglob-theme", theme);
  }, [theme]);

  useEffect(() => {
    document.title =
      mode === "register"
        ? "Diaglob — Create your workspace"
        : mode === "confirm"
          ? "Diaglob — Confirm your account"
          : "Diaglob — Sign in";
  }, [mode]);

  function clearFeedback() {
    setError("");
    setMessage("");
  }

  function changeMode(nextMode: AuthMode) {
    clearFeedback();
    setMode(nextMode);
  }

  function changeLanguage(language: string) {
    void i18n.changeLanguage(language);
    localStorage.setItem("diaglob-language", language);
  }

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    try {
      setLoading(true);
      clearFeedback();
      const result = await login(email.trim().toLowerCase(), password);
      saveSession(result.AccessToken, result.IdToken, result.RefreshToken);
      onAuthenticated();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("loginI18nLoginError"));
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(event: FormEvent) {
    event.preventDefault();
    const cleanName = name.trim();
    const cleanOrganization = organizationName.trim();
    const cleanEmail = email.trim().toLowerCase();

    if (!cleanName) {
      setError(t("loginI18nNameRequired"));
      return;
    }
    if (!cleanOrganization) {
      setError(t("loginI18nOrganizationRequired"));
      return;
    }
    if (!acceptedLegal) {
      setError(legalCopy.required);
      return;
    }

    try {
      setLoading(true);
      clearFeedback();
      await signUp(cleanName, cleanEmail, password);
      setMode("confirm");
      setMessage(t("loginI18nVerificationSent", { email: cleanEmail }));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("loginI18nCreateError"));
    } finally {
      setLoading(false);
    }
  }

  async function finishRegistration() {
    const cleanEmail = email.trim().toLowerCase();
    const cleanName = name.trim();
    const cleanOrganization = organizationName.trim();
    const result = await login(cleanEmail, password);
    await provisionAccount(result.AccessToken, cleanName, cleanOrganization);
    saveSession(result.AccessToken, result.IdToken, result.RefreshToken);
    onAuthenticated();
  }

  async function handleConfirm(event: FormEvent) {
    event.preventDefault();
    try {
      setLoading(true);
      clearFeedback();
      try {
        await confirmSignUp(email.trim().toLowerCase(), confirmationCode.trim());
      } catch (err) {
        const text = err instanceof Error ? err.message : "";
        if (!text.toLowerCase().includes("confirmed")) throw err;
      }
      await finishRegistration();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message === "ACCOUNT_PROVISION_FAILED"
            ? t("loginI18nProvisionError")
            : err.message
          : t("loginI18nConfirmError"),
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    try {
      setLoading(true);
      clearFeedback();
      await resendConfirmationCode(email.trim().toLowerCase());
      setMessage(t("loginI18nCodeResent"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("loginI18nResendError"));
    } finally {
      setLoading(false);
    }
  }

  const isLogin = mode === "login";
  const authHeadline = isLogin ? copy.auth.loginTitle : copy.auth.registerTitle;
  const authSubtitle = isLogin ? copy.auth.loginSubtitle : copy.auth.registerSubtitle;
  const authEyebrow = isLogin ? copy.auth.loginEyebrow : copy.auth.registerEyebrow;
  const proofIcons = [Bot, Workflow, BarChart3, Building2];
  const footerLabels =
    locale === "en"
      ? ["Secure workspace", "Multi-store", "AI + Analytics"]
      : locale === "pt-BR"
        ? ["Workspace seguro", "Multi-loja", "IA + Analytics"]
        : ["Workspace seguro", "Multi-tienda", "IA + Analítica"];

  return (
    <div className="marketing-auth-page">
      <section className="marketing-auth-story">
        <div className="marketing-auth-orb auth-orb-one" />
        <div className="marketing-auth-orb auth-orb-two" />
        <div className="marketing-auth-story-inner">
          <button className="marketing-brand auth-brand" onClick={onNavigateHome} type="button">
            <span className="marketing-brand-mark"><Sparkles size={19} /></span>
            <span className="marketing-brand-copy"><strong>DIAGLOB</strong><small>AI COMMERCE OS</small></span>
          </button>

          <div className="marketing-auth-story-copy">
            <span className="marketing-kicker light">{authEyebrow}</span>
            <h1>{authHeadline}</h1>
            <p>{authSubtitle}</p>
          </div>

          <div className="marketing-auth-proof">
            <span className="marketing-auth-proof-title">{copy.auth.proofTitle}</span>
            {copy.auth.proofItems.map((item, index) => {
              const Icon = proofIcons[index];
              return (
                <div key={item} className="marketing-auth-proof-item">
                  <span><Icon size={17} /></span>
                  <p>{item}</p>
                  <Check size={16} />
                </div>
              );
            })}
          </div>

          <div className="marketing-auth-story-footer">
            <span><i />{footerLabels[0]}</span>
            <span>{footerLabels[1]}</span>
            <span>{footerLabels[2]}</span>
          </div>
        </div>
      </section>

      <section className="marketing-auth-form-side">
        <div className="marketing-auth-topbar">
          <button type="button" className="marketing-auth-back" onClick={onNavigateHome}>
            <ArrowLeft size={16} />{copy.auth.backToProduct}
          </button>
          <div className="marketing-auth-controls">
            <div className="marketing-language compact-language">
              {(["es", "en", "pt-BR"] as const).map((language) => (
                <button
                  key={language}
                  className={locale === language ? "active" : ""}
                  onClick={() => changeLanguage(language)}
                  type="button"
                >
                  {language === "pt-BR" ? "PT" : language.toUpperCase()}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="marketing-icon-button"
              onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")}
              aria-label={theme === "dark" ? "Light mode" : "Dark mode"}
            >
              {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </div>

        <div className="marketing-auth-card">
          <div className="marketing-auth-mobile-brand">
            <span className="marketing-brand-mark"><Sparkles size={18} /></span>
            <strong>DIAGLOB</strong>
          </div>

          {mode === "login" && (
            <>
              <div className="marketing-auth-heading">
                <span>{copy.auth.loginEyebrow}</span>
                <h2>{t("loginI18nSignIn")}</h2>
                <p>{t("loginI18nSubtitle")}</p>
              </div>
              <form className="marketing-auth-form" onSubmit={handleLogin}>
                <label>
                  <span>{t("loginI18nEmail")}</span>
                  <div className="marketing-auth-input"><Mail size={18} /><input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></div>
                </label>
                <label>
                  <span>{t("loginI18nPassword")}</span>
                  <div className="marketing-auth-input"><LockKeyhole size={18} /><input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></div>
                </label>
                {error && <div className="marketing-auth-error">{error}</div>}
                <button className="marketing-primary-button auth-submit" type="submit" disabled={loading}>
                  {loading ? t("loginI18nSigningIn") : t("loginI18nSignIn")}
                </button>
                <div className="marketing-auth-switch">
                  <span>{locale === "en" ? "New to Diaglob?" : locale === "pt-BR" ? "Novo no Diaglob?" : "¿Nuevo en Diaglob?"}</span>
                  <button type="button" onClick={() => changeMode("register")}>{t("loginI18nCreateNewAccount")}</button>
                </div>
              </form>
            </>
          )}

          {mode === "register" && (
            <>
              <div className="marketing-auth-heading">
                <span>{copy.auth.registerEyebrow}</span>
                <h2>{t("loginI18nCreateAccount")}</h2>
                <p>{copy.auth.registerSubtitle}</p>
              </div>
              <form className="marketing-auth-form" onSubmit={handleRegister}>
                <div className="marketing-auth-field-grid">
                  <label>
                    <span>{t("loginI18nName")}</span>
                    <div className="marketing-auth-input"><UserRound size={18} /><input type="text" autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} required /></div>
                  </label>
                  <label>
                    <span>{locale === "en" ? "Company" : "Empresa"}</span>
                    <div className="marketing-auth-input"><Building2 size={18} /><input type="text" value={organizationName} onChange={(event) => setOrganizationName(event.target.value)} placeholder={t("loginI18nOrganizationPlaceholder")} required /></div>
                  </label>
                </div>
                <label>
                  <span>{t("loginI18nEmail")}</span>
                  <div className="marketing-auth-input"><Mail size={18} /><input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></div>
                </label>
                <label>
                  <span>{t("loginI18nPassword")}</span>
                  <div className="marketing-auth-input"><LockKeyhole size={18} /><input type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={8} required /></div>
                  <small>{t("loginI18nPasswordHint")}</small>
                </label>
                <label className="marketing-auth-consent">
                  <input
                    type="checkbox"
                    checked={acceptedLegal}
                    onChange={(event) => setAcceptedLegal(event.target.checked)}
                    required
                  />
                  <span>
                    {legalCopy.prefix}{" "}
                    <a href="/terms" target="_blank" rel="noopener noreferrer">{legalCopy.terms}</a>{" "}
                    {legalCopy.join}{" "}
                    <a href="/privacy" target="_blank" rel="noopener noreferrer">{legalCopy.privacy}</a>.
                  </span>
                </label>
                {error && <div className="marketing-auth-error">{error}</div>}
                <button className="marketing-primary-button auth-submit" type="submit" disabled={loading}>
                  {loading ? t("loginI18nCreating") : t("loginI18nCreateAccount")}
                </button>
                <div className="marketing-auth-refund-link">
                  <a href="/refund-policy" target="_blank" rel="noopener noreferrer">{legalCopy.refunds}</a>
                </div>
                <div className="marketing-auth-switch">
                  <span>{locale === "en" ? "Already have an account?" : locale === "pt-BR" ? "Já tem uma conta?" : "¿Ya tienes una cuenta?"}</span>
                  <button type="button" onClick={() => changeMode("login")}>{copy.nav.login}</button>
                </div>
              </form>
            </>
          )}

          {mode === "confirm" && (
            <>
              <div className="marketing-auth-heading">
                <span>{copy.auth.registerEyebrow}</span>
                <h2>{t("loginI18nConfirmEmailTitle")}</h2>
                <p>{t("loginI18nConfirmCodeHelp")} <strong>{email}</strong>.</p>
              </div>
              <form className="marketing-auth-form" onSubmit={handleConfirm}>
                <label>
                  <span>{locale === "en" ? "Verification code" : locale === "pt-BR" ? "Código de verificação" : "Código de verificación"}</span>
                  <div className="marketing-auth-input verification"><KeyRound size={18} /><input type="text" inputMode="numeric" autoComplete="one-time-code" value={confirmationCode} onChange={(event) => setConfirmationCode(event.target.value)} placeholder="123456" required /></div>
                </label>
                {message && <div className="marketing-auth-message">{message}</div>}
                {error && <div className="marketing-auth-error">{error}</div>}
                <button className="marketing-primary-button auth-submit" type="submit" disabled={loading}>
                  {loading ? t("loginI18nConfirming") : t("loginI18nConfirmAndEnter")}
                </button>
                <div className="marketing-auth-secondary-actions">
                  <button type="button" onClick={handleResend} disabled={loading}>{locale === "en" ? "Resend code" : locale === "pt-BR" ? "Reenviar código" : "Reenviar código"}</button>
                  <button type="button" onClick={() => changeMode("login")} disabled={loading}>{locale === "en" ? "Back to login" : locale === "pt-BR" ? "Voltar ao login" : "Volver al inicio"}</button>
                </div>
              </form>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
