export type FrontendObservabilityEnv = {
  VITE_SENTRY_DSN?: string;
  VITE_SENTRY_ENVIRONMENT?: string;
  VITE_SENTRY_RELEASE?: string;
  VITE_SENTRY_TRACES_SAMPLE_RATE?: string;
};

export type FrontendSentryInitOptions = {
  dsn: string;
  environment?: string;
  release?: string;
  tracesSampleRate: number;
  sendDefaultPii: false;
};

type SentryInitializer = (options: FrontendSentryInitOptions) => unknown;

function parseTraceSampleRate(rawValue?: string): number {
  if (!rawValue?.trim()) return 0;

  const value = Number(rawValue);
  if (!Number.isFinite(value) || value < 0 || value > 1) return 0;

  return value;
}

export function initializeFrontendObservability(
  env: FrontendObservabilityEnv,
  initializeSentry: SentryInitializer,
): boolean {
  const dsn = env.VITE_SENTRY_DSN?.trim() ?? "";
  if (!dsn) return false;

  const environment = env.VITE_SENTRY_ENVIRONMENT?.trim() || undefined;
  const release = env.VITE_SENTRY_RELEASE?.trim() || undefined;

  initializeSentry({
    dsn,
    ...(environment ? { environment } : {}),
    ...(release ? { release } : {}),
    tracesSampleRate: parseTraceSampleRate(env.VITE_SENTRY_TRACES_SAMPLE_RATE),
    sendDefaultPii: false,
  });

  return true;
}
