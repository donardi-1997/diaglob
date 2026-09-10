import assert from "node:assert/strict";
import test from "node:test";

import {
  degradedAlertMessage,
  degradedStatusLabel,
} from "../src/utils/operationsStatus.ts";


const degradedIntegrations = [
  {
    key: "meta_ads",
    provider: "meta_ads",
    name: "Meta Ads",
    category: "ads",
    connected: false,
    status: "degraded",
    available: true,
    scope: "store",
    degraded: true,
  },
  {
    key: "payment:nequi",
    provider: "nequi",
    name: "Nequi",
    category: "payments",
    connected: false,
    status: "degraded",
    available: true,
    scope: "store",
    degraded: true,
  },
];


test("renders degraded status copy for Spanish, English, and Portuguese", () => {
  assert.equal(degradedStatusLabel("es"), "Temporalmente no disponible");
  assert.equal(degradedStatusLabel("en-US"), "Temporarily unavailable");
  assert.equal(degradedStatusLabel("pt-BR"), "Temporariamente indisponível");
});


test("defaults degraded status copy to Spanish", () => {
  assert.equal(degradedStatusLabel(), "Temporalmente no disponible");
});


test("renders unique degraded integration names in the alert", () => {
  assert.equal(
    degradedAlertMessage("es", degradedIntegrations),
    "Estado de integración temporalmente no disponible: Meta Ads, Nequi",
  );
  assert.equal(
    degradedAlertMessage("en", degradedIntegrations),
    "Integration status temporarily unavailable: Meta Ads, Nequi",
  );
  assert.equal(
    degradedAlertMessage("pt-BR", degradedIntegrations),
    "Status de integração temporariamente indisponível: Meta Ads, Nequi",
  );
});


test("omits the suffix when degraded integration names are unavailable", () => {
  assert.equal(
    degradedAlertMessage("en", []),
    "Integration status temporarily unavailable",
  );
});
