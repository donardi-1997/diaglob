# Diaglob Pricing & Usage Economics Analysis
## Phase 4.5 — Pricing + Usage Economics

**Date:** 2026-09-08
**Author:** Automated Analysis
**Status:** ANALYSIS ONLY — NO PRICING CHANGES IMPLEMENTED

---

## 1. AI Architecture

### Provider
- **Provider:** AWS Bedrock
- **Region:** us-east-2
- **Runtime:** bedrock-runtime (converse API)
- **Config Source:** `DIAGLOB_CHAT_MODEL_ID` env var

### Model
- **Model ID:** `us.amazon.nova-2-lite-v1:0`
- **Model Name:** Amazon Nova 2 Lite
- **Call Type:** Synchronous (non-streaming)
- **Max Output Tokens:** 500
- **Temperature:** 0.2
- **Top P:** 0.9

### Usage Metadata
- **AVAILABLE:** YES — Bedrock converse API returns `usage.inputTokens`, `usage.outputTokens`, `usage.totalTokens`
- **CURRENTLY CAPTURED:** YES — Added in this block via `ai_generation.py` return dict
- **STORED:** Via PostHog `ai_interaction_completed` event

---

## 2. AI Token Usage (Estimated — No Production Sample)

### Prompt Composition

| Component | Source | Max Size | Truncation | Currently Measured |
|-----------|--------|----------|------------|-------------------|
| System instructions | `ai_generation.py` | ~800 chars | None | NO |
| Conversation history | `ai_reply_service.py` | 10 messages × ~200 chars = ~2,000 chars | Last 10 messages | NO |
| Catalog context | `ai_generation.py` | 5 products × ~300 chars = ~1,500 chars | 5 products | NO |
| Knowledge/RAG context | `rag.py` | 5 chunks × ~500 chars = ~2,500 chars | 5 results | NO |
| Customer message | WhatsApp inbound | ~500 chars | None | NO |
| Total input | — | ~7,300 chars | — | MEASURED via API |

### Estimated Token Counts (Amazon Nova 2 Lite)

| Metric | Estimate | Basis |
|--------|----------|-------|
| Avg input tokens | ~2,500 | ~3.5 chars/token for mixed content |
| Avg output tokens | ~150 | 2-3 sentence WhatsApp response |
| Avg total tokens | ~2,650 | Sum |

### Model Pricing (External — NOT in repo)

**Amazon Nova 2 Lite (us-east-2):**
- Input: ~$0.00006 per 1,000 tokens (estimated)
- Output: ~$0.00024 per 1,000 tokens (estimated)

**Estimated cost per AI interaction:**
```
Cost = (2,500 / 1,000,000 × $0.060) + (150 / 1,000,000 × $0.240)
Cost ≈ $0.000150 + $0.000036
Cost ≈ $0.000186 per interaction
```

**Cost per 1,000 AI interactions:**
```
$0.186 per 1,000 interactions
```

---

## 3. Cost Drivers

| Cost Driver | Fixed/Variable | Source | Currently Known | Meter |
|-------------|----------------|--------|----------------|-------|
| AI inference (Bedrock) | Variable | `ai_generation.py` | MEASURED_NOW | input/output tokens |
| Knowledge retrieval (Bedrock KB) | Variable | `rag.py` | UNKNOWN | query count |
| Embedding (Titan) | Variable | `bedrock_knowledge_base.py` | UNKNOWN | embedding count |
| S3 storage | Variable | Knowledge sources | UNKNOWN | bytes |
| WhatsApp messages | Fixed to merchant | Meta | NO_DIAGLOB_COST | N/A |
| Shopify API | Fixed | Shopify | NO_COST | N/A |
| Database (SQLite/Lightsail) | Fixed | Infrastructure | UNKNOWN | N/A |
| AWS Lightsail | Fixed | Infrastructure | UNKNOWN | N/A |
| Paddle fees | Variable | Paddle | EXTERNAL | transaction % |

### WhatsApp Economics
- **Meta account owner:** Merchant
- **Meta billing party:** Merchant directly
- **Diaglob direct message cost:** NO
- **BSP:** NO — Merchant uses their own Meta Business account

### Shopify Economics
- **Variable cost:** None — API calls are free
- **Storage:** Minimal — product/order records in DB

### Google/Knowledge Economics
- **Drive API:** Free (within quotas)
- **Bedrock Knowledge Base:** Variable (retrieval + embedding)
- **S3:** Variable (storage)
- **Embedding model:** Amazon Titan Embed Text V2

---

## 4. Current Plan Configuration

### Plan Limits (from `plan_limits.py`)

| Plan | Price | Stores | Monthly Customers | Members |
|------|-------|--------|-------------------|---------|
| Starter | $19/mo | 1 | 1,000 | 2 |
| Growth | $59/mo | 2 | 5,000 | 5 |
| Pro | $99/mo | 3 | 10,000 | 10 |
| Scale | $179/mo | 5 | 25,000 | 15 |

