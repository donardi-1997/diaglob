import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useMemo, useRef, useState } from "react";

import {
  Card,
  EmptyState,
  PageHeader,
  Screen,
} from "../../src/components/Ui";
import {
  createAgentChatSession,
  resolveApproval,
  sendAgentChatMessage,
  type AgentChatMessage,
  type AgentChatSession,
  type AgentToolCall,
} from "../../src/services/copilot";
import { useSession } from "../../src/providers/SessionProvider";
import { colors, radius, spacing } from "../../src/theme";

const SUGGESTIONS = [
  "¿Cómo va mi operación hoy?",
  "¿Qué pedidos necesitan atención?",
  "¿Qué clientes debería priorizar?",
];

export default function CopilotScreen() {
  const { store } = useSession();
  const [session, setSession] =
    useState<AgentChatSession | null>(null);
  const [input, setInput] = useState("");
  const [optimisticText, setOptimisticText] = useState("");
  const [busy, setBusy] = useState(false);
  const [approvalBusy, setApprovalBusy] =
    useState<number | null>(null);
  const [error, setError] = useState("");
  const listRef = useRef<FlatList<AgentChatMessage>>(null);

  const messages = useMemo(
    () => session?.messages || [],
    [session],
  );
  const pending = useMemo(
    () => session?.pending_actions || [],
    [session],
  );

  async function send(textOverride?: string) {
    const text = (textOverride || input).trim();
    if (!text || !store || busy) return;

    setBusy(true);
    setError("");
    setOptimisticText(text);
    if (!textOverride) setInput("");

    try {
      let current = session;
      if (!current) {
        current = await createAgentChatSession(store.id);
      }

      const updated = await sendAgentChatMessage(
        current.id,
        store.id,
        text,
      );
      setSession(updated);
      setOptimisticText("");
      requestAnimationFrame(() =>
        listRef.current?.scrollToEnd({
          animated: true,
        }),
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "El Copiloto no pudo responder.",
      );
    } finally {
      setOptimisticText("");
      setBusy(false);
    }
  }

  async function decide(
    call: AgentToolCall,
    action: "approve" | "cancel",
  ) {
    if (!store || !session || !call.approval) return;

    setApprovalBusy(call.approval.id);
    setError("");

    try {
      const updated = await resolveApproval(
        session.id,
        call.approval.id,
        store.id,
        action,
      );
      setSession(updated);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "No fue posible resolver la aprobación.",
      );
    } finally {
      setApprovalBusy(null);
    }
  }

  function newChat() {
    setSession(null);
    setInput("");
    setOptimisticText("");
    setError("");
  }

  if (!store) {
    return (
      <Screen>
        <PageHeader
          eyebrow="COPILOTO IA"
          title="Pregunta a Diaglob"
        />
        <EmptyState
          title="Selecciona una tienda"
          body="El Copiloto necesita una tienda activa para trabajar."
        />
      </Screen>
    );
  }

  return (
    <Screen>
      <KeyboardAvoidingView
        style={styles.root}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={4}
      >
        <View style={styles.headerRow}>
          <PageHeader
            eyebrow="COPILOTO IA"
            title="Pregunta a Diaglob"
            subtitle={store.name}
          />
          <Pressable
            style={styles.newChat}
            onPress={newChat}
          >
            <Text style={styles.newChatText}>Nuevo</Text>
          </Pressable>
        </View>

        {error ? (
          <Text style={styles.error}>{error}</Text>
        ) : null}

        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={[
            styles.messages,
            messages.length === 0 &&
              styles.messagesEmpty,
          ]}
          ListEmptyComponent={
            <View>
              <Text style={styles.hero}>
                ¿Qué quieres saber?
              </Text>
              <Text style={styles.heroBody}>
                Consulta pedidos, clientes y tu operación.
                Las acciones sensibles requieren aprobación.
              </Text>
              <View style={styles.suggestions}>
                {SUGGESTIONS.map((suggestion) => (
                  <Pressable
                    key={suggestion}
                    style={styles.suggestion}
                    onPress={() =>
                      void send(suggestion)
                    }
                  >
                    <Text style={styles.suggestionText}>
                      ✦ {suggestion}
                    </Text>
                  </Pressable>
                ))}
              </View>
            </View>
          }
          renderItem={({ item }) => (
            <View
              style={[
                styles.message,
                item.role === "user"
                  ? styles.userMessage
                  : styles.assistantMessage,
              ]}
            >
              <Text
                style={[
                  styles.messageRole,
                  item.role === "user" &&
                    styles.userRole,
                ]}
              >
                {item.role === "user"
                  ? "Tú"
                  : "Diaglob"}
              </Text>
              <Text
                style={[
                  styles.messageText,
                  item.role === "user" &&
                    styles.userText,
                ]}
              >
                {item.text}
              </Text>
            </View>
          )}
          ListFooterComponent={
            <View>
              {optimisticText ? (
                <View
                  style={[
                    styles.message,
                    styles.userMessage,
                  ]}
                >
                  <Text
                    style={[
                      styles.messageRole,
                      styles.userRole,
                    ]}
                  >
                    Tú
                  </Text>
                  <Text
                    style={[
                      styles.messageText,
                      styles.userText,
                    ]}
                  >
                    {optimisticText}
                  </Text>
                </View>
              ) : null}

              {busy ? (
                <Text style={styles.thinking}>
                  ✦ Diaglob está pensando...
                </Text>
              ) : null}

              {pending.map((call) => (
                <Card
                  key={call.id}
                  style={styles.approval}
                >
                  <Text style={styles.approvalTitle}>
                    {call.title}
                  </Text>
                  {call.description ? (
                    <Text style={styles.approvalBody}>
                      {call.description}
                    </Text>
                  ) : null}
                  <Text style={styles.approvalMeta}>
                    Requiere tu aprobación antes de ejecutarse.
                  </Text>
                  <View style={styles.approvalActions}>
                    <Pressable
                      style={[
                        styles.approvalButton,
                        styles.cancelButton,
                      ]}
                      disabled={
                        approvalBusy === call.approval?.id
                      }
                      onPress={() =>
                        void decide(call, "cancel")
                      }
                    >
                      <Text style={styles.cancelText}>
                        Cancelar
                      </Text>
                    </Pressable>
                    <Pressable
                      style={[
                        styles.approvalButton,
                        styles.approveButton,
                      ]}
                      disabled={
                        approvalBusy === call.approval?.id
                      }
                      onPress={() =>
                        void decide(call, "approve")
                      }
                    >
                      <Text style={styles.approveText}>
                        Aprobar
                      </Text>
                    </Pressable>
                  </View>
                </Card>
              ))}
            </View>
          }
        />

        <View style={styles.composer}>
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder="Pregunta a Diaglob..."
            placeholderTextColor="#98A2B3"
            multiline
            style={styles.input}
          />
          <Pressable
            style={[
              styles.send,
              (!input.trim() || busy) &&
                styles.sendDisabled,
            ]}
            disabled={!input.trim() || busy}
            onPress={() => void send()}
          >
            <Text style={styles.sendText}>↑</Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  newChat: {
    marginLeft: "auto",
    marginRight: spacing.md,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
  },
  newChatText: {
    color: colors.accent,
    fontSize: 11,
    fontWeight: "800",
  },
  error: {
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    color: colors.danger,
    fontSize: 12,
  },
  messages: {
    flexGrow: 1,
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.md,
  },
  messagesEmpty: {
    justifyContent: "center",
  },
  hero: {
    color: colors.text,
    fontSize: 23,
    fontWeight: "800",
    textAlign: "center",
  },
  heroBody: {
    maxWidth: 330,
    marginTop: 8,
    alignSelf: "center",
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
    textAlign: "center",
  },
  suggestions: {
    marginTop: spacing.lg,
    gap: spacing.sm,
  },
  suggestion: {
    padding: 14,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
  },
  suggestionText: {
    color: colors.text,
    fontSize: 12,
    lineHeight: 18,
  },
  message: {
    maxWidth: "88%",
    marginBottom: spacing.md,
    padding: 13,
    borderRadius: radius.md,
  },
  assistantMessage: {
    alignSelf: "flex-start",
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  userMessage: {
    alignSelf: "flex-end",
    backgroundColor: colors.accent,
  },
  messageRole: {
    marginBottom: 5,
    color: colors.accent,
    fontSize: 10,
    fontWeight: "800",
  },
  userRole: {
    color: "#E7E4FF",
  },
  messageText: {
    color: colors.text,
    fontSize: 13,
    lineHeight: 20,
  },
  userText: {
    color: "#FFFFFF",
  },
  thinking: {
    marginVertical: spacing.sm,
    color: colors.textMuted,
    fontSize: 12,
  },
  approval: {
    marginBottom: spacing.md,
    padding: spacing.md,
    borderColor: "#D9D3FF",
  },
  approvalTitle: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "800",
  },
  approvalBody: {
    marginTop: 5,
    color: colors.textMuted,
    fontSize: 11,
    lineHeight: 17,
  },
  approvalMeta: {
    marginTop: spacing.sm,
    color: colors.warning,
    fontSize: 10,
  },
  approvalActions: {
    marginTop: spacing.md,
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: spacing.sm,
  },
  approvalButton: {
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: radius.sm,
  },
  cancelButton: {
    backgroundColor: "#F2F4F7",
  },
  approveButton: {
    backgroundColor: colors.accent,
  },
  cancelText: {
    color: colors.text,
    fontSize: 11,
    fontWeight: "700",
  },
  approveText: {
    color: "#FFFFFF",
    fontSize: 11,
    fontWeight: "800",
  },
  composer: {
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    padding: 7,
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 7,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 20,
    backgroundColor: colors.surface,
  },
  input: {
    flex: 1,
    minHeight: 38,
    maxHeight: 120,
    paddingHorizontal: 10,
    paddingVertical: 9,
    color: colors.text,
    fontSize: 13,
  },
  send: {
    width: 40,
    height: 40,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.pill,
    backgroundColor: colors.accent,
  },
  sendDisabled: {
    opacity: 0.4,
  },
  sendText: {
    color: "#FFFFFF",
    fontSize: 22,
    fontWeight: "800",
  },
});
