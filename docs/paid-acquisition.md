# Paid acquisition tracking

Diaglob captures campaign attribution before paid traffic is enabled.

## Supported attribution parameters

- `utm_source`
- `utm_medium`
- `utm_campaign`
- `utm_content`
- `utm_term`
- `fbclid`
- `ttclid`

The browser keeps a first-touch and last-touch snapshot in local storage.

## Funnel events

| Diaglob event | Meta | TikTok |
| --- | --- | --- |
| `landing_view` | `ViewContent` | `ViewContent` |
| `registration_started` | custom | custom |
| `registration_submitted` | `Lead` | `Lead` |
| `complete_registration` | `CompleteRegistration` | `CompleteRegistration` |
| `pricing_plan_interest` | custom | custom |

`complete_registration` fires only after email confirmation, Cognito login and account provisioning succeed.

## Pixel activation

Set these variables in the frontend production environment:

```
VITE_META_PIXEL_ID=<meta-pixel-id>
VITE_TIKTOK_PIXEL_ID=<tiktok-pixel-id>
```

If a variable is absent, that provider is not loaded.

Advertising providers are consent-gated in the frontend. Meta Pixel and TikTok Pixel are not loaded until the user enables **Advertising and measurement** in the cookie preferences.

Consent is stored under `diaglob-cookie-consent-v1`. Users can reopen the **Cookies** control and revoke advertising measurement. Revocation clears Diaglob's local campaign-attribution storage and reloads the page so previously loaded advertising scripts are no longer active.

The public Privacy Policy documents Meta Pixel, TikTok Pixel, campaign identifiers, and the consent/withdrawal flow.

## UTM convention for the first Meta test

Use:

```
utm_source=meta
utm_medium=paid_social
utm_campaign=launch_colombia
utm_content=<creative-name>
```

Example creative values:

```
chaos_tools_v1
shopify_automation_v1
ai_copilot_v1
product_demo_v1
```

For TikTok, change only the source:

```
utm_source=tiktok
utm_medium=paid_social
utm_campaign=launch_colombia
utm_content=<creative-name>
```


## Server-side Meta Conversions API

Diaglob sends the final `CompleteRegistration` conversion from the backend when
advertising consent is enabled. The browser Pixel and the server event share the
same `event_id`, so Meta can deduplicate the conversion instead of counting the
registration twice.

The backend persists campaign attribution in
`marketing_registration_attributions`. It stores campaign metadata and delivery
status, but it does **not** persist raw email, client IP, or user-agent values.

Required backend variables:

```
META_PIXEL_ID=<meta-pixel-id>
META_CONVERSIONS_API_ACCESS_TOKEN=<meta-capi-token>
META_GRAPH_API_VERSION=<configured-graph-version>
```

Optional validation variable:

```
META_CAPI_TEST_EVENT_CODE=<meta-events-manager-test-code>
```

If the Pixel ID or Conversions API token is absent, registration still succeeds and
the attribution row is stored with `meta_delivery_status=disabled`.

### Registration event flow

```
Meta ad
  -> diaglob.tech/?utm_source=meta&...&fbclid=...
  -> consent accepted
  -> first/last touch stored in browser
  -> registration confirmed
  -> backend persists attribution
  -> backend sends CompleteRegistration through CAPI
  -> browser sends CompleteRegistration through Pixel
     using the same event_id
```

This tracking is for Diaglob's own customer acquisition. Merchant Meta Ads
connections remain isolated under the existing per-store Meta Ads integration.
