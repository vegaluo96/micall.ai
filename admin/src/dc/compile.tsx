// DC template → React element builders.
//
// Faithful port of the relevant parts of dc-runtime/src/compile.ts:
// walkText / walkIf / walkFor / walkElement / collectProps / compileAttr.
// We parse the *original* prototype template (verbatim bytes) into a DOM and
// compile it into builder functions; rendering then just feeds the live
// `renderVals()` object in. This means the prototype's markup, inline CSS,
// SVGs, animations and per-state styling are reproduced exactly, with zero
// hand-transcription of 900+ lines of finicky inline styles.
import {
  Fragment,
  createElement,
  isValidElement,
  type ReactNode,
} from "react";
import { resolve, type Vals } from "./resolve";
import { cssToObj } from "./css";
import { pseudoClass } from "./pseudo";

type Builder = (vals: Vals, key?: React.Key) => ReactNode;
type AttrGetter = (vals: Vals) => unknown;

const EVENT_MAP: Record<string, string> = {
  onclick: "onClick",
  onchange: "onChange",
  // The prototype binds text fields with `oninput`. React controlled inputs
  // want `onChange`; React fires onChange on every input event, so mapping
  // here is behaviourally identical and avoids the controlled-input warning.
  oninput: "onChange",
  onsubmit: "onSubmit",
  onkeydown: "onKeyDown",
  onkeyup: "onKeyUp",
  onkeypress: "onKeyPress",
  onmousedown: "onMouseDown",
  onmouseup: "onMouseUp",
  onmouseenter: "onMouseEnter",
  onmouseleave: "onMouseLeave",
  onfocus: "onFocus",
  onblur: "onBlur",
  ondoubleclick: "onDoubleClick",
  oncontextmenu: "onContextMenu",
};

function compileAttr(raw: string): AttrGetter {
  const whole = raw.match(/^\s*\{\{([\s\S]+?)\}\}\s*$/);
  if (whole) {
    const path = whole[1];
    return (vals) => resolve(vals, path);
  }
  if (raw.includes("{{")) {
    const parts = raw.split(/\{\{([\s\S]+?)\}\}/g);
    return (vals) =>
      parts.map((s, i) => (i & 1 ? (resolve(vals, s) ?? "") : s)).join("");
  }
  return () => raw;
}

interface CompiledProps {
  propGetters: [string, AttrGetter][];
  pseudoSpecs: [string, string][]; // (pseudo, css) pairs from style-*
}

function collectProps(el: Element): CompiledProps {
  const propGetters: [string, AttrGetter][] = [];
  const pseudoSpecs: [string, string][] = [];
  for (const attr of Array.from(el.attributes)) {
    let key = attr.name;
    const value = attr.value;
    if (key === "sc-name" || key === "data-dc-tpl") continue;
    if (key === "hint-size" || key.startsWith("hint-placeholder")) continue;
    if (key.startsWith("style-")) {
      // style-active / style-hover / ... → :active / :hover pseudo rule.
      pseudoSpecs.push([key.slice(6), value]);
      continue;
    }
    if (key === "class") key = "className";
    else if (key === "for") key = "htmlFor";
    else if (key.startsWith("on")) key = EVENT_MAP[key] || "on" + key[2].toUpperCase() + key.slice(3);
    propGetters.push([key, compileAttr(value)]);
  }
  return { propGetters, pseudoSpecs };
}

function walkChildren(node: ParentNode): Builder[] {
  return Array.from(node.childNodes)
    .map((c) => walk(c))
    .filter((b): b is Builder => b != null);
}

function walk(node: ChildNode): Builder | null {
  if (node.nodeType === Node.TEXT_NODE) return walkText(node as Text);
  if (node.nodeType !== Node.ELEMENT_NODE) return null;
  const el = node as Element;
  const tag = el.tagName.toLowerCase();
  if (tag === "helmet" || tag === "sc-helmet") return null; // injected separately
  if (tag === "sc-for") return walkFor(el);
  if (tag === "sc-if") return walkIf(el);
  return walkElement(el);
}

function walkText(node: Text): Builder | null {
  const txt = node.nodeValue ?? "";
  if (!txt.includes("{{")) {
    // Drop pure indentation/newlines (no space char), keep meaningful spaces.
    if (!txt.trim() && !txt.includes(" ")) return null;
    return () => txt;
  }
  const parts = txt.split(/\{\{([\s\S]+?)\}\}/g);
  return (vals, key) =>
    createElement(
      Fragment,
      { key },
      ...parts.map((p, i): ReactNode => {
        if (!(i & 1)) return p;
        const v = resolve(vals, p);
        if (v === undefined || v === null || typeof v === "boolean") return null;
        if (isValidElement(v) || Array.isArray(v)) {
          return createElement(Fragment, { key: i }, v as ReactNode);
        }
        return createElement("span", { key: i, className: "sc-interp" }, String(v));
      }),
    );
}

function walkIf(el: Element): Builder {
  const valueSrc = el.getAttribute("value") || "";
  const get = compileAttr(valueSrc);
  const kids = walkChildren(el);
  return (vals, key) => {
    if (!get(vals)) return null;
    return createElement(Fragment, { key }, ...kids.map((b, j) => b(vals, j)));
  };
}

function walkFor(el: Element): Builder {
  const listGet = compileAttr(el.getAttribute("list") || "");
  const asName = el.getAttribute("as") || "item";
  const kids = walkChildren(el);
  return (vals, key) => {
    const raw = listGet(vals);
    const list = Array.isArray(raw) ? raw : [];
    return createElement(
      Fragment,
      { key },
      ...list.map((item, idx) => {
        const scope: Vals = { ...vals, [asName]: item };
        return createElement(
          Fragment,
          { key: idx },
          ...kids.map((b, j) => b(scope, j)),
        );
      }),
    );
  };
}

function walkElement(el: Element): Builder {
  const tag = el.tagName.toLowerCase();
  const { propGetters, pseudoSpecs } = collectProps(el);
  const kids = walkChildren(el);
  return (vals, key) => {
    const props: Record<string, unknown> = { key };
    for (const [k, g] of propGetters) {
      let v = g(vals);
      if (k === "style" && typeof v === "string") v = cssToObj(v);
      if ((k === "value" || k === "checked") && v === undefined) {
        v = k === "checked" ? false : "";
      }
      props[k] = v;
    }
    if (pseudoSpecs.length) {
      const cls = pseudoSpecs.map(([p, css]) => pseudoClass(p, css));
      props.className = [props.className, ...cls].filter(Boolean).join(" ");
    }
    return createElement(tag, props, ...kids.map((b, j) => b(vals, j)));
  };
}

/** Compile a list of top-level template nodes into builder functions. */
export function compileTemplate(root: ParentNode): Builder[] {
  return walkChildren(root);
}

export type { Builder };
