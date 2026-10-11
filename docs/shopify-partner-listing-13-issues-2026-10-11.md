# Shopify App Store: unlock listing → App Pricing → no-charge E2E

**Checkpoint:** 2026-10-11. **Commercial release = NO-GO.**

## Verified facts — distinguish dashboard evidence from code

- Partner organization **DIAGLOB**: `5148778`; existing app numeric ID `416524435457`. These were verified by the authorized Partner operator; **do not assume** numeric dashboard ID is the Partner GraphQL App GID.
- `diaglob-poc.myshopify.com`: Partner operator confirmed Shopify shop type `dev`, sales USD 0 and **Diaglob not installed** (only Dropify shown in Apps). Do not use Bakatá for billing E2E.
- Partner operator reported **13 outstanding App Store listing issues**, including **Pricing plans**, with Shopify App Pricing controls unavailable in this session. The **other 12 issue descriptions were not supplied**. Do not claim they are fixed or invent their titles.
- Last verified production deploy `317553a8` passed GitHub Actions #38145344962; owner-only development-billing probe is deployed **OFF**, anonymous access HTTP 401. Five Partner billing settings absent and `SHOPIFY_BILLING_ENTITLEMENTS_ENABLED` plus `SHOPIFY_BILLING_SCHEDULER_ENABLED` OFF.
- Repository already includes a draft submission packet: `docs/shopify-app-store-publication-kit-2026-10-10.md`. The historic `docs/shopify-app-store-readiness.md` is **not a current Shopify approval certificate**.
- Repo contains `frontend/public/brand/diaglob-mark.svg` and `diaglob-logo-horizontal.svg`, plus square PNG logo variants; **1200×1200 final icon size/appearance has not been verified** and should not be declared complete.

## Resolve the circular-looking pricing blocker

Shopify's public documentation says the USD 0 private test plan is accessible under **Pricing content → Manage → Private plans** once Shopify App Pricing is available; a development store may test eligible paid plans without charges. The owner observed controls **disabled**, so no API, workaround, or fabricated plan handle can solve that state from Diaglob code. This may involve missing submission fields or the app's distribution/pricing eligibility. The **Pricing plans** item might be a consequence of App Pricing being disabled; do not assume the other twelve all must be resolved first unless the Dashboard explicitly says so.

**Authorized operator next action:**
1. Open Partner Dashboard, DIAGLOB org `5148778`, existing app `416524435457`, App Store review / listing checklist. Copy or screenshot **all thirteen exact issue descriptions**, including the detail shown on expanding each. Do not post any secret or test-login password.
2. Classify each exact issue as `listing-field`, `configuration`, `code/security`, `test-evidence`, `account/access` or `pricing`; record which page/control it links to. Fix non-pricing metadata and test instructions before trying Pricing again.
3. Confirm that the **existing** application supports Shopify App Pricing. If the Pricing content control stays disabled, inspect the disabled tooltip/help text or ask Shopify Partner Support with app ID and screenshot; do not switch to manual Billing API just to bypass the review gate.
4. After access is restored, create a **private test plan USD 0** with the verified `diaglob-poc.myshopify.com` store allowlist. Do not create/publish arbitrary Starter/Growth/Pro/Scale prices. The operator must confirm the actual plan structure and handle(s).
5. Authorized organization owner creates a Partner API client with **Manage apps** in the **Partner API clients** area (distinct from merchant product subscription access). Store the token in an approved encrypted destination after access controls, rotation and delivery to the backend are reviewed; no token in tickets, docs or chats.
6. Install the existing Diaglob app through a Shopify-owned install surface on the POC dev shop. Validate OAuth, app UI, and Admin-authenticated Shop GID. Then use the owner-only `GET /api/billing/shopify/development-probe` only with its separate test flags/allowlist explicitly enabled and commercial flags OFF.
7. Confirm the actual Partner `activeSubscription` response, free/private-plan shape, cancellation and reinstall. Only then revisit commercial prices, multishop policies, privacy P0 and release approvals.

## Dashboard issue register — exact thirteen, not guessed

Use the literal Dashboard message in column 2. Only row 1 is currently evidenced; the remainder are deliberately **unidentified**.

