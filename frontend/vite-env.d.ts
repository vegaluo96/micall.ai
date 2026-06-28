/// <reference types="vite/client" />

// Raw import of the verbatim DC template (the design source of truth).
declare module "*.template.html?raw" {
  const content: string;
  export default content;
}

interface ImportMetaEnv {
  /** Realtime control-signaling endpoint (WS). When empty, the app uses the
   *  built-in MockSignalingClient so it runs standalone with no backend. */
  readonly VITE_SIGNALING_URL?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** 构建期注入（vite.config.ts define）：版本号 + 构建日期 + git 短 hash，每次发布自动反映。 */
declare const __APP_VERSION__: string;
