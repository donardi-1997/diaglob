import {
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useCallback, useEffect, useState } from "react";

import {
  Badge,
  Card,
  EmptyState,
  LoadingState,
  PageHeader,
  Screen,
} from "../../src/components/Ui";
import {
  getCustomerList,
  type CustomerItem,
} from "../../src/services/customers";
import { useSession } from "../../src/providers/SessionProvider";
import { colors, spacing } from "../../src/theme";

function healthTone(health: string) {
  const normalized = health.toLowerCase();
  if (normalized.includes("risk")) return "danger" as const;
  if (normalized.includes("active")) return "success" as const;
  return "neutral" as const;
}

export default function CustomersScreen() {
  const { store } = useSession();
  const [customers, setCustomers] = useState<CustomerItem[]>([]);
  const [draftSearch, setDraftSearch] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(
    async (refresh = false) => {
      if (!store) {
        setCustomers([]);
        setLoading(false);
        return;
      }

      refresh ? setRefreshing(true) : setLoading(true);
      setError("");

      try {
        const result = await getCustomerList(
          store.id,
          search,
        );
        setCustomers(result.items);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "No fue posible cargar clientes.",
        );
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [store, search],
  );

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <Screen>
        <PageHeader
          eyebrow="CLIENTES"
          title="Clientes"
          subtitle={store?.name}
        />
        <LoadingState />
      </Screen>
    );
  }

  return (
    <Screen>
      <FlatList
        data={customers}
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
              eyebrow="CLIENTES"
              title="Clientes"
              subtitle={store?.name}
            />
            <View style={styles.searchWrap}>
              <TextInput
                value={draftSearch}
                onChangeText={setDraftSearch}
                placeholder="Nombre, correo o teléfono"
                placeholderTextColor="#98A2B3"
                returnKeyType="search"
                onSubmitEditing={() =>
                  setSearch(draftSearch.trim())
                }
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
            title="No encontramos clientes"
            body={
              search
                ? "Prueba otra búsqueda."
                : "Los clientes aparecerán cuando exista actividad."
            }
          />
        }
        renderItem={({ item }) => (
          <Card style={styles.card}>
            <View style={styles.top}>
              <View style={styles.identity}>
                <Text style={styles.name}>
                  {item.name || item.phone}
                </Text>
                <Text style={styles.contact}>
                  {item.email || item.phone}
                </Text>
              </View>
              {item.needs_attention ? (
                <Badge
                  label="Atención"
                  tone="warning"
                />
              ) : null}
            </View>

            <View style={styles.badges}>
              <Badge
                label={item.primary_segment || "sin segmento"}
                tone="accent"
              />
              <Badge
                label={item.customer_health || "sin estado"}
                tone={healthTone(
                  item.customer_health || "",
                )}
              />
            </View>

            <View style={styles.stats}>
              <Text style={styles.stat}>
                {item.successful_order_count} pedidos
              </Text>
              <Text style={styles.stat}>
                Score {Math.round(item.customer_score)}
              </Text>
              <Text style={styles.stat}>
                {item.priority || "prioridad normal"}
              </Text>
            </View>

            {item.next_best_action ? (
              <Text style={styles.action}>
                Siguiente acción: {item.next_best_action}
              </Text>
            ) : null}
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
  top: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
  },
  identity: {
    flex: 1,
  },
  name: {
    color: colors.text,
    fontSize: 15,
    fontWeight: "800",
  },
  contact: {
    marginTop: 3,
    color: colors.textMuted,
    fontSize: 11,
  },
  badges: {
    marginTop: spacing.sm,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
  },
  stats: {
    marginTop: spacing.sm,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  stat: {
    color: colors.textMuted,
    fontSize: 11,
  },
  action: {
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    color: colors.text,
    fontSize: 11,
    lineHeight: 16,
  },
});
