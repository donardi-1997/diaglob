/**
 * Vite dev-only browser harness. Renders the real automation page without
 * production authentication, while Playwright intercepts all store APIs.
 * The production build uses index.html and never includes this entrypoint.
 */
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "../src/i18n";
import "../src/App.css";
import "../src/design-system.css";
import AutomationsPage from "../src/pages/AutomationsPage";

export function Harness() {
  const [storeId, setStoreId] = useState(101);
  const [canWrite, setCanWrite] = useState(true);
  return (
    <div className="dg-shell" style={{ minHeight: "100vh" }}>
      <header aria-label="E2E test harness" style={{ padding: 12, display: "flex", gap: 12 }}>
        <button type="button" onClick={() => setStoreId((id) => id === 101 ? 202 : 101)}>Switch store</button>
        <button type="button" onClick={() => setCanWrite((value) => !value)}>Toggle write permission</button>
        <output data-testid="current-store">Store {storeId}</output>
      </header>
      <main className="dg-main-content">
        <AutomationsPage storeId={storeId} canWrite={canWrite} />
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<Harness />);
