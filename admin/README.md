# MiCall 运营管理端（Admin · 11 tab）

`MiCall Admin.dc.html` 原型 → 生产 React 应用。遵循 `docs/02-后端架构与实现规格.md §7`
（11 个 tab 全部实现）与 `docs/CLAUDE.md`：原型是 UI 唯一真相，逐像素复刻。

## 复刻方式（与用户端同一套低风险技术）

复用 `frontend/` 已验证的 **DC 模板渲染器**（`src/dc/`）：把 Admin 原型模板**逐字节**
（`src/app.template.html`，可由 `scripts/extract-template.mjs` 从冻结原型再生成）交给渲染器，
配一份**忠实移植**的逻辑类（`src/logic/AdminLogic.ts`），从而视觉/交互/文案逐像素一致，
零手工转写风险。

## 11 个 tab

数据概览 · 用户管理 · 角色管理（角色/音色/表情 + 导入导出）· 场景管理 · 通话记录 ·
工单反馈 · 订单充值 · 邀请裂变 · 接口配置（ASR/快脑/TTS/长记忆脑/Embedding 五节点，
endpoint+key 可配）· 成本与限流 · 权限管理。

> 「接口配置」节点划分与架构一致：LLM 分快脑（通话中，DeepSeek-V4-Flash）/ 慢脑（通话后，
> Qwen-Long），即「实时保延迟 / 离线享灵活」的分流（CLAUDE.md §4）。

## 登录与访问控制（重要的安全模型）

后台进站先过登录页（`src/AdminLogin.tsx` + `src/logic/auth.ts`）。但要清楚：

> 静态 SPA 在**没有后端时无法真正鉴权**——打包产物对任何人可下载。所以：
> - **真正的网络门禁** = nginx Basic Auth（账号 `admin` + 你 htpasswd 设的密码）或后端；
> - app 登录页在**无后端时只是 UX 软门禁**（密码由 `VITE_ADMIN_PASSWORD` 配，默认
>   `micall-admin`），可被绕过，不要当作真防护。

- **配了 `VITE_API_BASE`（生产）**：登录走后端 `POST /admin/login` 校验、发 token，
  存 sessionStorage，后续管理 API 带 `Authorization: Bearer`——这才是真鉴权。后端已
  **fail closed**：必须设强 `MICALL_ADMIN_PASSWORD` + 长随机 `MICALL_ADMIN_TOKEN`，
  否则 `/admin/login` 返回 503、其余 `/admin/*` 返回 401（见 deploy/README.md）。
- **没配（本地/演示）**：用 `VITE_ADMIN_PASSWORD` 软门禁（默认账号 `admin` / 密码
  `micall-admin`，可改），仅本地 dev、可被绕过；**线上请保留 nginx Basic Auth**。

左下角有「退出」浮层按钮；sessionStorage 关页即登出。

## 接口配置（密钥/端点）—— 已做实，可持久化

「接口配置」tab 的 5 个节点（ASR / 快脑 / TTS / 长记忆脑 / Embedding）endpoint+key+参数
**可编辑、可保存、可加载**（`src/logic/configService.ts`），落地 CLAUDE.md 铁律2
（endpoint/key 走配置、在线可切换，「先走 apiyi、卡了切直连」靠改这里）：

- **配置了 `VITE_API_BASE`（生产）**：读写走后端 REST
  `GET/PUT {VITE_API_BASE}/admin/api-config`，连通性测试走
  `POST {VITE_API_BASE}/admin/api-config/test`。**密钥存服务端、读取由后端打码，浏览器
  不持久化明文密钥。**
- **未配置（本地联调）**：配置落 `localStorage`，把功能跑通；⚠️ 仅供 dev，勿存真实密钥。

页面打开时自动加载已保存配置覆盖默认值；每个节点卡片的「保存」真正持久化、「测试」在有
后端时实测该节点。其余列表/详情数据仍为 mock，后端就绪后同样换 REST——UI 不变。
链路自测面板（接口配置页的「开始测试」）目前用本地计时模拟，接后端后改真实探测。

## 运行

```bash
cd admin
npm install
npm run dev        # http://localhost:5174
npm run build      # 类型检查 + 生产构建
npm run smoke      # 无浏览器渲染冒烟测试（覆盖 11 tab + 详情抽屉）
```
