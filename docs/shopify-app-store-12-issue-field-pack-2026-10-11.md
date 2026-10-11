# DIAGLOB: Shopify App Store listing — 12 verified issues (2026-10-11)

> **Status:** fields and creative prepared, not saved in Partner. No App Pricing activation, no live billing, no reviewer account or demo evidence. Commercial launch: **NO-GO**.
>
> Source: Partner operator's 2026-10-11 screenshot, which **supersedes** the older 13-issue assessment. The 12 missing fields are listed below individually, exactly as grouped in Shopify's UI.

Partner organization **5148778**, original Diaglob app **416524435457**. `diaglob-poc.myshopify.com` verified `dev` by the operator; DIAGLOB was **not installed** in its Apps panel. Do not use Bakatá for billing E2E.

## Issue-by-issue remediation

| # | Partner UI issue | Specific value / remediation | Evidence state |
|---|---|---|---|
| 1 | Basic app information: **App category** | Recommend **Store management → Operations → Operations - Other**. Use **Workflow automation** as primary tag only after end-to-end workflow execution has been proven; confirm category options in Partner UI. | Category proposed, **not submitted** |
| 2 | App store listing content: **Feature media** | Candidate 1600×900 PNG provided in user export bundle: `diaglob-feature-media-1600x900.png`. Brand graphic, not a simulated software screenshot. English ALT: "DIAGLOB ecommerce operations graphic illustrating products, orders, and team workflows." | Image generated; **not uploaded** |
| 3 | App store listing content: **Screenshots** | Capture **3–6 genuine 1600×900** UI views from a working authorized DIAGLOB development install: products, orders, team workspace and only verified/working assistant or automation. Crop browser chrome, blur private data, use unique scenes. | **Blocked** until live DIAGLOB installation / login |
| 4 | App store listing content: **Support** | Enter a real verified public support link and monitored inbox; confirm reception before saving. Do **not** invent `support@diaglob.tech` or a nonexistent contact page. | Requires tested support channel |
| 5 | Pricing details: **Pricing plans** | Investigate disabled Pricing content; under Shopify App Pricing, first use a **private test plan USD 0** allowlisted for `diaglob-poc.myshopify.com`. Public tiers and pricing candidates are **not approved**. Do not bypass UI/Partner eligibility. | **Blocked** by Partner configuration |
| 6 | App discovery content: **App store search terms** | Five independent terms: `store management`; `order management`; `product organization`; `ecommerce operations`; `team workflows`. Confirm exact UI features before publishing. | Text prepared, **not saved** |
| 7 | Install requirements: **Sales Channel requirements** | DIAGLOB is a **regular operations app**, not a Shopify Sales Channel. If its release uses Admin APIs only and no Online Store theme/POS features, select **Online Store NOT required** and **POS NOT required**. Verify actual scopes/extensions first. | Recommendation, needs app config check |
| 8 | Contact information: **Merchant review email** | Confirm a monitored authorized email for merchant review. Do not guess an address. | Requires operator |
| 9 | Contact information: **App submission email** | Use an authorized developer contact inbox that receives Shopify review messages; same inbox as #8 only if appropriate. | Requires operator |
| 10 | App testing information: **Test account** | Create a real reviewer account with sufficient feature access on synthetic data. Test login in incognito; put credentials **only in Shopify's private review form**, not GitHub/chat. | **Blocked** until provisioned and verified |
| 11 | App testing information: **Screencast URL** | Record authentic English/English-subtitled install/OAuth + DIAGLOB UI/products/orders/role access + supported workflows + safe billing step **after available**. Host at reviewer-accessible HTTPS URL. | **Blocked** until recording |
| 12 | App testing information: **Testing instructions** | Copy the reviewer script below; remove unverified features before submission and supply private credentials separately. | Draft prepared, needs live QA |

**12 = 1 category + 3 listing-media/support + 1 pricing + 1 discovery + 1 install requirement + 2 contacts + 3 testing.**

## Ready-to-paste English listing drafts

**App name:** DIAGLOB

**App card subtitle:** Keep products and orders organized in one workspace.

