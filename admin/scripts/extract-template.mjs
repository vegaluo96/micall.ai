// Regenerate src/app.template.html from the frozen Admin DC prototype.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = join(here, "../../prototype/MiCall Admin.dc.html");
const OUT = join(here, "../src/app.template.html");

const html = readFileSync(SRC, "utf8");
const open = html.match(/<x-dc(?:\s[^>]*)?>/);
if (!open) throw new Error("no <x-dc> open tag found");
const start = open.index + open[0].length;
const end = html.lastIndexOf("</x-dc>");
if (end < 0 || end < start) throw new Error("no </x-dc> close tag found");

let template = html.slice(start, end).replace(/^\n/, "");

// ── Production tweaks (product-directed) — keep regeneration consistent ──
// 1) Toast「正常显示，不要移动」：用纯淡入替换 adRise 的位移动画。
template = template.replace(
  "    @keyframes adRise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}",
  "    @keyframes adRise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}\n    @keyframes adFade{from{opacity:0}to{opacity:1}}",
);
template = template.replace(
  "box-shadow:0 10px 30px rgba(0,0,0,.25);animation:adRise .3s ease;\">{{ toast }}",
  "box-shadow:0 10px 30px rgba(0,0,0,.25);animation:adFade .18s ease;\">{{ toast }}",
);
// 2) 订单充值页提高信息密度：去掉「会员套餐」「充值记录」两个小标题。
template = template.replace(
  '          <div style="font-size:13px;font-weight:600;color:#878B95;margin-bottom:12px;">会员套餐</div>\n          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:26px;">',
  '          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:26px;">',
);
template = template.replace(
  '          <div style="font-size:13px;font-weight:600;color:#878B95;margin-bottom:12px;">充值记录</div>\n          <div style="background:#fff;border:1px solid #EBECEF;border-radius:14px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.03);">',
  '          <div style="background:#fff;border:1px solid #EBECEF;border-radius:14px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.03);">',
);

writeFileSync(OUT, template, "utf8");
console.log(`Wrote ${OUT} (${template.split("\n").length} lines) from prototype.`);
