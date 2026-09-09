---
name: frontend-engineering
description: Build and debug the Diaglob React TypeScript Vite frontend, including responsive UI, API integration, routing, billing UI, and production-safe UX changes.
compatibility: opencode
metadata:
  project: diaglob
  scope: frontend
---

## Stack

The frontend uses React 19, TypeScript, Vite, React Router, Axios, i18next, Lucide React, XYFlow, and Paddle JS.

## Rules

- Reuse existing components, layout conventions, API clients, translations, and state patterns before adding new ones.
- Keep TypeScript types aligned with actual backend contracts.
- Do not hide backend failures behind fake success states or hardcoded production data.
- Preserve loading, empty, success, and error states for asynchronous screens.
- Keep UI usable on mobile, tablet, and desktop when modifying layouts.
- Avoid horizontal page overflow. Data-heavy tables should receive an intentional responsive treatment rather than merely shrinking text.
- Preserve accessibility basics: semantic controls, labels, keyboard usability, visible focus, and meaningful button text/tooltips where needed.
- Do not expose secrets or server-only configuration through Vite environment variables.

## API changes

When a frontend task depends on backend data:

1. Inspect the actual backend route/schema.
2. Inspect the existing frontend API call and types.
3. Fix the contract mismatch at the correct layer instead of hardcoding replacement values.

## Validation

```bash
cd frontend
npm run build
npm run lint
```

If lint has unrelated pre-existing failures, report them precisely rather than changing unrelated files solely to obtain a green command.
