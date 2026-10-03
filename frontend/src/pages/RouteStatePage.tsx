interface RouteStatePageProps {
  kind: "not-found" | "forbidden" | "empty";
  onPrimaryAction: () => void;
  inApp?: boolean;
}

const content = {
  "not-found": {
    eyebrow: "404",
    title: "Esta ruta no existe",
    text: "Revisa la dirección o vuelve a una sección conocida de Diaglob.",
    action: "Volver al inicio",
  },
  forbidden: {
    eyebrow: "ACCESO",
    title: "No tienes acceso a esta sección",
    text: "La ruta existe, pero tu rol actual no tiene el permiso necesario para abrirla.",
    action: "Ir a mi inicio",
  },
  empty: {
    eyebrow: "WORKSPACE",
    title: "No hay secciones disponibles",
    text: "Tu sesión está activa, pero este workspace no tiene navegación habilitada para tu rol.",
    action: "Cerrar sesión",
  },
} as const;

export default function RouteStatePage({
  kind,
  onPrimaryAction,
  inApp = false,
}: RouteStatePageProps) {
  const copy = content[kind];

  return (
    <main className={inApp ? "route-state route-state-in-app" : "route-state"}>
      <div className="route-state-card">
        <span>{copy.eyebrow}</span>
        <h1>{copy.title}</h1>
        <p>{copy.text}</p>
        <button type="button" className="primary-button" onClick={onPrimaryAction}>
          {copy.action}
        </button>
      </div>
    </main>
  );
}
