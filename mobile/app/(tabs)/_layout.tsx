import { Redirect, Tabs } from "expo-router";
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { useSession } from "../../src/providers/SessionProvider";
import { colors } from "../../src/theme";

function TabIcon({
  symbol,
  color,
}: {
  symbol: string;
  color: string;
}) {
  return (
    <Text style={[styles.icon, { color }]}>
      {symbol}
    </Text>
  );
}

export default function TabsLayout() {
  const { ready, authenticated } = useSession();

  if (!ready) {
    return (
      <View style={styles.loading}>
        <ActivityIndicator color={colors.accent} />
      </View>
    );
  }

  if (!authenticated) {
    return <Redirect href="/login" />;
  }

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: "#98A2B3",
        tabBarStyle: styles.tabBar,
        tabBarLabelStyle: styles.tabLabel,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Inicio",
          tabBarIcon: ({ color }) => (
            <TabIcon symbol="⌂" color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="orders"
        options={{
          title: "Pedidos",
          tabBarIcon: ({ color }) => (
            <TabIcon symbol="▣" color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="customers"
        options={{
          title: "Clientes",
          tabBarIcon: ({ color }) => (
            <TabIcon symbol="◎" color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="copilot"
        options={{
          title: "IA",
          tabBarIcon: ({ color }) => (
            <TabIcon symbol="✦" color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="more"
        options={{
          title: "Más",
          tabBarIcon: ({ color }) => (
            <TabIcon symbol="•••" color={color} />
          ),
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.background,
  },
  tabBar: {
    height: 68,
    paddingTop: 6,
    paddingBottom: 8,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  tabLabel: {
    fontSize: 10,
    fontWeight: "700",
  },
  icon: {
    fontSize: 19,
    fontWeight: "800",
  },
});
