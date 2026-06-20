# stwEP — 短信转网页

将安卓手机收到的短信实时转发到任意浏览器。支持 Web 管理后台、多用户隔离、动态验证码、邮箱验证、Docker 部署。

## 快速安装

```bash
{ curl -fsSL --connect-timeout 10 https://gitee.com/li-zhangye/stw/raw/main/install.sh -o ~/stw.sh && bash ~/stw.sh; } || { curl -fsSL --connect-timeout 10 https://raw.githubusercontent.com/Li-Zhangye/stw/refs/heads/main/install.sh -o ~/stw.sh && bash ~/stw.sh; } || { wget -q --timeout=10 https://gitee.com/li-zhangye/stw/raw/main/install.sh -O ~/stw.sh && bash ~/stw.sh; } || { wget -q --timeout=10 https://raw.githubusercontent.com/Li-Zhangye/stw/refs/heads/main/install.sh -O ~/stw.sh && bash ~/stw.sh; }
```

> 一行命令，curl/wget + Gitee/GitHub 四种组合自动轮询，任一链通即自动安装。不加 `-y` 为交互模式。


### 手动启动

```bash
git clone https://github.com/Li-Zhangye/stw.git
cd stw
python3 server/server.py
```

首次启动自动生成管理员凭证，打印在终端。

### Docker

```bash
docker run -d --name stw -p 19672:19672 -p 19673:19673 ghcr.io/li-zhangye/stw:latest
```

## 功能

- **实时转发** — 安卓 SMS 接收即推送，浏览器秒收
- **双端分离** — 用户端 `http://IP:19672` + 管理端 `http://IP:19673`
- **多用户** — 每人独立收件箱，互不可见
- **多重认证** — 密码 + 动态验证码 + 邮箱验证码 + 登录失败锁定
- **短信管理** — 搜索、导出 CSV、批量操作
- **操作日志** — 完整审计轨迹
- **插件系统** — mod 目录热加载
- **Web 主题系统** — 17 项美化：深色模式、7 套预设主题、自定义主色、卡片/页面/文字色独立覆盖、圆角/阴影/字号/密度/动画独立控件、渐变+模糊毛玻璃、7 套字体预设（中文精选/等宽编程/衬线经典/手写体）、实时轮询 3 秒生效
- **Android 主题系统** — 16 项设置：深色模式、9 种预设色+自定义 HEX、卡片圆角/阴影/elevation、消息字号 10-24sp、3 档布局密度、渐变+模糊背景、列表动画、6 种字体（含自定义 TTF/OTF SAF 文件选择器）、服务端主题同步
- **三端独立语言切换** — 前端/后端/安卓各支持 简体中文/繁體中文/English，互不干扰，各自独立存储
- **管理端图标上传** — 任意图片格式 → Pillow 自动转换为 favicon/icon-192/icon-512/Android drawable
- **管理端字体上传** — TTF/OTF/WOFF → `@font-face` 注入，支持 6 种字体 MIME 类型
- **图片 MIME 覆盖** — 19 种扩展名（JPEG/PNG/GIF/WebP/AVIF/BMP/TIFF/SVG/HEIC 等）
- **字体 MIME 覆盖** — 6 种扩展名（TTF/OTF/WOFF/WOFF2/EOT/SFNT）
- **安全** — PBKDF2 密码、参数化 SQL、HttpOnly Cookie、CSP 头、CSRF 防护、hmac.compare_digest 时序安全比较、分 admin_level 授权

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3 + 内置 http.server（零依赖） |
| 前端 | 纯 HTML / CSS / JavaScript（无框架） |
| 数据库 | SQLite 3（WAL 模式） |
| 安卓 | Kotlin + OkHttp |
| 密码 | PBKDF2-HMAC-SHA256 / 600000 次迭代 / 随机 128 bit salt |
| 通信 | HTTP / HTTPS（自签名证书自动生成） |
| 图片处理 | Pillow（图标转换） |