### Current Limit Enforcement
- **Stores:** Backend-enforced (active store count vs limit)
- **Monthly customers:** Backend-enforced (customer capacity check)
- **Members:** Backend-enforced (member count check)
- **AI interactions:** NOT LIMITED
- **Automation executions:** NOT LIMITED

### Customer/Month Meaning
- **Definition:** Unique customer records stored for the organization
- **Reset:** Not monthly — it's a capacity check, not a usage meter
- **Enforcement:** Checked when creating new customers

---

## 5. AI Interaction Definition

### Commercial Definition
**One successfully generated AI response to a merchant/customer interaction.**

### Technical Source
- `generate_grounded_answer()` returns successfully with non-empty answer
- Answer is persisted as a Message with `sender="ai"`
- WhatsApp delivery succeeds or is attempted

### Failed Call Counted: NO
### Retry Counted: YES (if message is retried and AI generates new response)

---

## 6. Unit Economics Model

### Formula

```
AI_COST_PER_INTERACTION = 
  (input_tokens / 1,000,000 × model_input_price_per_million)
  + (output_tokens / 1,000,000 × model_output_price_per_million)

GROSS_MARGIN = (revenue - variable_costs) / revenue

BREAK_EVEN_INTERACTIONS = 
  (plan_price - fixed_costs) / AI_COST_PER_INTERACTION
```

### Scenario Model (No Production Data)

| Scenario | AI Interactions/Month | Input Tokens | Output Tokens | Est. Cost |
|----------|----------------------|--------------|----------------|-----------|
| Light | 100 | 2,500 | 150 | $0.02 |
| Normal | 500 | 2,500 | 150 | $0.09 |
| Heavy | 2,000 | 2,500 | 150 | $0.37 |
| Extreme | 10,000 | 2,500 | 150 | $1.86 |

### Plan Economics (Estimated)

**Assumptions:**
- Paddle fee: 5% of revenue
- Infrastructure: $50/month fixed (Lightsail, S3, etc.)
- AI cost: $0.000186 per interaction (estimated)

| Plan | Revenue | Paddle (5%) | AI Cost (500 interactions) | Gross Margin |
|------|---------|-------------|---------------------------|--------------|
| Starter $19 | $19 | $0.95 | $0.093 | 94.5% |
| Growth $59 | $59 | $2.95 | $0.093 | 94.8% |
| Pro $99 | $99 | $4.95 | $0.093 | 94.9% |
| Scale $179 | $179 | $8.95 | $0.093 | 94.9% |

**At 5,000 interactions/month:**

| Plan | Revenue | Paddle (5%) | AI Cost | Gross Margin |
|------|---------|-------------|---------|--------------|
| Starter $19 | $19 | $0.95 | $0.93 | 90.1% |
| Growth $59 | $59 | $2.95 | $0.93 | 93.4% |
| Pro $99 | $99 | $4.95 | $0.93 | 94.1% |
| Scale $179 | $179 | $8.95 | $0.93 | 94.5% |

**At 50,000 interactions/month (extreme):**

| Plan | Revenue | Paddle (5%) | AI Cost | Gross Margin |
|------|---------|-------------|---------|--------------|
| Starter $19 | $19 | $0.95 | $9.30 | 46.3% |
| Growth $59 | $59 | $2.95 | $9.30 | 79.2% |
| Pro $99 | $99 | $4.95 | $9.30 | 85.6% |
| Scale $179 | $179 | $8.95 | $9.30 | 90.2% |

---

## 7. Recommended Pricing Architecture

### Target Gross Margins
- **Minimum Acceptable:** 70%
- **Healthy Target:** 80%
- **High-Margin Target:** 90%

### Recommended Plan Structure

| Plan | Price | Stores | Active Contacts | AI Interactions | Overage |
|------|-------|--------|-----------------|-----------------|---------|
| Starter | $19/mo | 1 | 1,000 | 500 included | $5/1,000 |
| Growth | $49/mo | 2 | 5,000 | 2,000 included | $5/1,000 |
| Pro | $99/mo | 5 | 20,000 | 10,000 included | $4/1,000 |
| Scale | $199/mo | 10 | 50,000 | 50,000 included | $3/1,000 |

### Rationale
- **Starter $19:** Acquisition-focused. Low barrier to entry. Limited AI to protect margin.
- **Growth $49:** Reduced from $59 to improve conversion. Good value for growing merchants.
- **Pro $99:** Hero plan. 5 stores, generous AI. Differentiator from Growth.
- **Scale $199:** Increased from $179. High-value for large operations. Volume discount on overage.

### Included AI Interactions (at 80% target margin)

| Plan | Revenue | Max AI Cost (80% GM) | Safe Interactions |
|------|---------|---------------------|-------------------|
| Starter $19 | $19 | $3.80 | ~20,000 |
| Growth $49 | $49 | $9.80 | ~52,000 |
| Pro $99 | $99 | $19.80 | ~106,000 |
| Scale $199 | $199 | $39.80 | ~214,000 |

