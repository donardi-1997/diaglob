import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { AutomationCampaignPayload } from "../services/automations";
import {
  listClassifiedAudienceCustomers,
  type ClassifiedAudienceCustomer,
} from "../services/customerClassifications";
import {
  CLASSIFICATION_KEYS,
  VALUE_TIER_KEYS,
  classificationLabel,
  classificationLocale,
  valueTierLabel,
} from "../utils/customerClassification";
import "../automation-customer-classification.css";

type Filters = {
  search: string;
  segment: string;
  classification: string;
  value_tier: string;
  priority: string;
  health: string;
  country: string;
  needs_attention?: boolean;
};

interface Props {
  storeId: number;
  value: AutomationCampaignPayload;
  onChange: (
    value: Pick<
      AutomationCampaignPayload,
      | "member_ids"
      | "selection_mode"
      | "selected_customer_ids"
      | "excluded_customer_ids"
      | "audience_filters"
    >,
  ) => void;
}

const emptyFilters: Filters = {
  search: "",
  segment: "",
  classification: "",
  value_tier: "",
  priority: "",
  health: "",
  country: "",
};

const label = (value: string | null) =>
  value
    ? value
        .replaceAll("_", " ")
        .replace(/\b\w/g, (letter) => letter.toUpperCase())
    : "-";

const toAudienceFilters = (filters: Filters) => ({
  ...(filters.search ? { search: filters.search } : {}),
  ...(filters.segment ? { segment: [filters.segment] } : {}),
  ...(filters.classification
    ? { classification: [filters.classification] }
    : {}),
  ...(filters.value_tier ? { value_tier: [filters.value_tier] } : {}),
  ...(filters.priority ? { priority: [filters.priority] } : {}),
  ...(filters.health ? { health: [filters.health] } : {}),
  ...(filters.country ? { country_codes: [filters.country] } : {}),
});

