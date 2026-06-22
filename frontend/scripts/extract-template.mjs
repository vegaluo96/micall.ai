// Regenerate src/app.template.html from the frozen DC prototype.
//
// The prototype (prototype/AI Call.dc.html) is the design source of truth.
// The production app renders the *inner* of its <x-dc>…</x-dc> verbatim, so
// this script keeps src/app.template.html provably in sync — no hand editing.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = join(here, "../../prototype/AI Call.dc.html");
const OUT = join(here, "../src/app.template.html");

const html = readFileSync(SRC, "utf8");
const open = html.match(/<x-dc(?:\s[^>]*)?>/);
if (!open) throw new Error("no <x-dc> open tag found");
const start = open.index + open[0].length;
const end = html.lastIndexOf("</x-dc>");
if (end < 0 || end < start) throw new Error("no </x-dc> close tag found");

let template = html.slice(start, end).replace(/^\n/, "");

// Production-only hooks (product-directed responsive change): tag the two side
// drawers so app-level CSS can square their phone-frame corners on real devices.
// Pure class injection — no visual change vs. the prototype on its own.
template = template.replace(
  '<div style="position:absolute;top:0;bottom:0;left:0;width:74%;z-index:9;',
  '<div class="dcx-drawer-left" style="position:absolute;top:0;bottom:0;left:0;width:74%;z-index:9;',
);
template = template.replace(
  '<div style="position:absolute;top:0;bottom:0;right:0;width:74%;z-index:11;',
  '<div class="dcx-drawer-right" style="position:absolute;top:0;bottom:0;right:0;width:74%;z-index:11;',
);

writeFileSync(OUT, template, "utf8");
console.log(`Wrote ${OUT} (${template.split("\n").length} lines) from prototype.`);