**Recommended included amounts are much lower than theoretical max to protect margin against:**
- Paddle fees
- Infrastructure costs
- Knowledge/RAG costs
- Support costs
- Heavy usage outliers

---

## 8. Overage Economics

### Recommended Overage Pricing

| Plan | Overage Rate | Break-even at 70% GM |
|------|-------------|---------------------|
| Starter | $5/1,000 | ~2,700 interactions |
| Growth | $5/1,000 | ~2,700 interactions |
| Pro | $4/1,000 | ~2,200 interactions |
| Scale | $3/1,000 | ~1,600 interactions |

### Overage UX Principle
- **Soft limit + warnings + automatic overage**
- Do NOT abruptly stop WhatsApp AI during merchant sales activity
- Send warning at 80% of included usage
- Send alert at 100% of included usage
- Continue service with overage charges
- Monthly overage invoice via Paddle

---

## 9. Dropi Revenue Share Analysis

### Recommended Terms
- **Revenue Share:** 15% of subscription base revenue
- **Term:** 12 months
- **Overage Commissioned:** NO — exclude AI overage revenue from affiliate commission

### Customer Mix Scenarios

**STARTER-HEAVY (50% Starter, 30% Growth, 15% Pro, 5% Scale):**

| Customers | MRR | Dropi (15%) | Diaglob | 
|-----------|-----|-------------|---------|
| 50 | $2,450 | $367 | $2,083 |
| 100 | $4,900 | $735 | $4,165 |
| 500 | $24,500 | $3,675 | $20,825 |
| 1,000 | $49,000 | $7,350 | $41,650 |

**BALANCED (35% Starter, 35% Growth, 25% Pro, 5% Scale):**

| Customers | MRR | Dropi (15%) | Diaglob |
|-----------|-----|-------------|---------|
| 50 | $3,450 | $517 | $2,933 |
| 100 | $6,900 | $1,035 | $5,865 |
| 500 | $34,500 | $5,175 | $29,325 |
| 1,000 | $69,000 | $10,350 | $58,650 |

**PRO-HEAVY (20% Starter, 30% Growth, 40% Pro, 10% Scale):**

| Customers | MRR | Dropi (15%) | Diaglob |
|-----------|-----|-------------|---------|
| 50 | $4,650 | $697 | $3,953 |
| 100 | $9,300 | $1,395 | $7,905 |
| 500 | $46,500 | $6,975 | $39,525 |
| 1,000 | $93,000 | $13,950 | $79,050 |

---

## 10. Break-Even Analysis

### Per Plan (at $0.000186/interaction)

| Plan | Price | 90% GM | 80% GM | 70% GM | 0% Margin |
|------|-------|--------|--------|--------|-----------|
| Starter $19 | $19 | 1,022 | 2,043 | 3,065 | 10,215 |
| Growth $49 | $49 | 2,634 | 5,269 | 7,903 | 26,344 |
| Pro $99 | $99 | 5,323 | 10,645 | 15,968 | 53,226 |
| Scale $199 | $199 | 10,699 | 21,398 | 32,097 | 106,989 |

---

## 11. Activation Event Semantics Audit

### first_whatsapp_inbound
- **Current semantics:** First per conversation (new Conversation created)
- **Recommended:** First per store (check if any prior WhatsApp conversation exists for this store)
- **Correction needed:** YES — add `is_first_store_inbound` property

### first_whatsapp_ai_reply
- **Current semantics:** Per conversation (every AI reply to new conversation)
- **Recommended:** First per store (check if any prior AI reply exists for this store)
- **Correction needed:** YES — add `is_first_store_ai_reply` property

---

## 12. Data Quality Summary

| Input | Status |
|-------|--------|
| AI model ID | KNOWN |
| Model pricing | EXTERNAL_PRICE_REQUIRED |
| Token usage per interaction | MEASURABLE_NOW |
| Prompt composition | KNOWN |
| Catalog context size | KNOWN |
| Knowledge/RAG context | KNOWN |
| Conversation history | KNOWN |
| WhatsApp cost to Diaglob | KNOWN (NONE) |
| Paddle fees | EXTERNAL_PRICE_REQUIRED |
| Infrastructure cost | NEEDS_PRODUCTION_SAMPLE |
| Usage distribution | NEEDS_PRODUCTION_SAMPLE |

---

## 13. Recommendations

### Block 5 Go/No-Go
**GO BLOCK 5** — Pricing analysis is complete enough to proceed. We have:
- Clear model identification
- Token usage now measurable
- Economic model defined
- Safe included usage amounts recommended
- Overage pricing recommended

### Next Steps
1. Collect 1-2 weeks of production usage data via PostHog
2. Validate token estimates against real data
3. Finalize pricing with Adrián
4. Implement pricing changes
5. Proceed to Block 5 (Automation Templates + Dropi Value)
