// Renders a DC template (verbatim prototype bytes) against a live `vals` object.
//
// Parsing once, at module load, into a real DOM means the browser performs all
// the HTML/SVG attribute normalisation (viewBox casing, etc.) exactly as it did
// for the original runtime — so the output is byte-faithful to the prototype.
import { Fragment, createElement, useMemo, type ReactNode } from "react";
import { compileTemplate, type Builder } from "./compile";
import type { Vals } from "./resolve";

let helmetInjected = false;

/** Parse a template string into (a) its <helmet> CSS and (b) compiled builders. */
function prepare(template: string): { builders: Builder[]; helmetCss: string } {
  const doc = new DOMParser().parseFromString(
    `<body>${template}</body>`,
    "text/html",
  );
  // Collect every <style> living inside <helmet> (the prototype keeps its
  // keyframes + theme variables + responsive rules there).
  let helmetCss = "";
  doc.querySelectorAll("helmet style, sc-helmet style").forEach((s) => {
    helmetCss += s.textContent ?? "";
  });
  const builders = compileTemplate(doc.body);
  return { builders, helmetCss };
}

function injectHelmet(css: string) {
  if (helmetInjected || !css) return;
  const el = document.createElement("style");
  el.setAttribute("data-dc-helmet", "");
  el.textContent = css;
  document.head.appendChild(el);
  helmetInjected = true;
}

export function DcView({ template, vals }: { template: string; vals: Vals }): ReactNode {
  const { builders, helmetCss } = useMemo(() => prepare(template), [template]);
  injectHelmet(helmetCss);
  return createElement(
    Fragment,
    null,
    ...builders.map((b, i) => b(vals, i)),
  );
}
