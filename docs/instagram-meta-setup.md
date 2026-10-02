# Instagram Messaging — Meta setup

Diaglob routes Instagram Direct messages into the existing multi-store inbox.
The integration deliberately shares Conversation, Message, Agent, Knowledge
and AI capacity instead of creating a parallel chatbot system.

## Backend environment

```bash
INSTAGRAM_TOKEN_ENCRYPTION_KEY=<fernet-key>
INSTAGRAM_WEBHOOK_VERIFY_TOKEN=<long-random-value>
INSTAGRAM_APP_SECRET=<meta-app-secret>
# Or reuse META_APP_SECRET when Instagram and Meta Ads share the same Meta app.
META_GRAPH_API_VERSION=<supported-version>
INSTAGRAM_WEBHOOK_BASE_URL=https://api.diaglob.tech
```

Generate the Fernet key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Meta prerequisites

Use an Instagram professional/business account connected to the Meta assets
that own the access token. The token must be authorized for Instagram
Messaging and webhook access according to the permissions enabled on the
Meta app.

Diaglob validates the supplied Instagram Account ID against Meta before
persisting the connection. Tokens are encrypted at rest and are never
returned by the API after connection.

## Webhook

Callback:

```
https://api.diaglob.tech/api/webhooks/instagram
```

Verify Token:

Use the value configured in `INSTAGRAM_WEBHOOK_VERIFY_TOKEN`.

The callback:
- verifies the Meta challenge using the shared app-level token;
- verifies POST bodies with `X-Hub-Signature-256`;
- routes `entry.id` to the connected Diaglob store;
- ignores echo messages;
- deduplicates messages by Meta message id;
- stores the sender as `instagram:<IGSID>`;
- creates/reuses a shared Conversation with channel `Instagram`;
- schedules the existing permission-aware AI reply pipeline.

## Outbound

Both human replies from the unified inbox and automatic AI replies use the
same Instagram connection for the conversation's store. A conversation can
never send through a different store's Instagram account.

## Production checklist

1. Create `INSTAGRAM_TOKEN_ENCRYPTION_KEY`.
2. Set `INSTAGRAM_WEBHOOK_VERIFY_TOKEN`.
3. Set `INSTAGRAM_APP_SECRET` or the shared `META_APP_SECRET`.
4. Confirm `META_GRAPH_API_VERSION` is a version supported by the Meta app.
5. Configure the callback and verify token in Meta.
6. Subscribe the app to Instagram messaging webhook events required by the
   current Meta product configuration.
7. Connect the Instagram Business Account from Diaglob > Integrations.
8. Send a real DM and confirm it appears in Inbox as channel Instagram.
9. Reply as a human.
10. Return the conversation to AI and verify the AI reply is delivered.