## 安全设计

- 密码不以明文存储、不打印到日志、不写入 `server_info.json`
- 管理后台独立端口 + 独立会话 Cookie
- 所有 API 校验 `Origin` 头 + `X-Requested-With`，拒绝跨站请求
- 登录错误 3 次弹动态验证码，6 次锁定并发邮件通知
- 注册/找回密码不区分"手机号存在/不存在"，防止用户枚举
- 动态验证码 60 秒冷却、30 秒过期
- 会话过期时间 24 小时
- 请求体上限 1 MB
- 响应头：`CSP`、`X-Frame-Options DENY`、`X-Content-Type-Options nosniff`、`Referrer-Policy no-referrer`、`Cache-Control no-store`
- 登录密码用 `hmac.compare_digest` 比较，防止时序攻击
- CSRF 保护：`X-Requested-With: XMLHttpRequest` 头校验
- 管理 API 用 `admin_level` 分级授权（level 1-3）
- 文件上传经路径规范化检查，防止目录穿越

## 项目结构

```
stwEP/
├── install.sh          # 一键安装脚本（全自动）
├── stw                 # 命令行管理工具
├── Dockerfile          # 多架构 Docker 构建
├── docker-compose.yml  # Docker Compose 编排
├── README.md           # 本文档
├── output.jpg          # 项目图标源文件
├── server/
│   ├── server.py       # HTTP API 服务（3360+ 行）
│   ├── daemon.py       # 短信守护进程
│   ├── db.py           # SQLite 双检锁初始化
│   ├── mail.py         # SMTP 邮件发送（环境变量优先）
│   ├── admin_config.py # 管理员凭证（PBKDF2）
│   ├── session_store.py# 内存会话管理
│   ├── dynamic_code.py # 动态验证码（60s 冷却）
│   ├── rate_limiter.py # 频率限制
│   ├── check_env.py    # 环境检测
│   ├── mod_scanner.py  # 插件安全扫描
│   └── utils.py        # 工具函数
├── public/
│   ├── index.html      # 短信列表主页
│   ├── login.html      # 登录页
│   ├── register.html   # 注册页
│   ├── console.html    # 管理后台（1500+ 行）
│   ├── verify.html     # 邮箱验证
│   ├── forgot-password.html
│   ├── set-password.html
│   ├── css/style.css   # CSS 变量主题系统
│   ├── js/i18n.js      # 三语言国际化
│   ├── js/theme.js     # 主题轮询（3s）
│   ├── js/auth.js      # 公共 JS（API 封装、XSS 过滤）
│   ├── favicon.ico     # 网站图标
│   ├── icon.png        # 192x192 项目图标
│   ├── icon-512.png    # 512x512 大图标
│   └── fonts/          # 自定义字体上传目录
├── mobile/SmsToWeb/    # 安卓源代码（Kotlin）
│   └── app/src/main/
│       ├── java/com/sms2web/
│       │   ├── ui/      # Activity 界面
│       │   ├── api/     # 网络请求
│       │   ├── service/ # 短信转发服务
│       │   └── util/    # PrefManager 等
│       └── res/         # 资源文件
└── mod/                # 插件目录（热加载）
```

## API 参考

### 用户端 API

