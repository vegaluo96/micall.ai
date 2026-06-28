import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { execSync } from "node:child_process";

// Production build for the MiCall user-facing H5.
// The realtime signaling endpoint is read from config (VITE_SIGNALING_URL),
// never hardcoded — see CLAUDE.md 铁律2 ("所有外部服务 endpoint/key 走配置").

// 构建期注入版本号：基础版本 + 构建日期 + git 短 hash → 每次发布自动反映「关于」里的版本，无需手改。
const BASE_VERSION = "v1.0.0";
function buildVersion(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  const date = `${d.getFullYear()}.${p(d.getMonth() + 1)}.${p(d.getDate())}`;
  let hash = "";
  try { hash = execSync("git rev-parse --short HEAD", { encoding: "utf8" }).trim(); } catch { /* git 不可用就只用日期 */ }
  return hash ? `${BASE_VERSION} · ${date} · ${hash}` : `${BASE_VERSION} · ${date}`;
}

export default defineConfig({
  root: ".",
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(buildVersion()),
  },
  server: {
    host: true,
    port: 5173,
  },
  build: {
    outDir: "dist",
    sourcemap: false,   // 生产不外泄 TS 源码到浏览器 DevTools（dev 模式仍有内联 sourcemap，不影响调试）
  },
});
