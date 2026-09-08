import { useTranslation } from "react-i18next";
import {
  useState,
} from "react";

import type {
  FormEvent,
} from "react";

import {
  Building2,
  KeyRound,
  LockKeyhole,
  Mail,
  Sparkles,
  UserRound,
} from "lucide-react";

import {
  confirmSignUp,
  login,
  provisionAccount,
  resendConfirmationCode,
  signUp,
} from "../services/auth";

import {
  saveSession,
} from "../services/authStorage";


interface LoginPageProps {
  onAuthenticated: () => void;
  initialMode?: AuthMode;
}


type AuthMode =
  | "login"
  | "register"
  | "confirm";


export default function LoginPage({
  onAuthenticated,
  initialMode,
}: LoginPageProps) {
  const { t } = useTranslation();
  const [
    mode,
    setMode,
  ] = useState<AuthMode>(
    initialMode || "login"
  );

  const [name, setName] =
    useState("");

  const [
    organizationName,
    setOrganizationName,
  ] = useState("");

  const [email, setEmail] =
    useState("");

  const [password, setPassword] =
    useState("");

  const [
    confirmationCode,
    setConfirmationCode,
  ] = useState("");

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState("");

  const [message, setMessage] =
    useState("");


  function clearFeedback() {
    setError("");
    setMessage("");
  }


  function changeMode(
    nextMode: AuthMode,
  ) {
    clearFeedback();
    setMode(nextMode);
  }


  async function handleLogin(
    event: FormEvent,
  ) {
    event.preventDefault();

    try {
      setLoading(true);
      clearFeedback();

      const result =
        await login(
          email.trim().toLowerCase(),
          password,
        );

      saveSession(
        result.AccessToken,
        result.IdToken,
        result.RefreshToken,
      );

      onAuthenticated();

    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : t("loginI18nLoginError"),
      );

    } finally {
      setLoading(false);
    }
  }


  async function handleRegister(
    event: FormEvent,
  ) {
    event.preventDefault();

    const cleanName =
      name.trim();

    const cleanOrganization =
      organizationName.trim();

    const cleanEmail =
      email.trim().toLowerCase();

    if (!cleanName) {
      setError(
        t("loginI18nNameRequired")
      );
      return;
    }

    if (!cleanOrganization) {
      setError(
        t("loginI18nOrganizationRequired")
      );
      return;
    }

    try {
      setLoading(true);
      clearFeedback();

      await signUp(
        cleanName,
        cleanEmail,
        password,
      );

      setMode("confirm");

      setMessage(
        t("loginI18nVerificationSent", {
          email: cleanEmail,
        }),
      );

    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : t("loginI18nCreateError"),
      );

    } finally {
      setLoading(false);
    }
  }


  async function finishRegistration() {
    const cleanEmail =
      email.trim().toLowerCase();

    const cleanName =
      name.trim();

    const cleanOrganization =
      organizationName.trim();

    const result =
      await login(
        cleanEmail,
        password,
      );

    await provisionAccount(
      result.AccessToken,
      cleanName,
      cleanOrganization,
    );

    saveSession(
      result.AccessToken,
      result.IdToken,
      result.RefreshToken,
    );

    onAuthenticated();
  }


  async function handleConfirm(
    event: FormEvent,
  ) {
    event.preventDefault();

    try {
      setLoading(true);
      clearFeedback();

      try {
        await confirmSignUp(
          email.trim().toLowerCase(),
          confirmationCode.trim(),
        );
      } catch (err) {
        const text =
          err instanceof Error
            ? err.message
            : "";

        /*
         * Permite reintentar el aprovisionamiento
         * si Cognito ya confirmó la cuenta pero
         * falló la llamada posterior al backend.
         */
        if (
          !text
            .toLowerCase()
            .includes("confirmed")
        ) {
          throw err;
        }
      }

      await finishRegistration();

    } catch (err) {
      setError(
        err instanceof Error
          ? (
              err.message === "ACCOUNT_PROVISION_FAILED"
                ? t("loginI18nProvisionError")
                : err.message
            )
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

      await resendConfirmationCode(
        email.trim().toLowerCase(),
      );

      setMessage(
        t("loginI18nCodeResent"),
      );

    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : t("loginI18nResendError"),
      );

    } finally {
      setLoading(false);
    }
  }


  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <div className="brand-mark">
            <Sparkles size={22} />
          </div>

          <div>
            <div className="brand-name">
              DIAGLOB
            </div>

            <div className="brand-version">
              AI COMMERCE
            </div>
          </div>
        </div>


        {mode === "login" && (
          <>
            <div className="login-copy">
              <h1>
                Bienvenido
              </h1>

              <p>
                {t("loginI18nSubtitle")}
              </p>
            </div>

            <form
              className="login-form"
              onSubmit={handleLogin}
            >
              <label>
                {t("loginI18nEmail")}

                <div className="login-input">
                  <Mail size={18} />

                  <input
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(event) =>
                      setEmail(
                        event.target.value
                      )
                    }
                    required
                  />
                </div>
              </label>

              <label>
                {t("loginI18nPassword")}

                <div className="login-input">
                  <LockKeyhole
                    size={18}
                  />

                  <input
                    type="password"
                    autoComplete=
                      "current-password"
                    value={password}
                    onChange={(event) =>
                      setPassword(
                        event.target.value
                      )
                    }
                    required
                  />
                </div>
              </label>

              {error && (
                <div className="login-error">
                  {error}
                </div>
              )}

              <button
                className="login-submit"
                type="submit"
                disabled={loading}
              >
                {loading
                  ? t("loginI18nSigningIn")
                  : t("loginI18nSignIn")}
              </button>

              <button
                type="button"
                className="auth-secondary-action"
                onClick={() =>
                  changeMode(
                    "register"
                  )
                }
              >
                {t("loginI18nCreateNewAccount")}
              </button>
            </form>
          </>
        )}


        {mode === "register" && (
          <>
            <div className="login-copy">
              <h1>
                {t("loginI18nCreateAccount")}
              </h1>

              <p>
                Crea tu espacio de trabajo
                en Diaglob.
              </p>
            </div>

            <form
              className="login-form"
              onSubmit={
                handleRegister
              }
            >
              <label>
                {t("loginI18nName")}

                <div className="login-input">
                  <UserRound
                    size={18}
                  />

                  <input
                    type="text"
                    autoComplete="name"
                    value={name}
                    onChange={(event) =>
                      setName(
                        event.target.value
                      )
                    }
                    required
                  />
                </div>
              </label>


              <label>
                Empresa

                <div className="login-input">
                  <Building2
                    size={18}
                  />

                  <input
                    type="text"
                    value={
                      organizationName
                    }
                    onChange={(event) =>
                      setOrganizationName(
                        event.target.value
                      )
                    }
                    placeholder={t("loginI18nOrganizationPlaceholder")}
                    required
                  />
                </div>
              </label>


              <label>
                {t("loginI18nEmail")}

                <div className="login-input">
                  <Mail size={18} />

                  <input
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(event) =>
                      setEmail(
                        event.target.value
                      )
                    }
                    required
                  />
                </div>
              </label>


              <label>
                {t("loginI18nPassword")}

                <div className="login-input">
                  <LockKeyhole
                    size={18}
                  />

                  <input
                    type="password"
                    autoComplete=
                      "new-password"
                    value={password}
                    onChange={(event) =>
                      setPassword(
                        event.target.value
                      )
                    }
                    minLength={8}
                    required
                  />
                </div>

                <small className="auth-hint">
                  {t("loginI18nPasswordHint")}
                </small>
              </label>


              {error && (
                <div className="login-error">
                  {error}
                </div>
              )}

              <button
                className="login-submit"
                type="submit"
                disabled={loading}
              >
                {loading
                  ? t("loginI18nCreating")
                  : t("loginI18nCreateAccount")}
              </button>

              <div className="auth-legal-links">
                <a href="/privacy" target="_blank" rel="noopener noreferrer">
                  {t("loginI18nPrivacy") || "Política de privacidad"}
                </a>
                <span>·</span>
                <a href="/terms" target="_blank" rel="noopener noreferrer">
                  {t("loginI18nTerms") || "Términos de servicio"}
                </a>
              </div>

              <button
                type="button"
                className="auth-secondary-action"
                onClick={() =>
                  changeMode("login")
                }
              >
                Ya tengo una cuenta
              </button>
            </form>
          </>
        )}


        {mode === "confirm" && (
          <>
            <div className="login-copy">
              <h1>
                {t("loginI18nConfirmEmailTitle")}
              </h1>

              <p>
                {t("loginI18nConfirmCodeHelp")}
                <strong>
                  {" "}
                  {email}
                </strong>.
              </p>
            </div>

            <form
              className="login-form"
              onSubmit={
                handleConfirm
              }
            >
              <label>
                Código de verificación

                <div className="login-input">
                  <KeyRound
                    size={18}
                  />

                  <input
                    type="text"
                    inputMode="numeric"
                    autoComplete=
                      "one-time-code"
                    value={
                      confirmationCode
                    }
                    onChange={(event) =>
                      setConfirmationCode(
                        event.target.value
                      )
                    }
                    placeholder="123456"
                    required
                  />
                </div>
              </label>


              {message && (
                <div className="auth-message">
                  {message}
                </div>
              )}

              {error && (
                <div className="login-error">
                  {error}
                </div>
              )}


              <button
                className="login-submit"
                type="submit"
                disabled={loading}
              >
                {loading
                  ? t("loginI18nConfirming")
                  : t("loginI18nConfirmAndEnter")}
              </button>


              <button
                type="button"
                className="auth-secondary-action"
                onClick={
                  handleResend
                }
                disabled={loading}
              >
                Reenviar código
              </button>


              <button
                type="button"
                className="auth-secondary-action"
                onClick={() =>
                  changeMode("login")
                }
                disabled={loading}
              >
                Volver al inicio
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
