import type {
  OperationsAlert,
  OperationsHealthStatus,
  OperationsIntegration,
} from "../services/operations";


export function degradedStatusLabel(language?: string): string {
  if (language?.startsWith("pt")) return "Temporariamente indisponível";
  if (language?.startsWith("en")) return "Temporarily unavailable";
  return "Temporalmente no disponible";
}


export function operationsHealthLabel(
  status: OperationsHealthStatus,
  language?: string,
): string {
  if (language?.startsWith("pt")) {
    if (status === "attention") return "Requer atenção";
    if (status === "degraded") return "Degradado";
    return "Operacional";
  }

  if (language?.startsWith("en")) {
    if (status === "attention") return "Needs attention";
    if (status === "degraded") return "Degraded";
    return "Operational";
  }

  if (status === "attention") return "Requiere atención";
  if (status === "degraded") return "Degradado";
  return "Operativo";
}


export function sortOperationsAlerts(
  alerts: OperationsAlert[],
): OperationsAlert[] {
  const severityRank: Record<OperationsAlert["severity"], number> = {
    error: 0,
    warning: 1,
    info: 2,
  };

  return [...alerts].sort(
    (left, right) => severityRank[left.severity] - severityRank[right.severity],
  );
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
