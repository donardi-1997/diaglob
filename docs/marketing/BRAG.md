# Diaglob launch videos with /brag

This repository uses [latent-spaces/brag](https://github.com/latent-spaces/brag) as a **development and marketing tool** for short product videos.

It is not a runtime dependency of Diaglob and it must not be required to build or deploy the application.

## Why we use it

/brag reads the project source, identifies the product story and UI, creates a short storyboard and renders a launch-style video.

For Diaglob, the strongest current product story is:

1. Connect the ecommerce operation.
2. See the business from one operational view.
3. Ask the Diaglob Copilot what is happening.
4. Turn the answer into an automation.

This maps directly to existing product copy and UI in:

- `frontend/src/pages/PublicLandingPage.tsx`
- `frontend/src/pages/DashboardPage.tsx`
- `frontend/src/pages/IntegrationsHubPage.tsx`
- `frontend/src/pages/AutomationsPage.tsx`
- `frontend/src/components/FloatingCopilotButton.tsx`

## Install locally

The install is intentionally project-scoped. Do not install it globally for the first test.

### PowerShell

```powershell
./scripts/setup-brag.ps1
```

### Bash

```bash
./scripts/setup-brag.sh
```

The scripts install the upstream `brag` skill using the official Agent Skills installer and verify the local prerequisites.

Upstream requirements:

- Node.js 22+
- FFmpeg on PATH
- Hyperframes CLI, available through `npx hyperframes`

## First Diaglob test

Run the agent from the repository root and use:

```text
/brag --format vertical --duration 20 --tone app-store

Create a launch/ad video for Diaglob focused on ecommerce and dropshipping.

Use the existing product UI and existing product copy. The story should be:
connect the operation -> understand what is happening -> ask the Copilot -> automate the next action.

Prioritize these real screens and components:
- public ecommerce landing page
- Operations Center / dashboard
- Integrations
- Diaglob Copilot
- Automations

Use the paid-ecommerce landing claim as the hook:
"Deja de operar tu ecommerce entre cinco herramientas."

Use "Tu negocio, bajo control." as the main product reveal.

For the Copilot beat, use the existing demo interaction from PublicLandingPage:
"¿Qué pasó hoy con mis pedidos de Colombia?"
then transition to "Automatizar seguimiento".

Treat any order counts, percentages, store names, customer names or other business data as demo data. Never pull production data or secrets into the video.

End with a concise Diaglob CTA based only on claims already present in the repository.

Render locally. Do not publish or upload the result anywhere.
```

## Recommended 20-second storyboard

The skill should still inspect the current code before rendering. This storyboard is a direction, not a hardcoded template.

| Time | Beat | Source |
| --- | --- | --- |
| 0-2.5s | **Hook:** “Deja de operar tu ecommerce entre cinco herramientas.” | Paid ecommerce landing |
| 2.5-5s | **Reveal:** Diaglob Operations Center — “Tu negocio, bajo control.” | Dashboard |
| 5-8s | **Connected operation:** Shopify / messaging / suppliers / payments / knowledge in one ecosystem | Integrations |
| 8-13s | **Copilot:** ask what happened with the business; show a concise answer | Landing Copilot demo / product Copilot |
| 13-17s | **Action:** “Automatizar seguimiento” -> visual automation flow | Automations |
| 17-20s | **Outro:** orders, customers, automations, reporting and AI Copilot in one place | Paid ecommerce landing |

## Creative defaults

For paid social tests:

- Format: vertical, 1080x1920
- Duration: 18-22 seconds
- Tone: `app-store` or `polished`
- Language: Spanish first
- Product data: fictional/demo only
- Voiceover: disabled for the first iteration
- Music: use only music approved for commercial advertising

For a homepage/product launch variant:

```text
/brag --format landscape --duration 20 --tone polished
```

## Privacy and security rules

/brag is allowed to read normal product source files, but generated marketing material must never contain:

- `.env` values
- API keys or tokens
- AWS credentials
- private internal URLs
- customer names
- customer emails or phone numbers
- real order/customer data
- authentication credentials
- production screenshots containing personal or operational data

Use the product's built-in demo copy or fictional stand-ins.

Rendering must stay local. Uploading or publishing a rendered video requires a separate explicit decision.

## Output

/brag writes generated artifacts into:

```text
brag-output/
```

or a timestamped `brag-output-*/` directory.

These directories are ignored by Git and must not be committed by default.

The useful deliverables are:

- `brag.mp4`
- `brag.jpg`
- `brag-plan.md`
- `composition-brief.md`
- `share-copy.txt`

## Review checklist before using a video in ads

1. All product claims exist in the current Diaglob product/code.
2. No production or customer data is visible.
3. Text remains readable on a phone.
4. The first two seconds explain the pain or show the product.
5. The working product is visible, not just abstract animation.
6. The CTA matches the destination page.
7. Music/SFX are cleared for commercial use.
8. Meta/TikTok safe areas do not cover key copy or controls.
9. The video is reviewed once muted and once with audio.
10. The final asset is exported separately from the Git repository.
