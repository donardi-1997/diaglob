import { useEffect, useState } from "react";
import { Clock3, RotateCcw, X } from "lucide-react";
import {
  listFlowVersions,
  type AutomationFlowVersion,
} from "../../services/automationFlows";

interface Props {
  storeId: number;
  flowId: number;
  currentVersionId: number | null;
  activeVersionId: number | null;
  canRestore: boolean;
  onRestore: (version: AutomationFlowVersion) => void;
  onClose: () => void;
}

function graphSummary(version: AutomationFlowVersion): string {
  const nodes = version.graph?.nodes;
  const edges = version.graph?.edges;
  const nodeCount = Array.isArray(nodes) ? nodes.length : 0;
  const edgeCount = Array.isArray(edges) ? edges.length : 0;
  return `${nodeCount} nodos · ${edgeCount} conexiones`;
}

export default function FlowVersionHistory({
  storeId,
  flowId,
  currentVersionId,
  activeVersionId,
  canRestore,
  onRestore,
  onClose,
}: Props) {
  const [versions, setVersions] = useState<AutomationFlowVersion[]>([]);
  const [previewId, setPreviewId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    setPreviewId(null);
    setVersions([]);
    void listFlowVersions(storeId, flowId)
      .then((response) => {
        if (cancelled) return;
        setVersions([...response].sort((a, b) => b.version_number - a.version_number));
      })
      .catch(() => {
        if (!cancelled) setError("No se pudo consultar el historial de versiones.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [storeId, flowId]);

  return (
    <section className="flow-version-history" aria-label="Historial de versiones">
      <div className="flow-version-history-heading">
        <div>
          <strong><Clock3 size={16} /> Historial de versiones</strong>
          <p>Revisa versiones guardadas sin modificar el flujo activo.</p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Cerrar historial">
          <X size={16} />
        </button>
      </div>
      {loading && <p role="status">Cargando versiones...</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && !error && versions.length === 0 && (
        <p>Este flujo todavía no tiene versiones guardadas.</p>
      )}
      <div className="flow-version-history-list">
        {versions.map((version) => {
          const isCurrent = currentVersionId === version.id;
          const isActive = activeVersionId === version.id;
          const preview = previewId === version.id;
          const hasGraph = Array.isArray(version.graph?.nodes)
            && Array.isArray(version.graph?.edges);
          return (
            <div className="flow-version-item" key={version.id}>
              <button
                type="button"
                className="flow-version-preview"
                onClick={() => setPreviewId(preview ? null : version.id)}
                aria-expanded={preview}
              >
                <span>
                  <strong>Versión {version.version_number}</strong>
                  <small>
                    {version.created_at
                      ? new Date(version.created_at).toLocaleString("es-CO")
                      : "Sin fecha"}
                  </small>
                </span>
                <span className="flow-version-labels">
                  {isCurrent && <em>Actual</em>}
                  {isActive && <em>En ejecución</em>}
                  {version.published_at && <em>Publicada</em>}
                </span>
              </button>
              {preview && (
                <div className="flow-version-detail">
                  <p>{graphSummary(version)}</p>
                  <p>Esta previsualización muestra solo la estructura, sin mensajes ni datos sensibles.</p>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={!canRestore || !hasGraph}
                    onClick={() => onRestore(version)}
                    title={!canRestore ? "Pausa el flujo antes de restaurar una versión" : undefined}
                  >
                    <RotateCcw size={14} /> Cargar en el editor
                  </button>
                  <small>Se carga como cambio local. Debes guardarlo y publicarlo explícitamente.</small>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
