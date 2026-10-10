# DIAGLOB — Shopify App Store submission kit (copy + evidence checklist)
Prepared 2026-10-10 by ChatGPT · **DRAFT / DO NOT SUBMIT**

## Positioning guard
Audience: dropshippers and ecommerce teams rather than developers. Explain outcomes first: see your store in one place, stay on top of orders, organize repetitive work and use an assistant to find information. Avoid unverifiable claims (guaranteed sales, unlimited AI, instant supplier availability, certified GDPR compliance, automated checkout outside Shopify, unsupported workflow execution).

**Provisional English app name:** DIAGLOB (verify naming and trademark).

### Public listing copy — candidate
**Subtitle:** Keep your Shopify store organized from one workspace.

**Short introduction:** DIAGLOB brings your products, order visibility, team workflows, and AI-assisted support together to help you spend less time switching tools.

**Description:**
Running an online store shouldn't require jumping between disconnected tools. DIAGLOB gives ecommerce teams a shared workspace to view the Shopify catalog and order information available to their business, coordinate work, and use an AI assistant with the permissions granted to each team member.

Use DIAGLOB to organize store activity, understand what needs attention, and configure available operational workflows. Features and integration availability depend on your connected services, plan and configuration.

DIAGLOB does not replace Shopify Checkout. Product and supplier availability must be confirmed from the connected source before any fulfillment commitment.

**Candidate benefit bullets (remove any item not proven in E2E):**
- Review products and available store/order information in one workspace.
- Give team members access according to their roles.
- Use the AI assistant to help locate information and navigate supported tools.
- Configure and review only automation workflows supported by the current release.

**Do NOT advertise as live:** complete privacy erasure, executable drag-and-drop flows not yet implemented, guaranteed supplier stock, direct-to-customer payments bypassing Shopify, or Shopify App Pricing before subscription setup.

**Draft keyword themes:** ecommerce operations; order visibility; catalog organization; dropshipping operations; store automation; AI assistant. Verify actual Shopify keyword guidance and unsupported claims before publication.

### Required public assets
- Existing DIAGLOB brand artwork: use the selected D/arrow logo; create the required **1200×1200 PNG/JPEG app icon** from the final approved source without replacing identity.
- Capture genuine production-equivalent English interface screenshots from a development store **after install works**; no synthesized UI proof or screenshots from stale builds.
- Short screencast showing: Shopify-owned Install → OAuth approval → functioning DIAGLOB UI → verified shop → catalog/order view (synthetic data) → permitted Copilot scenario → supported automation → support/contact/exit.
- Functional reviewer account and dedicated test development store with authorized access; **never commit credentials, passwords, store tokens or screenshots containing customer PII**.
- Valid public privacy/terms URLs, support inbox, emergency developer contact email/phone, app API contact, and confirmed TLS/redirect URLs.

## Reviewer instruction draft — placeholders must be replaced
1. Install DIAGLOB using the existing App Store/Partner installation flow on **[approved reviewer development store]**.
2. Complete Shopify OAuth and confirm the UI opens successfully without unapproved extra setup.
3. Log in using the secure credentials provided **in the Partner Dashboard** (not in source control).
4. Review the test catalog and any seeded order records; no real customer purchases or fulfillment.
5. Ask DIAGLOB AI assistant for information about an explicitly active test product. Explain expected answer and required role.
6. Demonstrate one workflow that the release actually executes end-to-end; if automation execution isn't supported, exclude the feature from listing and demo.
7. Provide a documented test privacy callback procedure, HMAC verification evidence and redaction/export behavior once operationally implemented. **Do not submit while callbacks merely acknowledge requests.**
8. Explain subscription selection using Shopify-hosted pricing and show verified entitlement update on test store **after** implemented.
9. Describe uninstall and reinstall auth behavior once E2E verified.

## Partner Dashboard operator checklist (owner / Codex pairing)
- [ ] Confirm **existing** DIAGLOB app identity and Partner organization. Never create another app.
- [ ] Confirm app distribution and whether embedded/standalone; reconcile code, OAuth redirects, allowed domains, required scopes and test accounts.
- [ ] Deploy app-level mandatory webhook subscriptions **only after explicitly approved release** and verify deployed version and signed callback responses.
- [ ] Fill customer protected-data application with **verified** collection/use/retention, field minimization and security statements (do not invent encryption guarantees).
- [ ] Confirm Shopify App Pricing configuration is enabled and public plans approved; verify plan handles and allowed frequencies with Partner API.
- [ ] Complete actual primary-English listing, contact, 1200×1200 icon, screenshot assets, working screencast and reviewer account.
- [ ] Run Shopify automated checks and code self-review; capture dated outcomes, app version and evidence.
- [ ] Run separate no-charge store install/reinstall, subscription and read-only integration E2E; create no real merchant charge without owner authorization.
- [ ] Confirm release readiness gate evidence is complete and QA/owner signoff recorded.
- [ ] Submit only after P0 defects and legal/owner approvals are resolved.

## Technical risks and disclosure accuracy
- Current `docs/shopify-app-store-readiness.md` is a historical audit with later partial updates, not final release evidence.
- Multi-store Shopify pricing and default product/order write scopes have not been validated for current Shopify App Store use.
- Reviewer instructions and descriptions must exactly match **currently working** flows, not future roadmap commitments.
- URLs: https://diaglob.tech / https://diaglob.tech/privacy / https://diaglob.tech/terms / https://api.diaglob.tech — **not verified live in this document**.

Official references:
- https://shopify.dev/docs/apps/launch/app-store-review/submit-app-for-review
- https://shopify.dev/docs/apps/launch/app-store-review/pass-app-review
- https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements
- https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing
