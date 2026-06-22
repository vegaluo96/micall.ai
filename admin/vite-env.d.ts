/// <reference types="vite/client" />

declare module "*.template.html?raw" {
  const content: string;
  export default content;
}

interface ImportMetaEnv {
  /** Backend admin API base (REST). Empty = use built-in mock data. */
  readonly VITE_API_BASE?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
