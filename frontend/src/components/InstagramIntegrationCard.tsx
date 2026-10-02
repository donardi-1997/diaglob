import { useEffect, useState } from "react";
import { Check, Copy, Instagram, Loader2, Trash2 } from "lucide-react";

import {
  connectInstagram,
  disconnectInstagram,
  getInstagramStatus,
  type InstagramConnectionStatus,
} from "../services/instagram";


interface Props {
  storeId: number;
  canWrite: boolean;
}


export default function InstagramIntegrationCard({ storeId, canWrite }: Props) {
  const [status, setStatus] = useState<InstagramConnectionStatus | null>(null);
  const [accountId, setAccountId] = useState("");
  const [pageId, setPageId] = useState("");
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  async function load() {
    try {
      setLoading(true);
      setError("");
      setStatus(await getInstagramStatus(storeId));
    } catch {
      setError("No pudimos leer el estado de Instagram.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [storeId]);

  async function handleConnect(event: React.FormEvent) {
    event.preventDefault();
    if (!accountId.trim() || !token.trim()) {
      setError("Instagram Account ID y Access Token son obligatorios.");
      return;
    }
    try {
      setSaving(true);
      setError("");
      const result = await connectInstagram(storeId, {
        instagram_account_id: accountId.trim(),
        page_id: pageId.trim() || undefined,
        access_token: token.trim(),
      });
      setStatus(result);
      setAccountId("");
      setPageId("");
      setToken("");
    } catch (err: any) {
      setError(
        err?.response?.data?.detail?.message
        || err?.response?.data?.detail
        || "No pudimos conectar Instagram.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDisconnect() {
    try {
      setSaving(true);
      setError("");
      await disconnectInstagram(storeId);
      await load();
    } catch {
      setError("No pudimos desconectar Instagram.");
    } finally {
      setSaving(false);
    }
  }

  async function copyWebhook() {
    if (!status?.webhook_url) return;
    await navigator.clipboard.writeText(status.webhook_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  if (loading) {
    return (
      <div className="store-integration-block">
        <Loader2 className="spin" size={16} />
        <span>Cargando Instagram...</span>
      </div>
    );
  }

  return (
    <div className="store-integration-block instagram">
      <div className="store-integration-header">
        <div className="store-integration-title">
          <Instagram size={17} />
          <strong>Instagram</strong>
          <span className={
            status?.connected
              ? "integration-status connected"
              : "integration-status disconnected"
          }>
            {status?.connected ? "Conectado" : "Desconectado"}
          </span>
        </div>
      </div>

      {error && <div className="stores-alert error">{error}</div>}

      {status?.connected ? (
        <>
          <div className="store-integration-detail">
            <span>@{status.username || status.instagram_account_id}</span>
          </div>
          <div className="store-integration-webhook">
            <code>{status.webhook_url}</code>
            <button
              type="button"
              className="store-integration-copy"
              onClick={() => void copyWebhook()}
              title="Copiar webhook"
            >
              {copied ? <Check size={15} /> : <Copy size={15} />}
            </button>
          </div>
          {status.verify_token && (
            <div className="store-integration-detail">
              <span style={{ fontSize: 11, opacity: .6 }}>Verify Token:</span>
              <code style={{ fontSize: 11 }}>{status.verify_token}</code>
            </div>
          )}
          {!status.webhook_ready && (
            <div className="stores-alert error">
              Falta INSTAGRAM_WEBHOOK_VERIFY_TOKEN en el backend.
            </div>
          )}
          {canWrite && (
            <button
              type="button"
              className="store-integration-button danger"
              onClick={() => void handleDisconnect()}
              disabled={saving}
            >
              {saving ? <Loader2 className="spin" size={14} /> : <Trash2 size={14} />}
              Desconectar
            </button>
          )}
        </>
      ) : canWrite ? (
        <form className="store-integration-form" onSubmit={handleConnect}>
          <label>
            <span>Instagram Account ID</span>
            <input
              value={accountId}
              onChange={(event) => setAccountId(event.target.value)}
              placeholder="1784..."
              autoComplete="off"
            />
          </label>
          <label>
            <span>Facebook Page ID (opcional)</span>
            <input
              value={pageId}
              onChange={(event) => setPageId(event.target.value)}
              autoComplete="off"
            />
          </label>
          <label>
            <span>Access Token</span>
            <input
              type="password"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              autoComplete="off"
            />
          </label>
          <button
            type="submit"
            className="store-integration-button primary"
            disabled={saving}
          >
            {saving ? <Loader2 className="spin" size={14} /> : <Check size={14} />}
            Conectar Instagram
          </button>
        </form>
      ) : (
        <p>Un administrador puede conectar Instagram para esta tienda.</p>
      )}
    </div>
  );
}
