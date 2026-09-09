# Telegram V1

Telegram V1 adds one Telegram bot per Diaglob store as a messaging channel for private text conversations.

## Scope

Supported in V1:

- One Telegram bot per store.
- Bot Token validation with Telegram `getMe`.
- Automatic webhook registration with `setWebhook`.
- Authenticated webhook delivery using a random URL token plus Telegram's `X-Telegram-Bot-Api-Secret-Token` header.
- Private text messages only.
- Customer, Conversation, and Message persistence in the existing Diaglob inbox.
- Human replies from the unified Conversations inbox.
- AI auto-replies through the existing Diaglob agent, RAG, and commerce context pipeline.
- Dashboard integration status.

Not supported in V1:

- Group or supergroup conversations.
- Photos, audio, video, documents, stickers, locations, or contacts.
- Telegram commands beyond their text representation.
- Shared bots across multiple stores.
- Proactive messaging to users who have never started a chat with the bot.

## Production configuration

The backend requires a stable Fernet key:

```text
TELEGRAM_TOKEN_ENCRYPTION_KEY=<fernet-key>
```

Generate it with Python and `cryptography`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store the value in the normal production environment/secret store. Do not commit it to Git. The key encrypts both the Telegram Bot Token and the webhook secret stored in the database.

The key must remain stable after bots are connected. Replacing it without re-encrypting existing rows will make stored Telegram credentials unreadable.

Optional:

```text
TELEGRAM_WEBHOOK_BASE_URL=https://api.diaglob.tech
```

If omitted, the backend uses `https://api.diaglob.tech`.

The Telegram schema migration is:

```text
d7e8f9a0b1c2_add_telegram_connections.py
```

Apply it through the normal Diaglob Alembic deployment process before using Telegram in production.

## Connecting a store

1. Create a bot with Telegram `@BotFather`.
2. Copy the Bot Token.
3. Open the store's Integrations section in Diaglob.
4. Paste the token into the Telegram card and select **Conectar Telegram**.
5. Diaglob validates the token with `getMe`.
6. Diaglob generates a random webhook path and webhook secret.
7. Diaglob registers the webhook with Telegram automatically.
8. The raw Bot Token is cleared from the browser state after a successful connection and is never returned by the API.

The webhook URL does not contain the Bot Token.

## Message flow

Inbound:

```text
Telegram -> authenticated webhook -> Telegram service -> Customer -> Conversation -> Message
                                                     -> automation events
                                                     -> AI auto-reply when eligible
```

For a private Telegram chat, Diaglob stores the external chat identity as:

```text
telegram:<chat_id>
```

in the existing customer phone field. This avoids changing the shared Customer schema in V1 while retaining the exact chat identifier needed for outbound `sendMessage` calls.

Outbound human replies from `/api/conversations/{conversation_id}/messages` are automatically routed through Telegram when the conversation channel is Telegram. Existing WhatsApp behavior remains unchanged.

## Security properties

- Bot Tokens are encrypted at rest with Fernet.
- Webhook secrets are encrypted at rest with Fernet.
- Webhook URLs contain a high-entropy random path token, not the Bot Token.
- Incoming requests must match both the stored random path and the decrypted `X-Telegram-Bot-Api-Secret-Token` value.
- Secret comparison uses constant-time comparison.
- Store and organization ownership are enforced on authenticated management and outbound routes.
- A Telegram bot cannot be attached to more than one store.
- Duplicate inbound Telegram messages are ignored using the provider message ID.

## Validation

The final Telegram V1 implementation passed the pull-request validation pipeline: Ruff, 858 backend tests, dependency installation, and the production TypeScript/Vite build. The Telegram-specific coverage includes connection, authenticated webhook processing, idempotency, group rejection, unified-inbox delivery, AI channel delivery, and the API route contract.

## Smoke test

After deployment:

1. Confirm the migration is applied.
2. Confirm `TELEGRAM_TOKEN_ENCRYPTION_KEY` exists in the backend environment.
3. Connect a test bot from Store Integrations.
4. Verify the card displays the bot username and connected state.
5. From a private Telegram account, open the bot and send a text message.
6. Verify the conversation appears in Diaglob with channel `Telegram`.
7. Put the conversation in human mode and send a reply from Diaglob; verify it arrives in Telegram.
8. Return the conversation to AI mode and send another customer message; verify the AI response is delivered through Telegram.
9. Send the same webhook update twice in a test environment and verify only one message is persisted.
10. Disconnect the bot and confirm Telegram's webhook is removed and Diaglob reports it as disconnected.
