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

Before enabling a provider in production, update the privacy/cookie disclosure for advertising measurement and review the consent requirements that apply to the launch country.

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
