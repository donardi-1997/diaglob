import type { ReactNode } from "react";
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { colors, radius, spacing } from "../theme";

export function Screen({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <SafeAreaView
      edges={["top"]}
      style={styles.screen}
    >
      {children}
    </SafeAreaView>
  );
}

export function PageHeader({
  eyebrow,
  title,
  subtitle,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
}) {
  return (
    <View style={styles.pageHeader}>
      {eyebrow ? (
        <Text style={styles.eyebrow}>{eyebrow}</Text>
      ) : null}
      <Text style={styles.title}>{title}</Text>
      {subtitle ? (
        <Text style={styles.subtitle}>{subtitle}</Text>
      ) : null}
    </View>
  );
}

export function Card({
  children,
  style,
}: {
  children: ReactNode;
  style?: object;
}) {
  return (
    <View style={[styles.card, style]}>
      {children}
    </View>
  );
}

export function MetricCard({
  label,
  value,
  tone = "accent",
}: {
  label: string;
  value: string;
  tone?: "accent" | "success" | "warning" | "danger";
}) {
  const toneColor = {
    accent: colors.accent,
    success: colors.success,
    warning: colors.warning,
    danger: colors.danger,
  }[tone];

  return (
    <Card style={styles.metric}>
      <View
        style={[
          styles.metricDot,
          { backgroundColor: toneColor },
        ]}
      />
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </Card>
  );
}

export function LoadingState({
  label = "Cargando...",
}: {
  label?: string;
}) {
  return (
    <View style={styles.center}>
      <ActivityIndicator color={colors.accent} />
      <Text style={styles.centerText}>{label}</Text>
    </View>
  );
}

export function EmptyState({
  title,
  body,
}: {
  title: string;
  body?: string;
}) {
  return (
    <View style={styles.empty}>
      <Text style={styles.emptyTitle}>{title}</Text>
      {body ? (
        <Text style={styles.centerText}>{body}</Text>
      ) : null}
    </View>
  );
}

export function Badge({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?:
    | "neutral"
    | "success"
    | "warning"
    | "danger"
    | "accent";
}) {
  const palette = {
    neutral: {
      backgroundColor: "#EEF1F5",
      color: colors.textMuted,
    },
    success: {
      backgroundColor: "#E8F8F0",
      color: colors.success,
    },
    warning: {
      backgroundColor: "#FFF4E5",
      color: colors.warning,
    },
    danger: {
      backgroundColor: "#FEEDEC",
      color: colors.danger,
    },
    accent: {
      backgroundColor: colors.surfaceSoft,
      color: colors.accent,
    },
  }[tone];

  return (
    <View
      style={[
        styles.badge,
        { backgroundColor: palette.backgroundColor },
      ]}
    >
      <Text
        style={[
          styles.badgeText,
          { color: palette.color },
        ]}
      >
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  pageHeader: {
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  eyebrow: {
    marginBottom: 4,
    color: colors.accent,
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },
  title: {
    color: colors.text,
    fontSize: 28,
    fontWeight: "800",
    letterSpacing: -0.7,
  },
  subtitle: {
    marginTop: 6,
    color: colors.textMuted,
    fontSize: 13,
    lineHeight: 19,
  },
  card: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
  },
  metric: {
    minWidth: "47%",
    flexGrow: 1,
    padding: spacing.md,
  },
  metricDot: {
    width: 8,
    height: 8,
    marginBottom: spacing.sm,
    borderRadius: radius.pill,
  },
  metricValue: {
    color: colors.text,
    fontSize: 22,
    fontWeight: "800",
  },
  metricLabel: {
    marginTop: 4,
    color: colors.textMuted,
    fontSize: 11,
    textTransform: "uppercase",
  },
  center: {
    flex: 1,
    minHeight: 220,
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
  },
  centerText: {
    color: colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
    textAlign: "center",
  },
  empty: {
    margin: spacing.md,
    padding: spacing.xl,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
  },
  emptyTitle: {
    marginBottom: 6,
    color: colors.text,
    fontSize: 16,
    fontWeight: "700",
    textAlign: "center",
  },
  badge: {
    alignSelf: "flex-start",
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: radius.pill,
  },
  badgeText: {
    fontSize: 10,
    fontWeight: "800",
    textTransform: "uppercase",
  },
});
