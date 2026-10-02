import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardPlus,
  LoaderCircle,
  PackageCheck,
  RotateCcw,
  ShieldCheck,
  X,
} from "lucide-react";

import {
  createPostSalesCase,
  getPostSalesCases,
  getPostSalesSummary,
  updatePostSalesCase,
  type PostSalesCase,
  type PostSalesCaseType,
  type PostSalesPriority,
  type PostSalesStatus,
  type PostSalesSummary,
} from "../services/postSales";
import "../post-sales.css";


interface Props {
  storeId: number;
  canWrite: boolean;
}

const CASE_LABELS: Record<PostSalesCaseType, string> = {
  warranty: "Garantía",
  return: "Devolución",
  refund: "Reembolso",
  damaged: "Producto dañado",
  wrong_product: "Producto incorrecto",
  delivery_issue: "Novedad de entrega",
  other: "Otro",
};

const STATUS_LABELS: Record<PostSalesStatus, string> = {
  open: "Abierto",
  waiting_customer: "Esperando cliente",
  investigating: "Investigando",
  approved: "Aprobado",
  rejected: "Rechazado",
  resolved: "Resuelto",
  closed: "Cerrado",
};

const STATUS_OPTIONS = Object.keys(STATUS_LABELS) as PostSalesStatus[];

