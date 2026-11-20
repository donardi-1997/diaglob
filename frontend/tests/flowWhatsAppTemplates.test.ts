import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  FLOW_TEMPLATE_VARIABLES,
  previewTemplateBody,
  resizeTemplateMapping,
  templateBodyText,
  templateConfigIssue,
  templateParameterCount,
} from "../src/components/automation-flows/flowWhatsAppTemplates.ts";

const approved = {
  status: "approved",
  components: {
    items: [
      { type: "HEADER", text: "Pedido {{1}}" },
      { type: "BODY", text: "Hola {{1}}, tu pedido {{2}} va con {{3}}. Gracias {{1}}" },
    ],
  },
};

test("reads the BODY and counts distinct parameters", () => {
  assert.equal(templateBodyText(approved), "Hola {{1}}, tu pedido {{2}} va con {{3}}. Gracias {{1}}");
  assert.equal(templateParameterCount(approved), 3);
  assert.equal(templateParameterCount({ components: {} }), 0);
  assert.equal(templateParameterCount(null), 0);
});

test("resizes the mapping keeping existing choices", () => {
  assert.deepEqual(resizeTemplateMapping(["order.number"], 3), ["order.number", "customer.name", "customer.name"]);
  assert.deepEqual(resizeTemplateMapping(["a", "b", "c"], 1), ["a"]);
  assert.deepEqual(resizeTemplateMapping(undefined, 0), []);
});

test("previews parameters with their variable names", () => {
  assert.equal(
    previewTemplateBody("Pedido {{1}} va con {{2}}", ["order.number", "shipment.carrier"]),
    "Pedido [order.number] va con [shipment.carrier]",
  );
});

test("flags incomplete message configurations", () => {
  assert.equal(templateConfigIssue({ message_mode: "template" }, null), "template_required");
  assert.equal(templateConfigIssue({ message_mode: "auto", message_template: "" }, null), "text_required");
  assert.equal(
    templateConfigIssue({ message_mode: "template", whatsapp_template_id: 1, template_variables: { body: ["customer.name"] } }, approved),
    "parameter_mismatch",
  );
  assert.equal(
    templateConfigIssue(
      { message_mode: "template", whatsapp_template_id: 1, template_variables: { body: ["customer.name", "order.number", "customer.email"] } },
      approved,
    ),
    "unsupported_variable",
  );
  assert.equal(
    templateConfigIssue({ message_mode: "template", whatsapp_template_id: 1 }, { ...approved, status: "pending" }),
    "template_not_approved",
  );
  assert.equal(
    templateConfigIssue(
      { message_mode: "auto", message_template: "Hola", whatsapp_template_id: 1, template_variables: { body: ["customer.name", "order.number", "shipment.carrier"] } },
      approved,
    ),
    null,
  );
});

test("frontend template variables mirror the backend allow-list", () => {
  const source = readFileSync(new URL("../../backend/app/whatsapp_compliance.py", import.meta.url), "utf8");
  const base = source.match(/^TEMPLATE_VARIABLES = \{([^}]*)\}/m)?.[1] ?? "";
  const flow = source.match(/FLOW_TEMPLATE_VARIABLES = frozenset\(TEMPLATE_VARIABLES \| \{([\s\S]*?)\}\)/)?.[1] ?? "";
  const backend = new Set([...`${base},${flow}`.matchAll(/"([a-z_.]+)"/g)].map((match) => match[1]));
  assert.ok(backend.size > 4);
  assert.deepEqual(new Set(FLOW_TEMPLATE_VARIABLES), backend);
});
