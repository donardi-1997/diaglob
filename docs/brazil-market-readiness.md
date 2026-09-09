# Brazil Market Readiness

## Supported Locale

- **Locale:** pt-BR (Brazilian Portuguese)
- **Country:** BR (Brazil)
- **Currency:** BRL (Brazilian Real)
- **Timezone:** America/Sao_Paulo (and other Brazilian time zones)

## Language Behavior

- Dashboard UI can be switched to pt-BR
- Language preference persists in localStorage (`diaglob-language`)
- Fallback order: selected locale → English → translation key
- Language is separate from store country/currency/timezone

## Brazilian Formatting

### Numbers

Under pt-BR locale:
- 1,234.56 → 1.234,56
- Uses browser `Intl.NumberFormat('pt-BR')`

### Currency

- BRL: R$ 1.234,56
- USD: US$ 1.234,56 (or US$19.00)
- Currency follows the underlying data currency, not the UI locale

### Dates

- pt-BR format: dd/MM/yyyy
- Uses browser `Intl.DateTimeFormat('pt-BR')`

### Timezones

- Brazil spans multiple time zones
- Store timezone is authoritative
- Not all Brazilian stores use America/Sao_Paulo

## Phone Support

- Brazilian country code: +55
- E.164 storage format preserved: +5511999999999
- Display may be localized: (11) 99999-9999

## AI Language Behavior

- AI responds in the customer's language
- Portuguese customer → Portuguese response
- Spanish customer → Spanish response
- English customer → English response
- Dashboard language does NOT force chat language

## Meta Ads Brazil

- BRL spend supported
- BRL revenue + BRL spend → Blended ROAS supported
- BRL revenue + USD spend → Blended ROAS N/A (no FX)
- Meta account timezone respected

## Payments — PIX

- PIX processing is implemented through Mercado Pago's Payments API.
- Provider code: `mercado_pago`
- Payment method: `pix`
- Market restriction: `BR` + `BRL` only.
- Connection credential: Mercado Pago private Access Token, encrypted through the existing payment connection secret storage.
- Payment creation requires payer email and CPF.
- Payment creation uses `X-Idempotency-Key`.
- Initial payment response can include PIX copy-and-paste code, QR image payload, and ticket URL in `action_data`.
- Status reconciliation, cancellation, and full refund are supported through the provider adapter.
- Mercado Pago webhook verification is not enabled in this phase; status reconciliation remains available through the payment API.

## Billing

- Current subscription prices are USD
- No BRL subscription billing yet
- PIX here is for store/customer payment processing; it does not change Diaglob subscription billing
- Plans displayed as: US$ 19/mês (under pt-BR)

## Current Limitations

| Feature | Status |
|---------|--------|
| BRL subscription billing | NOT SUPPORTED |
| PIX customer payments via Mercado Pago | BACKEND SUPPORTED |
| PIX connection UI | PENDING |
| Mercado Pago webhook verification | PENDING |
| NF-e/NFS-e | NOT SUPPORTED |
| LGPD certification | NOT CERTIFIED |
| Brazilian tax compliance | NOT SUPPORTED |
| Local Brazilian support | NOT AVAILABLE |
| Automatic FX conversion | NOT SUPPORTED |

## Pilot Recommendation

- 3-5 Brazilian Shopify/Nuvemshop merchants
- Validate Mercado Pago test credentials before enabling production credentials
- Track: onboarding, PIX conversion, reconciliation, refunds, WhatsApp, AI quality, Meta Ads BRL, support friction
- Do not describe BRL subscription billing, tax compliance, or webhook-driven PIX reconciliation as supported yet
