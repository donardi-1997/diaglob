"""One-off PlansPage adjustments for local merchant trials."""
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "frontend/src/pages/PlansPage.tsx"


def replace_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise SystemExit(f"Expected PlansPage block not found: {old[:100]!r}")
    return text.replace(old, new, 1)


def main() -> None:
    text = PATH.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "  const [loadingPlan, setLoadingPlan] = useState(true);\n\n",
        "  const [loadingPlan, setLoadingPlan] = useState(true);\n\n"
        "  const [trialStatus, setTrialStatus] = useState<{\n"
        "    status: string;\n"
        "    started_at: string | null;\n"
        "    ends_at: string | null;\n"
        "    days_remaining: number | null;\n"
        "    ai_response_limit: number;\n"
        "  } | null>(null);\n\n",
    )

    text = replace_once(
        text,
        "  const daysUntilRenewal =\n    getDaysUntilBilling(\n      nextBilledAt,\n    );\n\n",
        "  const daysUntilRenewal =\n    getDaysUntilBilling(\n      nextBilledAt,\n    );\n\n"
        "  const hasPaidPlan = Boolean(\n"
        "    currentPlan &&\n"
        "    (planOrder[currentPlan.toLowerCase()] ?? 0) > 0,\n"
        "  );\n\n",
    )

    text = replace_once(
        text,
        "          const hasActivePlan =\n            normalizedPlan !== \"none\";\n\n"
        "          if (hasActivePlan) {\n",
        "          const hasActivePlan =\n"
        "            (planOrder[normalizedPlan] ?? 0) > 0;\n\n"
        "          setTrialStatus(organization.trial);\n\n"
        "          if (hasActivePlan) {\n",
    )

    # Paid subscription controls must not treat the local free trial as Paddle.
    text = text.replace(
        "          {currentPlan &&\n            currentPlan.toLowerCase() !== \"none\" && (",
        "          {hasPaidPlan && (",
    )
    text = text.replace(
        "                currentPlan &&\n                currentPlan.toLowerCase() !== \"none\" &&\n                period.months !== currentBillingPeriod",
        "                hasPaidPlan &&\n                period.months !== currentBillingPeriod",
    )
    text = text.replace(
        "        {currentPlan &&\n          currentPlan.toLowerCase() !== \"none\" && (",
        "        {hasPaidPlan && (",
    )
    text = text.replace(
        "                  currentPlan.toLowerCase() !== \"none\" &&\n                  isImmediateUpgrade",
        "                  hasPaidPlan &&\n                  isImmediateUpgrade",
    )
    text = text.replace(
        "                          currentPlan &&\n                          currentPlan.toLowerCase() !== \"none\"",
        "                          hasPaidPlan",
    )
    text = text.replace(
        "                                ? t(\"plansUpgrade\")",
        "                                ? t(\"plansUpgrade\")",
    )
    text = text.replace(
        "                                  currentPlan.toLowerCase() !== \"none\"\n                                ? t(\"plansUpgrade\")",
        "                                  hasPaidPlan\n                                ? t(\"plansUpgrade\")",
    )
    text = replace_once(
        text,
        "        enabled={Boolean(\n          currentPlan && currentPlan.toLowerCase() !== \"none\"\n        )}\n",
        "        enabled={hasPaidPlan}\n",
    )

    # Hide auto-renew entirely until Paddle owns a paid subscription.
    text = replace_once(
        text,
        "      <section className=\"auto-renew-plan-section\">\n",
        "      {hasPaidPlan && (\n"
        "      <section className=\"auto-renew-plan-section\">\n",
    )
    text = replace_once(
        text,
        "      </section>\n\n\n      {upgradePreview && upgradePlan && (",
        "      </section>\n"
        "      )}\n\n\n      {upgradePreview && upgradePlan && (",
    )

    # Trial status is visible using translation fallbacks without requiring a
    # synchronized locale-file migration for this functional PR.
    marker = "      {pendingPlan && (\n"
    banner = '''      {trialStatus?.status === "pending" && (\n        <div className="plans-current-status">\n          <strong>\n            {t("plansTrialPendingTitle", {\n              defaultValue: "Tu prueba gratis está lista",\n            })}\n          </strong>\n          <br />\n          <span>\n            {t("plansTrialPendingHelp", {\n              defaultValue:\n                "Conecta tu primera tienda Shopify o Nuvemshop para iniciar tus 7 días gratis.",\n            })}\n          </span>\n        </div>\n      )}\n\n      {trialStatus?.status === "active" && (\n        <div className="plans-current-status">\n          <strong>\n            {t("plansTrialActiveTitle", {\n              defaultValue: "Prueba gratuita activa",\n            })}\n          </strong>\n          <br />\n          <span>\n            {t("plansTrialActiveHelp", {\n              count: trialStatus.days_remaining ?? 0,\n              limit: trialStatus.ai_response_limit,\n              defaultValue:\n                "Te quedan {{count}} días · hasta {{limit}} respuestas IA durante la prueba.",\n            })}\n          </span>\n        </div>\n      )}\n\n      {trialStatus?.status === "expired" && (\n        <div className="plans-current-status">\n          <strong>\n            {t("plansTrialExpiredTitle", {\n              defaultValue: "Tu prueba gratuita terminó",\n            })}\n          </strong>\n          <br />\n          <span>\n            {t("plansTrialExpiredHelp", {\n              defaultValue:\n                "Tus datos siguen disponibles. Elige un plan para reactivar las funciones operativas y la IA.",\n            })}\n          </span>\n        </div>\n      )}\n\n      {trialStatus?.status === "blocked" && (\n        <div className="plans-current-status">\n          <strong>\n            {t("plansTrialBlockedTitle", {\n              defaultValue: "Prueba gratuita no disponible",\n            })}\n          </strong>\n          <br />\n          <span>\n            {t("plansTrialBlockedHelp", {\n              defaultValue:\n                "La tienda verificada ya utilizó una prueba gratuita. Puedes continuar eligiendo un plan de pago.",\n            })}\n          </span>\n        </div>\n      )}\n\n'''
    text = replace_once(text, marker, banner + marker)

    PATH.write_text(text, encoding="utf-8")
    print("PlansPage trial UX applied")


if __name__ == "__main__":
    main()
