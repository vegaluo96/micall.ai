// CSS string → React style object. Faithful port of cssToObj from
// dc-runtime/src/encode.ts. Keeps the prototype's inline `style="..."` strings
// verbatim (no manual camelCasing → no transcription risk), converting them to
// React style objects at runtime exactly as the original runtime did.
import type { CSSProperties } from "react";

export function kebabToCamel(s: string): string {
  return s.replace(/-([a-z])/g, (_, c: string) => c.toUpperCase());
}

// inline style 字符串 → React style 对象的缓存。模板里的 style 大多是静态的，且
// sc-for 列表项常重复同一串；每次重渲染都重新 split/trim/camelCase 是纯浪费。按原始
// 字符串缓存解析结果：命中即零解析，且返回同一冻结引用，React 还能据此跳过 diff。
// 模板里 style 字符串种类有界（静态 + 有限的插值变体），缓存不会无界膨胀。
const cache = new Map<string, CSSProperties>();

export function cssToObj(css: string): CSSProperties {
  const hit = cache.get(css);
  if (hit !== undefined) return hit;
  const o: Record<string, string> = {};
  for (const decl of css.split(";")) {
    const i = decl.indexOf(":");
    if (i < 0) continue;
    const prop = decl.slice(0, i).trim();
    if (!prop) continue;
    // CSS custom properties (--foo) keep their name; everything else camelCases.
    o[prop.startsWith("--") ? prop : kebabToCamel(prop)] = decl.slice(i + 1).trim();
  }
  // 冻结：共享引用绝不能被下游 mutate（walkElement 不会 mutate style）。
  const obj = Object.freeze(o) as CSSProperties;
  cache.set(css, obj);
  return obj;
}
