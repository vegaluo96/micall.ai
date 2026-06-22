/// <reference types="vite/client" />

declare module "*.template.html?raw" {
  const content: string;
  export default content;
}

interface ImportMetaEnv {
  /** Backend admin API base (REST). Empty = use built-in mock data. */
  readonly VITE_API_BASE?: string;
  /** No-backend soft-gate password for the admin login page (dev only).
   *  Ignored once VITE_API_BASE is set (login then goes through the backend). */
  readonly VITE_ADMIN_PASSWORD?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
