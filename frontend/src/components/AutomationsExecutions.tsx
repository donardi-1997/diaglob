import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import {
  ExternalLink,
  LoaderCircle,
  X,
} from "lucide-react";
import {
  listAllAutomationExecutions,
  type AutomationExecution,
} from "../services/automations";


interface AutomationsExecutionsProps {
  canWrite: boolean;
  storeId: number;
}


function getStatusClass(
  status: string,
): string {
  return status;
}


function formatDuration(
  started: string | null,
  completed: string | null,
): string {
  if (!started || !completed) return "—";

  const start = new Date(started).getTime();
  const end = new Date(completed).getTime();
  const ms = end - start;

  if (ms < 1000) return `${ms}ms`;

  return `${(ms / 1000).toFixed(1)}s`;
}


export default function AutomationsExecutions({
  canWrite: _canWrite,
  storeId,
}: AutomationsExecutionsProps) {
  const { t } = useTranslation();

  const [executions, setExecutions] =
    useState<AutomationExecution[]>([]);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");

  const [detailOpen, setDetailOpen] =
    useState(false);

  const [selected, setSelected] =
    useState<AutomationExecution | null>(null);


  useEffect(() => {
    loadData();
  }, [storeId]);


  async function loadData() {
    try {
      setLoading(true);
      setError("");

      const data =
        await listAllAutomationExecutions(storeId);

      setExecutions(data.items);
    } catch {
      setError(t("autoExecLoadError"));
    } finally {
      setLoading(false);
    }
  }


  function openDetail(
    exec: AutomationExecution,
  ) {
    setSelected(exec);
    setDetailOpen(true);
  }


  if (loading) {
    return (
      <div className="commerce-loading">
        <LoaderCircle
          className="spin"
          size={24}
        />
      </div>
    );
  }


  return (
    <div className="automations-executions">
      {error && (
        <div className="commerce-empty">
          <p>{error}</p>
        </div>
      )}

      {!error && executions.length === 0 && (
        <div className="commerce-empty">
          <p>{t("autoNoExecutions")}</p>
        </div>
      )}

      {executions.length > 0 && (
        <div className="commerce-orders-table-wrapper">
          <table className="commerce-orders-table">
            <thead>
              <tr>
                <th>
                  {t("autoExecAutomation")}
                </th>
                <th>
                  {t("autoExecEvent")}
                </th>
                <th>
                  {t("autoExecStatus")}
                </th>
                <th>
                  {t("autoExecStarted")}
                </th>
                <th>
                  {t("autoExecDuration")}
                </th>
                <th />
              </tr>
            </thead>
            <tbody>
              {executions.map((exec) => (
                <tr key={exec.id}>
                  <td className="commerce-order-number">
                    {exec.automation_name}
                  </td>

                  <td>
                    <span className="automation-trigger-badge">
                      {exec.event_type}
                    </span>
                  </td>

                  <td>
                    <span
                      className={
                        "automation-exec-status "
                        + getStatusClass(
                            exec.status,
                          )
                      }
                    >
                      {exec.status}
                    </span>
                  </td>

                  <td className="commerce-order-date">
                    {exec.started_at
                      ? new Date(
                          exec.started_at,
                        ).toLocaleString()
                      : "—"}
                  </td>

                  <td>
                    {formatDuration(
                      exec.started_at,
                      exec.completed_at,
                    )}
                  </td>

                  <td>
                    <button
                      className="commerce-link"
                      onClick={() =>
                        openDetail(exec)
                      }
                    >
                      <ExternalLink
                        size={14}
                      />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}


      {detailOpen && selected && (
        <div
          className="management-modal-backdrop"
          onMouseDown={() =>
            setDetailOpen(false)
          }
        >
          <div
            className="management-modal management-modal-lg"
            onMouseDown={(e) =>
              e.stopPropagation()
            }
          >
            <header className="management-modal-header">
              <div>
                <span className="eyebrow">
                  {t("autoExecDetail")}
                </span>
                <h2>
                  {selected.automation_name}
                </h2>
              </div>

              <button
                className="icon-button"
                onClick={() =>
                  setDetailOpen(false)
                }
              >
                <X size={18} />
              </button>
            </header>

            <div className="automation-detail-content">
              <div className="automation-detail-section">
                <strong>
                  {t("autoExecStatus")}
                </strong>

                <span
                  className={
                    "automation-exec-status "
                    + selected.status
                  }
                >
                  {selected.status}
                </span>
              </div>

              <div className="automation-detail-section">
                <strong>
                  {t("autoExecEvent")}
                </strong>

                <span>
                  {selected.event_type}
                </span>
              </div>

              <div className="automation-detail-section">
                <strong>
                  {t("autoExecStarted")}
                </strong>

                <span>
                  {selected.started_at
                    ? new Date(
                        selected.started_at,
                      ).toLocaleString()
                    : "—"}
                </span>
              </div>

              <div className="automation-detail-section">
                <strong>
                  {t("autoExecDuration")}
                </strong>

                <span>
                  {formatDuration(
                    selected.started_at,
                    selected.completed_at,
                  )}
                </span>
              </div>

              {selected.error_message && (
                <div className="automation-detail-section">
                  <strong>
                    {t("autoExecError")}
                  </strong>

                  <pre className="automation-error-text">
                    {
                      selected.error_message
                    }
                  </pre>
                </div>
              )}

              <div className="automation-detail-section">
                <strong>
                  {t("autoExecInput")}
                </strong>

                <pre>
                  {JSON.stringify(
                    selected.input_json,
                    null,
                    2,
                  )}
                </pre>
              </div>

              <div className="automation-detail-section">
                <strong>
                  {t("autoExecResult")}
                </strong>

                <pre>
                  {JSON.stringify(
                    selected.result_json,
                    null,
                    2,
                  )}
                </pre>
              </div>
            </div>

            <footer className="management-modal-actions">
              <button
                className="secondary-button"
                onClick={() =>
                  setDetailOpen(false)
                }
              >
                {t("autoClose")}
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
