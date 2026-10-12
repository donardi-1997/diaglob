import assert from "node:assert/strict";
import test from "node:test";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync, cpSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

import {
  clientIdFromConfig, extensionUidFromConfig, makeExtensionConfig,
  parseArguments, prepareExistingExtension, repositoryRoot,
} from "../../scripts/shopify/prepare-meta-web-pixel.mjs";

const APP_ID = "abcdef0123456789abcdef0123456789";
const EXTENSION_UID = "deadbeef1234567890abcdef12345678";

test("client and UID readers only recognize explicit verified config", () => {
  assert.equal(clientIdFromConfig('client_id = "' + APP_ID + '"'), APP_ID);
  assert.equal(extensionUidFromConfig('uid = "' + EXTENSION_UID + '"'), EXTENSION_UID);
  assert.equal(extensionUidFromConfig('name = "untrusted"'), null);
  assert.equal(clientIdFromConfig("no client_id"), null);
  assert.throws(() => parseArguments(["--client-id", "short"]));
});

test("inert generated UID replaces placeholder; no invented ID", () => {
  const template = 'type = "web_pixel_extension"\nname = "diaglob-meta-pixel"\nruntime_context = "strict"\n';
  const rendered = makeExtensionConfig(template, EXTENSION_UID);
  assert.ok(rendered.includes('uid = "' + EXTENSION_UID + '"'));
  assert.match(rendered, /runtime_context = "strict"/);
  assert.throws(() => makeExtensionConfig(template, "fake"));
  assert.throws(() => makeExtensionConfig(template + '\nuid = "invented"', EXTENSION_UID));
});

function setup(scopes = "write_pixels,read_customer_events") {
  const root = mkdtempSync(join(tmpdir(), "diaglob-meta-cli-test-"));
  const src = join(repositoryRoot, "shopify", "web-pixel-staging");
  cpSync(src, join(root, "shopify", "web-pixel-staging"), { recursive: true });
  mkdirSync(join(root, "shopify", "cli-app"), { recursive: true });
  writeFileSync(join(root, "shopify", "cli-app", "shopify.app.toml"),
    'client_id = "' + APP_ID + '"\n[access_scopes]\nscopes = "' + scopes + '"\n');
  const commands = [];
  const run = (...args) => {
    commands.push(args);
    if (args[0] === "app" && args[1] === "generate") {
      const dir = join(root, "shopify", "cli-app", "extensions", "diaglob-meta-pixel");
      mkdirSync(join(dir, "src"), { recursive: true });
      writeFileSync(join(dir, "shopify.extension.toml"),
        'type = "web_pixel_extension"\nname = "diaglob-meta-pixel"\nuid = "' + EXTENSION_UID + '"\n');
      writeFileSync(join(dir, "src", "index.js"), "// created by Shopify CLI");
    }
  };
  return { root, commands, run, cleanup: () => rmSync(root, { recursive: true, force: true }) };
}

test("bootstrap only existing app and preserves CLI UID, never releases", () => {
  const t = setup();
  try {
    const result = prepareExistingExtension({
      root: t.root, clientId: APP_ID, run: t.run,
    });
    const index = readFileSync(join(result.extensionDir, "src", "index.js"), "utf8");
    const toml = readFileSync(join(result.extensionDir, "shopify.extension.toml"), "utf8");
    assert.equal(result.uid, EXTENSION_UID);
    assert.ok(index.includes('settings?.trackingEnabled !== "true"'));
    assert.ok(toml.includes('uid = "' + EXTENSION_UID + '"'));
    assert.equal(result.draftCreated, false);
    assert.equal(t.commands.length, 1);
    assert.equal(t.commands[0][1], "generate");
    assert.ok(t.commands[0].includes(join(t.root, "shopify", "cli-app")));
    assert.ok(existsSync(join(t.root, "shopify", "cli-app", "package.json")));
  } finally { t.cleanup(); }
});

test("never rewires an existing app or deploys without pixel scopes", () => {
  const t = setup("read_products");
  try {
    assert.throws(() => prepareExistingExtension({
      root: t.root, clientId: "f".repeat(32), run: t.run,
    }), /mismatch/);
    assert.equal(t.commands.length, 0);
    assert.throws(() => prepareExistingExtension({
      root: t.root, clientId: APP_ID, run: t.run, draft: true,
    }), /without approved scopes/);
    assert.equal(t.commands.filter((c) => c[1] === "deploy").length, 0);
  } finally { t.cleanup(); }
});
