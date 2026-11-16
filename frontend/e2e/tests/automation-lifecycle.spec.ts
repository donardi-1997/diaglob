import { expect, test, type Page, type Route } from "@playwright/test";

type Graph = {
  nodes: Array<{ id: string; type: string; config: Record<string, unknown>; position: { x: number; y: number } }>;
  edges: Array<{ source: string; target: string }>;
};

function initialGraph(): Graph {
  return {
    nodes: [
      { id: "trigger", type: "trigger", position: { x: 220, y: 20 }, config: { trigger_type: "manual" } },
      { id: "message", type: "message", position: { x: 220, y: 180 },
        config: { message_mode: "auto", message_template: "Hola {{customer.name}}" } },
      { id: "end", type: "end", position: { x: 220, y: 340 }, config: {} },
    ],
    edges: [{ source: "trigger", target: "message" }, { source: "message", target: "end" }],
  };
}

interface Scenario {
  available?: boolean;
}

async function mockStoreApi(page: Page, options: Scenario = {}) {
  const state = {
    created: false,
    status: "draft",
    version: 1,
    published: false,
    graph: initialGraph(),
    publishAttempts: 0,
    activateAttempts: 0,
    savedDrafts: [] as Graph[],
    getRequests: [] as string[],
    simulationCount: 0,
  };

  await page.route("**/api/stores/**", async (route: Route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    const method = request.method();
    const storeMatch = pathname.match(/^\/api\/stores\/(\d+)\//);
    const storeId = storeMatch ? Number(storeMatch[1]) : 0;
    const respond = (json: unknown, status = 200) =>
      route.fulfill({ json, status, headers: { "access-control-allow-origin": "*" } });

    if (method === "GET" && /\/automation-flow-templates$/.test(pathname)) {
      const available = options.available !== false && storeId === 101;
      return respond({
        items: [{
          id: "welcome", name: "Bienvenida de prueba",
          description: "Mensaje de bienvenida de prueba",
          category: "Retention", recommended_for: "stores",
          graph: initialGraph(), required_integrations: ["whatsapp"], icon: "sparkles",
          estimated_setup_minutes: 2,
          availability: {
            available, missing: available ? [] : ["whatsapp"],
            status: available ? "ready" : "integration_required",
          },
        }],
        categories: ["Retention"], total: 1,
      });
    }

    if (method === "POST" && /\/automation-flow-templates\/welcome$/.test(pathname)) {
      if (options.available === false || storeId !== 101) return respond({ detail: "Integration required" }, 400);
      state.created = true;
      return respond({ template_id: "welcome", flow: { id: 42 }, next_step: "review_publish_activate" });
    }

    const flow = () => ({
      id: 42, name: "Bienvenida de prueba", description: "",
      status: state.status, created_by: 10,
      created_at: "2026-11-15T00:00:00Z", updated_at: "2026-11-15T00:00:00Z",
      current_version_id: state.version,
      active_version_id: state.status === "active" ? state.version : null,
      current_version: {
        id: state.version, flow_id: 42, version_number: state.version,
        graph: state.graph, published_at: state.published ? "2026-11-15T01:00:00Z" : null,
        activated_at: state.status === "active" ? "2026-11-15T01:00:00Z" : null,
        created_at: "2026-11-15T00:00:00Z",
      },
    });

    if (pathname.endsWith("/automation-flows") && method === "GET") {
      return respond(storeId === 101 && state.created ? [flow()] : []);
    }
    if (/\/automation-flows\/42$/.test(pathname) && method === "GET") {
      state.getRequests.push(pathname);
      return storeId === 101 && state.created ? respond(flow()) : respond({ detail: "Not found" }, 404);
    }
    if (/\/automation-flows\/42\/versions$/.test(pathname) && method === "POST") {
      if (storeId !== 101) return respond({ detail: "Not found" }, 404);
      const body = request.postDataJSON() as { graph: Graph };
      state.savedDrafts.push(structuredClone(body.graph));
      state.graph = structuredClone(body.graph);
      state.published = false;
      state.version += 1;
      return respond(flow().current_version);
    }
    if (/\/automation-flows\/42\/versions\/\d+\/publish$/.test(pathname) && method === "POST") {
      state.publishAttempts++;
      if (!state.graph.nodes.find((n) => n.type === "message" && n.config.message_template)) {
        return respond({ detail: { errors: ["Missing message"] } }, 422);
      }
      state.published = true;
      return respond(flow().current_version);
    }
    if (/\/automation-flows\/42\/activate$/.test(pathname) && method === "POST") {
      state.activateAttempts++;
      if (!state.published) return respond({ detail: "Publish first" }, 409);
      state.status = "active";
      return respond(flow());
    }
    if (/\/automation-flows\/42\/deactivate$/.test(pathname) && method === "POST") {
      state.status = "draft";
      return respond(flow());
    }
    if (/\/automation-flows\/simulate$/.test(pathname) && method === "POST") {
      state.simulationCount++;
      return respond({ valid: true, errors: [], warnings: [], summary: {
        total_nodes: 3, message_nodes: 1, wait_nodes: 0, condition_nodes: 0, end_nodes: 1,
      } });
    }
    if (method === "GET" && /\/automation-campaigns$/.test(pathname)) {
      return respond({ items: [], total: 0 });
    }
    if (method === "GET" && /\/automations$/.test(pathname)) {
      return respond({ items: [], total: 0 });
    }
    return respond({ detail: "Unmocked API route: " + pathname }, 404);
  });
  return state;
}

async function openTemplateEditor(page: Page) {
  await page.goto("/e2e/harness.html");
  await page.getByRole("button", { name: "Plantillas", exact: true }).click();
  const card = page.locator(".template-card").filter({ hasText: "Bienvenida de prueba" });
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Ver pasos" }).click();
  await expect(card.locator(".template-preview-steps li")).toHaveCount(3);
  await card.getByRole("button", { name: "Crear flujo" }).click();
  await expect(page.locator(".flow-builder-section")).toBeVisible();
  await expect(page.locator(".flow-editor-actions h3")).toHaveText("Bienvenida de prueba");
}

test("template creates exact flow, simulates, publishes and activates only with confirmation", async ({ page }) => {
  const state = await mockStoreApi(page);
  await openTemplateEditor(page);

  expect(state.getRequests).toContain("/api/stores/101/automation-flows/42");
  expect(state.activateAttempts).toBe(0);
  await page.getByRole("button", { name: "Simular" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("válido");
  await page.getByRole("dialog").getByRole("button", { name: "Cerrar" }).click();
  expect(state.simulationCount).toBe(1);

  await page.getByRole("button", { name: "Publicar versión" }).click();
  await expect(page.getByRole("button", { name: "Activar flujo" })).toBeVisible();
  expect(state.published).toBe(true);
  expect(state.activateAttempts).toBe(0);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Activar flujo" }).click();
  await expect(page.getByRole("button", { name: "Pausar" })).toBeVisible();
  expect(state.activateAttempts).toBe(1);
  await page.getByRole("button", { name: "Pausar" }).click();
  await expect(page.getByRole("button", { name: "Activar flujo" })).toBeVisible();
});

test("incomplete draft survives save but cannot be published or activated", async ({ page }) => {
  const state = await mockStoreApi(page);
  await openTemplateEditor(page);

  await page.locator('.react-flow__node[data-id="message"]').click();
  await expect(page.locator(".flow-sidebar textarea")).toBeVisible();
  await page.locator(".flow-sidebar textarea").fill("");
  await expect(page.locator(".flow-sidebar-footer").getByRole("button", { name: "Guardar", exact: true })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Publicar versión" })).toBeDisabled();
  await page.locator(".flow-sidebar-footer").getByRole("button", { name: "Guardar", exact: true }).click();
  await expect(page.locator(".flow-sidebar-footer").getByRole("button", { name: "Guardar", exact: true })).toBeDisabled();
  expect(state.savedDrafts).toHaveLength(1);
  expect(state.savedDrafts[0].nodes.find((n) => n.id === "message")?.config.message_template).toBe("");
  expect(state.publishAttempts).toBe(0);
  expect(state.activateAttempts).toBe(0);

  await page.getByRole("button", { name: "Cerrar inspector" }).click();
  await page.getByRole("button", { name: "Volver a la lista" }).click();
  await expect(page.locator(".flow-card")).toHaveCount(1);
  await page.locator(".flow-card-actions .icon-button").first().click();
  await expect(page.locator(".flow-builder-section")).toBeVisible();
  await page.locator('.react-flow__node[data-id="message"]').click();
  await expect(page.locator(".flow-sidebar textarea")).toHaveValue("");
  await expect(page.getByRole("button", { name: "Publicar versión" })).toBeDisabled();
});

test("missing integrations and read-only permissions block flow creation", async ({ page }) => {
  await mockStoreApi(page, { available: false });
  await page.goto("/e2e/harness.html");
  await page.getByRole("button", { name: "Plantillas", exact: true }).click();
  const card = page.locator(".template-card").first();
  await expect(card).toContainText("whatsapp");
  await expect(card.getByRole("button", { name: "Crear flujo" })).toBeDisabled();
  await page.getByRole("button", { name: "Toggle write permission" }).click();
  await expect(card.getByRole("button", { name: "Crear flujo" })).toHaveCount(0);
});

test("store changes never open previously created flow in a different store", async ({ page }) => {
  await mockStoreApi(page);
  await openTemplateEditor(page);
  await page.getByRole("button", { name: "Switch store" }).click();
  await expect(page.getByTestId("current-store")).toContainText("202");
  await expect(page.locator(".flow-builder-section")).toHaveCount(0);
  await expect(page.locator(".flow-card")).toHaveCount(0);
});