| 端点 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/api/auth/login` | POST | 密码/动态码/邮箱码登录 | 无 |
| `/api/auth/register/send-code` | POST | 注册发送邮箱验证码 | 无 |
| `/api/auth/register/verify-code` | POST | 验证邮箱验证码 | 无 |
| `/api/auth/register/set-password` | POST | 设置登录密码 | 无 |
| `/api/auth/login/send-email-code` | POST | 登录场景发送邮箱验证码 | 无 |
| `/api/auth/forgot-password/send-code` | POST | 忘记密码发送验证码 | 无 |
| `/api/auth/forgot-password/verify` | POST | 验证重置密码验证码 | 无 |
| `/api/auth/change-password` | POST | 修改密码 | 用户 Session |
| `/api/auth/change-password-by-email` | POST | 邮箱验证码改密码 | 用户 Session |
| `/api/auth/user/info` | POST | 获取当前用户信息 | 用户 Session |
| `/api/auth/logout` | POST | 退出登录 | 用户 Session |
| `/api/sms/list` | GET | 获取短信列表（支持长轮询） | 用户 Session |
| `/api/sms/receive` | POST | 接收转发短信 | 用户 Session |
| `/api/sms/mark-read` | POST | 标记已读 | 用户 Session |
| `/api/sms/mark-unread` | POST | 标记未读 | 用户 Session |
| `/api/sms/delete` | POST | 删除短信 | 用户 Session |
| `/api/sms/export` | GET | 导出短信 JSON | 用户 Session |
| `/api/dynamic-code` | POST | 获取当前动态验证码 | 用户 Session |
| `/api/heartbeat` | POST | 设备在线心跳 | 用户 Session |
| `/api/theme` | GET | 获取主题配置 | 无 |
| `/api/languages` | GET | 获取支持的语言列表 | 无 |

### 管理端 API

| 端点 | 方法 | 说明 | 权限 |
|------|------|------|------|
| `/api/admin/login` | POST | 管理员登录 | 无 |
| `/api/admin/logout` | POST | 管理员退出 | Admin |
| `/api/admin/check` | POST | 检查登录状态 | Admin |
| `/api/admin/stats` | POST | 系统统计 | Admin |
| `/api/admin/users` | POST | 用户列表 | Admin |
| `/api/admin/user/detail` | POST | 用户详情 | Admin |
| `/api/admin/user/toggle-active` | POST | 启用/禁用用户 | Admin |
| `/api/admin/user/delete` | POST | 删除用户 | Admin |
| `/api/admin/user/sms` | POST | 查看指定用户短信 | Admin |
| `/api/admin/user/update` | POST | 更新用户信息 | Admin |
| `/api/admin/user/change-password` | POST | 管理员改用户密码 | Admin |
| `/api/admin/logs` | GET/POST | 操作日志 | Admin |
| `/api/admin/settings/language` | POST | 设置管理员语言（session 独立） | Admin |
| `/api/admin/languages` | GET | 获取语言列表 | Admin |
| `/api/admin/upload-icon` | POST | 上传项目图标（base64） | Admin level 2+ |
| `/api/admin/upload-font` | POST | 上传自定义字体（base64） | Admin level 2+ |
| `/api/admin/notifications` | GET/POST | 通知管理 | Admin |
| `/api/admin/export/sms-csv` | GET | 导出 SMS CSV | Admin |
| `/api/admin/export/users-csv` | GET | 导出用户 CSV | Admin |
| `/api/admin/export/sms-json` | POST | 导出 SMS JSON | Admin |
| `/api/admin/daemon/restart` | POST | 重启守护进程 | Admin level 2+ |
| `/api/admin/report/create` | POST | 创建安全报告 | Admin |
| `/api/admin/report/list` | POST | 报告列表 | Admin |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATA_DIR` | 数据目录（数据库/配置/日志） | `server/data` |
| `FORCE_USER_PORT` | 强制用户端口 | 随机 |
| `FORCE_ADMIN_PORT` | 强制管理端口 | 用户端口+1 |
| `SMTP_HOST` | SMTP 服务器地址 | 配置文件 |
| `SMTP_PORT` | SMTP 端口 | 25 |
| `SMTP_USER` | SMTP 用户名 | - |
| `SMTP_PASS` | SMTP 密码 | - |
| `COOKIE_SECURE` | 设为 `1` 启用 Secure Cookie | 0 |
| `MOD_DIR` | 插件目录 | `./mod` |

## Docker 部署

### 方式一：直接运行

