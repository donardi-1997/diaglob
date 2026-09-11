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


function alertCount(alert: OperationsAlert): string | null {
  return alert.message.match(/\d+/)?.[0] ?? null;
}


export function operationsAlertMessage(
  language: string | undefined,
  alert: OperationsAlert,
  integrations: OperationsIntegration[],
): string {
  if (alert.type === "integration_status_degraded") {
    return degradedAlertMessage(language, integrations);
  }

  const count = alertCount(alert);

  if (language?.startsWith("pt")) {
    if (alert.type === "failed_automations") {
      return count
        ? `${count} automatizações falharam nos últimos 7 dias`
        : "Algumas automatizações falharam nos últimos 7 dias";
    }
    if (alert.type === "unknown_orders") {
      return count
        ? `${count} pedidos estão com status desconhecido`
        : "Alguns pedidos estão com status desconhecido";
    }
    if (alert.type === "no_whatsapp") {
      return "Nenhuma conexão de WhatsApp para esta loja";
    }
    if (alert.type === "no_commerce") {
      return "Nenhuma plataforma de comércio está conectada a esta loja";
    }
  }

  if (language?.startsWith("en")) {
    if (alert.type === "failed_automations") {
      return count
        ? `${count} automations failed in the last 7 days`
        : "Some automations failed in the last 7 days";
    }
    if (alert.type === "unknown_orders") {
      return count
        ? `${count} orders have unknown status`
        : "Some orders have unknown status";
    }
    if (alert.type === "no_whatsapp") {
      return "No WhatsApp connection is configured for this store";
    }
    if (alert.type === "no_commerce") {
      return "No commerce platform is connected to this store";
    }
  }

  if (alert.type === "failed_automations") {
    return count
      ? `${count} automatizaciones fallaron en los últimos 7 días`
      : "Algunas automatizaciones fallaron en los últimos 7 días";
  }
  if (alert.type === "unknown_orders") {
    return count
      ? `${count} pedidos tienen estado desconocido`
      : "Algunos pedidos tienen estado desconocido";
  }
  if (alert.type === "no_whatsapp") {
    return "No hay una conexión de WhatsApp para esta tienda";
  }
  if (alert.type === "no_commerce") {
    return "No hay una plataforma de comercio conectada a esta tienda";
  }

  return alert.message;
}
