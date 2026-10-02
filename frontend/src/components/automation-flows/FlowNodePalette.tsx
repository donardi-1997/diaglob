import { useMemo, useState } from "react";
import {
  Clock,
  GitBranch,
  MessageSquare,
  Search,
  Square,
  Zap,
} from "lucide-react";
import type { FlowNodeType } from "./flowGraphUtils";

interface Props {
  canWrite: boolean;
  onAdd: (type: FlowNodeType) => void;
}

const ITEMS: Array<{
  type: FlowNodeType;
  title: string;
  description: string;
  group: string;
  icon: typeof Zap;
}> = [
  {
    type: "trigger",
    title: "Trigger",
    description: "Inicia el flujo por evento o manualmente.",
    group: "Inicio",
    icon: Zap,
  },
  {
    type: "condition",
    title: "Condición",
    description: "Divide el flujo según datos del cliente.",
    group: "Lógica",
    icon: GitBranch,
  },
  {
    type: "wait",
    title: "Espera",
    description: "Pausa la ejecución por minutos, horas o días.",
    group: "Lógica",
    icon: Clock,
  },
  {
    type: "message",
    title: "WhatsApp",
    description: "Envía un mensaje o plantilla al cliente.",
    group: "Acciones",
    icon: MessageSquare,
  },
  {
    type: "end",
    title: "Fin",
    description: "Finaliza una rama del flujo.",
    group: "Control",
    icon: Square,
  },
];

export default function FlowNodePalette({ canWrite, onAdd }: Props) {
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return ITEMS;
    return ITEMS.filter((item) =>
      [item.title, item.description, item.group]
        .join(" ")
        .toLowerCase()
        .includes(term),
    );
  }, [query]);

  const groups = useMemo(
    () => [...new Set(visible.map((item) => item.group))],
    [visible],
  );

  function handleDragStart(
    event: React.DragEvent<HTMLButtonElement>,
    type: FlowNodeType,
  ) {
    if (!canWrite) {
      event.preventDefault();
      return;
    }
    event.dataTransfer.setData("application/diaglob-flow-node", type);
    event.dataTransfer.effectAllowed = "move";
  }

  return (
    <aside className="flow-palette">
      <div className="flow-palette-heading">
        <span>Herramientas</span>
        <strong>Nodos</strong>
      </div>

      <label className="flow-palette-search">
        <Search size={14} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Buscar nodo..."
        />
      </label>

      <div className="flow-palette-groups">
        {groups.map((group) => (
          <section key={group} className="flow-palette-group">
            <h4>{group}</h4>
            {visible
              .filter((item) => item.group === group)
              .map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.type}
                    type="button"
                    className="flow-palette-item"
                    draggable={canWrite}
                    disabled={!canWrite}
                    onDragStart={(event) =>
                      handleDragStart(event, item.type)}
                    onClick={() => onAdd(item.type)}
                  >
                    <span className={`flow-palette-icon type-${item.type}`}>
                      <Icon size={15} />
                    </span>
                    <span>
                      <strong>{item.title}</strong>
                      <small>{item.description}</small>
                    </span>
                  </button>
                );
              })}
          </section>
        ))}
      </div>

      <p className="flow-palette-help">
        Arrastra un nodo al canvas o haz clic para agregarlo.
      </p>
    </aside>
  );
}
