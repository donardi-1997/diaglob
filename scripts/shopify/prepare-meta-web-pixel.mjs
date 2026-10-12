#!/usr/bin/env node
/**
 * Bootstrap an inert Shopify Web Pixel extension on the EXISTING Diaglob app.
 * Usage:
 * node scripts/shopify/prepare-meta-web-pixel.mjs --client-id EXISTING_CLIENT_ID
 * node scripts/shopify/prepare-meta-web-pixel.mjs --client-id EXISTING_CLIENT_ID --deploy-draft
 * Never creates an app, releases a version, enables tracking, or touches Bakatá.
 */
import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

export function clientIdFromConfig(config) {
  return /^\s*client_id\s*=\s*["']([A-Za-z0-9_-]{10,128})["']\s*$/m.exec(config)?.[1] ?? null;
}

export function extensionUidFromConfig(config) {
  return /^\s*uid\s*=\s*["']([A-Za-z0-9_-]{16,128})["']\s*$/m.exec(config)?.[1] ?? null;
}

export function makeExtensionConfig(template, uid) {
  if (!/^[A-Za-z0-9_-]{16,128}$/.test(uid)) throw new Error("Invalid CLI-generated extension UID.");
  if (!/^name = "diaglob-meta-pixel"$/m.test(template)) throw new Error("Unexpected Web Pixel TOML template.");
  if (/^\s*uid\s*=/m.test(template)) throw new Error("Template contains a fabricated UID.");
  return template.replace(/^name = "diaglob-meta-pixel"$/m,
    'name = "diaglob-meta-pixel"\nuid = "' + uid + '"');
}

export function parseArguments(argv) {
  const draft = argv.includes("--deploy-draft");
  const pos = argv.indexOf("--client-id");
  const clientId = pos >= 0 ? argv[pos + 1] : process.env.DIAGLOB_SHOPIFY_CLIENT_ID;
  if (!clientId || !/^[A-Za-z0-9_-]{10,128}$/.test(clientId)) {
    throw new Error("Pass the EXISTING Shopify app Client ID via --client-id or DIAGLOB_SHOPIFY_CLIENT_ID.");
  }
  if (argv.some((arg) => !["--client-id", clientId, "--deploy-draft"].includes(arg))) {
    throw new Error("Usage: --client-id CLIENT_ID [--deploy-draft]");
  }
  return { clientId, draft };
}

function runShopify(...args) {
  const executable = process.platform === "win32" ? "shopify.cmd" : "shopify";
  execFileSync(executable, args, {
    cwd: repositoryRoot,
    stdio: "inherit",
    shell: process.platform === "win32",
    env: process.env,
  });
}

export function findWebPixelExtension(base) {
  if (!existsSync(base)) return null;
  const matches = readdirSync(base, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => join(base, entry.name))
    .filter((dir) => {
      const toml = join(dir, "shopify.extension.toml");
      if (!existsSync(toml)) return false;
      const contents = readFileSync(toml, "utf8");
      return /^type\s*=\s*"web_pixel_extension"$/m.test(contents) &&
        /^name\s*=\s*"diaglob-meta-pixel"$/m.test(contents);
    });
  if (matches.length > 1) throw new Error("Multiple matching Web Pixels; review manually.");
  return matches[0] ?? null;
}

export function prepareExistingExtension({ root, clientId, run = runShopify, draft = false }) {
  const configPath = join(root, "shopify.app.toml");
  if (!existsSync(configPath)) {
    console.log("Linking Diaglob's EXISTING app. Authenticate as its developer when prompted.");
    run("app", "config", "link", "--client-id", clientId, "--file-name", "shopify.app.toml");
  }
  if (!existsSync(configPath)) throw new Error("Shopify CLI did not create shopify.app.toml.");
  const appConfig = readFileSync(configPath, "utf8");
  if (clientIdFromConfig(appConfig) !== clientId) {
    throw new Error("STOP: linked app Client ID mismatch. No extension generated.");
  }

  const extensionRoot = join(root, "extensions");
  let extensionDir = findWebPixelExtension(extensionRoot);
  let newlyGenerated = false;
  if (!extensionDir) {
    console.log("Generating extension under the linked app; select JavaScript.");
    run("app", "generate", "extension", "--template", "web_pixel", "--name", "diaglob-meta-pixel");
    extensionDir = findWebPixelExtension(extensionRoot);
    newlyGenerated = true;
  }
  if (!extensionDir) throw new Error("CLI did not create the expected extension.");
  const extensionToml = join(extensionDir, "shopify.extension.toml");
  const uid = extensionUidFromConfig(readFileSync(extensionToml, "utf8"));
  if (!uid) throw new Error("STOP: extension lacks a real Shopify-generated UID.");

  const stagedDir = join(root, "shopify", "web-pixel-staging");
  const template = readFileSync(join(stagedDir, "shopify.extension.toml.template"), "utf8");
  const newToml = makeExtensionConfig(template, uid);
  const stagedIndex = readFileSync(join(stagedDir, "src", "index.js"), "utf8");
  if (!stagedIndex.includes('settings?.trackingEnabled !== "true"')) {
    throw new Error("STOP: staged source does not explicitly disable tracking.");
  }
  const indexPath = join(extensionDir, "src", "index.js");
  if (!newlyGenerated && existsSync(indexPath) &&
      readFileSync(indexPath, "utf8") !== stagedIndex) {
    throw new Error("STOP: existing extension differs from staging; review manually.");
  }
  mkdirSync(join(extensionDir, "src"), { recursive: true });
  copyFileSync(join(stagedDir, "src", "index.js"), indexPath);
  copyFileSync(join(stagedDir, "src", "mapping.mjs"), join(extensionDir, "src", "mapping.mjs"));
  writeFileSync(extensionToml, newToml);
  console.log("Shopify generated extension UID: " + uid + "; trackingEnabled=false");

  // Scopes must be approved explicitly in the existing app configuration.
  const scopeString = /^\s*scopes\s*=\s*["']([^"']+)["']/m.exec(appConfig)?.[1] ?? "";
  const scopes = new Set(scopeString.split(",").map((s) => s.trim()));
  const missing = ["write_pixels", "read_customer_events", "read_pixels"].filter((scope) => !scopes.has(scope));
  if (missing.length) console.log("Missing scopes (approval required): " + missing.join(", "));
  if (draft) {
    if (missing.length) throw new Error("STOP: cannot prepare a draft app version without approved scopes.");
    run("app", "config", "validate");
    run("app", "deploy", "--no-release");
    console.log("Created UNRELEASED Shopify app version. No merchant rollout.");
  } else {
    console.log("No app version created. Review changes and rerun with --deploy-draft.");
  }
  return { uid, extensionDir, missingScopes: missing, draftCreated: draft };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    prepareExistingExtension({ root: repositoryRoot, ...parseArguments(process.argv.slice(2)) });
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
