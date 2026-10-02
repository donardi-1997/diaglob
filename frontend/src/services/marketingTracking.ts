import {
  COOKIE_CONSENT_EVENT,
  hasAdvertisingConsent,
  type CookieConsentPreferences,
} from "./cookieConsent";

export type MarketingEventName =
  | "landing_view"
  | "registration_started"
  | "registration_submitted"
  | "complete_registration"
  | "pricing_plan_interest";

export interface MarketingAttribution {
  source?: string;
  medium?: string;
  campaign?: string;
  content?: string;
  term?: string;
  fbclid?: string;
  ttclid?: string;
  landingPath: string;
  capturedAt: string;
}

type MarketingEventParams = Record<string, string | number | boolean | undefined>;

const FIRST_TOUCH_KEY = "diaglob-marketing-first-touch";
const LAST_TOUCH_KEY = "diaglob-marketing-last-touch";
const META_PIXEL_ID = import.meta.env.VITE_META_PIXEL_ID?.trim();
const TIKTOK_PIXEL_ID = import.meta.env.VITE_TIKTOK_PIXEL_ID?.trim();

let advertisingTrackingActive = false;
let consentListenerRegistered = false;

type Fbq = {
  (...args: unknown[]): void;
  callMethod?: (...args: unknown[]) => void;
  queue?: unknown[];
  push?: (...args: unknown[]) => void;
  loaded?: boolean;
  version?: string;
};

type TikTokQueue = Array<unknown> & {
  track?: (event: string, params?: Record<string, unknown>) => void;
  page?: () => void;
  grantConsent?: () => void;
  revokeConsent?: () => void;
};

declare global {
  interface Window {
    fbq?: Fbq;
    _fbq?: Fbq;
    ttq?: TikTokQueue;
    TiktokAnalyticsObject?: string;
  }
}

function safeParseAttribution(raw: string | null): MarketingAttribution | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as MarketingAttribution;
  } catch {
    return null;
  }
}

function storageAvailable() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function clearMarketingAttribution() {
  if (!storageAvailable()) return;
  window.localStorage.removeItem(FIRST_TOUCH_KEY);
  window.localStorage.removeItem(LAST_TOUCH_KEY);
}

export function captureMarketingAttribution(): MarketingAttribution | null {
  if (!storageAvailable() || !hasAdvertisingConsent()) return null;

  const params = new URLSearchParams(window.location.search);
  const hasCampaignSignal = [
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "fbclid",
    "ttclid",
  ].some((key) => params.has(key));

  if (!hasCampaignSignal) {
    return safeParseAttribution(window.localStorage.getItem(LAST_TOUCH_KEY));
  }

  const attribution: MarketingAttribution = {
    source: params.get("utm_source") || undefined,
    medium: params.get("utm_medium") || undefined,
    campaign: params.get("utm_campaign") || undefined,
    content: params.get("utm_content") || undefined,
    term: params.get("utm_term") || undefined,
    fbclid: params.get("fbclid") || undefined,
    ttclid: params.get("ttclid") || undefined,
    landingPath: `${window.location.pathname}${window.location.search}`,
    capturedAt: new Date().toISOString(),
  };

  if (!window.localStorage.getItem(FIRST_TOUCH_KEY)) {
    window.localStorage.setItem(FIRST_TOUCH_KEY, JSON.stringify(attribution));
  }
  window.localStorage.setItem(LAST_TOUCH_KEY, JSON.stringify(attribution));

  return attribution;
}

export function getMarketingAttribution() {
  if (!storageAvailable() || !hasAdvertisingConsent()) {
    return { firstTouch: null, lastTouch: null };
  }

  return {
    firstTouch: safeParseAttribution(window.localStorage.getItem(FIRST_TOUCH_KEY)),
    lastTouch: safeParseAttribution(window.localStorage.getItem(LAST_TOUCH_KEY)),
  };
}

function initializeMetaPixel(pixelId: string) {
  if (typeof window === "undefined" || !pixelId || window.fbq) return;

  const fbq: Fbq = (...args: unknown[]) => {
    if (fbq.callMethod) {
      fbq.callMethod(...args);
      return;
    }
    fbq.queue?.push(args);
  };
  fbq.queue = [];
  fbq.loaded = true;
  fbq.version = "2.0";
  fbq.push = fbq;

  window.fbq = fbq;
  window._fbq = fbq;

  const script = document.createElement("script");
  script.async = true;
  script.src = "https://connect.facebook.net/en_US/fbevents.js";
  script.dataset.diaglobAdvertising = "meta";
  document.head.appendChild(script);

  fbq("init", pixelId);
  fbq("track", "PageView");
}