**App introduction:** Bring products, order visibility, and daily store operations into one workspace.

**App details draft:** DIAGLOB helps ecommerce teams review the store information they need for everyday operations. Bring connected Shopify product and order information into one workspace, coordinate work with teammates, and navigate available tools with AI-assisted guidance. Capabilities depend on connected integrations, organization permissions, and plan configuration. DIAGLOB does not replace Shopify Checkout.

**App Store search terms**, enter as five distinct entries (not one string):
1. store management
2. order management
3. product organization
4. ecommerce operations
5. team workflows

**Feature-media ALT:** DIAGLOB brand graphic: Know your store, stay in control — products, orders, and team workflows.

### Reviewer testing instructions (verify each step before pasting)

1. Open DIAGLOB through the **Shopify-owned** install entry point for the approved development shop. Do not ask the reviewer to type a shop domain into an offsite installation form.
2. Complete Shopify OAuth, check that DIAGLOB loads and displays the connected store, and use the reviewer account supplied **privately in Shopify Partner** if the app asks for a separate DIAGLOB login.
3. Open Products and inspect synthetic test products associated with the test shop. Verify the product and store mapping.
4. Open Orders and review synthetic test orders, with **no real charges, customer purchases, or fulfillment**.
5. Review team permissions on an authorized role; unsupported features must not be claimed as functional.
6. Show one **already proven** assistant/automation scenario and expected output; omit if the release cannot execute it end-to-end.
7. **Only when Partner permits it:** select the store-authorized private USD 0 Shopify App Pricing plan, verify `activeSubscription`, and ensure no commercial entitlements are granted based on a development contract. Remove this step until it exists.
8. Uninstall/reinstall and verify renewed Shopify OAuth, privacy/terms/help links, and return to the DIAGLOB UI.

### English screencast storyboard

- 00:00–00:20 Shopify development shop + approved DIAGLOB install entry.
- 00:20–00:45 OAuth and app landing.
- 00:45–01:20 Genuine products/orders with synthetic fixtures.
- 01:20–01:45 Roles and only verified assistant/automation.
- 01:45–02:15 Private Shopify USD 0 plan **only after Partner actually unlocks pricing**.
- 02:15–02:40 Reinstall and support/help/privacy.

Shopify requires complete test credentials and an English or English-subtitled screencast; do **not** use synthetic screenshots as proof.

## Delivered creative, upload by authorized operator

The user export bundle `diaglob-shopify-listing-kit.zip` contains:

- `diaglob-app-icon-1200.png` (1200×1200) — candidate PNG rasterized from the already-tracked, geometric DIAGLOB SVG mark at `frontend/public/brand/diaglob-mark.svg`. Owner must approve final styling.
- `diaglob-feature-media-1600x900.png` (1600×900) — brand graphic promoting products/orders/team workflows, **not** an app UI screenshot.
- `SHOPIFY_SUBMISSION_12_ISSUES.md` — field copy plus recording steps.

The PNG assets were exported for user download; **they are not stored in this Git commit and have not been uploaded to Shopify Partner**.

## Pricing and installation release blockers (separate from filling form fields)

- Partner App Pricing is currently disabled; no public/private plan handles. Only Partner-authorized account access can opt in and save plans.
- Commercial charges and entitlement flags remain disabled. Don't publish unapproved candidate prices.
- Shopify compliance (privacy export/redaction, installed app OAuth/App Bridge rules, GraphQL scope minimization, customer data, and checkout) requires independent end-to-end evidence beyond the listing form.
- The current operator-confirmed `dev` store is *eligible* for free billing tests, but DIAGLOB is **not installed**. No E2E has been claimed.
- A reserved SSM `SecureString` placeholder is **not a real Partner token** or a properly approved secret-handling workflow.
- Do not classify the application as a Sales Channel merely to satisfy a sales-channel requirement field.

## Official Shopify references

- https://shopify.dev/docs/apps/launch/app-store-review/app-listing-categories
- https://shopify.dev/docs/apps/launch/shopify-app-store/best-practices
- https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements
- https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing
- https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing/plans
