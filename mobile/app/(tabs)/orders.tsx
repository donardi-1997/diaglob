import {
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Badge,
  Card,
  EmptyState,
  LoadingState,
  PageHeader,
  Screen,
} from "../../src/components/Ui";
import {
  listCommerceOrders,
  type CommerceOrder,
} from "../../src/services/commerce";
import { useSession } from "../../src/providers/SessionProvider";
import { colors, spacing } from "../../src/theme";

function statusTone(status: string | null) {
  if (status === "failed") return "danger" as const;
  if (status === "pending") return "warning" as const;
  if (status === "created") return "success" as const;
  return "neutral" as const;
}

export default function OrdersScreen() {
  const { store } = useSession();
  const [orders, setOrders] = useState<CommerceOrder[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(
    async (refresh = false) => {
      if (!store) {
        setOrders([]);
        setLoading(false);
        return;
      }

      refresh ? setRefreshing(true) : setLoading(true);
      setError("");

      try {
        const result = await listCommerceOrders(store.id);
        setOrders(result.items);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "No fue posible cargar los pedidos.",
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

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return orders;

    return orders.filter((order) =>
      [
        order.order_number,
        order.source || "",
        order.financial_status || "",
        order.fulfillment_status || "",
      ].some((value) =>
        value.toLowerCase().includes(normalized),
      ),
    );
  }, [orders, query]);

  if (loading) {
    return (
      <Screen>
        <PageHeader
          eyebrow="COMERCIO"
          title="Pedidos"
          subtitle={store?.name}
        />
        <LoadingState />
      </Screen>
    );
  }

  return (
    <Screen>
      <FlatList
        data={filtered}
        keyExtractor={(item) => String(item.id)}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void load(true)}
            tintColor={colors.accent}
          />
        }
        contentContainerStyle={styles.content}
        ListHeaderComponent={
          <>
            <PageHeader
              eyebrow="COMERCIO"
              title="Pedidos"
              subtitle={
                store
                  ? `${orders.length} pedidos · ${store.name}`
                  : undefined
              }
            />
            <View style={styles.searchWrap}>
              <TextInput
                value={query}
                onChangeText={setQuery}
                placeholder="Buscar pedido, estado o fuente"
                placeholderTextColor="#98A2B3"
                style={styles.search}
              />
            </View>
            {error ? (
              <Text style={styles.error}>{error}</Text>
            ) : null}
          </>
        }
        ListEmptyComponent={
          <EmptyState
            title={
              query
                ? "No encontramos pedidos"
                : "No hay pedidos"
            }
            body={
              query
                ? "Prueba otra búsqueda."
                : "Los pedidos sincronizados aparecerán aquí."
            }
          />
        }
        renderItem={({ item }) => (
          <Card style={styles.card}>
            <View style={styles.row}>
              <Text style={styles.number}>
                #{item.order_number}
              </Text>
              <Badge
                label={
                  item.external_creation_status ||
                  "desconocido"
                }
                tone={statusTone(
                  item.external_creation_status,
                )}
              />
            </View>

            <Text style={styles.amount}>
              {item.currency}{" "}
              {item.total_amount.toLocaleString()}
            </Text>

            <View style={styles.details}>
              <Text style={styles.detail}>
                Pago: {item.financial_status || "—"}
              </Text>
              <Text style={styles.detail}>
                Fulfillment:{" "}
                {item.fulfillment_status || "—"}
              </Text>
              <Text style={styles.detail}>
                Fuente: {item.source || "—"}
              </Text>
            </View>
          </Card>
        )}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingBottom: spacing.xl,
  },
  searchWrap: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.md,
  },
  search: {
    minHeight: 48,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    backgroundColor: colors.surface,
    color: colors.text,
  },
  error: {
    marginHorizontal: spacing.md,
    marginBottom: spacing.md,
    color: colors.danger,
    fontSize: 12,
  },
  card: {
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    padding: spacing.md,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  number: {
    flex: 1,
    color: colors.text,
    fontSize: 14,
    fontWeight: "800",
  },
  amount: {
    marginTop: spacing.sm,
    color: colors.text,
    fontSize: 20,
    fontWeight: "800",
  },
  details: {
    marginTop: spacing.sm,
    gap: 3,
  },
  detail: {
    color: colors.textMuted,
    fontSize: 11,
  },
});
