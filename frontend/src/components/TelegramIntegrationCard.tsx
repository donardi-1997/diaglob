import { useEffect, useState, type FormEvent } from "react";
import { Bot, Check, Loader2, Plug, Trash2 } from "lucide-react";

import {
  connectTelegram,
  disconnectTelegram,
  getTelegramStatus,
  type TelegramConnectionStatus,
} from "../services/telegram";

interface TelegramIntegrationCardProps {
  storeId: number;
  canWrite: boolean;
}

export default function TelegramIntegrationCard({
  storeId,
  canWrite,
}: TelegramIntegrationCardProps) {
  const [status, setStatus] = useState<TelegramConnectionStatus | null>(null);
  const [botToken, setBotToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function load() {
    try {
      setLoading(true);
      setStatus(await getTelegramStatus(storeId));
      setError("");
    } catch (err: any) {
      setError(formatError(err) || "No pudimos cargar Telegram.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [storeId]);

  async function handleConnect(event: FormEvent) {
    event.preventDefault();
    const token = botToken.trim();
    if (!token) {
      setError("Pega el Bot Token entregado por @BotFather.");
      return;
    }

    try {
      setConnecting(true);
      setError("");
      setSuccess("");
      await connectTelegram(storeId, token);
      setBotToken("");
      setSuccess("Telegram quedó conectado y el webhook fue registrado.");
      await load();
    } catch (err: any) {
      setError(formatError(err) || "No pudimos conectar el bot de Telegram.");
    } finally {
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    try {
      setDisconnecting(true);
      setError("");
      setSuccess("");
      await disconnectTelegram(storeId);
      setSuccess("Telegram fue desconectado.");
      await load();
    } catch (err: any) {
      setError(formatError(err) || "No pudimos desconectar Telegram.");
    } finally {
      setDisconnecting(false);
    }
  }

  return (
    <div className="store-integration-block telegram">
      <div className="store-integration-header">
        <div className="store-integration-title">
          <Bot size={17} />
          <strong>Telegram</strong>
          <span
            className={
              status?.connected
                ? "integration-status connected"
                : "integration-status disconnected"
            }
          >
            {status?.connected ? "Conectado" : "Desconectado"}
          </span>
        </div>
      </div>

      {loading ? (
        <div className="store-integration-detail">
          <Loader2 className="spin" size={14} />
          <span>Cargando Telegram...</span>
        </div>
      ) : status?.connected ? (
        <>
          <div className="store-integration-detail">
            <Bot size={14} />
            <span>
              {status.bot_name || "Telegram Bot"}
              {status.bot_username ? ` — @${status.bot_username}` : ""}
            </span>
          </div>
          <div className="store-integration-detail">
            <span>
              Los mensajes privados de texto entran a Conversaciones y pueden ser
              respondidos por un agente o por la IA de Diaglob.
            </span>
          </div>
        </>
      ) : (
        <div className="store-integration-detail">
          <span>
            Crea un bot con @BotFather, copia su Bot Token y pégalo aquí. Diaglob
            valida el bot y registra el webhook automáticamente.
          </span>
        </div>
      )}

      {error && <div className="stores-alert error">{error}</div>}
      {success && (
        <div className="stores-alert success">
          <Check size={15} />
          {success}
        </div>
      )}

      {canWrite && status?.connected && (
        <div className="store-integration-actions">
          <button
            type="button"
            className="store-integration-button danger"
            onClick={() => void handleDisconnect()}
            disabled={disconnecting}
          >
            {disconnecting
              ? <Loader2 className="spin" size={15} />
              : <Trash2 size={15} />}
            Desconectar
          </button>
        </div>
      )}

      {canWrite && !status?.connected && !loading && (
        <form className="store-integration-whatsapp-form" onSubmit={handleConnect}>
          <input
            type="password"
            value={botToken}
            onChange={(event) => setBotToken(event.target.value)}
            placeholder="Bot Token de @BotFather"
            autoComplete="off"
          />
          <button
            type="submit"
            className="store-integration-button primary"
            disabled={connecting}
          >
            {connecting
              ? <Loader2 className="spin" size={15} />
              : <Plug size={15} />}
            Conectar Telegram
          </button>
        </form>
      )}
    </div>
  );
}

function formatError(err: any): string {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (detail?.message) {
    return detail.message;
  }
  return "";
}