```bash
docker run -d --name stw \
  -p 19672:19672 \
  -p 19673:19673 \
  -v stw_data:/app/data \
  ghcr.io/li-zhangye/stw:latest
```

### 方式二：Docker Compose

```bash
wget https://raw.githubusercontent.com/Li-Zhangye/stw/refs/heads/main/docker-compose.yml
docker compose up -d
```

## 常见问题

**Q: 安装后如何找到管理员信息？**
A: 安装脚本末尾会打印管理员手机号和密码。如果忘了，运行 `./stw` → 菜单 10 添加新管理员。

**Q: 端口被占用怎么办？**
A: 运行 `./stw` → 菜单 9 重置端口，或设置环境变量 `FORCE_USER_PORT=19672 FORCE_ADMIN_PORT=19673`。

**Q: 如何开启 HTTPS？**
A: 运行 `./stw` → 菜单 7，脚本会自动用 openssl 生成自签名证书。首次生成后永久有效（10 年）。

**Q: 用户可以注册吗？**
A: 默认开放注册。运行 `./stw` → 菜单 8 可关闭注册，仅允许管理员后台添加。

**Q: 安卓 App 在哪里下载？**
A: 安卓源代码在 `mobile/SmsToWeb/`，需用 Android Studio 编译。编译后的 APK 位于 `mobile/SmsToWeb/apk/stw.apk`。

**Q: 如何修改短信列表的样式/主题？**
A: 运行 `./stw` → 菜单 15 进入主题配置，支持颜色、圆角、字体、深色模式等。Android App 的设置中也有主题选项。

**Q: 支持多少种图片/字体格式？**
A: 图片 19 种（JPEG/PNG/GIF/WebP/AVIF/BMP/TIFF/SVG/HEIC 等），字体 6 种（TTF/OTF/WOFF/WOFF2/EOT/SFNT）。可通过管理 API 上传自定义图标和字体。

**Q: 语言切换在哪里？**
A: 网页端在页面顶部右侧下拉菜单；安卓端在 App 主题设置中；后端语言在管理后台顶部下拉菜单。三端独立互不影响。

## 许可

MIT License

---

# stwEP — SMS to Web

Forward Android SMS to any browser in real time. Includes web admin panel, multi-user isolation, dynamic verification codes, email auth, and Docker support.

## Quick Install

```bash
{ curl -fL --connect-timeout 10 https://gitee.com/li-zhangye/stw/raw/main/install.sh -o /tmp/stw.sh && bash /tmp/stw.sh; } || { curl -fL --connect-timeout 10 https://raw.githubusercontent.com/Li-Zhangye/stw/refs/heads/main/install.sh -o /tmp/stw.sh && bash /tmp/stw.sh; } || { wget -q --timeout=10 https://gitee.com/li-zhangye/stw/raw/main/install.sh -O /tmp/stw.sh && bash /tmp/stw.sh; } || { wget -q --timeout=10 https://raw.githubusercontent.com/Li-Zhangye/stw/refs/heads/main/install.sh -O /tmp/stw.sh && bash /tmp/stw.sh; }
```

> One-liner: curl/wget + Gitee/GitHub 4 combinations auto-retry. Drop `-y` for interactive mode.



## Features

- Real-time SMS forwarding from Android to browser
- Separate ports for user frontend `:19672` and admin panel `:19673`
- Multi-user with isolated inboxes
- Multi-factor auth: password + dynamic code + email verification + fail lockout
- SMS search, CSV export, batch operations
- Full audit log
- Hot-swappable mod plugin system
- PBKDF2 password hashing, parameterized SQL, HttpOnly cookies, CSP headers, CSRF protection, timing-safe password comparison, admin level authorization
- **Web theme system** — 17 controls: dark mode, 7 presets + custom color, card/page/text color overrides, radius/shadow/size/density/animation, gradient + blur, 7 font presets, 3s live polling
- **Android theme system** — 16 controls: dark mode, 9 presets + custom HEX, radius SeekBar, shadow/elevation, font size 10-24sp, 3 density modes, gradient + blur, list animation, 6 fonts (TTF/OTF file picker via SAF), server sync
- **Tri-language i18n** — Frontend/Backend/Android each support 简体中文/繁體中文/English, independently stored
- **Admin icon upload** — Any image format → Pillow auto-converts to favicon/icon-192/icon-512/Android drawable
- **Admin font upload** — TTF/OTF/WOFF → `@font-face` injection
- **19 image MIME types** — JPEG/PNG/GIF/WebP/AVIF/BMP/TIFF/SVG/HEIC/ICO etc.
- **6 font MIME types** — TTF/OTF/WOFF/WOFF2/EOT/SFNT

