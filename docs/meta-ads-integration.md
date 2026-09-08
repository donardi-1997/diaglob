# Meta Ads Integration

## Architecture

```
Frontend → Diaglob API → Meta Ads Service → Meta Ads Client → Meta Graph API
                                    ↓
                              Ads Analytics Service ← Commerce Data (Orders)
```

## Meta API Version

- **Graph API:** v21.0 (configurable via `META_GRAPH_API_VERSION`)

## Required Permissions

- `ads_read` — Read ad account data
- `ads_management` — Manage ad campaigns (future)
- `business_management` — Access business assets

## OAuth Flow

1. Frontend requests OAuth URL from `meta_ads_service.get_oauth_url()`
2. User authorizes in Meta
3. Meta redirects to callback with code
4. Backend exchanges code for access token
5. Backend lists accessible ad accounts
6. User selects account for store
7. Backend encrypts and stores token

## Environment Variables

| Variable | Description |
|----------|-------------|
| `META_APP_ID` | Meta App ID |
| `META_APP_SECRET` | Meta App Secret |
| `META_ADS_REDIRECT_URI` | OAuth callback URL |
| `META_ADS_ENCRYPTION_KEY` | Fernet encryption key for tokens |
| `META_GRAPH_API_VERSION` | Graph API version (default: v21.0) |

## Account Selection

One Meta Ads account per Diaglob store.

- Colombia Store → Meta Account Colombia
- Peru Store → Meta Account Peru
- Mexico Store → Meta Account Mexico

## Security

- Access tokens encrypted with Fernet
- OAuth state validated
- Account selection validated against authorized accounts
- No raw tokens in frontend/logs

## Metric Definitions

| Metric | Formula |
|--------|---------|
| Revenue | Sum of eligible orders in period |
| Ad Spend | Meta Insights `spend` |
| Blended ROAS | Revenue / Ad Spend |
| CPA (Orders) | Ad Spend / Orders |
| AOV | Revenue / Orders |
| CPA (Delivered) | Ad Spend / Delivered Orders |

## Limitations

- Blended ROAS, not attributed campaign ROAS
- No cross-currency aggregation
- No campaign-level attribution yet
- Delivery rate requires canonical order statuses
