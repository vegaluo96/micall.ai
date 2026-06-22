// API 接口配置（endpoint / key / 模型参数）的持久化层。
//
// 这是 CLAUDE.md 铁律2 的落地：ASR/LLM/TTS 等节点的 endpoint 与 key 全部走配置、
// 可在线切换（「先走 apiyi、卡了切直连」靠改这里，不动对话逻辑）。后台「接口配置」
// 页是这份配置的编辑界面，后端实时管线是它的消费者。
//
// 两种后端：
//   • 配置了 VITE_API_BASE：走后端 REST（GET/PUT /admin/api-config）。**生产用这条**
//     ——密钥存服务端、读取时由后端打码，浏览器永不持久化明文密钥。
//   • 未配置：落 localStorage，方便无后端时本地把配置功能跑通（dev/演示）。
//
// ⚠️ 安全：localStorage 持久化仅供本地联调。生产务必配置 VITE_API_BASE，让密钥留在
//    服务端；不要把真实 key 长期存在浏览器里。

export type ApiConfig = Record<string, Record<string, string>>;

const LS_KEY = "micall_admin_api_cfg";

function base(): string {
  // optional chaining keeps this safe outside Vite (tests / SSR)
  return (import.meta.env?.VITE_API_BASE || "").trim();
}

/** 是否走真实后端（决定密钥落地位置）。 */
export function usingBackend(): boolean {
  return !!base();
}

/** 读取已保存的配置；无则返回 null（调用方回退到内置默认）。 */
export async function loadApiConfig(): Promise<ApiConfig | null> {
  const b = base();
  if (b) {
    try {
      const r = await fetch(`${b}/admin/api-config`, { credentials: "include" });
      if (r.ok) return (await r.json()) as ApiConfig;
    } catch {
      /* 网络/后端不可用：保持默认，不阻塞页面 */
    }
    return null;
  }
  try {
    const raw = localStorage.getItem(LS_KEY);
    return raw ? (JSON.parse(raw) as ApiConfig) : null;
  } catch {
    return null;
  }
}

/** 保存整份配置；返回是否成功。 */
export async function saveApiConfig(cfg: ApiConfig): Promise<boolean> {
  const b = base();
  if (b) {
    try {
      const r = await fetch(`${b}/admin/api-config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(cfg),
      });
      return r.ok;
    } catch {
      return false;
    }
  }
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(cfg));
    return true;
  } catch {
    return false;
  }
}

/** 连通性测试。有后端则让后端实测该节点；无后端时本地无法跨域直连，返回 null（未知）。 */
export async function testApiSection(sectionKey: string, cfg: Record<string, string>): Promise<boolean | null> {
  const b = base();
  if (!b) return null;
  try {
    const r = await fetch(`${b}/admin/api-config/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ section: sectionKey, config: cfg }),
    });
    if (!r.ok) return false;
    const data = await r.json().catch(() => ({}));
    return data && typeof data.ok === "boolean" ? data.ok : true;
  } catch {
    return false;
  }
}
