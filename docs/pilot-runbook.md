# Diaglob Pilot Launch Runbook

## Pilot Objective

Validate Diaglob with 10–20 real merchants to answer:

1. Can merchants activate?
2. Where do they get stuck?
3. Does WhatsApp AI work reliably with real stores?
4. How much AI does a real merchant consume?
5. What does one AI interaction actually cost?
6. Which integrations fail most often?
7. Which product features are actually used?
8. What bugs block payment or activation?
9. Which pricing limits should we ultimately choose?
10. Is Diaglob ready to expand to 50–100 merchants?

## Target Cohort

**Size:** 10–20 merchants
**Profile:** Active ecommerce/dropshipping merchant with Shopify, WhatsApp, real products, and real customer conversations
**Dropi:** Supported if products flow through Shopify. Direct Dropi API integration is NOT required.

## Primary KPI

**ACTIVATED** = store has emitted `first_whatsapp_ai_reply`

A merchant is considered activated when a store successfully reaches the first AI-powered WhatsApp reply using their actual catalog/knowledge.

## Secondary KPIs

- signup → store creation
- store → Shopify connected
- Shopify → catalog synced
- catalog → WhatsApp connected
- WhatsApp → first inbound
- first inbound → first AI reply
- signup → first AI reply (TTFV)
- first AI reply → automation created
- signup → checkout started
- checkout → completed payment

## Assisted Onboarding Flow

**Duration:** 20–30 minutes

1. Create account (register + email verification)
2. Create store (name, country, currency)
3. Connect Shopify (OAuth)
4. Sync catalog (confirm products visible)
5. Connect WhatsApp (credentials from Meta Business Suite)
6. Send test customer message
7. Confirm first AI reply
8. Create first automation (template)
9. Explain billing/plan
10. Show support path

## WhatsApp Checklist

### Prerequisites

- Meta Business account (verified)
- WhatsApp Business account (active)
- Phone number associated with WhatsApp Business
- Phone Number ID (from Meta Business Suite → Settings → Phone numbers)
- Business Account ID (from Meta Business Suite → Account information)
- Access Token (from Meta Business Suite → System → System users → Tokens)

### Setup Steps

1. Navigate to Settings → Integrations
2. Enter Phone Number ID
3. Enter Business Account ID
4. Enter Access Token
5. Click Connect
6. Copy Webhook URL: `https://api.diaglob.tech/api/webhooks/whatsapp`
7. Copy Verify Token (shown after connection)
8. Configure webhook in Meta Business Suite
9. Send test message to business number
10. Confirm AI reply appears in Conversations

### Common Failures

- **Invalid credentials:** Verify token hasn't expired; regenerate in Meta
- **Webhook not verified:** Ensure webhook URL and verify token are configured correctly in Meta
- **No AI reply:** Check agent is assigned to store and is active

## Shopify Checklist

### Setup Steps

1. Navigate to Settings → Integrations
2. Enter `.myshopify.com` domain
3. Click Connect Shopify
4. Authorize in Shopify OAuth screen
5. Return to Diaglob
6. Click Sync Products
7. Confirm products appear in Commerce → Products

### Common Failures

- **Invalid shop domain:** Must be `.myshopify.com` format
- **OAuth denied:** Merchant must approve in Shopify
- **Sync fails:** Check Shopify connection status

## Dropi Pilot Positioning

### Supported Path

```
Dropi → Shopify → Diaglob catalog → WhatsApp AI
```

### What Works

- Products imported into Shopify are available in Diaglob catalog
- AI can reference Dropi products when answering WhatsApp messages
- Dropi detection through Shopify is shown

### What Does NOT Work (Yet)

- Direct Dropi API product sync
- Direct Dropi order creation
- Direct Dropi stock sync
- Direct Dropi price sync

### Honest Explanation

"Dropi products that are synced to Shopify are automatically available in Diaglob. Your AI assistant can recommend these products to customers. Direct Dropi integration for orders and inventory is coming soon."

## Activation Definition

**ACTIVATED STORE** = store that has emitted `first_whatsapp_ai_reply`

This means:
- Store exists
- WhatsApp is connected
- At least one inbound message was received
- AI generated and persisted a reply

## Time to First Value (TTFV)

Measured as:

```
TTFV = first_whatsapp_ai_reply.timestamp - signup_completed.timestamp
```

PostHog can calculate this via funnel analysis.

## Operator Diagnostics

### Identifying Stuck Merchants

Query PostHog for stores that have:
- `whatsapp_connected` but NO `first_whatsapp_ai_reply` after 24 hours

This indicates merchant needs assisted support.

### Daily Review (10–15 minutes)

