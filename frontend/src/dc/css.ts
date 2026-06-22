// CSS string → React style object. Faithful port of cssToObj from
// dc-runtime/src/encode.ts. Keeps the prototype's inline `style="..."` strings
// verbatim (no manual camelCasing → no transcription risk), converting them to
// React style objects at runtime exactly as the original runtime did.
import type { CSSProperties } from "react";

export function kebabToCamel(s: string): string {
  return s.replace(/-([a-z])/g, (_, c: string) => c.toUpperCase());
}

export function cssToObj(css: string): CSSProperties {
  const o: Record<string, string> = {};
  for (const decl of css.split(";")) {
    const i = decl.indexOf(":");
    if (i < 0) continue;
    const prop = decl.slice(0, i).trim();
    if (!prop) continue;
    // CSS custom properties (--foo) keep their name; everything else camelCases.
    o[prop.startsWith("--") ? prop : kebabToCamel(prop)] = decl.slice(i + 1).trim();
  }
  return o as CSSProperties;
}
