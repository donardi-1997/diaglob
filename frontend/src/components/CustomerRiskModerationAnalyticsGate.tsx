import { useEffect, useState } from "react";

import { getAdminRiskStats } from "../services/adminRisk";
import CustomerRiskModerationAnalytics from "./CustomerRiskModerationAnalytics";


export default function CustomerRiskModerationAnalyticsGate() {
  const [authorized, setAuthorized] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function probe() {
      try {
        await getAdminRiskStats();
        if (!cancelled) setAuthorized(true);
      } catch {
        if (!cancelled) setAuthorized(false);
      }
    }
    void probe();
    return () => {
      cancelled = true;
    };
  }, []);

  if (authorized !== true) return null;
  return <CustomerRiskModerationAnalytics />;
}