function initializeTikTokPixel(pixelId: string) {
  if (typeof window === "undefined" || !pixelId || window.ttq) return;

  const safePixelId = JSON.stringify(pixelId);
  const script = document.createElement("script");
  script.dataset.diaglobAdvertising = "tiktok-bootstrap";
  script.text = `
    !function(w,d,t){
      w.TiktokAnalyticsObject=t;
      var ttq=w[t]=w[t]||[];
      ttq.methods=["page","track","identify","instances","debug","on","off","once","ready","alias","group","enableCookie","disableCookie","holdConsent","grantConsent","revokeConsent"];
      ttq.setAndDefer=function(t,e){t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}};
      for(var i=0;i<ttq.methods.length;i++)ttq.setAndDefer(ttq,ttq.methods[i]);
      ttq.instance=function(t){for(var e=ttq._i[t]||[],n=0;n<ttq.methods.length;n++)ttq.setAndDefer(e,ttq.methods[n]);return e};
      ttq.load=function(e,n){
        var i="https://analytics.tiktok.com/i18n/pixel/events.js";
        ttq._i=ttq._i||{};
        ttq._i[e]=[];
        ttq._i[e]._u=i;
        ttq._t=ttq._t||{};
        ttq._t[e]=+new Date;
        ttq._o=ttq._o||{};
        ttq._o[e]=n||{};
        var o=d.createElement("script");
        o.type="text/javascript";
        o.async=!0;
        o.src=i+"?sdkid="+e+"&lib="+t;
        o.dataset.diaglobAdvertising="tiktok";
        var a=d.getElementsByTagName("script")[0];
        a.parentNode.insertBefore(o,a)
      };
      ttq.grantConsent();
      ttq.load(${safePixelId});
      ttq.page();
    }(window,document,"ttq");
  `;
  document.head.appendChild(script);
}

function activateAdvertisingTracking() {
  if (!hasAdvertisingConsent()) return;

  advertisingTrackingActive = true;
  captureMarketingAttribution();

  if (META_PIXEL_ID) {
    initializeMetaPixel(META_PIXEL_ID);
  }

  if (TIKTOK_PIXEL_ID) {
    initializeTikTokPixel(TIKTOK_PIXEL_ID);
    window.ttq?.grantConsent?.();
  }
}

function deactivateAdvertisingTracking() {
  advertisingTrackingActive = false;
  clearMarketingAttribution();
  window.ttq?.revokeConsent?.();
}

function handleConsentChange(event: Event) {
  const consentEvent = event as CustomEvent<CookieConsentPreferences>;
  if (consentEvent.detail?.advertising) {
    activateAdvertisingTracking();
    return;
  }

  deactivateAdvertisingTracking();
}

export function initializeMarketingTracking() {
  if (hasAdvertisingConsent()) {
    activateAdvertisingTracking();
  } else {
    clearMarketingAttribution();
  }

  if (!consentListenerRegistered && typeof window !== "undefined") {
    window.addEventListener(COOKIE_CONSENT_EVENT, handleConsentChange);
    consentListenerRegistered = true;
  }
}

function metaEventFor(event: MarketingEventName) {
  switch (event) {
    case "landing_view":
      return "ViewContent";
    case "registration_submitted":
      return "Lead";
    case "complete_registration":
      return "CompleteRegistration";
    default:
      return null;
  }
}

function tiktokEventFor(event: MarketingEventName) {
  switch (event) {
    case "landing_view":
      return "ViewContent";
    case "registration_submitted":
      return "Lead";
    case "complete_registration":
      return "CompleteRegistration";
    default:
      return null;
  }
}

export function trackMarketingEvent(
  event: MarketingEventName,
  params: MarketingEventParams = {},
) {
  if (typeof window === "undefined") return;

  const advertisingAllowed = advertisingTrackingActive && hasAdvertisingConsent();
  const attribution = advertisingAllowed ? getMarketingAttribution().lastTouch : null;
  const payload = {
    ...params,
    utm_source: attribution?.source,
    utm_medium: attribution?.medium,
    utm_campaign: attribution?.campaign,
    utm_content: attribution?.content,
  };

  window.dispatchEvent(
    new CustomEvent("diaglob:marketing-event", {
      detail: { event, payload, advertisingAllowed },
    }),
  );

  if (!advertisingAllowed) return;

  const metaEvent = metaEventFor(event);
  if (metaEvent && window.fbq) {
    window.fbq("track", metaEvent, payload);
  } else if (window.fbq) {
    window.fbq("trackCustom", event, payload);
  }

  const tiktokEvent = tiktokEventFor(event);
  if (tiktokEvent && window.ttq?.track) {
    window.ttq.track(tiktokEvent, payload);
  } else if (window.ttq?.track) {
    window.ttq.track(event, payload);
  }
}