export default function AutomationAudienceSelector({
  storeId,
  value,
  onChange,
}: Props) {
  const { t, i18n } = useTranslation();
  const locale = classificationLocale(
    i18n.resolvedLanguage || i18n.language || "es",
  );
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [rows, setRows] = useState<ClassifiedAudienceCustomer[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  const selected = new Set(value.selected_customer_ids ?? value.member_ids);
  const excluded = new Set(value.excluded_customer_ids ?? []);
  const allFiltered = value.selection_mode === "all_filtered";
  const selectedCount = allFiltered
    ? Math.max(0, total - excluded.size)
    : selected.size;

  const send = (next: Partial<AutomationCampaignPayload>) =>
    onChange({
      member_ids: next.member_ids ?? [...selected],
      selection_mode:
        next.selection_mode ?? (allFiltered ? "all_filtered" : "explicit"),
      selected_customer_ids: next.selected_customer_ids ?? [...selected],
      excluded_customer_ids: next.excluded_customer_ids ?? [...excluded],
      audience_filters: next.audience_filters ?? value.audience_filters,
    });

  const load = async () => {
    setLoading(true);
    setFailed(false);
    try {
      const result = await listClassifiedAudienceCustomers(storeId, {
        ...filters,
        page,
        page_size: pageSize,
      });
      setRows(result.items);
      setTotal(result.total);
      setTotalPages(result.total_pages);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [storeId, page, pageSize]);

  useEffect(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      setPage(1);
      void load();
    }, 300);
    return () => window.clearTimeout(timer.current);
  }, [filters]);

  const updateFilters = (next: Filters) => {
    if (allFiltered && !window.confirm(t("autoAudienceFiltersReset"))) return;
    if (allFiltered) {
      send({
        selection_mode: "explicit",
        selected_customer_ids: [],
        excluded_customer_ids: [],
        member_ids: [],
        audience_filters: toAudienceFilters(next),
      });
    } else {
      send({ audience_filters: toAudienceFilters(next) });
    }
    setFilters(next);
  };

  const toggle = (customer: ClassifiedAudienceCustomer) => {
    if (allFiltered) {
      if (excluded.has(customer.customer_id)) excluded.delete(customer.customer_id);
      else excluded.add(customer.customer_id);
      send({ excluded_customer_ids: [...excluded] });
    } else {
      if (selected.has(customer.customer_id)) selected.delete(customer.customer_id);
      else selected.add(customer.customer_id);
      send({
        member_ids: [...selected],
        selected_customer_ids: [...selected],
      });
    }
  };

  const visibleSelected = rows.filter((row) =>
    allFiltered
      ? !excluded.has(row.customer_id)
      : selected.has(row.customer_id),
  );

  const togglePage = () => {
    const shouldSelect = visibleSelected.length !== rows.length;
    if (allFiltered) {
      rows.forEach((row) =>
        shouldSelect
          ? excluded.delete(row.customer_id)
          : excluded.add(row.customer_id),
      );
    } else {
      rows.forEach((row) =>
        shouldSelect
          ? selected.add(row.customer_id)
          : selected.delete(row.customer_id),
      );
    }
    send(
      allFiltered
        ? { excluded_customer_ids: [...excluded] }
        : {
            member_ids: [...selected],
            selected_customer_ids: [...selected],
          },
    );
  };

  const classificationFilterLabel =
    locale === "en"
      ? "All classifications"
      : locale === "pt-BR"
        ? "Todas as classificações"
        : "Todas las clasificaciones";
  const valueTierFilterLabel =
    locale === "en"
      ? "All value tiers"
      : locale === "pt-BR"
        ? "Todos os níveis de valor"
        : "Todos los niveles de valor";
  const classificationColumn =
    locale === "en"
      ? "Value classification"
      : locale === "pt-BR"
        ? "Classificação de valor"
        : "Clasificación de valor";

  return (
    <div className="automation-audience-selector">
      <div className="automation-selector-summary">
        <strong>{t("autoSelectedCustomers", { count: selectedCount })}</strong>
        {allFiltered && (
          <span>{t("autoAllFilteredExcept", { count: excluded.size })}</span>
        )}
        <button
          type="button"
          className="text-button"
          onClick={() => {
            send({
              selection_mode: "explicit",
              member_ids: [],
              selected_customer_ids: [],
              excluded_customer_ids: [],
            });
          }}
        >
          {t("autoClearSelection")}
        </button>
      </div>

      <div className="automation-selector-filters">
        <input
          aria-label={t("autoSearchCustomers")}
          placeholder={t("autoSearchCustomers")}
          value={filters.search}
          onChange={(event) =>
            updateFilters({ ...filters, search: event.target.value })
          }
        />
        <select
          value={filters.segment}
          onChange={(event) =>
            updateFilters({ ...filters, segment: event.target.value })
          }
        >
          <option value="">{t("autoAllSegments")}</option>
          {["new", "interested", "high_intent", "buyer", "repeat_buyer", "vip", "inactive"].map(
            (item) => (
              <option key={item} value={item}>{label(item)}</option>
            ),
          )}
        </select>
        <select
          value={filters.classification}
          onChange={(event) =>
            updateFilters({ ...filters, classification: event.target.value })
          }
        >
          <option value="">{classificationFilterLabel}</option>
          {CLASSIFICATION_KEYS.map((item) => (
            <option key={item} value={item}>
              {classificationLabel(item, locale)}
            </option>
          ))}
        </select>
        <select
          value={filters.value_tier}
          onChange={(event) =>
            updateFilters({ ...filters, value_tier: event.target.value })
          }
        >
          <option value="">{valueTierFilterLabel}</option>
          {VALUE_TIER_KEYS.map((item) => (
            <option key={item} value={item}>{valueTierLabel(item, locale)}</option>
          ))}
        </select>
        <select
          value={filters.priority}
          onChange={(event) =>
            updateFilters({ ...filters, priority: event.target.value })
          }
        >
          <option value="">{t("autoAllPriorities")}</option>
          {["high", "medium", "low"].map((item) => (
            <option key={item} value={item}>{label(item)}</option>
          ))}
        </select>
        <select
          value={filters.health}
          onChange={(event) =>
            updateFilters({ ...filters, health: event.target.value })
          }
        >
          <option value="">{t("autoAllHealth")}</option>
          {["active", "at_risk", "inactive"].map((item) => (
            <option key={item} value={item}>{label(item)}</option>
          ))}
        </select>
        <input
          aria-label={t("autoCountry")}
          placeholder={t("autoCountry")}
          maxLength={2}
          value={filters.country}
          onChange={(event) =>
            updateFilters({
              ...filters,
              country: event.target.value.toUpperCase(),
            })
          }
        />
      </div>

      {loading ? (
        <p>{t("autoAudienceLoading")}</p>
      ) : failed ? (
        <button type="button" onClick={() => void load()}>{t("autoRetry")}</button>
      ) : (
        <>
          <div className="automation-selector-actions">
            <label>
              <input
                type="checkbox"
                aria-label={t("autoSelectPage")}
                checked={rows.length > 0 && visibleSelected.length === rows.length}
                ref={(input) => {
                  if (input) {
                    input.indeterminate =
                      visibleSelected.length > 0 &&
                      visibleSelected.length < rows.length;
                  }
                }}
                onChange={togglePage}
              />
              {t("autoSelectPage")}
            </label>
            {!allFiltered && total > rows.length && (
              <button
                type="button"
                className="text-button"
                onClick={() =>
                  send({
                    selection_mode: "all_filtered",
                    selected_customer_ids: [],
                    member_ids: [],
                    excluded_customer_ids: [],
                  })
                }
              >
                {t("autoSelectAllFiltered", { count: total })}
              </button>
            )}
          </div>

          <div className="automation-selector-table-wrap">
            <table className="automation-selector-table">
              <thead>
                <tr>
                  <th />
                  <th>{t("autoCustomer")}</th>
                  <th>{t("autoSegment")}</th>
                  <th>{classificationColumn}</th>
                  <th>{t("autoPriority")}</th>
                  <th>{t("autoScore")}</th>
                  <th>{t("autoHealth")}</th>
                  <th>{t("autoLastInteraction")}</th>
                  <th>{t("autoOrders")}</th>
                  <th>{t("autoSpend")}</th>
                  <th>{t("autoCountry")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const checked = allFiltered
                    ? !excluded.has(row.customer_id)
                    : selected.has(row.customer_id);
                  return (
                    <tr key={row.customer_id}>
                      <td>
                        <input
                          type="checkbox"
                          aria-label={row.name}
                          checked={checked}
                          onChange={() => toggle(row)}
                        />
                      </td>
                      <td><strong>{row.name}</strong><small>{row.email || row.phone}</small></td>
                      <td>{label(row.primary_segment)}</td>
                      <td>
                        <span className={`automation-classification-badge is-${row.commercial_classification}`}>
                          {classificationLabel(row.commercial_classification, locale)}
                        </span>
                        <small>{valueTierLabel(row.value_tier, locale)} · RFM {row.rfm_score}/15</small>
                      </td>
                      <td>{label(row.priority)}</td>
                      <td>{row.customer_score}</td>
                      <td>{label(row.customer_health)}</td>
                      <td>{row.last_interaction_at ? new Date(row.last_interaction_at).toLocaleDateString() : "-"}</td>
                      <td>{row.successful_order_count}</td>
                      <td>{Object.entries(row.spend_by_currency).map(([currency, spend]) => `${currency} ${spend.total}`).join(" · ")}</td>
                      <td>{row.country_code}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {!rows.length && <p>{t("autoAudienceEmpty")}</p>}

          <div className="automation-selector-pagination">
            <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t("autoPrevious")}</button>
            <span>{page} / {totalPages}</span>
            <select
              value={pageSize}
              onChange={(event) => {
                setPageSize(Number(event.target.value));
                setPage(1);
              }}
            >
              {[25, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}
            </select>
            <button type="button" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>{t("autoNext")}</button>
          </div>
        </>
      )}
    </div>
  );
}
