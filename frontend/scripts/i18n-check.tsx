// 一次性校验：英文 UI 包是否真生效（zh 默认不变 / en 翻译命中）。镜像 smoke.tsx 的 jsdom 装配。
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const dom = new JSDOM("<!doctype html><html><head></head><body></body></html>", { url: "http://localhost/" });
const g = globalThis as any;
g.window = dom.window;
g.document = dom.window.document;
g.DOMParser = dom.window.DOMParser;
g.Node = dom.window.Node;
g.localStorage = dom.window.localStorage;

const { createElement } = await import("react");
const { renderToStaticMarkup } = await import("react-dom/server");
const { DcView } = await import("../src/dc/DcView.tsx");
const { MiCallLogic } = await import("../src/logic/MiCallLogic.ts");

const here = dirname(fileURLToPath(import.meta.url));
const template = readFileSync(join(here, "../src/app.template.html"), "utf8");

function render(lang: string, mutate?: (l: any) => void): string {
  const logic: any = new MiCallLogic({ theme: "light", orbColor: "#AAB8FF", aiName: "VEGA" });
  logic.state.lang = lang;
  if (mutate) mutate(logic);
  return renderToStaticMarkup(createElement(DcView, { template, vals: logic.renderVals() }));
}

let fails = 0;
function expect(label: string, html: string, present: string[], absent: string[] = []) {
  const miss = present.filter((s) => !html.includes(s));
  const bad = absent.filter((s) => html.includes(s));
  if (miss.length || bad.length) {
    fails++;
    console.log(`✗ ${label}`, miss.length ? `missing ${JSON.stringify(miss)}` : "", bad.length ? `should-be-gone ${JSON.stringify(bad)}` : "");
  } else console.log(`✓ ${label}`);
}

const zhMenu = render("中文", (l) => { l.state.menuOpen = true; });
expect("zh menu unchanged", zhMenu, ["账单", "邀请好友", "设置", "联系我们"]);

const enMenu = render("English", (l) => { l.state.menuOpen = true; });
expect("en menu", enMenu, ["Billing", "Invite friends", "Settings", "Contact us"], ["账单", "邀请好友"]);

const enLang = render("English", (l) => { l.state.langOpen = true; });
expect("en language sheet", enLang, ["Language"], ["语言"]);

const enIdle = render("English");
expect("en home icons", enIdle, ["Memories", "Discover", "Status"], ["回忆", "发现"]);

const enChar = render("English", (l) => { l.state.charOpen = true; });
expect("en char sheet tabs", enChar, ["For you", "Popular", "Favorites"], ["推荐", "热门"]);

console.log(fails ? `\n${fails} check(s) failed` : "\nAll i18n checks passed.");
process.exit(fails ? 1 : 0);