export default function PostSalesPage({ storeId, canWrite }: Props) {
  const [items, setItems] = useState<PostSalesCase[]>([]);
  const [summary, setSummary] = useState<PostSalesSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [filter, setFilter] = useState<"all" | "open" | "urgent">("all");
  const [form, setForm] = useState({
    case_type: "delivery_issue" as PostSalesCaseType,
    priority: "normal" as PostSalesPriority,
    title: "",
    description: "",
    order_id: "",
  });

  async function load() {
    if (!storeId) return;
    try {
      setLoading(true);
      setError("");
      const [casesResponse, summaryResponse] = await Promise.all([
        getPostSalesCases(storeId),
        getPostSalesSummary(storeId),
      ]);
      setItems(casesResponse.items);
      setSummary(summaryResponse);
    } catch (err) {
      console.error(err);
      setError("No pudimos cargar Postventa.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [storeId]);

  const visibleItems = useMemo(() => {
    if (filter === "open") {
      return items.filter((item) => !["resolved", "closed"].includes(item.status));
    }
    if (filter === "urgent") {
      return items.filter(
        (item) => item.priority === "urgent" && !["resolved", "closed"].includes(item.status),
      );
    }
    return items;
  }, [filter, items]);

  async function handleCreate() {
    const title = form.title.trim();
    if (!title) {
      setError("Escribe un título para el caso.");
      return;
    }
    try {
      setError("");
      await createPostSalesCase(storeId, {
        case_type: form.case_type,
        priority: form.priority,
        title,
        description: form.description.trim(),
        order_id: form.order_id ? Number(form.order_id) : undefined,
      });
      setModalOpen(false);
      setForm({
        case_type: "delivery_issue",
        priority: "normal",
        title: "",
        description: "",
        order_id: "",
      });
      await load();
    } catch (err) {
      console.error(err);
      setError("No pudimos crear el caso. Revisa que el pedido pertenezca a esta tienda.");
    }
  }

  async function changeStatus(item: PostSalesCase, status: PostSalesStatus) {
    try {
      setSavingId(item.id);
      setError("");
      await updatePostSalesCase(storeId, item.id, { status });
      await load();
    } catch (err) {
      console.error(err);
      setError("La transición de estado no es válida o no pudo guardarse.");
    } finally {
      setSavingId(null);
    }
  }

  if (!storeId) {
    return (
      <div className="content">
        <section className="panel empty-management">
          <ShieldCheck size={30} />
          <strong>Selecciona una tienda</strong>
          <span>Postventa siempre opera dentro del contexto de una tienda.</span>
        </section>
      </div>
    );
  }

  return (
    <div className="content post-sales-page">
      <section className="page-heading management-heading">
        <div>
          <span className="eyebrow">OPERACIÓN POSTVENTA</span>
          <h1>Postventa</h1>
          <p>
            Centraliza garantías, devoluciones, reembolsos y novedades de entrega
            vinculadas a pedidos reales.
          </p>
        </div>
        {canWrite && (
          <button className="primary-button" onClick={() => setModalOpen(true)}>
            <ClipboardPlus size={17} />
            Nuevo caso
          </button>
        )}
      </section>

      {error && <div className="api-error">{error}</div>}

      <section className="post-sales-summary">
        <button className={filter === "all" ? "is-active" : ""} onClick={() => setFilter("all")}>
          <PackageCheck size={18} />
          <span>Total</span>
          <strong>{summary?.total ?? "—"}</strong>
        </button>
        <button className={filter === "open" ? "is-active" : ""} onClick={() => setFilter("open")}>
          <RotateCcw size={18} />
          <span>Abiertos</span>
          <strong>{summary?.open ?? "—"}</strong>
        </button>
        <button className={filter === "urgent" ? "is-active" : ""} onClick={() => setFilter("urgent")}>
          <AlertTriangle size={18} />
          <span>Urgentes</span>
          <strong>{summary?.urgent ?? "—"}</strong>
        </button>
        <div className="post-sales-summary-static">
          <CheckCircle2 size={18} />
          <span>Resueltos</span>
          <strong>{summary?.resolved ?? "—"}</strong>
        </div>
      </section>

      {loading ? (
        <div className="conversation-loading"><LoaderCircle className="spin" size={28} /></div>
      ) : (
        <section className="post-sales-grid">
          {visibleItems.map((item) => (
            <article className="panel post-sales-card" key={item.id}>
              <header>
                <div>
                  <span className={"post-sales-priority " + item.priority}>{item.priority}</span>
                  <h3>{item.title}</h3>
                  <small>
                    {CASE_LABELS[item.case_type]}
                    {item.order_id ? " · Pedido #" + item.order_id : ""}
                  </small>
                </div>
                <span className={"status-pill " + (["resolved", "closed"].includes(item.status) ? "active" : "")}>
                  {STATUS_LABELS[item.status]}
                </span>
              </header>
              {item.description && <p>{item.description}</p>}
              <footer>
                <span>
                  Actualizado {item.updated_at ? new Date(item.updated_at).toLocaleString() : "—"}
                </span>
                {canWrite && (
                  <select
                    value={item.status}
                    disabled={savingId === item.id || item.status === "closed"}
                    onChange={(event) => void changeStatus(item, event.target.value as PostSalesStatus)}
                  >
                    {STATUS_OPTIONS.map((status) => (
                      <option value={status} key={status}>{STATUS_LABELS[status]}</option>
                    ))}
                  </select>
                )}
              </footer>
            </article>
          ))}
          {!visibleItems.length && (
            <div className="panel empty-management">
              <ShieldCheck size={28} />
              <strong>No hay casos en esta vista</strong>
              <span>Los casos nuevos aparecerán aquí con su pedido y línea de tiempo.</span>
            </div>
          )}
        </section>
      )}

      {modalOpen && (
        <div className="management-modal-backdrop" onMouseDown={() => setModalOpen(false)}>
          <div className="management-modal" onMouseDown={(event) => event.stopPropagation()}>
            <header className="management-modal-header">
              <div>
                <span className="eyebrow">POSTVENTA</span>
                <h2>Nuevo caso</h2>
              </div>
              <button className="icon-button" onClick={() => setModalOpen(false)}><X size={18} /></button>
            </header>

            <div className="management-form">
              <label>
                <span>Tipo</span>
                <select
                  value={form.case_type}
                  onChange={(event) => setForm((current) => ({
                    ...current,
                    case_type: event.target.value as PostSalesCaseType,
                  }))}
                >
                  {(Object.keys(CASE_LABELS) as PostSalesCaseType[]).map((type) => (
                    <option value={type} key={type}>{CASE_LABELS[type]}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>Prioridad</span>
                <select
                  value={form.priority}
                  onChange={(event) => setForm((current) => ({
                    ...current,
                    priority: event.target.value as PostSalesPriority,
                  }))}
                >
                  <option value="low">Baja</option>
                  <option value="normal">Normal</option>
                  <option value="high">Alta</option>
                  <option value="urgent">Urgente</option>
                </select>
              </label>
              <label>
                <span>ID de pedido (opcional)</span>
                <input
                  type="number"
                  min="1"
                  value={form.order_id}
                  onChange={(event) => setForm((current) => ({ ...current, order_id: event.target.value }))}
                />
              </label>
              <label>
                <span>Título</span>
                <input
                  value={form.title}
                  onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                  placeholder="Ej. Producto llegó roto"
                />
              </label>
              <label>
                <span>Descripción</span>
                <textarea
                  rows={4}
                  value={form.description}
                  onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
                  placeholder="Qué ocurrió y qué información tenemos."
                />
              </label>
            </div>

            <footer className="management-modal-actions">
              <button className="secondary-button" onClick={() => setModalOpen(false)}>Cancelar</button>
              <button className="primary-button" onClick={() => void handleCreate()}>Crear caso</button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
