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

## Payments

- Local-payment market policy reserves **PIX exclusively for BR/BRL**.
- Nequi is not eligible for Brazilian stores; Nequi remains **CO/COP only**.
- PIX market eligibility does **not** mean PIX processing is live yet.
- A concrete Brazilian PSP/bank adapter must be selected and implemented before PIX can be connected or charged.
- Do not expose PIX as connected/usable unless a supporting provider adapter and connection exist.

## Billing

- Current subscription prices are USD
- No BRL billing yet
- Plans displayed as: US$ 19/mês (under pt-BR)

## Current Limitations

| Feature | Status |
|---------|--------|
| BRL billing | NOT SUPPORTED |
| PIX market eligibility | BR/BRL ONLY |
| PIX processing provider | NOT IMPLEMENTED |
| NF-e/NFS-e | NOT SUPPORTED |
| LGPD certification | NOT CERTIFIED |
| Brazilian tax compliance | NOT SUPPORTED |
| Local Brazilian support | NOT AVAILABLE |
| Automatic FX conversion | NOT SUPPORTED |

## Pilot Recommendation

- 3-5 Brazilian Shopify merchants
- Track: onboarding, WhatsApp, AI quality, Meta Ads BRL, support friction
- Do not promise live PIX collection until a concrete PSP adapter is implemented and validated
