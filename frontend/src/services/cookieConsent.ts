export const COOKIE_CONSENT_STORAGE_KEY = "diaglob-cookie-consent-v1";
export const COOKIE_CONSENT_EVENT = "diaglob:cookie-consent-changed";
export const COOKIE_CONSENT_VERSION = 1;

export interface CookieConsentPreferences {
  version: number;
  necessary: true;
  advertising: boolean;
  decidedAt: string;
}

function canUseStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function getCookieConsent(): CookieConsentPreferences | null {
  if (!canUseStorage()) return null;

  const raw = window.localStorage.getItem(COOKIE_CONSENT_STORAGE_KEY);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as Partial<CookieConsentPreferences>;
    if (
      parsed.version !== COOKIE_CONSENT_VERSION
      || typeof parsed.advertising !== "boolean"
      || typeof parsed.decidedAt !== "string"
    ) {
      return null;
    }

    return {
      version: COOKIE_CONSENT_VERSION,
      necessary: true,
      advertising: parsed.advertising,
      decidedAt: parsed.decidedAt,
    };
  } catch {
    return null;
  }
}

export function hasAdvertisingConsent() {
  return getCookieConsent()?.advertising === true;
}

export function saveCookieConsent(advertising: boolean): CookieConsentPreferences {
  const preferences: CookieConsentPreferences = {
    version: COOKIE_CONSENT_VERSION,
    necessary: true,
    advertising,
    decidedAt: new Date().toISOString(),
  };

  if (canUseStorage()) {
    window.localStorage.setItem(COOKIE_CONSENT_STORAGE_KEY, JSON.stringify(preferences));
    window.dispatchEvent(
      new CustomEvent<CookieConsentPreferences>(COOKIE_CONSENT_EVENT, {
        detail: preferences,
      }),
    );
  }

  return preferences;
}
