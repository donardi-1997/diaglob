import {
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useCallback, useEffect, useState } from "react";

import {
  Card,
  EmptyState,
  LoadingState,
  MetricCard,
  PageHeader,
  Screen,
  Badge,
} from "../../src/components/Ui";
import {
  getCommerceSummary,
  type CommerceSummary,
} from "../../src/services/commerce";
import {
  getCustomerSummary,
  type CustomerSummary,
} from "../../src/services/customers";
import { useSession } from "../../src/providers/SessionProvider";
import { colors, spacing } from "../../src/theme";

function money(value: number, currency: string) {
  try {
    return new Intl.NumberFormat("es-CO", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${currency} ${Math.round(value).toLocaleString()}`;
  }
}

function orderTone(status: string | null) {
  if (status === "failed") return "danger" as const;
  if (status === "pending") return "warning" as const;
  if (status === "created") return "success" as const;
  return "neutral" as const;
}

export default function HomeScreen() {
  const { store } = useSession();
  const [commerce, setCommerce] =
    useState<CommerceSummary | null>(null);
  const [customers, setCustomers] =
    useState<CustomerSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(
    async (refresh = false) => {
      if (!store) {
        setCommerce(null);
        setCustomers(null);
        setLoading(false);
        return;
      }

      refresh ? setRefreshing(true) : setLoading(true);
      setError("");

      try {
        const [commerceResult, customerResult] =
          await Promise.all([
            getCommerceSummary(store.id),
            getCustomerSummary(store.id),
          ]);

        setCommerce(commerceResult);
        setCustomers(customerResult);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "No fue posible cargar el resumen.",
        );
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [store],
  );

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <Screen>
        <PageHeader
          eyebrow="DIAGLOB MOBILE"
          title="Inicio"
          subtitle={store?.name}
        />
        <LoadingState label="Leyendo tu operación..." />
      </Screen>
    );
  }

  if (!store) {
    return (
      <Screen>
        <PageHeader
          eyebrow="DIAGLOB MOBILE"
          title="Inicio"
        />
        <EmptyState
          title="No hay una tienda activa"
          body="Configura una tienda en Diaglob web para comenzar."
        />
      </Screen>
    );
  }

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void load(true)}
            tintColor={colors.accent}
          />
        }
      >
        <PageHeader
          eyebrow="OPERACIÓN"
          title="Hoy en Diaglob"
          subtitle={store.name}
        />

        {error ? (
          <Text style={styles.error}>{error}</Text>
        ) : null}

        {commerce ? (
          <>
            <View style={styles.metrics}>
              <MetricCard
                label="Pedidos"
                value={String(commerce.total_orders)}
              />
              <MetricCard
                label="Valor total"
                value={money(
                  commerce.total_order_value,
                  commerce.currency || store.currency,
                )}
                tone="success"
              />
              <MetricCard
                label="Pendientes"
                value={String(
                  commerce.orders_by_status.pending,
                )}
                tone="warning"
              />
              <MetricCard
                label="Fallidos"
                value={String(
                  commerce.orders_by_status.failed,
                )}
                tone="danger"
              />
            </View>

            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>
                Atención
              </Text>
              <Text style={styles.sectionMeta}>
                Clientes
              </Text>
            </View>

            <View style={styles.metrics}>
              <MetricCard
                label="Requieren seguimiento"
                value={String(
                  customers?.needs_followup || 0,
                )}
                tone="warning"
              />
              <MetricCard
                label="En riesgo"
                value={String(
                  customers?.at_risk || 0,
                )}
                tone="danger"
              />
            </View>

            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>
                Pedidos recientes
              </Text>
            </View>

            {commerce.recent_orders.length === 0 ? (
              <EmptyState
                title="Aún no hay pedidos"
                body="Cuando entren pedidos aparecerán aquí."
              />
            ) : (
              commerce.recent_orders.map((order) => (
                <Card
                  key={order.id}
                  style={styles.orderCard}
                >
                  <View style={styles.orderTop}>
                    <Text style={styles.orderNumber}>
                      #{order.order_number}
                    </Text>
                    <Badge
                      label={
                        order.external_creation_status ||
                        "desconocido"
                      }
                      tone={orderTone(
                        order.external_creation_status,
                      )}
                    />
                  </View>
                  <Text style={styles.orderAmount}>
                    {money(
                      order.total_amount,
                      order.currency,
                    )}
                  </Text>
                  <Text style={styles.orderMeta}>
                    {order.source || "Sin fuente"}
                  </Text>
                </Card>
              ))
            )}
          </>
        ) : null}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingBottom: spacing.xl,
  },
  error: {
    marginHorizontal: spacing.md,
    marginBottom: spacing.md,
    color: colors.danger,
    fontSize: 12,
  },
  metrics: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  sectionHeader: {
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
    paddingHorizontal: spacing.md,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  sectionTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: "800",
  },
  sectionMeta: {
    color: colors.textMuted,
    fontSize: 11,
  },
  orderCard: {
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    padding: spacing.md,
  },
  orderTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  orderNumber: {
    flex: 1,
    color: colors.text,
    fontSize: 14,
    fontWeight: "800",
  },
  orderAmount: {
    marginTop: spacing.sm,
    color: colors.text,
    fontSize: 18,
    fontWeight: "800",
  },
  orderMeta: {
    marginTop: 4,
    color: colors.textMuted,
    fontSize: 11,
  },
});
