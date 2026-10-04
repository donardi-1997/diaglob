import { Redirect } from "expo-router";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useState } from "react";

import { LoadingState, Screen } from "../src/components/Ui";
import { useSession } from "../src/providers/SessionProvider";
import { colors, radius, spacing } from "../src/theme";

export default function LoginScreen() {
  const {
    ready,
    authenticated,
    login,
  } = useSession();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  if (!ready) {
    return (
      <Screen>
        <LoadingState />
      </Screen>
    );
  }

  if (authenticated) {
    return <Redirect href="/(tabs)" />;
  }

  async function submit() {
    if (!email.trim() || !password) return;

    setSubmitting(true);
    setError("");

    try {
      await login(email, password);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "No fue posible iniciar sesión.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Screen>
      <KeyboardAvoidingView
        style={styles.root}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <View style={styles.brand}>
          <View style={styles.mark}>
            <Text style={styles.markText}>✦</Text>
          </View>
          <Text style={styles.brandName}>DIAGLOB</Text>
          <Text style={styles.brandSubtitle}>
            Commerce OS · Mobile
          </Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.title}>Bienvenido</Text>
          <Text style={styles.subtitle}>
            Controla tu operación desde cualquier lugar.
          </Text>

          <TextInput
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            placeholder="Correo"
            placeholderTextColor="#98A2B3"
            style={styles.input}
          />

          <TextInput
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            placeholder="Contraseña"
            placeholderTextColor="#98A2B3"
            style={styles.input}
            onSubmitEditing={() => void submit()}
          />

          {error ? (
            <Text style={styles.error}>{error}</Text>
          ) : null}

          <Pressable
            onPress={() => void submit()}
            disabled={
              submitting ||
              !email.trim() ||
              !password
            }
            style={({ pressed }) => [
              styles.button,
              pressed && styles.buttonPressed,
              (submitting ||
                !email.trim() ||
                !password) &&
                styles.buttonDisabled,
            ]}
          >
            <Text style={styles.buttonText}>
              {submitting
                ? "Ingresando..."
                : "Entrar a Diaglob"}
            </Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    justifyContent: "center",
    padding: spacing.lg,
  },
  brand: {
    alignItems: "center",
    marginBottom: spacing.xl,
  },
  mark: {
    width: 62,
    height: 62,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 14,
    borderRadius: 20,
    backgroundColor: colors.accent,
  },
  markText: {
    color: "#FFFFFF",
    fontSize: 30,
  },
  brandName: {
    color: colors.text,
    fontSize: 24,
    fontWeight: "900",
    letterSpacing: 2.4,
  },
  brandSubtitle: {
    marginTop: 4,
    color: colors.textMuted,
    fontSize: 12,
  },
  card: {
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
  },
  title: {
    color: colors.text,
    fontSize: 24,
    fontWeight: "800",
  },
  subtitle: {
    marginTop: 5,
    marginBottom: spacing.lg,
    color: colors.textMuted,
    fontSize: 13,
    lineHeight: 19,
  },
  input: {
    minHeight: 52,
    marginBottom: spacing.sm,
    paddingHorizontal: 15,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    backgroundColor: "#FAFAFC",
    color: colors.text,
    fontSize: 15,
  },
  error: {
    marginVertical: 4,
    color: colors.danger,
    fontSize: 12,
  },
  button: {
    minHeight: 52,
    marginTop: spacing.sm,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.md,
    backgroundColor: colors.accent,
  },
  buttonPressed: {
    backgroundColor: colors.accentDark,
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "800",
  },
});