| Metric | Source |
|--------|--------|
| New signups | PostHog: signup_completed |
| New activated stores | PostHog: first_whatsapp_ai_reply |
| Activation failures | PostHog funnel gaps |
| P0/P1 issues | Support tickets |
| AI interactions | PostHog: ai_interaction_completed |
| Token usage | PostHog: ai_interaction_completed.sum(total_tokens) |
| Checkout starts | PostHog: checkout_started |
| Payments | PostHog: checkout_completed |

### Support Diagnostics Collection

When a merchant reports an issue, collect:

- Merchant email/account
- Store name
- Approximate time of failure
- Integration involved (Shopify/WhatsApp/etc.)
- Safe screenshot of error

**NEVER ask for:**
- Access tokens
- API secrets
- Passwords
- Raw credentials

## Blocker Severity

| Level | Definition | Action |
|-------|-----------|--------|
| P0 | Security, data loss, system unavailable | Fix immediately |
| P1 | Merchant cannot activate/pay/use core AI loop | Fix before next cohort |
| P2 | Merchant can continue with workaround | Document, fix post-pilot |
| P3 | Cosmetic/polish | Document, backlog |

## AI Cost Formula

```
AI_COST_PER_INTERACTION = 
  (input_tokens / 1,000,000 × input_token_price_per_million)
  + (output_tokens / 1,000,000 × output_token_price_per_million)
```

External token prices must remain configurable analysis inputs.

**Amazon Nova 2 Lite (estimated):**
- Input: ~$0.060 per 1M tokens
- Output: ~$0.240 per 1M tokens

## Pricing Validation Questions

Pilot must answer:

1. Is 1,000 AI interactions enough for Starter?
2. Is 5,000 enough for Growth?
3. Is 20,000 enough for Pro?
4. Is 50,000 excessive for Scale?
5. How many AI interactions does one active contact generate?
6. What percentage of included usage does a normal merchant consume?

## Merchant Interview Questions

1. What tools were you using before Diaglob?
2. How much do you spend monthly on those tools?
3. Which tool could Diaglob replace?
4. Which Diaglob feature creates the most value for you?
5. How would you rate the AI response quality (1–5)?
6. How useful is the product catalog context in AI replies?
7. What's the biggest thing missing from Diaglob?
8. What monthly price range feels fair for what you get?

## Pilot Exit Criteria

| Criterion | Target |
|-----------|--------|
| Real merchants onboarded | ≥10 |
| Created first store | ≥70% |
| Connected commerce integration | ≥50% |
| Reached first AI reply | ≥40% |
| Unresolved P0 issues | 0 |
| Unresolved P1 issues | ≤2 (with documented workaround) |
| AI unit economics measured | Real Bedrock data |
| Pricing usage distribution | Available |
| Merchant interviews | ≥5 completed |

## Expansion Criteria (→ 50–100 merchants)

- Core activation loop stable
- No recurring P0 issues
- P1 rate acceptable
- Support workload manageable
- AI unit economics validated
- Billing conversion works
- Top onboarding friction identified and addressed

## Pilot Decision Framework

| Verdict | Criteria |
|---------|----------|
| EXPAND | Core loop stable, unit economics acceptable, no structural blockers |
| EXTEND_PILOT | Insufficient sample but no structural blocker |
| PAUSE_AND_FIX | Repeated P0/P1 or broken economics |

## Pilot Report Template

```
PILOT REPORT
Date: YYYY-MM-DD
Cohort size: N
Activated stores: N (X%)
Median TTFV: X hours
AI interactions: N
Total tokens: N
Estimated AI cost: $X
Checkout conversion: X%
P0 incidents: N
P1 incidents: N
Top friction: [description]
Top requested feature: [description]
Merchant interview summary: [key findings]
Pricing observations: [findings]
Decision: EXPAND / EXTEND_PILOT / PAUSE_AND_FIX
```

## PostHog Dashboard Specification

### ACTIVATION Section

- signup_completed count
- store_created rate
- shopify_connected rate
- catalog_synced rate
- whatsapp_connected rate
- first_whatsapp_inbound rate
- first_whatsapp_ai_reply rate
- TTFV median/P75/P90

### USAGE Section

- ai_interaction_completed count
- sum(input_tokens)
- sum(output_tokens)
- sum(total_tokens)
- AI interactions per store
- AI interactions per activated store

### RELIABILITY Section

- ai_generation_failed count (if instrumented)
- integration failure categories
- automation failure count

### MONETIZATION Section

- checkout_started count
- checkout_completed count
- activated → checkout rate
- checkout → paid rate
- signup → paid rate
