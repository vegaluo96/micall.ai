# 部署（阿里云 ECS · Ubuntu · Nginx）

两个站点共用一台 ECS：

| 站点 | 域名 | 产物 | web root |
|---|---|---|---|
| 用户端 H5 | `zsky.com` | `frontend/dist` | `/var/www/micall` |
| 运营后台 | `admin.zsky.com` | `admin/dist` | `/var/www/micall-admin` |

nginx 模板见 `deploy/nginx/`。两个站点都需 HTTPS 才能用真麦克风/安全 Cookie；大陆 ECS 用域名
访问 80/443 通常需 ICP 备案，未备案可先用 `公网IP:高端口` 临时验证。

---

## 用户端 zsky.com（更新部署）

```bash
cd ~/micall.ai && git pull origin main
cd frontend && npm ci
echo 'VITE_SIGNALING_URL=' > .env.production    # 暂用 mock；接后端填 wss://zsky.com/realtime/signal
npm run build
sudo mkdir -p /var/www/micall && sudo cp -r dist/* /var/www/micall/

sudo cp ~/micall.ai/deploy/nginx/micall.conf /etc/nginx/sites-available/micall
sudo ln -sf /etc/nginx/sites-available/micall /etc/nginx/sites-enabled/micall
sudo nginx -t && sudo systemctl reload nginx
```

## 运营后台 admin.zsky.com（首次部署）

**1) DNS**：给 `admin.zsky.com` 加一条 A 记录，指向与 `zsky.com` 同一个公网 IP
（或加 `*.zsky.com` 泛解析）。

**2) 构建产物**
```bash
cd ~/micall.ai && git pull origin main
cd admin && npm ci
echo 'VITE_API_BASE=' > .env.production    # 暂用内置 mock；接后端填如 https://zsky.com
npm run build
sudo mkdir -p /var/www/micall-admin && sudo cp -r dist/* /var/www/micall-admin/
```

**3) 访问控制（后台无登录，必须做）**
```bash
sudo apt-get install -y apache2-utils
sudo htpasswd -c /etc/nginx/.micall_admin_htpasswd admin   # 按提示设密码
# 之后加人：sudo htpasswd /etc/nginx/.micall_admin_htpasswd <用户名>
```

**4) 站点配置 + reload**
```bash
sudo cp ~/micall.ai/deploy/nginx/micall-admin.conf /etc/nginx/sites-available/micall-admin
sudo ln -sf /etc/nginx/sites-available/micall-admin /etc/nginx/sites-enabled/micall-admin
sudo nginx -t && sudo systemctl reload nginx
```

**5) 放行端口 + HTTPS**
- 阿里云安全组放行 80 / 443。
- 证书（把三个域名一起签）：
  ```bash
  sudo apt-get install -y certbot python3-certbot-nginx
  sudo certbot --nginx -d zsky.com -d www.zsky.com -d admin.zsky.com
  ```

打开 `http(s)://admin.zsky.com` → 输 Basic Auth 账号密码 → 进入后台。

### 后台没配上 HTTPS？逐项排查
1. **DNS**：`dig +short admin.zsky.com` 必须返回你的公网 IP（A 记录没加/没生效，certbot 取不到证）。
2. **Basic Auth 挡了校验**：Let's Encrypt 的 HTTP-01 校验要访问
   `/.well-known/acme-challenge/...`，会被后台的 `auth_basic` 挡成 401 → 取证失败。
   `micall-admin.conf` 已加 `location ^~ /.well-known/acme-challenge/ { auth_basic off; }` 放行；
   确认你用的是仓库里这份最新配置后 `sudo nginx -t && sudo systemctl reload nginx`，再单独补签：
   ```bash
   sudo certbot --nginx -d admin.zsky.com
   ```
3. **80 端口**：certbot HTTP 校验走 80，安全组/防火墙要放行；大陆 ECS 用域名还需 ICP 备案。
4. 签好后 certbot 会自动加 443 跳转；`sudo certbot certificates` 可看已签域名。

---

## 关于「接口配置」里的密钥

- 现在没后端：后台「接口配置」的 endpoint/key **暂存浏览器 localStorage**，仅供联调，
  **别填真实生产密钥**。
- 后端就绪后：给 admin 配 `VITE_API_BASE`、放开 `micall-admin.conf` 里的 `/admin/` 反代，
  密钥即改为存服务端、读取打码，浏览器不再留明文（CLAUDE.md 铁律2）。