## Security

- Passwords never stored in plaintext, never logged, never written to `server_info.json`
- Admin console on separate port with separate session cookies
- All APIs validate `Origin` header + `X-Requested-With`, rejecting cross-site requests
- 3 failed logins trigger dynamic code, 6 trigger lockout + email alert
- Registration/password-reset does not reveal whether a phone number exists
- Dynamic code: 60s cooldown, 30s expiry
- Session expiry: 24 hours
- Request body limit: 1 MB
- Security headers: CSP, X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy no-referrer, Cache-Control no-store
- Password comparison via `hmac.compare_digest` (timing-safe)
- CSRF protection via `X-Requested-With: XMLHttpRequest`
- Admin API uses `admin_level` role-based authorization (level 1-3)
- File uploads path-normalized to prevent directory traversal

## Docker

### Direct run

```bash
docker run -d --name stw \
  -p 19672:19672 \
  -p 19673:19673 \
  -v stw_data:/app/data \
  ghcr.io/li-zhangye/stw:latest
```

### Docker Compose

```bash
wget https://raw.githubusercontent.com/Li-Zhangye/stw/refs/heads/main/docker-compose.yml
docker compose up -d
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATA_DIR` | Data directory (DB/config/logs) | `server/data` |
| `FORCE_USER_PORT` | Force user port | Random |
| `FORCE_ADMIN_PORT` | Force admin port | user port + 1 |
| `SMTP_HOST` | SMTP server | Config file |
| `SMTP_PORT` | SMTP port | 25 |
| `SMTP_USER` | SMTP username | - |
| `SMTP_PASS` | SMTP password | - |
| `COOKIE_SECURE` | Set `1` to enable Secure cookies | 0 |
| `MOD_DIR` | Mod plugin directory | `./mod` |

## API Reference

