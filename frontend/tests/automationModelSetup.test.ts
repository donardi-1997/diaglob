import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  buildModelSetupPayload,
  modelSetupErrorKey,
  suggestedMapping,
  suggestedTemplateClipboard,
} from "../src/utils/automationModelSetup.ts";

test("keeps the model suggestion per parameter and pads extra ones", () => {
  const suggested = ["customer.name", "order.number", "order.total_display"];
  assert.deepEqual(suggestedMapping(suggested, 3), suggested);
  assert.deepEqual(suggestedMapping(suggested, 2), ["customer.name", "order.number"]);
  assert.deepEqual(suggestedMapping(suggested, 4), [...suggested, "customer.name"]);
  assert.deepEqual(suggestedMapping(undefined, 1), ["customer.name"]);
});

test("payload only binds a template when one is chosen", () => {
  assert.deepEqual(
    buildModelSetupPayload(
      { name: "Confirmar pedido", whatsappTemplateId: null, mapping: [], messageMode: "auto", activate: false },
      "Confirmar pedido",
    ),
    { activate: false },
  );
  assert.deepEqual(
    buildModelSetupPayload(
      { name: " COD Colombia ", whatsappTemplateId: 7, mapping: ["customer.name"], messageMode: "template", activate: true },
      "Confirmar pedido",
    ),
    {
      activate: true,
      name: "COD Colombia",
      whatsapp_template_id: 7,
      template_variables: { body: ["customer.name"] },
      message_mode: "template",
    },
  );
});

test("clipboard text explains every parameter", () => {
  const text = suggestedTemplateClipboard({
    name: "diaglob_pedido_recibido",
    category: "UTILITY",
    language: "es",
    body: "Hola {{1}}, pedido {{2}}",
    variables: ["customer.name", "order.number"],
  });
  assert.match(text, /diaglob_pedido_recibido/);
  assert.match(text, /\{\{1\}\} = customer\.name/);
  assert.match(text, /\{\{2\}\} = order\.number/);
});

test("maps API errors to translated keys and never to raw text", () => {
  const apiError = (status: number, detail: unknown) => ({ response: { status, data: { detail } } });
  assert.equal(modelSetupErrorKey(apiError(409, { code: "WHATSAPP_TEMPLATE_NOT_APPROVED" })), "autoModelError_WHATSAPP_TEMPLATE_NOT_APPROVED");
  assert.equal(modelSetupErrorKey(apiError(400, { code: "SOMETHING_NEW" })), "autoModelError_GENERIC");
  assert.equal(modelSetupErrorKey(apiError(403, "Forbidden")), "autoModelError_FORBIDDEN");
  assert.equal(modelSetupErrorKey(apiError(422, { errors: ["x"] })), "autoModelError_INVALID_FLOW");
  assert.equal(modelSetupErrorKey(new Error("Request failed with status code 500")), "autoModelError_GENERIC");
});

test("every setup error code the backend can return has a translation", () => {
  const service = readFileSync(
    new URL("../../backend/app/services/automation_flow_template_setup.py", import.meta.url), "utf8",
  );
  const codes = [...service.matchAll(/FlowTemplateSetupError\("([A-Z_]+)"\)/g)].map((match) => match[1]);
  const i18n = readFileSync(new URL("../src/i18n.ts", import.meta.url), "utf8");
  assert.ok(codes.length >= 8);
  for (const code of new Set(codes)) {
    const occurrences = i18n.split(`autoModelError_${code}:`).length - 1;
    assert.equal(occurrences, 3, `missing es/en/pt-BR translation for ${code}`);
  }
});
