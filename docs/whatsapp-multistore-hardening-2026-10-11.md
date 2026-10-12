# DIAGLOB — WhatsApp Business multi-store hardening (2026-10-11)

## Existing implementation
WhatsApp Cloud API is **already present**: per-store encrypted access tokens and phone/WABA IDs, GET/POST signed webhook, inbound text and status events to Conversations, delivery via Graph API, Meta template listing, human/AI response and automation campaign compliance checks. This release does **not** launch a separate WhatsApp app or perform any Meta sends.

## Security changes
- All six `/api/stores/{store_id}/whatsapp...` endpoints require `require_authorized_path_store` as well as role permissions, so restricted memberships cannot inspect or alter WhatsApp on unassigned stores.
- Direct `POST /api/conversations/{conversation_id}/whatsapp/send` verifies organization, store assignments, WhatsApp channel and customer organization, and **blocks free-form messages outside the 24-hour service window**. Use an approved template plus recipient opt-in for business-initiated messages. Neither AI nor a human agent can bypass the Cloud API rules through this endpoint.
- Delivery `statuses` from signed Meta webhook are matched by phone-to-connection and organization/store/channel before updating local message. A shared/provider-reused message ID cannot update a different tenant.
- Meta verifies one **app-level** callback URL/token on the developer app. Production can set `WHATSAPP_WEBHOOK_VERIFY_TOKEN` in the backend to use that one global token, without showing it to store members. If unset, existing per-store verification remains supported for transition. Shared app secret `WHATSAPP_APP_SECRET` is required for HMAC-SHA256 checks on incoming POST; token must not be exposed to tenants.
- New **read-only** `GET /api/stores/{store_id}/whatsapp/diagnostics` with `stores.read` permission and assigned-store scope. It uses the connection's encrypted Meta token server-side to read WABA phone inventory and `subscribed_apps` (when `WHATSAPP_META_APP_ID` configured). Returns flags only, never tokens, phone lists or Graph errors. The UI marks stored configuration as *configured / not verified*, rather than a confirmed active integration.
- No subscription or template send is triggered automatically; no production credentials, app settings or customer messages changed.

## Actual Meta setup still required
1. In Meta Business Manager / Meta for Developers, use the **existing DIAGLOB Meta Business app** with WhatsApp product (do not create a new app without an explicit business decision).
2. Set backend `WHATSAPP_APP_SECRET`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN`, `WHATSAPP_TOKEN_ENCRYPTION_KEY`, `WHATSAPP_META_APP_ID` securely in production. Note that `WHATSAPP_WEBHOOK_VERIFY_TOKEN` is **app-wide**: do not distribute it to merchant tenants; admins must configure callback verification. Keep `WHATSAPP_GRAPH_API_VERSION` explicitly pinned to a supported version after compatibility testing.
3. Configure Callback URL `https://api.diaglob.tech/api/webhooks/whatsapp`; subscribe to `messages` on the app. In WhatsApp Business Platform, each WABA used by merchants must **also be subscribed to the app** (`POST /{WABA-ID}/subscribed_apps` with appropriate access and consent) or have an approved WABA override; subscribing a phone alone is not enough.
4. For each test merchant, configure phone number ID, WABA ID and properly scoped system-user access token via Diaglob > Tiendas > Integraciones. Meta owns token and phone verification; a saved configuration does **not** prove valid access until diagnostics pass.
5. Run the **read-only diagnostics**. Both provider_verified and waba_subscription_verified must be true before relying on inbound webhook processing. Then send one **inbound message from a consenting test number** and verify it appears in the correct Inbox; do not send unsolicited marketing.
6. For proactive notifications and campaigns, use only approved templates, purpose-specific opt-in records, rate limits and compliance controls. Free-form replies are permitted only during the 24-hour customer service window.

## Acceptance/E2E not performed yet
- Signed/mismatched HMAC, app verify token GET, idempotent incoming message, read/delivered/failed receipts, AI escalation, operator reply inside/outside 24-hour window, template consent, two tenant isolation, unassigned restricted membership denial, token expiry/rotation, remove phone, and real WABA subscription.
- Meta token + WABA association and real test-number sending requires authorized Meta/Business login and opt-in. Do not substitute a different merchant's WABA or phone.

Official documentation:
- https://www.postman.com/meta/whatsapp-business-platform/folder/ozgs3jn/webhook-subscriptions
- https://www.postman.com/meta/whatsapp-business-platform/request/tl2wk2j/get-all-subscriptions-for-a-waba
- https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks
- https://docs.aws.amazon.com/social-messaging/latest/userguide/whatsapp-send-message.html
