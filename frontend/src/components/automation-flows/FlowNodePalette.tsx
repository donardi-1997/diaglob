import { useState } from "react";
import {
  BarChart3,
  Bot,
  Braces,
  Clock,
  GitBranch,
  MessageSquare,
  PackageSearch,
  PhoneCall,
  Search,
  ShoppingBag,
  Square,
  Store,
  Truck,
  Users,
  Webhook,
  Zap,
} from "lucide-react";
import type {
  FlowNodeConfig,
  FlowNodeType,
} from "./flowGraphUtils";
import {
  FLOW_TOOL_CATALOG,
  type FlowToolCatalogItem,
} from "./flowToolCatalog";

interface Props {
  canWrite: boolean;
  onAdd: (
    type: FlowNodeType,
    config?: Partial<FlowNodeConfig>,
  ) => void;
}

interface PaletteItem {
  id: string;
  type: FlowNodeType;
  title: string;
  description: string;
  group: string;
  icon: typeof Zap;
  config?: Partial<FlowNodeConfig>;
  planned?: boolean;
}

const CORE_ITEMS: PaletteItem[] = [
  {
    id: "trigger-manual",
    type: "trigger",
    title: "Inicio manual",
    description: "Ejecuta el flujo manualmente o sobre una audiencia.",
    group: "Inicio",
    icon: Zap,
    config: { trigger_type: "manual" },
  },
  {
    id: "trigger-order-created",
    type: "trigger",
    title: "Pedido creado",
    description: "Inicia el flujo cuando se registra un pedido.",
    group: "Inicio",
    icon: ShoppingBag,
    config: { trigger_type: "order_created" },
  },
  {
    id: "trigger-failed-order",
    type: "trigger",
    title: "Pedido fallido",
    description: "Inicia el flujo ante un pedido fallido.",
    group: "Inicio",
    icon: ShoppingBag,
    config: { trigger_type: "failed_order" },
  },
  {
    id: "trigger-customer-created",
    type: "trigger",
    title: "Cliente creado",
    description: "Inicia el flujo al crear un cliente.",
    group: "Inicio",
    icon: Users,
    config: { trigger_type: "customer_created" },
  },
  {
    id: "trigger-customer-segment",
    type: "trigger",
    title: "Segmento de cliente",
    description: "Inicia el flujo según clasificación del cliente.",
    group: "Inicio",
    icon: Users,
    config: { trigger_type: "customer_segment" },
  },
  {
    id: "condition",
    type: "condition",
    title: "Condición",
    description: "Divide el flujo según datos del cliente.",
    group: "Lógica",
    icon: GitBranch,
  },
  {
    id: "wait",
    type: "wait",
    title: "Espera",
    description: "Pausa la ejecución por minutos, horas o días.",
    group: "Lógica",
    icon: Clock,
  },
  {
    id: "message",
    type: "message",
    title: "WhatsApp",
    description: "Envía un mensaje o plantilla al cliente.",
    group: "Canales",
    icon: MessageSquare,
  },
  {
    id: "call",
    type: "call",
    title: "Llamada IA",
    description: "Llama al cliente y ramifica según confirme, rechace o no conteste.",
    group: "Canales",
    icon: PhoneCall,
  },
  {
    id: "end",
    type: "end",
    title: "Fin",
    description: "Finaliza una rama del flujo.",
    group: "Control",
    icon: Square,
  },
];

const TOOL_ICONS: Record<FlowToolCatalogItem["group"], typeof Zap> = {
  Pedidos: ShoppingBag,
  Productos: PackageSearch,
  Clientes: Users,
  Proveedores: Truck,
  Analytics: BarChart3,
};

const TOOL_ITEMS: PaletteItem[] = FLOW_TOOL_CATALOG.map((tool) => ({
  id: `tool-${tool.name}`,
  type: "tool",
  title: tool.title,
  description: tool.description,
  group: tool.group,
  icon: TOOL_ICONS[tool.group],
  config: {
    tool_name: tool.name,
    arguments: tool.defaultArguments,
  },
}));

const PLANNED_ITEMS: PaletteItem[] = [
  {
    id: "planned-shopify-write",
    type: "tool",
    title: "Acción Shopify",
    description: "Escrituras sobre pedidos/productos con control de aprobación.",
    group: "Próximamente",
    icon: Store,
    planned: true,
  },
  {
    id: "planned-http",
    type: "tool",
    title: "HTTP / Webhook",
    description: "Requests salientes con allowlist y protección SSRF.",
    group: "Próximamente",
    icon: Webhook,
    planned: true,
  },
  {
    id: "planned-variables",
    type: "tool",
    title: "Variables",
    description: "Guardar outputs y reutilizarlos en nodos posteriores.",
    group: "Próximamente",
    icon: Braces,
    planned: true,
  },
  {
    id: "planned-ai",
    type: "tool",
    title: "IA",
    description: "Transformar, clasificar o generar datos con modelos.",
    group: "Próximamente",
    icon: Bot,
    planned: true,
  },
];

const ITEMS = [...CORE_ITEMS, ...TOOL_ITEMS, ...PLANNED_ITEMS];

export default function FlowNodePalette({ canWrite, onAdd }: Props) {
  const [query, setQuery] = useState("");
  const term = query.trim().toLowerCase();
  const visible = term
    ? ITEMS.filter((item) =>
        [item.title, item.description, item.group]
          .join(" ")
          .toLowerCase()
          .includes(term),
      )
    : ITEMS;
  const groups = [...new Set(visible.map((item) => item.group))];

  function payload(item: PaletteItem) {
    return JSON.stringify({
      type: item.type,
      config: item.config || {},
    });
  }

  function handleDragStart(
    event: React.DragEvent<HTMLButtonElement>,
    item: PaletteItem,
  ) {
    if (!canWrite || item.planned) {
      event.preventDefault();
      return;
    }
    event.dataTransfer.setData(
      "application/diaglob-flow-node",
      payload(item),
    );
    event.dataTransfer.effectAllowed = "move";
  }

  return (
    <aside className="flow-palette">
      <div className="flow-palette-heading">
        <span>Herramientas</span>
        <strong>Catálogo operativo</strong>
      </div>

      <label className="flow-palette-search">
        <Search size={14} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Buscar nodo, CJ, pedido..."
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
                    key={item.id}
                    type="button"
                    className={
                      item.planned
                        ? "flow-palette-item planned"
                        : "flow-palette-item"
                    }
                    draggable={canWrite && !item.planned}
                    disabled={!canWrite || item.planned}
                    onDragStart={(event) =>
                      handleDragStart(event, item)}
                    onClick={() =>
                      !item.planned
                      && onAdd(item.type, item.config)}
                  >
                    <span
                      className={
                        `flow-palette-icon type-${item.type}`
                      }
                    >
                      <Icon size={15} />
                    </span>
                    <span>
                      <strong>
                        {item.title}
                        {item.planned && (
                          <em className="flow-planned-badge">
                            Próximamente
                          </em>
                        )}
                      </strong>
                      <small>{item.description}</small>
                    </span>
                  </button>
                );
              })}
          </section>
        ))}
      </div>

      <p className="flow-palette-help">
        Solo las capacidades ejecutables están habilitadas. Las acciones
        sensibles seguirán requiriendo controles adicionales antes de
        habilitarse en segundo plano.
      </p>
    </aside>
  );
}
