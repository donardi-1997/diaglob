import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import {
  Badge,
  Card,
  PageHeader,
  Screen,
} from "../../src/components/Ui";
import { useSession } from "../../src/providers/SessionProvider";
import { colors, radius, spacing } from "../../src/theme";

export default function MoreScreen() {
  const {
    user,
    organization,
    stores,
    store,
    selectStore,
    logout,
  } = useSession();

  function confirmLogout() {
    Alert.alert(
      "Cerrar sesión",
      "¿Quieres salir de Diaglob Mobile?",
      [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Cerrar sesión",
          style: "destructive",
          onPress: () => void logout(),
        },
      ],
    );
  }

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={styles.content}
      >
        <PageHeader
          eyebrow="WORKSPACE"
          title="Más"
          subtitle="Cuenta, tienda y preferencias"
        />

        <Card style={styles.profile}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>
              {(user?.name || user?.email || "DG")
                .slice(0, 2)
                .toUpperCase()}
            </Text>
          </View>
          <View style={styles.profileCopy}>
            <Text style={styles.profileName}>
              {user?.name || "Diaglob"}
            </Text>
            <Text style={styles.profileEmail}>
              {user?.email}
            </Text>
            {organization ? (
              <Text style={styles.organization}>
                {organization.name} · {organization.role}
              </Text>
            ) : null}
          </View>
        </Card>

        <Text style={styles.sectionTitle}>
          Tienda activa
        </Text>

        <View style={styles.storeList}>
          {stores.map((item) => {
            const selected = item.id === store?.id;
            return (
              <Pressable
                key={item.id}
                onPress={() =>
                  void selectStore(item.id)
                }
              >
                <Card
                  style={[
                    styles.storeCard,
                    selected && styles.storeSelected,
                  ]}
                >
                  <View style={styles.storeCopy}>
                    <Text style={styles.storeName}>
                      {item.name}
                    </Text>
                    <Text style={styles.storeMeta}>
                      {item.country_code || "—"} ·{" "}
                      {item.currency}
                    </Text>
                  </View>
                  {selected ? (
                    <Badge
                      label="Activa"
                      tone="success"
                    />
                  ) : null}
                </Card>
              </Pressable>
            );
          })}
        </View>

        <Text style={styles.sectionTitle}>
          Sobre esta versión
        </Text>

        <Card style={styles.infoCard}>
          <Text style={styles.infoTitle}>
            Diaglob Mobile V0
          </Text>
          <Text style={styles.infoBody}>
            Inicio, pedidos, clientes y Copiloto conectados
            al mismo backend de Diaglob.
          </Text>
        </Card>

        <Pressable
          style={styles.logout}
          onPress={confirmLogout}
        >
          <Text style={styles.logoutText}>
            Cerrar sesión
          </Text>
        </Pressable>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingBottom: spacing.xl,
  },
  profile: {
    marginHorizontal: spacing.md,
    padding: spacing.md,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
  },
  avatar: {
    width: 48,
    height: 48,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 16,
    backgroundColor: colors.surfaceSoft,
  },
  avatarText: {
    color: colors.accent,
    fontSize: 15,
    fontWeight: "900",
  },
  profileCopy: {
    flex: 1,
  },
  profileName: {
    color: colors.text,
    fontSize: 15,
    fontWeight: "800",
  },
  profileEmail: {
    marginTop: 2,
    color: colors.textMuted,
    fontSize: 11,
  },
  organization: {
    marginTop: 5,
    color: colors.accent,
    fontSize: 10,
    fontWeight: "700",
  },
  sectionTitle: {
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
    paddingHorizontal: spacing.md,
    color: colors.text,
    fontSize: 15,
    fontWeight: "800",
  },
  storeList: {
    gap: spacing.sm,
  },
  storeCard: {
    marginHorizontal: spacing.md,
    padding: spacing.md,
    flexDirection: "row",
    alignItems: "center",
  },
  storeSelected: {
    borderColor: "#C9C1FF",
    backgroundColor: "#FBFAFF",
  },
  storeCopy: {
    flex: 1,
  },
  storeName: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "800",
  },
  storeMeta: {
    marginTop: 3,
    color: colors.textMuted,
    fontSize: 10,
  },
  infoCard: {
    marginHorizontal: spacing.md,
    padding: spacing.md,
  },
  infoTitle: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "800",
  },
  infoBody: {
    marginTop: 5,
    color: colors.textMuted,
    fontSize: 11,
    lineHeight: 17,
  },
  logout: {
    minHeight: 50,
    marginHorizontal: spacing.md,
    marginTop: spacing.xl,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#F7C7C3",
    borderRadius: radius.md,
    backgroundColor: "#FFF8F7",
  },
  logoutText: {
    color: colors.danger,
    fontSize: 13,
    fontWeight: "800",
  },
});