### User APIs

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/api/auth/login` | POST | Login with password/dynamic code/email code | No |
| `/api/auth/register/send-code` | POST | Send email verification code | No |
| `/api/auth/register/verify-code` | POST | Verify email code | No |
| `/api/auth/register/set-password` | POST | Set initial password | No |
| `/api/auth/login/send-email-code` | POST | Send email code for login | No |
| `/api/auth/forgot-password/send-code` | POST | Send password reset code | No |
| `/api/auth/change-password` | POST | Change password | Session |
| `/api/auth/user/info` | POST | Get current user info | Session |
| `/api/auth/logout` | POST | Logout | Session |
| `/api/sms/list` | GET | List SMS (long-poll supported) | Session |
| `/api/sms/receive` | POST | Receive forwarded SMS | Session |
| `/api/sms/mark-read` | POST | Mark as read | Session |
| `/api/sms/mark-unread` | POST | Mark as unread | Session |
| `/api/sms/delete` | POST | Delete SMS | Session |
| `/api/sms/export` | GET | Export SMS as JSON | Session |
| `/api/dynamic-code` | POST | Get current dynamic code | Session |
| `/api/heartbeat` | POST | Device online heartbeat | Session |
| `/api/theme` | GET | Get theme config | No |
| `/api/languages` | GET | List supported languages | No |

### Admin APIs

| Endpoint | Method | Description | Level |
|----------|--------|-------------|-------|
| `/api/admin/login` | POST | Admin login | - |
| `/api/admin/logout` | POST | Admin logout | 1+ |
| `/api/admin/stats` | POST | System statistics | 1+ |
| `/api/admin/users` | POST | User list | 1+ |
| `/api/admin/user/detail` | POST | User detail | 1+ |
| `/api/admin/user/delete` | POST | Delete user | 2+ |
| `/api/admin/user/sms` | POST | View user SMS | 1+ |
| `/api/admin/logs` | GET/POST | Operation logs | 1+ |
| `/api/admin/settings/language` | POST | Set admin language (per session) | 2+ |
| `/api/admin/upload-icon` | POST | Upload project icon (base64) | 2+ |
| `/api/admin/upload-font` | POST | Upload custom font (base64) | 2+ |
| `/api/admin/notifications` | GET/POST | Notifications | 1+ |
| `/api/admin/export/sms-csv` | GET | Export SMS CSV | 1+ |
| `/api/admin/export/users-csv` | GET | Export users CSV | 1+ |
| `/api/admin/daemon/restart` | POST | Restart daemon | 2+ |

## Project Structure

```
stwEP/
├── install.sh          # One-click install script
├── stw                 # CLI management tool
├── Dockerfile          # Multi-arch Docker build
├── docker-compose.yml  # Docker Compose
├── server/             # Python backend
│   ├── server.py       # HTTP API server (3360+ lines)
│   ├── daemon.py       # SMS daemon process
│   ├── db.py           # SQLite with double-check locking
│   ├── mail.py         # SMTP email (env var priority)
│   ├── admin_config.py # Admin credentials (PBKDF2)
│   ├── session_store.py# In-memory sessions
│   ├── dynamic_code.py # Dynamic verification codes
│   ├── rate_limiter.py # Rate limiting
│   ├── check_env.py    # Environment checker
│   ├── mod_scanner.py  # Plugin security scanner
│   └── utils.py        # Utility functions
├── public/             # Web frontend
│   ├── index.html      # SMS inbox
│   ├── login.html      # Login page
│   ├── register.html   # Registration
│   ├── console.html    # Admin console (1500+ lines)
│   ├── css/style.css   # CSS variable theme system
│   ├── js/i18n.js      # Tri-language i18n
│   ├── js/theme.js     # Theme polling (3s)
│   ├── js/auth.js      # Shared JS utilities
│   └── icon.png        # 192x192 project icon
├── mobile/SmsToWeb/    # Android app (Kotlin)
└── mod/                # Plugin directory
```

## FAQ

**Q: How do I find the admin credentials after install?**
A: The install script prints them at the end. If forgotten, run `./stw` → menu 10 to add a new admin.

**Q: Ports are occupied?**
A: Run `./stw` → menu 9 to reset ports, or set `FORCE_USER_PORT` and `FORCE_ADMIN_PORT` env vars.

**Q: How to enable HTTPS?**
A: Run `./stw` → menu 7. The script auto-generates a self-signed certificate (10-year validity).

**Q: Can I disable user registration?**
A: Yes, run `./stw` → menu 8. Only admins can then add users from the console.

**Q: Where is the Android APK?**
A: Source code is in `mobile/SmsToWeb/`. Build with Android Studio or use the prebuilt APK at `mobile/SmsToWeb/apk/stw.apk`.

**Q: How to customize the theme?**
A: Run `./stw` → menu 15 for web themes, or use the Android app's theme settings.

**Q: What image/font formats are supported?**
A: 19 image types (JPEG/PNG/GIF/WebP/AVIF/BMP/TIFF/SVG/HEIC) and 6 font types (TTF/OTF/WOFF/WOFF2/EOT/SFNT).

**Q: Where is the language switcher?**
A: Web: dropdown in the top-right corner. Android: theme settings. Admin console: top bar. All three are independent.

## License

MIT
