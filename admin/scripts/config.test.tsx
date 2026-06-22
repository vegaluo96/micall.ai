// Round-trip test for the 接口配置 persistence (localStorage path, no backend).
// Verifies save → load returns the same config, and that AdminLogic.componentDidMount
// merges a persisted edit over the built-in defaults.
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><head></head><body></body></html>", { url: "http://localhost/" });
const g = globalThis as any;
g.window = dom.window;
g.document = dom.window.document;
g.localStorage = dom.window.localStorage;

const { loadApiConfig, saveApiConfig, usingBackend } = await import("../src/logic/configService.ts");
const { AdminLogic } = await import("../src/logic/AdminLogic.ts");

let failures = 0;
function assert(label: string, cond: boolean) {
  if (cond) console.log("✓ " + label);
  else { failures++; console.error("✗ " + label); }
}

assert("no backend configured (uses localStorage)", usingBackend() === false);

// save → load round-trip
const cfg = { fast: { endpoint: "https://direct.deepseek.com/v1", key: "sk-real-123", temp: "0.7", maxTokens: "256" } };
const ok = await saveApiConfig(cfg);
assert("saveApiConfig returns true", ok === true);
const loaded = await loadApiConfig();
assert("loaded endpoint round-trips", !!loaded && loaded.fast.endpoint === "https://direct.deepseek.com/v1");
assert("loaded key round-trips", !!loaded && loaded.fast.key === "sk-real-123");

// componentDidMount merges persisted edit over defaults
const logic = new AdminLogic();
logic.attach(() => {});
const defaultTtsEndpoint = logic.state.apiCfg.tts.endpoint; // untouched default
await logic.componentDidMount();
assert("mount applied persisted fast.endpoint", logic.state.apiCfg.fast.endpoint === "https://direct.deepseek.com/v1");
assert("mount kept untouched tts default", logic.state.apiCfg.tts.endpoint === defaultTtsEndpoint);

if (failures) { console.error(`\n${failures} check(s) failed`); process.exit(1); }
console.log("\nConfig persistence checks passed.");
