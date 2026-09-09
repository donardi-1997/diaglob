export interface BillingUpgradeSummaryAmount {
  amount: string;
  currency_code: string;
}

export interface BillingUpgradePreviewLike {
  currency_code: string | null;
  amount_due: string | null;
  update_summary?: {
    credit?: BillingUpgradeSummaryAmount;
    charge?: BillingUpgradeSummaryAmount;
    result?: {
      action: string;
      amount: string;
      currency_code: string;
    };
  };
}

export interface BillingUpgradePayableAmount {
  amount: string;
  currencyCode: string;
}

export function getBillingUpgradePayableAmount(
  preview: BillingUpgradePreviewLike,
): BillingUpgradePayableAmount | null {
  const result = preview.update_summary?.result;
  const resultAmount = Number(result?.amount ?? "");

  if (
    result &&
    result.action === "charge" &&
    Number.isFinite(resultAmount) &&
    resultAmount > 0
  ) {
    return {
      amount: String(Math.trunc(resultAmount)),
      currencyCode:
        result.currency_code ||
        preview.currency_code ||
        "USD",
    };
  }

  const amountDue = Number(preview.amount_due ?? "");

  if (Number.isFinite(amountDue) && amountDue > 0) {
    return {
      amount: String(Math.trunc(amountDue)),
      currencyCode:
        preview.currency_code ||
        result?.currency_code ||
        "USD",
    };
  }

  const charge = preview.update_summary?.charge;
  const chargeAmount = Number(charge?.amount ?? "");

  if (
    charge &&
    Number.isFinite(chargeAmount) &&
    chargeAmount > 0
  ) {
    return {
      amount: String(Math.trunc(chargeAmount)),
      currencyCode:
        charge.currency_code ||
        preview.currency_code ||
        "USD",
    };
  }

  return null;
}

export function normalizeBillingUpgradePreview<
  T extends BillingUpgradePreviewLike,
>(preview: T): T {
  const payable = getBillingUpgradePayableAmount(preview);

  if (!payable) {
    return preview;
  }

  return {
    ...preview,
    currency_code:
      preview.currency_code || payable.currencyCode,
    amount_due:
      preview.amount_due || payable.amount,
    update_summary: {
      ...preview.update_summary,
      result: {
        action: "charge",
        amount: payable.amount,
        currency_code: payable.currencyCode,
      },
    },
  };
}
