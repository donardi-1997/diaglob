# Diaglob Web Pixel — bootstrap existing Shopify app

## Verified status

- Production deployment of commit 7839479f succeeded (GitHub Actions #38192329062).
- The repository still lacks a Shopify CLI-generated extension UID and a verified linked Shopify app configuration.
- Shopify CLI is unavailable in the assistant's container and its terminal cannot reach npmjs.com or github.com due DNS restrictions.
- The ChatGPT Shopify connection is to Bakatá, NOT Diaglob POC. No live Partner app version or Meta event was deployed from this environment.

## One-shot setup in Windows PowerShell

Prerequisites: Node.js, Shopify CLI, authenticated access to the EXISTING Diaglob app in Shopify Developer Dashboard, and a local checkout of donardi-1997/diaglob at this PR.

1. Find the EXISTING Diaglob app Client ID in Developer Dashboard. This is not the numeric Partner organization ID or store domain.
2. Install Shopify CLI if needed: npm install -g @shopify/cli
3. Authenticate interactively: shopify auth login
4. From the repository root run:

   node scripts/shopify/prepare-meta-web-pixel.mjs --client-id CLIENT_ID_OF_EXISTING_DIAGLOB_APP

The script operates from the dedicated shopify/cli-app workspace (which has its own package.json), links only the specified app via Shopify CLI, checks its actual Client ID, generates the official UID, and transfers the staged inert pixel source. It does not create another Shopify app, modify the Diaglob web backend, or require a generated app home. It fails closed on app mismatch, UID missing, existing modified extension or invalid template. It does not create a new app, publish an extension, change scopes or enable events.

5. Confirm the app is the right one, its configuration is intact and the necessary scopes have been explicitly approved: write_pixels, read_customer_events and read_pixels. Changes to scopes may require merchant reauthorization.
6. To create a preview app version but NOT release it, run:

   node scripts/shopify/prepare-meta-web-pixel.mjs --client-id CLIENT_ID_OF_EXISTING_DIAGLOB_APP --deploy-draft

This invokes shopify app config validate and shopify app deploy --no-release from shopify/cli-app using the CLI --path flag. Review shopify/cli-app/shopify.app.toml and shopify/cli-app/extensions/diaglob-meta-pixel before drafting. It NEVER executes shopify app release.

## Mandatory gates before recording customer events

- Use only diaglob-poc.myshopify.com. Keep Bakatá excluded.
- The generated extension has trackingEnabled false and still has no customer-event collector or Meta CAPI delivery. It is NOT an active Pixel.
- Keep META_WEB_PIXEL_SHOPIFY_PROVISION_ENABLED and META_WEB_PIXEL_EXTENSION_DEPLOYED false and shop allowlist empty until dev-app review, scopes and actual extension publishing are verified.
- Implement a secure consent-aware collector and per-store Meta token handling before any event can be enabled; do not treat a public sourceId or browser Purchase as proof of Shopify purchase.
- Validate Shopify Customer Events and Meta Events Manager test reception, five standard events, consent denied/granted, anti-duplication with Facebook & Instagram Shopify app, store isolation, uninstall/reinstall and no charges.

Issue #203 remains open until these E2E tests prove the system receives genuine events.

Official references:
https://shopify.dev/docs/apps/build/marketing/build-web-pixels
https://shopify.dev/docs/api/shopify-cli/app/app-config-link
https://shopify.dev/docs/api/shopify-cli/app/app-deploy
https://shopify.dev/docs/api/admin-graphql/latest/objects/WebPixel
