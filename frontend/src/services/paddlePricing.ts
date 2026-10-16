export interface PaddlePriceItem {
  priceId: string;
  quantity: number;
}

export interface PaddlePricePreviewRequest {
  items: PaddlePriceItem[];
  address?: { countryCode: string };
}

export interface PaddlePreviewLineItem {
  price?: { id?: string };
  priceId?: string;
  formattedTotals?: { subtotal?: string };
}

export interface PaddleCheckoutOptionsInput {
  priceId: string;
  customerEmail?: string | null;
  countryCode?: string | null;
  customData: Record<string, string | number>;
  origin: string;
}

export function buildPaddlePricePreviewRequest(
  items: PaddlePriceItem[],
  countryCode?: string | null,
): PaddlePricePreviewRequest {
  const normalizedCountry = countryCode?.trim().toUpperCase();
  if (!normalizedCountry || !/^[A-Z]{2}$/.test(normalizedCountry) || normalizedCountry === "XX") {
    return { items };
  }

  return {
    items,
    address: { countryCode: normalizedCountry },
  };
}

export function mapPaddleFormattedTotals(
  lineItems: PaddlePreviewLineItem[],
): Record<string, string> {
  const totals: Record<string, string> = {};
  for (const item of lineItems) {
    const priceId = item.price?.id ?? item.priceId;
    const subtotal = item.formattedTotals?.subtotal;
    if (priceId && typeof subtotal === "string" && subtotal.length > 0) {
      totals[priceId] = subtotal;
    }
  }
  return totals;
}

export function buildPaddleCheckoutOptions({
  priceId,
  customerEmail,
  countryCode,
  customData,
  origin,
}: PaddleCheckoutOptionsInput) {
  const normalizedEmail = customerEmail?.trim();
  const normalizedCountry = countryCode?.trim().toUpperCase();
  const countryIsValid = Boolean(
    normalizedCountry && /^[A-Z]{2}$/.test(normalizedCountry) && normalizedCountry !== "XX",
  );
  const customer = normalizedEmail
    ? {
        email: normalizedEmail,
        ...(countryIsValid
          ? { address: { countryCode: normalizedCountry } }
          : {}),
      }
    : undefined;

  return {
    items: [{ priceId, quantity: 1 }],
    ...(customer ? { customer } : {}),
    customData,
    settings: {
      displayMode: "overlay" as const,
      variant: "one-page" as const,
      successUrl: new URL("/welcome", origin).toString(),
    },
  };
}