| # | Shopify issue text | Exact Dashboard destination | Assigned remediation | Verified resolved? |
|---|---|---|---|---|
| 1 | Pricing plans | Pricing content (disabled) | Restore App Pricing eligibility, then private test plan; no commercial publication | NO |
| 2 | **Not provided** | — | Obtain exact message | NO |
| 3 | **Not provided** | — | Obtain exact message | NO |
| 4 | **Not provided** | — | Obtain exact message | NO |
| 5 | **Not provided** | — | Obtain exact message | NO |
| 6 | **Not provided** | — | Obtain exact message | NO |
| 7 | **Not provided** | — | Obtain exact message | NO |
| 8 | **Not provided** | — | Obtain exact message | NO |
| 9 | **Not provided** | — | Obtain exact message | NO |
| 10 | **Not provided** | — | Obtain exact message | NO |
| 11 | **Not provided** | — | Obtain exact message | NO |
| 12 | **Not provided** | — | Obtain exact message | NO |
| 13 | **Not provided** | — | Obtain exact message | NO |

### Prefill only what is demonstrably true

- **Public URLs to enter and test:** `https://diaglob.tech`, `https://diaglob.tech/privacy`, `https://diaglob.tech/terms`; API at `https://api.diaglob.tech`. Production deploy smoke checks cover health, privacy, and terms, but do not prove legal compliance or protected-data fulfilment.
- **App name:** DIAGLOB, subject to name/branding uniqueness review.
- **English tagline draft:** `Organize your Shopify store in one workspace.`
- **Short description draft:** `View store information, coordinate everyday operations, and use AI-assisted tools to understand what needs attention. Available capabilities depend on your connected services and plan.`
- **Full copy, benefits and reviewer script:** see existing publication kit; **do not claim features not verified against a real Shopify install**.
- **Required human-input fields:** emergency developer email and phone, support contact, accurate privacy/protected-data answers, effective API scopes, functioning reviewer credentials, English demo screencast, genuine app screenshots, verified 1200×1200 icon.
- **App config:** `shopify.app.toml` is not tracked; use Shopify CLI to **link the existing app**, preserving deployed OAuth URLs/scopes. Review mandatory compliance webhook subscriptions, not just callback HTTP 200. Do not fabricate or commit secrets.
- **P0 review risks:** privacy exports/redaction and retention policy still need end-to-end evidence; protected customer data, OAuth install/reinstall, App Bridge (if embedded), unnecessary API scopes and Shopify checkout/merchant billing must be independently verified.

## AWS encrypted destination reserved for Partner credentials (2026-10-11)

Provisioned in AWS account `765761474007`, region `us-east-2`:

- SSM Parameter Store name: `/diaglob/prod/shopify/partner-api-token`
- Type: **SecureString**, tier **Standard**, encrypted with the account-managed KMS alias `aws/ssm`.
- Current value: **placeholder only** — **no authentic Partner API credential** exists in the parameter.
- Not mapped to `SHOPIFY_PARTNER_ACCESS_TOKEN` in the Lightsail service. No production access or feature flags were enabled.
- Tags indicate the value is awaiting authorized operator replacement.

**This reserved location is not yet approved for a real token.** AWS warns that the default `aws/ssm` KMS key is shared across account IAM principals with compatible Parameter Store read permissions and is not a fine-grained secret boundary. **Before replacing the placeholder**, review and restrict IAM SSM read/write access and either move the token to AWS Secrets Manager (preferred for long-lived API tokens and rotation, paid service) or encrypt the parameter under a properly scoped customer-managed KMS key (also potentially charged). Do not store a real Partner credential under the present default-key configuration without this access review.

A Partner organization owner may create the authorized **Manage apps** Partner API client after the approved protected storage and rotation/rollback procedure is ready. **Never send the token over chat, include it in GitHub, print it in CI, place it on a shell command line or expose it in logs.**

A separately reviewed secret-delivery procedure is needed to pass it securely from AWS to the Lightsail runtime and rotate/revoke it safely. Lightsail isn't registered as an SSM managed instance in the current AWS audit, so do not claim automatic retrieval works. No secret has been consumed by production; do not deploy placeholder text as if it were a real Partner token.

## Hard release boundaries

- Shopify App Store **submission**, **public plan publication**, **commercial entitlement activation**, **merchant charges** and **production erasure of personal data** require separate operational/legal authorization.
- Never mark a pending Dashboard issue resolved because a local test or PR passed.
- Never re-label a USD 0 development contract as commercial payment.
- No Bakatá changes; no duplicate Diaglob app.
- If available, Shopify's AI self-review `/shopify-app-store-review` can help code-level readiness, but it does not validate live Partner listing fields, test-store installation or merchant UX.

## Official Shopify documentation

- https://shopify.dev/docs/apps/launch/app-store-review/submit-app-for-review
- https://shopify.dev/docs/apps/launch/app-store-review/pass-app-review
- https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements
- https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing
- https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing/plans
