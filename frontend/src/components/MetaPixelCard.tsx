import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { BarChart3, Loader2, AlertTriangle } from "lucide-react";

import {
  getStoreMetaPixel,
  getMetaPixelReadiness,
  provisionMetaPixel,
  unprovisionMetaPixel,
  removeStoreMetaPixel,
  saveStoreMetaPixel,
  type MetaPixelSettingsStatus,
  type MetaPixelReadiness,
} from "../services/integrations";

type TrackingKind = MetaPixelSettingsStatus["existing_tracking"];

export default function MetaPixelCard({
  storeId,
  canWrite,
}: {
  storeId: number;
  canWrite: boolean;
}) {
  const { i18n } = useTranslation();
  const english = i18n.language.toLowerCase().startsWith("en");
  const portuguese = i18n.language.toLowerCase().startsWith("pt");
  const msg = (es: string, en: string, pt: string) =>
    portuguese ? pt : english ? en : es;

  const [status, setStatus] = useState<MetaPixelSettingsStatus | null>(null);
  const [readiness, setReadiness] = useState<MetaPixelReadiness | null>(null);
  const [pixelId, setPixelId] = useState("");
  const [existingTracking, setExistingTracking] = useState<TrackingKind>("unknown");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setStatus(null);
    setReadiness(null);
    setPixelId("");
    setExistingTracking("unknown");
    setError("");
    setNotice("");
    void Promise.all([getStoreMetaPixel(storeId), getMetaPixelReadiness(storeId)])
      .then(([response, gates]) => {
        setReadiness(gates);
        if (!mounted) return;
        setStatus(response);
        setPixelId(response.pixel_id || "");
        setExistingTracking(response.existing_tracking);
      })
      .catch(() => {
        if (mounted) setError(msg(
          "No pudimos consultar Meta Pixel para esta tienda.",
          "Could not load this store's Meta Pixel configuration.",
          "Não foi possível carregar o Meta Pixel desta loja.",
        ));
      })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
    // Language changes do not require re-fetching merchant settings.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId]);

  async function save() {
    if (!/^[0-9]{8,30}$/.test(pixelId)) {
      setError(msg("El Pixel ID debe tener entre 8 y 30 dígitos.",
        "Pixel ID must contain 8–30 digits.",
        "O Pixel ID deve conter de 8 a 30 dígitos."));
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const next = await saveStoreMetaPixel(storeId, pixelId, existingTracking);
      setStatus(next);
      setReadiness(await getMetaPixelReadiness(storeId));
      setNotice(msg(
        "Configuración guardada. La medición sigue desactivada hasta instalar y validar la extensión de Shopify.",
        "Settings saved. Tracking remains off until the Shopify extension is installed and validated.",
        "Configuração salva. A medição permanece desativada até a extensão da Shopify ser validada.",
      ));
    } catch {
      setError(msg("No se pudo guardar. Revisa tus permisos.",
        "Could not save settings. Check permissions.",
        "Não foi possível salvar. Verifique as permissões."));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const next = await removeStoreMetaPixel(storeId);
      setStatus(next);
      setPixelId("");
      setExistingTracking("unknown");
      setReadiness(await getMetaPixelReadiness(storeId));
      setNotice(msg("Configuración eliminada.", "Configuration removed.", "Configuração removida."));
    } catch {
      setError(msg("No se pudo eliminar la configuración.",
        "Could not remove configuration.",
        "Não foi possível remover a configuração."));
    } finally {
      setBusy(false);
    }
  }

  async function changeProvisioning(undo = false) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (undo) await unprovisionMetaPixel(storeId);
      else await provisionMetaPixel(storeId);
      const [next, gate] = await Promise.all([
        getStoreMetaPixel(storeId), getMetaPixelReadiness(storeId),
      ]);
      setStatus(next);
      setReadiness(gate);
      setNotice(msg(
        "Registro Shopify actualizado. El envío de eventos continúa desactivado.",
        "Shopify pixel record updated. Event delivery remains disabled.",
        "Registro Shopify atualizado. O envio de eventos permanece desativado.",
      ));
    } catch {
      setError(msg(
        "Shopify no permitió esta operación. Revisa permisos, despliegue y tienda de pruebas.",
        "Shopify could not complete the operation. Verify permissions, deployment and test shop.",
        "A Shopify não permitiu a operação. Verifique permissões e a loja de teste.",
      ));
    } finally { setBusy(false); }
  }

  return (
    <section className="store-integration-block" aria-label="Meta Pixel">
      <div className="store-integration-header">
        <div className="store-integration-title">
          <BarChart3 size={17} />
          <strong>Meta Pixel</strong>
          <span className="integration-status disconnected">
            {msg("Sin activar", "Not active", "Não ativado")}
          </span>
        </div>
      </div>
      <p className="store-integration-detail">
        {msg(
          "Configura un Pixel diferente para cada tienda. Guardarlo no lo instala en Shopify ni envía eventos.",
          "Set a separate Pixel for each store. Saving does not install it on Shopify or send events.",
          "Configure um Pixel diferente para cada loja. Salvar não instala nem envia eventos.",
        )}
      </p>
      {loading ? <p role="status"><Loader2 size={15} className="spin" /> {msg("Cargando…", "Loading…", "Carregando…")}</p> : (
        <div className="store-integration-actions" style={{ flexDirection: "column", alignItems: "stretch" }}>
          <label htmlFor={`meta-pixel-id-${storeId}`}>
            {msg("ID del Pixel de esta tienda", "This store's Pixel ID", "ID do Pixel desta loja")}
          </label>
          <input
            id={`meta-pixel-id-${storeId}`}
            type="text"
            inputMode="numeric"
            pattern="[0-9]{8,30}"
            autoComplete="off"
            placeholder="123456789012345"
            value={pixelId}
            disabled={!canWrite || busy || status?.extension_installed}
            onChange={(event) => setPixelId(event.target.value.trim())}
          />
          <label htmlFor={`meta-tracking-kind-${storeId}`}>
            {msg("¿La tienda ya mide eventos con Meta?", "Does this store already use Meta tracking?", "Esta loja já usa medição da Meta?")}
          </label>
          <select
            id={`meta-tracking-kind-${storeId}`}
            value={existingTracking}
            disabled={!canWrite || busy}
            onChange={(event) => setExistingTracking(event.target.value as TrackingKind)}
          >
            <option value="unknown">{msg("No lo sé", "Not sure", "Não sei")}</option>
            <option value="shopify_meta">Facebook &amp; Instagram (Shopify)</option>
            <option value="manual_pixel">{msg("Pixel instalado manualmente", "Manually installed Pixel", "Pixel instalado manualmente")}</option>
            <option value="none">{msg("No tiene medición Meta", "No existing Meta tracking", "Sem medição Meta")}</option>
          </select>
          {status?.duplicate_tracking_risk === "high" || existingTracking === "shopify_meta" || existingTracking === "manual_pixel" ? (
            <p role="status" className="stores-alert" style={{ display: "flex", alignItems: "start", gap: 8 }}>
              <AlertTriangle size={17} />
              {msg(
                "Ya existe otra fuente de eventos Meta. Antes de activar una segunda, debemos evitar duplicados.",
                "Existing Meta tracking detected. Duplicate events must be prevented before activating another source.",
                "Já existe outra fonte Meta. Precisamos evitar eventos duplicados antes de ativar outra.",
              )}
            </p>
          ) : null}
          {status?.configured ? (
            <p role="status">
              {status.extension_installed
                ? msg("Extensión registrada en Shopify, pero eventos aún desactivados.",
                  "Shopify extension provisioned, but event delivery remains off.",
                  "Extensão registrada na Shopify, mas eventos desativados.")
                : msg("Estado: pendiente de extensión y pruebas en Shopify.",
                  "Status: awaiting Shopify extension and testing.",
                  "Status: aguardando extensão e testes na Shopify.")}
            </p>
          ) : null}
          {error && <p role="alert" className="stores-alert error">{error}</p>}
          {notice && <p role="status" className="stores-alert success">{notice}</p>}
          {canWrite && (
            <div className="store-integration-actions">
              <button type="button" className="store-integration-button primary" disabled={busy || loading || status?.extension_installed} onClick={() => void save()}>
                {busy ? <Loader2 size={14} className="spin" /> : null}
                {msg("Guardar Pixel", "Save Pixel", "Salvar Pixel")}
              </button>
              {status?.configured && !status.extension_installed && (
                <button type="button" className="store-integration-button secondary" disabled={busy} onClick={() => void remove()}>
                  {msg("Quitar configuración", "Remove settings", "Remover configuração")}
                </button>
              )}
              {readiness?.can_provision && !status?.extension_installed && (
                <button type="button" className="store-integration-button secondary"
                  disabled={busy} onClick={() => void changeProvisioning()}>
                  {msg("Registrar extensión (sin eventos)", "Provision extension (no events)", "Registrar extensão (sem eventos)")}
                </button>
              )}
              {status?.extension_installed && (
                <button type="button" className="store-integration-button secondary"
                  disabled={busy} onClick={() => void changeProvisioning(true)}>
                  {msg("Retirar extensión Shopify", "Remove Shopify extension", "Remover extensão Shopify")}
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
