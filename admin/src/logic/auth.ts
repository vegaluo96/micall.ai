// 后台登录鉴权。
//
// 安全模型（重要）：静态 SPA 在没有后端时无法真正鉴权——打包产物对任何人可下载，
// 因此这一层在「无后端」时只是 UX 软门禁，真正的网络门禁应由 nginx Basic Auth 或后端
// 提供。接上后端后（VITE_API_BASE），登录走后端校验、发 token，才是真鉴权。
//
//   • 配置了 VITE_API_BASE：POST {base}/admin/login {username,password}
//       成功 → 存 token（sessionStorage，关页即失效）；后续管理 API 带 Authorization。
//   • 未配置：用 VITE_ADMIN_PASSWORD（构建期，默认 "micall-admin"）做本地软门禁。

const TOKEN_KEY = "micall_admin_token";

function base(): string {
  // optional chaining keeps this safe outside Vite (tests)
  return (import.meta.env?.VITE_API_BASE || "").trim();
}

export function isAuthed(): boolean {
  try {
    return !!sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return false;
  }
}

export function authToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function logout(): void {
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* noop */
  }
}

export async function login(username: string, password: string): Promise<{ ok: boolean; error?: string }> {
  const b = base();
  if (b) {
    try {
      const r = await fetch(`${b}/admin/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username, password }),
      });
      if (r.ok) {
        const d = (await r.json().catch(() => ({}))) as { token?: string };
        sessionStorage.setItem(TOKEN_KEY, d.token || "ok");
        return { ok: true };
      }
      if (r.status === 401 || r.status === 403) return { ok: false, error: "账号或密码错误" };
      return { ok: false, error: `登录失败（${r.status}）` };
    } catch {
      return { ok: false, error: "无法连接服务器" };
    }
  }
  // 无后端：本地软门禁（仅 UX，真防护靠 nginx Basic Auth / 后端登录）。
  // 绝不把真实密码写进源码（会进 git）：未配 VITE_ADMIN_PASSWORD 时用非敏感占位，生产必须显式设置。
  const expected = (import.meta.env?.VITE_ADMIN_PASSWORD || "micall-admin").trim();
  if (password === expected) {
    sessionStorage.setItem(TOKEN_KEY, "dev");
    return { ok: true };
  }
  return { ok: false, error: "密码错误" };
}
