// 触摸手势层（产品方变更 b/c：侧栏滑动手势 + 交互优化「丝滑版」）。
//
// 跟手拖拽 + 实时跟随：拖拽期间直接改目标元素的 transform（GPU 合成层，廉价），不走 React
// 重渲染（每帧重建整棵 DC 树太慢），松手后按位移+速度吸附到「完成」或「回弹」。不改 DOM
// 结构、不改任何 inline 设计样式 —— 只在交互瞬间叠加 transform/opacity，结束即交还或随
// 元素卸载清除。手势与既有点击完全等价，只是多了一种「跟手」的触发方式。
//
// 覆盖：
//   • 左边缘右拖 → 实时拉出菜单；右边缘左拖 → 实时拉出历史（仅在无任何弹窗时）。
//   • 菜单已开左拖 / 历史已开右拖 → 实时推回；底部弹窗已开下拖 → 实时下移（起手列表在顶部）。
//   • 松手：拖动过半或快速甩动 → 完成（开/关）；否则回弹原位。遮罩随进度淡入淡出。
//
// 与原生滚动协调：touchstart 只记录，touchmove 超过 SLOP 才判定方向；判成拖拽才接管并
// preventDefault（阻止滚动/橡皮筋），判不中则彻底让位给原生滚动。
//
// iOS Safari 标签页「屏幕最边缘滑动」是浏览器前进/后退手势，可能与边缘拉出侧栏抢手势；
// 加主屏 / PWA（standalone）下无此冲突。
import { useEffect } from "react";
import type { MiCallLogic } from "./MiCallLogic";

type Mode = "closeMenu" | "openMenu" | "closeHistory" | "openHistory" | "closeSheet";

const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v);

