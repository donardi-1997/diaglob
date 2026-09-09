import { FormEvent, useEffect, useState } from "react";
import { Check, Copy, CreditCard, ExternalLink, Loader2, Plug, RefreshCw, Trash2 } from "lucide-react";

import {
  connectMercadoPagoPix,
  createPixPayment,
  disconnectMercadoPagoPix,
  getPaymentProviders,
  getPaymentStatus,
  reconcilePayment,
  type PaymentConnectionStatus,
  type PaymentTransaction,
} from "../services/payments";

interface PixPaymentsPanelProps {
  storeId: number;
  canWrite: boolean;
}

export default function PixPaymentsPanel({ storeId, canWrite }: PixPaymentsPanelProps) {
  const [available, setAvailable] = useState(false);
  const [connection, setConnection] = useState<PaymentConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [creating, setCreating] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [accessToken, setAccessToken] = useState("");
  const [environment, setEnvironment] = useState<"sandbox" | "production">("sandbox");
  const [amount, setAmount] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [cpf, setCpf] = useState("");
  const [payment, setPayment] = useState<PaymentTransaction | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const providers = await getPaymentProviders(storeId);
      const mercadoPago = providers.providers.find(
        (provider) => provider.code === "mercado_pago" && provider.payment_methods.includes("pix"),
      );
      setAvailable(Boolean(mercadoPago));

      if (mercadoPago) {
        setConnection(await getPaymentStatus(storeId, "mercado_pago"));
      } else {
        setConnection(null);
      }
    } catch (err) {
      setAvailable(false);
      setConnection(null);
      setError(formatError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [storeId]);

  async function handleConnect(event: FormEvent) {
    event.preventDefault();
    const token = accessToken.trim();
    if (!token) {
      setError("El Access Token de Mercado Pago es obligatorio.");
      return;
    }

    setConnecting(true);
    setError("");
    setSuccess("");
    try {
      await connectMercadoPagoPix(storeId, token, environment);
      setAccessToken("");
      setSuccess("Mercado Pago / PIX conectado correctamente.");
      await load();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    setDisconnecting(true);
    setError("");
    setSuccess("");
    try {
      await disconnectMercadoPagoPix(storeId);
      setPayment(null);
      setSuccess("Mercado Pago desconectado.");
      await load();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setDisconnecting(false);
    }
  }

  async function handleCreatePix(event: FormEvent) {
    event.preventDefault();
    const parsedAmount = Number(amount.replace(",", "."));
    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      setError("Ingresa un valor PIX válido mayor que cero.");
      return;
    }
    if (!email.trim() || !cpf.trim() || !phone.trim()) {
      setError("Email, CPF y teléfono son obligatorios para crear el PIX.");
      return;
    }

    setCreating(true);
    setError("");
    setSuccess("");
    try {
      const result = await createPixPayment(storeId, {
        amount: parsedAmount,
        customer_phone: phone.trim(),
        customer_email: email.trim(),
        customer_document: cpf.trim(),
      });
      setPayment(result);
      setSuccess("PIX creado. El cliente ya puede escanear o copiar el código.");
    } catch (err) {
      setError(formatError(err));
    } finally {
      setCreating(false);
    }
  }

  async function handleReconcile() {
    if (!payment) return;
    setReconciling(true);
    setError("");
    try {
      setPayment(await reconcilePayment(storeId, payment.id));
    } catch (err) {
      setError(formatError(err));
    } finally {
      setReconciling(false);
    }
  }

  async function copyPix() {
    const value = payment?.action_data?.qr_code;
    if (!value) return;
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  if (loading) {
    return (
      <div className="store-integrations loading">
        <Loader2 className="spin" size={16} />
        <span>Cargando métodos de pago…</span>
      </div>
    );
  }

  if (!available) {
    return (
      <div className="store-integration-block">
        <div className="store-integration-title">
          <CreditCard size={17} />
          <strong>PIX</strong>
          <span className="integration-status disconnected">No disponible</span>
        </div>
        <div className="store-integration-detail">
          PIX solo está disponible para tiendas configuradas en Brasil con moneda BRL.
        </div>
      </div>
    );
  }

  return (
    <div className="store-integrations">
      {error && <div className="stores-alert error">{error}</div>}
      {success && (
        <div className="stores-alert success">
          <Check size={15} /> {success}
        </div>
      )}

      <div className="store-integration-block">
        <div className="store-integration-header">
          <div className="store-integration-title">
            <CreditCard size={17} />
            <strong>Mercado Pago / PIX</strong>
            <span className={connection?.connected ? "integration-status connected" : "integration-status disconnected"}>
              {connection?.connected ? "Conectado" : "Desconectado"}
            </span>
          </div>
        </div>

        <div className="store-integration-detail">
          PIX para Brasil (BRL). El token se guarda cifrado y nunca se vuelve a mostrar.
        </div>

        {!connection?.connected && canWrite && (
          <form className="store-integration-whatsapp-form" onSubmit={handleConnect}>
            <label>
              <span>Entorno</span>
              <select value={environment} onChange={(event) => setEnvironment(event.target.value as "sandbox" | "production")}>
                <option value="sandbox">Sandbox</option>
                <option value="production">Producción</option>
              </select>
            </label>
            <label>
              <span>Mercado Pago Access Token</span>
              <input
                type="password"
                value={accessToken}
                onChange={(event) => setAccessToken(event.target.value)}
                placeholder="APP_USR-…"
                autoComplete="off"
              />
            </label>
            <button className="store-integration-button primary" type="submit" disabled={connecting}>
              {connecting ? <Loader2 className="spin" size={15} /> : <Plug size={15} />}
              Conectar PIX
            </button>
          </form>
        )}

        {connection?.connected && canWrite && (
          <div className="store-integration-actions">
            <button className="store-integration-button danger" type="button" onClick={handleDisconnect} disabled={disconnecting}>
              {disconnecting ? <Loader2 className="spin" size={15} /> : <Trash2 size={15} />}
              Desconectar
            </button>
          </div>
        )}
      </div>

      {connection?.connected && canWrite && (
        <div className="store-integration-block">
          <div className="store-integration-title">
            <CreditCard size={17} />
            <strong>Crear PIX</strong>
          </div>
          <form className="store-integration-whatsapp-form" onSubmit={handleCreatePix}>
            <input inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="Valor en BRL, ej. 49.90" />
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email del cliente" />
            <input value={cpf} onChange={(event) => setCpf(event.target.value)} placeholder="CPF" inputMode="numeric" />
            <input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="Teléfono +55…" />
            <button className="store-integration-button primary" type="submit" disabled={creating}>
              {creating ? <Loader2 className="spin" size={15} /> : <CreditCard size={15} />}
              Generar PIX
            </button>
          </form>
        </div>
      )}

      {payment && (
        <div className="store-integration-block">
          <div className="store-integration-title">
            <strong>PIX #{payment.id}</strong>
            <span className={payment.status === "paid" ? "integration-status connected" : "integration-status disconnected"}>
              {payment.status}
            </span>
          </div>

          {payment.action_data?.qr_code_base64 && (
            <div style={{ marginTop: 12 }}>
              <img
                src={`data:image/png;base64,${payment.action_data.qr_code_base64}`}
                alt="QR PIX"
                style={{ width: 220, maxWidth: "100%", borderRadius: 12 }}
              />
            </div>
          )}

          {payment.action_data?.qr_code && (
            <div className="store-integration-webhook" style={{ marginTop: 12 }}>
              <code style={{ overflowWrap: "anywhere" }}>{payment.action_data.qr_code}</code>
              <button className="store-integration-copy" type="button" onClick={copyPix} title="Copiar PIX">
                {copied ? <Check size={15} /> : <Copy size={15} />}
              </button>
            </div>
          )}

          <div className="store-integration-actions">
            <button className="store-integration-button secondary" type="button" onClick={handleReconcile} disabled={reconciling}>
              {reconciling ? <Loader2 className="spin" size={15} /> : <RefreshCw size={15} />}
              Actualizar estado
            </button>
            {payment.action_data?.ticket_url && (
              <a className="store-integration-button secondary" href={payment.action_data.ticket_url} target="_blank" rel="noreferrer">
                <ExternalLink size={15} /> Abrir pago
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function formatError(err: unknown): string {
  const value = err as {
    response?: { data?: { detail?: string | { message?: string } } };
    message?: string;
  };
  const detail = value.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && detail.message) return detail.message;
  return value.message || "No fue posible completar la operación de PIX.";
}
