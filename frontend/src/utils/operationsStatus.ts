import type { OperationsIntegration } from "../services/operations";


export function degradedStatusLabel(language?: string): string {
  if (language?.startsWith("pt")) return "Temporariamente indisponível";
  if (language?.startsWith("en")) return "Temporarily unavailable";
  return "Temporalmente no disponible";
}


export function degradedAlertMessage(
  language: string | undefined,
  integrations: OperationsIntegration[],
): string {
  const names = Array.from(
    new Set(
      integrations
        .filter((integration) => integration.degraded)
        .map((integration) => integration.name),
    ),
  );
  const suffix = names.length ? `: ${names.join(", ")}` : "";

  if (language?.startsWith("pt")) {
    return `Status de integração temporariamente indisponível${suffix}`;
  }
  if (language?.startsWith("en")) {
    return `Integration status temporarily unavailable${suffix}`;
  }
  return `Estado de integración temporalmente no disponible${suffix}`;
}