export function useGestures(logic: MiCallLogic): void {
  useEffect(() => {
    const EDGE = 30; // 边缘起手判定带宽(px)
    const SLOP = 10; // 方向判定前的「静区」
    const COMPLETE = 0.4; // 位移过此比例即吸附到「完成」
    const FLING = 0.5; // 甩动速度阈值(px/ms)
    const DUR = 0.26; // 吸附动画时长(s)
    const EASE = "cubic-bezier(.22,1,.36,1)";

    let sx = 0, sy = 0, st = 0; // 起手位置/时间
    let startScrollTop = 0;
    let snap = { menuOpen: false, historyOpen: false, sheetOpen: false, modal: false };
    let stage: "none" | "pending" | "drag" = "none";
    let mode: Mode | null = null;
    let panel: HTMLElement | null = null;
    let backdrop: HTMLElement | null = null;
    let axis: "x" | "y" = "x";
    let extent = 0; // 目标尺寸（抽屉宽 / 弹窗高）
    let offset = 0; // 当前 transform 量
    let settling = false;

    const qs = (s: string) => document.querySelector(s) as HTMLElement | null;

    const nearestScroller = (el: EventTarget | null): Element | null => {
      let n = el instanceof Element ? el : null;
      for (; n; n = n.parentElement) {
        if (n.classList && n.classList.contains("nobar")) return n;
      }
      return null;
    };

    const setT = (v: number) => {
      if (!panel) return;
      offset = v;
      panel.style.transform = axis === "x" ? `translateX(${v}px)` : `translateY(${v}px)`;
      if (backdrop) {
        // 进度 0(全关/全开起点)→1(完全打开)；遮罩透明度跟随。
        const open = 1 - Math.abs(v) / extent;
        backdrop.style.opacity = String(clamp(open, 0, 1));
      }
    };

    const grab = (el: HTMLElement, ax: "x" | "y") => {
      panel = el;
      axis = ax;
      extent = ax === "x" ? el.offsetWidth : el.offsetHeight;
      backdrop = el.previousElementSibling as HTMLElement | null;
      el.style.transition = "none";
      el.style.animation = "none"; // 停掉 enter 动画，避免与跟手打架
      if (backdrop) backdrop.style.animation = "none";
    };

    // 命中某拖拽场景则接管，返回是否接管。
    const decide = (dx: number, dy: number): boolean => {
      const adx = Math.abs(dx), ady = Math.abs(dy);
      const horizontal = adx > ady;
      if (snap.menuOpen) {
        if (horizontal && dx < 0) { const el = qs(".dcx-drawer-left"); if (el) { mode = "closeMenu"; grab(el, "x"); return true; } }
        return false;
      }
      if (snap.historyOpen) {
        if (horizontal && dx > 0) { const el = qs(".dcx-drawer-right"); if (el) { mode = "closeHistory"; grab(el, "x"); return true; } }
        return false;
      }
      if (snap.sheetOpen) {
        if (!horizontal && dy > 0 && startScrollTop <= 0) { const el = qs(".dcx-sheet"); if (el) { mode = "closeSheet"; grab(el, "y"); return true; } }
        return false;
      }
      // 无 overlay：边缘拉出侧栏（先挂载，再 rAF 接管 transform）。
      if (horizontal && dx > 0 && sx <= EDGE) {
        mode = "openMenu"; logic.openMenu();
        requestAnimationFrame(() => { const el = qs(".dcx-drawer-left"); if (el) { grab(el, "x"); setT(-extent + Math.max(0, dx)); } else { stage = "none"; mode = null; } });
        return true;
      }
      if (horizontal && dx < 0 && sx >= window.innerWidth - EDGE) {
        mode = "openHistory"; logic.openHistory();
        requestAnimationFrame(() => { const el = qs(".dcx-drawer-right"); if (el) { grab(el, "x"); setT(extent + Math.min(0, dx)); } else { stage = "none"; mode = null; } });
        return true;
      }
      return false;
    };

    const update = (dx: number, dy: number) => {
      if (!panel) return; // open 类在 rAF 接管前，panel 仍为空
      if (mode === "closeMenu") setT(clamp(dx, -extent, 0));
      else if (mode === "openMenu") setT(clamp(-extent + dx, -extent, 0));
      else if (mode === "closeHistory") setT(clamp(dx, 0, extent));
      else if (mode === "openHistory") setT(clamp(extent + dx, 0, extent));
      else if (mode === "closeSheet") setT(clamp(dy, 0, extent));
    };

    const finish = (toOpen: boolean) => {
      const el = panel, bd = backdrop, m = mode;
      if (!el) { stage = "none"; mode = null; return; }
      settling = true;
      const target = toOpen ? 0 : (axis === "y" || m === "closeHistory" || m === "openHistory" ? extent : -extent);
      el.style.transition = `transform ${DUR}s ${EASE}`;
      if (bd) bd.style.transition = `opacity ${DUR}s ease`;
      requestAnimationFrame(() => {
        el.style.transform = axis === "x" ? `translateX(${target}px)` : `translateY(${target}px)`;
        if (bd) bd.style.opacity = toOpen ? "1" : "0";
      });
      let done = false;
      const cleanup = () => {
        if (done) return;
        done = true;
        el.removeEventListener("transitionend", cleanup);
        if (toOpen) {
          // 停在打开位（保留 transform:0 + animation:none，避免重播 enter 动画）；只清过渡。
          el.style.transition = "";
          if (bd) { bd.style.transition = ""; bd.style.opacity = ""; }
        } else {
          // 关闭：更新 state 卸载元素，内联样式随之消失。
          if (m === "closeMenu" || m === "openMenu") logic.closeMenu();
          else if (m === "closeHistory" || m === "openHistory") logic.closeHistory();
          else logic.closeTopSheet();
        }
        panel = null; backdrop = null; mode = null; settling = false; stage = "none";
      };
      el.addEventListener("transitionend", cleanup);
      setTimeout(cleanup, DUR * 1000 + 80); // 兜底：transitionend 偶发不触发
    };

    const onStart = (e: TouchEvent) => {
      if (settling || e.touches.length !== 1) { stage = "none"; return; }
      const t = e.touches[0];
      sx = t.clientX; sy = t.clientY; st = Date.now();
      startScrollTop = (nearestScroller(e.target)?.scrollTop) ?? 0;
      snap = logic.gestureSnapshot();
      stage = snap.modal ? "none" : "pending";
    };

    const onMove = (e: TouchEvent) => {
      if (stage === "none") return;
      const t = e.touches[0];
      const dx = t.clientX - sx, dy = t.clientY - sy;
      if (stage === "pending") {
        if (Math.abs(dx) < SLOP && Math.abs(dy) < SLOP) return;
        if (decide(dx, dy)) stage = "drag";
        else { stage = "none"; return; }
      }
      if (stage === "drag") {
        e.preventDefault(); // 接管后阻止原生滚动/橡皮筋
        update(dx, dy);
      }
    };

    const onEnd = (e: TouchEvent) => {
      if (stage !== "drag") { stage = "none"; return; }
      const t = e.changedTouches[0];
      const dt = Math.max(1, Date.now() - st);
      const dist = axis === "x" ? (t.clientX - sx) : (t.clientY - sy);
      const speed = dist / dt; // 方向带符号速度(px/ms)
      const opened = panel ? 1 - Math.abs(offset) / extent : 0; // 当前打开程度 0..1
      const isOpenMode = mode === "openMenu" || mode === "openHistory";
      // 「完成方向」的甩动符号：菜单完成=向右(+)/向左推回(-)，历史相反，弹窗向下(+)关。
      let flingComplete = false;
      if (mode === "closeMenu") flingComplete = speed < -FLING;
      else if (mode === "openMenu") flingComplete = speed > FLING;
      else if (mode === "closeHistory") flingComplete = speed > FLING;
      else if (mode === "openHistory") flingComplete = speed < -FLING;
      else if (mode === "closeSheet") flingComplete = speed > FLING;
      // open 类：完成=打开；close 类：完成=关闭。统一用「打开程度 + 甩动」判定终态。
      const reachedOpen = opened > COMPLETE;
      const toOpen = isOpenMode ? (reachedOpen || flingComplete) : !(((1 - opened) > COMPLETE) || flingComplete);
      finish(toOpen);
    };

    document.addEventListener("touchstart", onStart, { passive: true });
    document.addEventListener("touchmove", onMove, { passive: false });
    document.addEventListener("touchend", onEnd, { passive: true });
    document.addEventListener("touchcancel", onEnd, { passive: true });
    return () => {
      document.removeEventListener("touchstart", onStart);
      document.removeEventListener("touchmove", onMove);
      document.removeEventListener("touchend", onEnd);
      document.removeEventListener("touchcancel", onEnd);
    };
  }, [logic]);
}
