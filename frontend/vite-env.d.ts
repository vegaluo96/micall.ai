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
