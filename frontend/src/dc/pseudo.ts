// Pseudo-class style sheet for `style-active="..."` (and style-hover, etc.).
// Faithful port of createPseudoSheet from dc-runtime/src/pseudo.ts.
//
// The prototype expresses press feedback with `style-active="transform:scale(.93)"`.
// The runtime turns each unique (pseudo, css) pair into a generated class with a
// real `:active` rule. We reproduce that exactly so press/hover states match
// the prototype pixel-for-pixel.

let el: HTMLStyleElement | null = null;
const cache = new Map<string, string>();
let n = 0;

export function pseudoClass(pseudo: string, css: string): string {
  const k = pseudo + "|" + css;
  const hit = cache.get(k);
  if (hit) return hit;
  if (!el) {
    el = document.createElement("style");
    el.setAttribute("data-dc-pseudo", "");
    document.head.appendChild(el);
  }
  const cls = "scp" + (n++).toString(36);
  const sel =
    pseudo === "before" || pseudo === "after"
      ? "." + cls + "::" + pseudo
      : "." + cls + ":" + pseudo;
  el.sheet!.insertRule(sel + "{" + css + "}", el.sheet!.cssRules.length);
  cache.set(k, cls);
  return cls;
}
