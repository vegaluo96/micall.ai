# MiCall 用户端 H5（前端复刻轨）

`AI Call.dc.html` 原型 → 生产 React 应用。遵循 `docs/03-前端对接规格.md` 与
`docs/CLAUDE.md` 的第一性原理：**前端 UI 是设计唯一真相，逐像素逐文案复刻，不擅自改动。**

## 设计取舍：为什么这样复刻（最不容易出错）

原型用一套自定义的 DC 模板格式（`<x-dc>` + `support.js` 运行时）写成，包含 ~960 行
精调的内联样式、动画时长与 SVG。为了**最大化保真、最小化转写出错**，本应用：

- **不手工把 960 行内联样式逐条翻成 JSX**（那会引入大量肉眼难查的样式/SVG 大小写错误）。
- 而是把**原型模板原封不动**（`src/app.template.html`，逐字节来自原型）交给一个
  **自带的、精简的 DC 模板渲染器**（`src/dc/`，对 `support.js` 相关语义的干净移植：
  插值 / `sc-if` / `sc-for` / `style` 字符串 / `style-active` 伪类 / 主题）。
- 因此视觉、交互、文案、动画、状态机与原型**逐像素一致**，且是一个真正的
  Vite + React + TypeScript 生产工程。

## Mock → 服务端信令（spec 03 §3/§4/§5）

唯一的实质改动在“通话流程”——把原型里的 `setTimeout/setInterval` 假流程换成服务端控制信令：

| 原型 mock | 生产实现 |
|---|---|
| `dial()` 的 18% 随机接通失败 | **删除**（仅在真实网络/服务错误时 `call_failed`） |
| `setInterval` 前端自计时/扣费 | **删除**，计费**服务端权威**（`billing`/`low_minutes`/`out_of_minutes`） |
| `toListen/toThink/toSpeak` 轮播假台词 | **删除**，状态切换+字幕全由 `state`/`subtitle`/`emotion`/`interrupted` 驱动 |
| `grantMic()` 直接置位 | 真实 `getUserMedia({echoCancellation:true})`（AEC），成功后建连 |
| 预约 / 来电 | 原型已移除，未实现 |

`scenarioDefs[].lines` 仅作为**静态设计文案**（角色详情页 slogan）保留，**不再被回放为实时对话**。

信令协议见 `src/logic/signaling.ts`，端点由 `VITE_SIGNALING_URL` 配置（铁律2，不硬编码）；
留空则使用内置 `MockSignalingClient`，应用可**无后端独立运行**用于复刻验收。

> 注：原型用“光球”作为角色影像**占位**。生产版应在光球区替换为《角色资产生成规范》定义的
> 循环视频（200–300ms crossfade），`emotion` 信令已接好但因当前无资产暂不切换画面——这是
> 后续唯一的视觉替换，其余布局/交互不动。

## 运行

```bash
cd frontend
npm install
npm run dev        # 本地开发（默认走 mock 信令，无需后端）
npm run build      # 类型检查 + 生产构建
npm run preview    # 预览构建产物
```

## 目录

```
src/
  app.template.html      ← 原型模板（逐字节，唯一真相）
  dc/                    ← 精简 DC 模板渲染器（resolve/css/pseudo/compile/DcView）
  logic/
    MiCallLogic.ts       ← 原型 Component 的忠实移植 + 信令化通话流程
    signaling.ts         ← 控制信令协议 + WebSocket/Mock 两个实现
    useMiCall.ts         ← React 桥接（setState → 重渲染）
  App.tsx / main.tsx     ← 入口
```
