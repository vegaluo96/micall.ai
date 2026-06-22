// Auth soft-gate test (no backend path): VITE_ADMIN_PASSWORD default, wrong vs
// right password, and isAuthed/logout round-trip via sessionStorage.
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><head></head><body></body></html>", { url: "http://localhost/" });
const g = globalThis as any;
g.window = dom.window;
g.document = dom.window.document;
g.sessionStorage = dom.window.sessionStorage;

const { login, isAuthed, logout } = await import("../src/logic/auth.ts");

let failures = 0;
function assert(label: string, cond: boolean) {
  if (cond) console.log("✓ " + label);
  else { failures++; console.error("✗ " + label); }
}

assert("starts unauthenticated", isAuthed() === false);

const bad = await login("admin", "wrong");
assert("wrong password rejected", bad.ok === false && !isAuthed());

const ok = await login("admin", "luoweijia"); // default VITE_ADMIN_PASSWORD
assert("default password accepted", ok.ok === true);
assert("authed after login", isAuthed() === true);

logout();
assert("logout clears session", isAuthed() === false);

if (failures) { console.error(`\n${failures} check(s) failed`); process.exit(1); }
console.log("\nAuth soft-gate checks passed.");
