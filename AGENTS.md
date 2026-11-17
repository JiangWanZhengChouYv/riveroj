# AGENTS.md — Hydro-Dev 本地 OJ 与洛谷插件（含计划）

本文件面向后续接手本仓库的 AGENTS。**开工前先读第 4 节现状与第 6 节计划状态**：阶段 A（洛谷登录）与阶段 B（全量拉取）已于 2026-11-15 实现并验证；阶段 C 保持现状；阶段 D 已实现洛谷提交与反算样例。所有决策、进展与协作约定都记在本文件，`collaboration.md` 保留为空占位。

## 1. 这个仓库是什么

一个用 Docker Compose 跑起来的 **HydroOJ 开发实例**（独立于 `~/Hydro/Hydro-Docker` 的 8888 实例），外加一个自研洛谷插件：

- **HydroOJ 版本**：v5.1.0（`hydrooj` npm 包，Node 22，容器内全局安装）
- **访问地址**：http://127.0.0.1:8889
- **测试账号**：`JWZCY` / `Hydro123`（uid 2，superadmin / root，`priv=-1`）
- **评测机账号**：`hydro` / `Hydro7890`（uid 1，`setJudge`）
- **容器**：`dev-oj-mongo`、`dev-oj-backend`、`dev-oj-judge`（compose project `hydro-dev`）

> 账号是用户指定用于所有测试的，不要改动或删除。

## 2. 目录结构

```
.
├── AGENTS.md                   # 本文件（项目现状 + 计划状态）
├── collaboration.md            # 空占位文件（协作约定已并入 AGENTS.md）
├── docker-compose.yml          # 三容器编排，backend 暴露 8889:8888（judge 带 healthcheck）
├── scripts/judge-healthcheck.js # judge 健康检查脚本（只读挂进容器，不改镜像）
├── backend/
│   ├── Dockerfile              # node:22-trixie-slim + pm2 + hydrooj + ui-default
│   └── entrypoint.sh           # 首次初始化：建 hydro/JWZCY 账号、写 addon.json
├── judge/                      # 评测机镜像（7GB+，别重建）
│   ├── Dockerfile
│   ├── entrypoint.sh
│   └── judge.yaml              # 只用于 build，运行时用镜像内烘焙的那份
├── addons/
│   ├── luogu-import/           # ★ 洛谷插件（源码在此，只读挂载进容器）
│   │   ├── index.ts            # 路由 / CLI 脚本 / 控制面板注入 / 启动恢复任务 / 本地评测联动
│   │   ├── src/client.ts       # 洛谷 HTTP（C3VK + 登录 cookie）、登录校验、提交、验证码
│   │   ├── src/config.ts       # 全站拉题凭据 AES-256-GCM 加密存取（Mongo 密文 + 本地密钥）
│   │   ├── src/accounts.ts     # 按用户独立的提交账号（加密存 luogu.accounts）
│   │   ├── src/submit.ts       # 题号/语言/状态映射、洛谷记录解析、来源标记
│   │   ├── src/oracle.ts       # ★ 反算样例：标程入库 + Hydro generate 极限重算
│   │   ├── src/importer.ts     # 多语言题面构建、题号映射、单题导入
│   │   ├── src/jobs.ts         # Mongo 持久化任务、断点、状态机、重启恢复、规模估算
│   │   ├── locales/{zh,en}.yaml
│   │   └── templates/          # luogu_import.html / luogu_account.html / luogu_submit.html
│   │       └── partials/       # problem_sidebar_normal.html（覆盖）/ luogu_scratchpad.html
│   └── riveroj-brand/          # ★ 站点品牌：只提供 public/ 图标，覆盖 ui-default 同名文件（见第 11 节）
├── refs/
│   └── ClionLuogu/             # ★ 只读参考实现（用户的 CLion 洛谷插件，见第 5 节）
├── data/                       # 运行时数据（gitignore）
│   ├── backend/addon.json      # 已注册 luogu-import
│   └── backend/luogu.key       # 登录凭据加密密钥（权限 600，绝不提交）
├── public/                     # gitignore
└── README.md                   # 部署说明
```

## 3. 启动 / 重部署 / 改代码

```bash
cd /Users/markzhang/Documents/Hydro-Dev

docker compose ps
docker compose up -d
docker compose down                 # 保留 data/

# 改了 backend/entrypoint.sh 或 Dockerfile：
docker build -t hydro-dev-backend:latest ./backend
docker compose up -d --force-recreate oj-backend

# 只改 addons/ 下的代码或模板：
docker compose restart oj-backend   # 插件在启动时加载，必须重启
# judge 现在有 healthcheck：backend 重启导致的断连会在数秒内自动恢复，无需一起重启
```

`./addons` 以只读方式挂到 `/root/.hydro/addons`，直接改本仓库文件即可。

**全新部署（data/ 被删）**：`backend/entrypoint.sh` 会建 `hydro`、`JWZCY` 两个账号并写含 `luogu-import` 的 `addon.json`。新增插件时必须同步改 `entrypoint.sh` 和 `data/backend/addon.json`。

## 4. 插件现状：登录 + 全量导入版（2026-11-15 实现并验证）

> 用户已确认：全量范围 = 全部来源；多语言按 Hydro 官方机制；登录态在后台配置并加密；允许长时间无人值守跑；本次只做实现 + 小样验证，**未启动真·全量任务**。

**新增接口**（全部要求 `PRIV_EDIT_SYSTEM`，POST 必须带 `Referer`）：
`GET/POST /manage/luogu/config`（保存/清除登录态）、`POST /manage/luogu/test-login`、
`GET /manage/luogu/estimate`、`GET /manage/luogu/jobs`、`POST /manage/luogu/job-action`（pause/resume/cancel）、
`GET /manage/luogu/status?jobId=`、`POST /manage/luogu/import`（`mode: manual | full`）。

### 入口

1. **后台页面**：JWZCY 登录 → `/manage/luogu`（控制面板侧边栏「洛谷题目导入」）
   - 单个/多个题号、题号区间（`P1000-P1010`）、按关键词/难度/标签翻列表抓取
   - 测试点来源（第一组样例 / 全部样例 / 不生成）、隐藏、覆盖、目标域
   - POST JSON + 轮询任务状态，实时进度与日志
2. **CLI**：
   ```bash
   docker exec dev-oj-backend sh -c 'hydrooj cli script luoguImport '"'"'{"pids":["P1001"]}'"'"''
   docker exec dev-oj-backend sh -c 'hydrooj cli script luoguImport '"'"'{"range":"P1000-P1005"}'"'"''
   docker exec dev-oj-backend sh -c 'hydrooj cli script luoguImport '"'"'{"list":{"type":"P","difficulty":[1],"tag":[1],"pages":1}}'"'"''
   ```

### 已实现要点（新版）

- **登录态**：后台「洛谷账号」区填 `_uid` + `__client_id`；`__client_id` 用 AES-256-GCM 加密存 `luogu.config`，密钥在 `data/backend/luogu.key`（600）；API / 日志 / 页面只出现 uid 与 clientId 长度。
- **测试登录**：`GET /user/{uid}?_contentOnly=1` 带 cookie 取用户名；失败给可读诊断（缺值 / 403 / 未取到用户名）。
- **抓取**：匿名 C3VK cookie jar 仍可用，配置后默认带登录 cookie；全量模式默认要求登录，UI 可显式勾选「允许匿名抓取公开题」降级（小样验证用）。
- **多语言题面**：洛谷 `data.translations`（`en` / `zh-CN` …）→ Hydro 官方多语言：`ProblemModel.add/edit` 传 `JSON.stringify({zh: md, en: md})`，写入 `problem.statement`（`zh.md` / `en.md`），题目页 `?lang=zh|en` 切换；`document.content` 为空属正常。locale 映射 `zh-CN→zh`、`en→en`、`zh-TW→zh_TW`。
- **题号映射**：Hydro `Types.ProblemId` 不允许下划线，AT 库 `AT1202Contest_a` 经 `toHydroPid()` 去非法字符 + 稳定短哈希后落库，抓取仍用洛谷原题号；`normalizePid` 不再无脑 `toUpperCase()`。
- **持久化任务**：`luogu.job` collection，每题落一次 cursor + 统计 + 日志（保留 400 行）；已存在题目直接跳过、不请求题面；支持 `pause / resume / cancel`，backend 重启由 `app/started` 自动从断点续跑；暂停/取消逐题检查，最多延迟一题。
- **全量拉取**：按来源 `P/B/CF/SP/AT/UVA`（可配置）逐页遍历，题数上限（0=不限）、限速（默认 1500ms）、磁盘/耗时估算（实测 45919 题 / 921 页 / 359 MB / 19.5 小时）；`maxPages` 可只拉前几页做小样验证。
- 难度映射、标签字典、`config.yaml` 时空限制、样例测试点三档（first/all/none）、`LUOGU_DELAY_MS` 限速保持旧版行为。

### 已验证通过（2026-11-15）

- 冒烟：登录、后台页、config / jobs / tags / status / estimate 接口、`/p` 列表、评测机 Online。
- 多语言：CF1A 落库后 `problem.statement` 有 `zh.md`(472 字符) / `en.md`(840)，默认中文、`?lang=zh` 中文、`?lang=en` 英文，页面出现语言切换入口。
- 断点：P 库小样 8 题（7 成功 1 跳过）、30 题（22 成功 8 跳过）；已存在题跳过且不请求题面。
- 状态机：`pause → resume → cancel → resume` 从断点继续并跑完（8/8）；暂停逐题生效（t+2s 与 t+5s 的 done 均为 3）。
- 重启恢复：日志 `recovered 1 interrupted jobs` / `auto-resumed 1 interrupted import jobs`，任务从断点继续到 done。
- 加密：假凭据写入后 Mongo 只有 `enc/iv/tag`、无明文；密钥文件 600；日志无 cookie 值；清除生效。
- **登录已验证（2026-11-16）**：真实凭据测试登录返回 `{"ok":true,"uname":"MarkZhang0520","uid":"2270787","clientIdLength":48}`；`/manage/luogu/config` 只回显 `configured/uid/clientIdLength`。全量真跑仍未启动（仅 1 题小样）。
- 旧版结论仍有效：导入后 `cc.cc14o2` 提交 **AC 100**（本地样例测试点）。

### 远端提交（2026-11-15 新增，用户要求「先做提交」）

- **入口**：洛谷题的题目页侧栏自动出现「提交到 Luogu」（与原生 Submit 并列），题面末尾也有链接。识别 = 导入时写 `luogu.problems` 标记，旧题用 pid 前缀兜底。
- **UI**：`/luogu/submit/{pid}` 复用原生 `problem_submit.html` 的结构（代码框、语言下拉、上传文件、按钮），语言列表来自 `SettingModel.langs`，只启用 C++ 系列；O2 由语言 id 表达，无额外开关。权限是 `PRIV.PRIV_USER_PROFILE`（登录用户），不是 `PRIV_EDIT_SYSTEM`。
- **协议**：`GET /ranking` 取 `<meta name="csrf-token">` → `POST /fe/api/problem/submit/{pid}`，body `{code, lang, enableO2, captcha?}`，头 `X-CSRF-Token` / `X-Requested-With` / `Origin` / `Referer` + 登录 cookie；从 302 Location 或 JSON 任意层级 `rid` 取评测号。
- **验证码**：只要没拿到 rid 且响应里出现「验证码 / captcha」关键词就判定（**不限 HTTP 403**，洛谷也可能 4xx 带 HTML 或 2xx 只在 `errorMessage` 里提示）→ 后端返回 `needCaptcha / image / imageError` → `GET /api/verify/captcha`（**会 302，必须跟随**，实测返回 `image/jpeg`）→ 弹图人工输入后带原代码重提，前端最多 3 次；`GET /luogu/captcha` 可刷新。图片取不到时弹窗照样显示，并给「换一张 / 去洛谷手动提交」兜底，不再静默吞成空图。
- **结果**：`GET /record/{rid}?_contentOnly=1` → `data.record`，`formatRecord()` 整理状态 / 分数 / 时空 / `detail.judgeResult.subtasks[].testCases[]` 逐测试点 / 编译错误；前端每 1.5s 轮询到终态（除 0 / 1 外）。**不写 Hydro record**，只在插件自有页面展示。
- **语言映射**：Hydro `cc.cc14o2` ↔ 洛谷 `lang=11, enableO2=true`；C++98/11/14/17/20/23 = 3/4/11/12/27/34；不支持的语言明确报错。
- **已验证**（不真发提交）：提交页 200、侧栏入口、题面链接、来源标记、验证码图片、空代码/不支持语言/不存在题目/非法 rid 的错误路径、表单 UI。
- **待用户验收**：真实提交、验证码重提、逐测试点结果解析。用户已配置真实登录态并明确「提交靠我测试」。

### 账号体系与在线编程入口（2026-11-15 18:40 追加）

- **两套账号完全隔离**：`luogu.config`（全站）= 拉取题目账号，只有管理员在 `/manage/luogu` 后台维护；`luogu.accounts`（`_id` = Hydro uid）= 每位用户自己的提交账号，在导航「第三方账号」页绑定。用户登录 / 清除 / 校验**不会**修改拉题账号。
- **导航**：`ctx.injectUI('Nav', 'luogu_account', { prefix:'luogu', before:'record_main' }, PRIV.PRIV_USER_PROFILE)`，与首页 / 题库 / 训练 / 比赛同级；中文名走插件 `locales/zh.yaml` 的 `luogu_account` 键（Nav 模板用 `_(item.name)`，`displayName` 不生效）。
- **第三方账号页** `/luogu/account`：绑定 / 清除 / 测试登录；`GET /luogu/account/profile` 自动用已存凭据校验洛谷并缓存 `data.user`（用户名、头像、主页、排名、通过 / 提交数），再次打开页面自动展示。`__client_id` 仍加密存库。
- **迁移与回退**：启动时把现有全站配置单向复制为 JWZCY(uid 2) 的提交账号初值，`meta:migrated-global` 保证只迁一次；未绑定用户提交时按约定回退共享账号，并在页面 / 提交页明确标注。
- **提交按用户隔离**：`resolveSubmitCredentials(uid)` → 自己的账号优先、共享账号回退；`submitCode` / `fetchLuoguRecord` / `fetchCaptchaImage` / `fetchCsrfToken` 都接收**本次请求的 cookie**，不再用进程级全局 `authCookie`（全局只服务拉题），避免多用户并发串号。
- **在线编程（scratchpad）**：插件 `templates/partials/luogu_scratchpad.html` 在洛谷题的 `.scratchpad__toolbar__submit`（递交评测）后插入同款 ToolbarButton「提交到 Luogu」；代码取 `window.editor.getValue()`（编辑器组件挂到全局），语言取工具栏 `select.select`，题目取 `UiContext.pdoc.pid`，POST `/luogu/submit/{pid}`；结果在**居中模态 + 遮罩**里轮询展示状态 / 分数 / 时空 / 逐测试点，验证码也在模态内弹图重提。**不写 Hydro record**。面板绝不能套 Hydro 的 `.section` 类，原因见第 8 节。
- **已验证**（未真发提交）：Nav 入口与链接、账号页自动展示真实洛谷资料（MarkZhang0520 / 头像 / 主页）、提交页显示 own 账号、全站拉题账号 `updatedAt` 未变、迁移记录、scratchpad 脚本注入、全部校验路径与基础冒烟。
- **19:02 修复（用户反馈「在线编程内点提交没反应」）**：日志显示请求其实发出并成功（3 次 P1001 → rid 310167279 / 293 / 299，`/luogu/record/{rid}` 均返回 **AC 100**、逐测试点 1 组），是旧版右下角浮层不够明显且连点无防重；已改为居中模态 + 遮罩、按钮即时状态与禁用、工具栏 inline 状态。同期修复评测机 Waiting（judge 断连，重启后重连）。
- **2026-11-15 20:50 已修**：用户实测「显示需输入但只屏幕变灰、不弹窗」，根因是 Hydro 全局 CSS `.hasjs .section{opacity:0}` 把动态创建的面板变全透明（遮罩正常显示）。面板改为不使用 `.section` 类、纯 inline 样式并显式 `opacity:1 / visibility:visible / display:block`；用 headless Chrome 加载真实 `theme-4.59.1.css` 对照验证：修复前 `opacity=0 / visible=false`，修复后 `opacity=1 / visible=true` 且验证码图与输入区可见。另暴露 `window.__luoguShowCaptcha()` 自查入口：只拉一张验证码图显示弹窗，不发提交，浏览器控制台随时可验。
- **待用户验收**：再点一次在线编程按钮确认新面板可见；验证码重提、逐点结果的完整交互；多用户各自绑定的隔离请用第二个 Hydro 账号实测（本次未创建测试账号以免污染用户库）。

## 5. 参考实现：refs/ClionLuogu（只读，不要改）

用户的 CLion 洛谷插件，已 clone 到 `refs/ClionLuogu`（`gh repo clone JiangWanZhengChouYv/ClionLuogu`，depth 1）。**只作参考，不要构建、不要改、不要提交进本仓库**。

关键文件：

| 文件 | 内容 |
| --- | --- |
| `src/main/kotlin/com/user/clionluogu/api/LuoguHttpClient.kt` | 浏览器伪装头、CookieJar（处理 C3VK）、cookie 注入 |
| `src/main/kotlin/com/user/clionluogu/api/LuoguApiService.kt` | 拉题、搜索、登录校验、提交、验证码、评测轮询（核心） |
| `src/main/kotlin/com/user/clionluogu/api/dto.kt` | 题面 / 评测记录 DTO |
| `src/main/kotlin/com/user/clionluogu/service/JudgePollingService.kt` | 评测轮询 |
| `src/main/kotlin/com/user/clionluogu/ui/LoginPanel.kt` | 登录页（`__client_id` + `_uid`） |
| `src/main/kotlin/com/user/clionluogu/action/SubmitCodeAction.kt` | 提交流程 |

从参考实现提取到的可用事实（做登录/远端评测时直接用，不用重新猜）：

- **登录**：浏览器 Cookie 里的 `_uid`（数字）与 `__client_id`（UUID）；请求头 `Cookie: _uid=<uid>; __client_id=<clientId>`。校验：`GET https://www.luogu.com.cn/user/{uid}?_contentOnly=1`（带 cookie）能取到用户名即登录有效。诊断文案只报 uid 与 client_id 长度，**绝不输出 cookie 值**。
- **拉题**：`GET /problem/{pid}`，解析 `lentille-context` / `type="application/json"` 块，与现插件一致。
- **题目列表/搜索**：`GET /problem/list?type=<P|B|CF|SP|AT|UVA...>&page=<n>&keyword=<kw>&_contentOnly=1`。注意：**即使带 `_contentOnly=1` 也返回 HTML**，数据在 JSON 脚本块里；`type` 是来源过滤，CF/SP/AT/UVA 是独立来源库。
- **提交**：`POST https://www.luogu.com.cn/fe/api/problem/submit/{pid}`，JSON body `{code, lang, enableO2, captcha?}`，头：`X-CSRF-Token`（从 `GET /ranking` 页面 `<meta name="csrf-token">` 取）、`X-Requested-With: XMLHttpRequest`、`Origin/Referer`、`Content-Type: application/json` + 登录 cookie。
- **验证码**：403 且 message 含「验证码错误」→ `GET /api/verify/captcha` 得 PNG，人工输入后带 `captcha` 重提，最多重试 3 次。
- **评测轮询**：`GET /record/{rid}?_contentOnly=1` → `data.record` 的 `status / time / memory / subtasks / testCases / compileError`；`testCases` 逐点给状态，`subtasks` 给子任务得分。
- **语言 id**：C++98=3、C++11=4、C++14=11、C++17=12、C++20=27、C++23=34；O2 用同一个 id + `enableO2: true`。

## 6. 目标计划与完成情况（按用户新要求，2026-11-15 修订）

**当前进度**：A / B 已实现并通过小样验证（详见第 4 节）；C 保持现状；D 明确不做。以下保留原始目标与验收标准，供回归与后续扩展参考。

### 阶段 A（P0，✅ 已实现）：洛谷登录

目标：插件持有并校验洛谷登录态，后续"拉全题目"依赖它。

1. 后台页面加「洛谷账号」配置区：`_uid` + `__client_id`，保存到 Mongo（系统设置或插件自有 collection），**不要**写到仓库文件或日志。
2. 提供「测试登录」按钮：`GET /user/{uid}?_contentOnly=1` 校验并显示用户名；失败给出可读诊断（缺 `_uid` / 缺 `__client_id` / cookie 失效）。
3. 抓取请求默认带登录 cookie；保留匿名 fallback（未配置时仍可抓公开题，但全量模式要求登录）。
4. 显示需脱敏：`_uid=12345`、`__client_id=已配置(36 位)`，不回显原值。

验收：配置后后台能显示"已登录：<用户名>"；配置错误时提示明确；重启 backend 后配置仍在。

### 阶段 B（P0，✅ 已实现）：拉全题目

目标：登录后能把洛谷题库**全量**拉进 Hydro（题面 + 样例 + 难度 + 标签 + 时空限制）。

1. 「全量拉取」模式：按来源（`P`、`B`、`CF`、`SP`、`AT`、`UVA`…可配置）逐页遍历 `/problem/list?type=T&page=N` 直到 `result` 为空或达到 `count`。
2. **可恢复**：每页完成后把进度（来源、页码、已处理 pid 数）落 Mongo；中断后从断点继续；已存在的 pid 默认跳过（不重复请求题面）。
3. **限速与预算**：沿用 `LUOGU_DELAY_MS`（全量建议 ≥1500ms）；单次任务设题目上限（可配置，默认比如 5000），并显示预计耗时。
4. **磁盘估算**：默认只生成样例测试点（1 点/题），导入前给出"约 N 题、约 X MB"的估算；`samples=none` 可只导题面。
5. 任务模型从"内存 Map"升级为**可持久化任务**（Mongo collection），支持暂停/继续/取消，页面显示进度条与成功/跳过/失败统计。
6. 全量任务放在后台串行执行，不能阻塞 Web 请求；崩溃/重启后能接着跑。

验收：选 `P` 全量跑 1~2 页能完整落库；中断后继续不重复、不丢；页面能看到断点与统计；`/p` 列表能看到导入的题。

> **开放问题已确认（2026-11-15，用户答复）**：① 全量范围 = 全部来源 `P/B/CF/SP/AT/UVA`（可配置）；② 多语言按 Hydro 官方 statement 机制导入全部翻译题面，不合并、不拆题；③ 登录态在后台页面配置并加密；④ 允许长时间 / 无人值守跑，不设时间窗，题数上限可设 0（不限），仍保留 1500ms 限速；⑤ 本次只实现 + 小样验证，**未启动真·全量任务**，等用户明确说开跑。

### 阶段 C（✅ 保持现状）：本地评测只到样例

- 本地测试点继续只用题面样例生成（第一组 / 全部 / 不生成三档）。
- 明确写进 UI：洛谷官方测试数据不公开，本地判题只能验证样例，不等价于洛谷 AC。

### 阶段 D（✅ 已实现）：远端提交 + 提交即本地评测 + 反算样例

> 2026-11-16 完成。用户要求：结果进原生评测记录面板、提交时自动本地评测一次、用 AC 标程反算样例、清迁移与私人内容以便分发。

1. **提交链路**：`/luogu/submit/{pid}` 与在线编程并列按钮都走同一后端；POST 成功返回 `{rid, localRid}`，前端轮询 `/luogu/record/{rid}` 拿洛谷结果与本地结果。
2. **结果呈现**：在线编程里不再弹居中模态——结果按 Hydro 原生 `.scratchpad__records__table tbody` 的 `<tr>` 结构插入（复用 `record-status--border/icon/text pass|fail|pending` 与 `col--memory/time/at`），洛谷行与 `LOCAL` 行并列；React 重渲染后由 MutationObserver 自动补回。点行才弹详情；只有验证码才弹窗。
3. **提交即本地评测**：`RecordModel.add(domainId, docId, uid, lang, code, true, {type:'judge'})`，用题目现有测试点跑一遍；rid 存 `luogu.submissions`。
4. **反算样例（`src/oracle.ts`，2026-11-16 重做为「按题面数据范围造极限数据」）**：
   洛谷 AC 后把该份代码存为 `luogu.oracle`（按 `domainId/docId`，hash 幂等），并触发 Hydro 自带 generate 判题器重算测试点。
   - **规模来源**：从题面「提示 / 数据范围」解析 `n/N` 上界与值域上界（支持 `10^4`、`5*10^3`、`10^9`、`n,m<=20` 等写法），目标规模直接取题面上界；解析不到才按样例行数估一个默认值（≤20 万）。
   - **结构识别**：从官方样例识别 `单个 n` / `行内数组` / `n 行` / `n 行 + 尾行` / `n m 行` / `n m 行 + 尾行` / `n` 后跟 `m` 再一行 `m` 个数 / 坐标题；识别不了的退化为「只随机值、不改规模」，保证不造非法数据。
   - **方格题按 n² 填满**：`首行单个 n + 3 列坐标行 + 全 0 哨兵`（如 P1004 方格取数）识别为 dense grid，极限数据生成 `n×n` 个格子（P1004 为 81 行）而不是只重复样例那 8 行。
   - **10 组 profile**：第 1 组最小边界，2–6 随机，7 升序，8 降序，9 全值域最大；下标类列夹在 `[1, targetN]`，全 0 终止行原样保留。
   - **时限**：generate 用题面限制的 **90%**（`ratio` 可调），不再用「一半」；标程在真实上界跑不过的组由 judge 丢弃，**成功 ≥6 组即 done**（边界组不合法不会毁掉整批）。
   - **自动升降档**：数据成功但标程耗时 < 25% 且规模还没到题面上界 → 升 4 倍再跑一次；一组都没成功 → 降到 1/10 重试一次。升档硬上限是解析出的 `n` 上界，超过题面约束的规模一律不生成；**只有样例结构可放大（`seedLooksScalable`：单个数 / 行内数组 / n 行 / n m 行 / n 后跟 m 个数 / 坐标题）才升档**，A+B 这种一行两个数的题不会为了碰时限白跑两轮。
   - **统计**：`luogu.samplefix` 落 `targetN / pairs / maxStdTime / worst / attempt / parsedN`，`GET /manage/luogu/oracle/:pid` 返回（会先收尾再重查，前端能看到真实 stats）。
   同一 hash + 同一目标规模只重算一次，保证样例稳定。
5. **管理入口**：`/manage/luogu/oracle/:pid` GET 看标程 hash 与修复记录（不回显源码），POST `{force:true}` 手动触发重算。
6. **仍不做**：不写 Hydro record 的洛谷分数回写（不伪装判题回调）；不抓题解代码当标程（版权）。

> 验证时造的测试标程与生成样例已全部清除，P1001 样例恢复为官方 `2 2 / 4`；`meta:migrated-global` 历史标记已删除。源码无私人用户名 / uid / 真实 rid / 迁移函数。

## 7. 冒烟测试（改完必跑）

```bash
cd /tmp && rm -f lg.txt
curl -sS -c lg.txt -o /dev/null http://127.0.0.1:8889/login
curl -sS -b lg.txt -c lg.txt -X POST http://127.0.0.1:8889/login \
  --data-urlencode 'uname=JWZCY' --data-urlencode 'password=Hydro123' -o /dev/null -w '%{http_code}\n'

curl -sS -b lg.txt -o /dev/null -w 'page=%{http_code}\n' http://127.0.0.1:8889/manage/luogu
curl -sS -b lg.txt -H 'Accept: application/json' http://127.0.0.1:8889/manage/luogu/tags | head -c 200

# 导入（CSRF：必须带 Referer）
curl -sS -b lg.txt -X POST http://127.0.0.1:8889/manage/luogu/import \
  -H 'Content-Type: application/json' -H 'Accept: application/json' \
  -H 'Referer: http://127.0.0.1:8889/manage/luogu' \
  --data '{"pids":"P1001","samples":"first"}'
curl -sS -b lg.txt -H 'Accept: application/json' \
  "http://127.0.0.1:8889/manage/luogu/status?jobId=<jobId>"

curl -sS http://127.0.0.1:8889/status | grep -o Online | head -2
```

### A/B 追加冒烟（2026-11-15 已跑通）

```bash
# 登录态：保存（用假值即可验证加密/脱敏）→ 查看 → 测试 → 清除
curl -sS -b lg.txt -X POST http://127.0.0.1:8889/manage/luogu/config \
  -H 'Content-Type: application/json' -H 'Referer: http://127.0.0.1:8889/manage/luogu' \
  --data '{"uid":"12345","clientId":"00000000-0000-0000-0000-000000000000"}'
curl -sS -b lg.txt -H 'Accept: application/json' http://127.0.0.1:8889/manage/luogu/config
curl -sS -b lg.txt -X POST http://127.0.0.1:8889/manage/luogu/test-login \
  -H 'Content-Type: application/json' -H 'Referer: http://127.0.0.1:8889/manage/luogu' --data '{}'
curl -sS -b lg.txt -X POST http://127.0.0.1:8889/manage/luogu/config \
  -H 'Content-Type: application/json' -H 'Referer: http://127.0.0.1:8889/manage/luogu' --data '{"action":"clear"}'

# 多语言：导入 CF1A 后查 statement，并验证 ?lang= 切换
docker exec dev-oj-mongo mongo --quiet hydro --eval \
  'var p=db.document.findOne({pid:"CF1A"}); db["problem.statement"].find({domainId:p.domainId,docId:p.docId}).forEach(function(x){print(x.name,x.lang)})'
curl -sS -b lg.txt 'http://127.0.0.1:8889/p/CF1A?lang=en' | grep -o 'flagstones' | head -1

# 估算 / 全量小样 / 状态机（allowAnonymous 仅用于没有登录态时的小样验证）
curl -sS -b lg.txt -H 'Accept: application/json' 'http://127.0.0.1:8889/manage/luogu/estimate?sources=P,B,CF,SP,AT,UVA&samples=first&delay=1500'
curl -sS -b lg.txt -X POST http://127.0.0.1:8889/manage/luogu/import \
  -H 'Content-Type: application/json' -H 'Referer: http://127.0.0.1:8889/manage/luogu' \
  --data '{"mode":"full","sources":["P"],"maxPages":1,"maxProblems":8,"delayMs":600,"samples":"none","allowAnonymous":true}'
curl -sS -b lg.txt -X POST http://127.0.0.1:8889/manage/luogu/job-action \
  -H 'Content-Type: application/json' -H 'Referer: http://127.0.0.1:8889/manage/luogu' \
  --data '{"jobId":"<jobId>","action":"pause"}'   # resume / cancel 同理
docker compose restart oj-backend   # 日志应出现 auto-resumed，任务从断点续跑；judge 由 healthcheck 自动重连
```

配置真实 cookie 后的验收：后台显示「已登录：<用户名>」、重启 backend 后配置仍在。

### 远端提交冒烟（不向洛谷发真实提交）

```bash
# 提交页 / 题目页入口
curl -sS -b lg.txt -o /dev/null -w 'submit=%{http_code}\n' http://127.0.0.1:8889/luogu/submit/CF1A
curl -sS -b lg.txt http://127.0.0.1:8889/p/CF1A | grep -o '提交到 Luogu' | sort | uniq -c

# 只走校验路径（不会触达洛谷）
curl -sS -b lg.txt -X POST http://127.0.0.1:8889/luogu/submit/CF1A \
  -H 'Content-Type: application/json' -H 'Referer: http://127.0.0.1:8889/luogu/submit/CF1A' \
  --data '{"code":"","lang":"cc.cc14o2"}'                       # 期望「代码不能为空」
curl -sS -b lg.txt -X POST http://127.0.0.1:8889/luogu/submit/CF1A \
  -H 'Content-Type: application/json' -H 'Referer: http://127.0.0.1:8889/luogu/submit/CF1A' \
  --data '{"code":"int main(){}","lang":"py"}'                   # 期望「洛谷暂不支持语言 py」
curl -sS -b lg.txt -H 'Accept: application/json' http://127.0.0.1:8889/luogu/record/abc   # 期望「评测记录号格式不正确」

# 验证码图片（只读 GET，会 302，插件已跟随）
curl -sS -b lg.txt -H 'Accept: application/json' http://127.0.0.1:8889/luogu/captcha | head -c 60

# 来源标记（导入新题后）
docker exec dev-oj-mongo mongo --quiet hydro --eval 'db["luogu.problems"].find().forEach(printjson)'
```

真实提交由用户在页面上操作，**Agent 不要代为向洛谷发提交**。

### 账号体系 / 在线编程冒烟（不真发提交）

```bash
# 导航同级入口
curl -sS -b lg.txt http://127.0.0.1:8889/ | grep -o '第三方账号\|href="/luogu/account"'

# 第三方账号页与自动资料展示
curl -sS -b lg.txt -o /dev/null -w 'account=%{http_code}\n' http://127.0.0.1:8889/luogu/account
curl -sS -b lg.txt -H 'Accept: application/json' http://127.0.0.1:8889/luogu/account/profile | head -c 300

# 两套账号隔离
docker exec dev-oj-mongo mongo --quiet hydro --eval \
  'printjson(db["luogu.accounts"].findOne({_id:"2"})); print(db["luogu.config"].findOne({_id:"credentials"}).uid)'
curl -sS -b lg.txt -H 'Accept: application/json' http://127.0.0.1:8889/manage/luogu/config

# 在线编程按钮注入标记
curl -sS -b lg.txt http://127.0.0.1:8889/p/CF1B | grep -o 'luogu-scratchpad-submit\|lg-sp-panel' | sort | uniq -c
```

## 8. 环境坑位（踩过的）

- `hydrooj cli user create` 必须 4 个参数：`mail uname password uid`；少传会静默失败。
- 手工调接口必须带 `Referer`（Hydro CSRF 校验 referer host）。
- `docker build` 曾因沙箱写 `~/.docker/buildx` 失败；当前会话已放开。
- backend 镜像烘死了 `entrypoint.sh`，改它必须 rebuild；改 `addons/` 只需 restart。
- judge 镜像 7GB+ 别重建；运行时配置是镜像内 `/root/.hydro/judge.yaml`（密码 `Hydro7890`）。
- 洛谷 `/problem/list` 带 `_contentOnly=1` 仍返回 HTML；别指望它是 JSON API。
- 洛谷 `_contentOnly=1` 未登录时会被 302 回 HTML 或直接 302 自跳；匿名抓取必须走 cookie jar。
- 不要把 `data/`、`public/`、`refs/` 提交进仓库；`data/backend/luogu.key` 是加密密钥，权限 600，`data/` 被删后必须重新配置登录态。
- Hydro 5.1 多语言题面：`content` 传 JSON 字符串（对象 `{lang: md}` 或数组 `[{name,lang,content}]`），内部 `normalizeStatements` 写 `problem.statement`；locale key 是 `zh / en / ko / zh_TW`，`document.content` 为空是正常的。
- Hydro `Types.ProblemId = /^(?:[a-z0-9]{1,10}-)?[a-z0-9]+$/i`：题号不许有下划线；AT 库 `AT1202Contest_a` 必须映射，且 `normalizePid` 不能整体大写（洛谷题号大小写敏感）。
- 插件里取 Mongo collection 用 `ctx.db.db.collection(name)`；`hydrooj` 导出的 `db` 是 deprecated proxy。
- 任务恢复挂 `ctx.on('app/started')`，并用 `NODE_APP_INSTANCE === '0'` 限制只在 master 执行，避免 CLI 进程抢任务。
- `ValidationError` 的 JSON 响应把具体中文原因放在 `error.params`，外层 `message` 只是模板；前端要读 `params`。
- 全量估算会对每个来源请求一次列表首页（6 个来源约 10 秒），启动全量时也会估算一次，别误以为卡死。
- **同一路径的 GET / POST 必须共用一个 Handler 类**（`ctx.Route` 注册一次，类里同时写 `get()` / `post()`）；注册两次会互相覆盖。
- **题目页注入数据用 `h.UiContext`，不要用 `h.response.body`**：framework 在 handler 执行时会重建 `response.body`，`UiContext` 才是贯穿渲染的同一对象；插件 ctx 带 isolate，`ctx.on('handler/create', cb)` 要传第三参 `{ global: true }` 才收得到事件。
- 覆盖 ui-default 模板：把同名文件放到插件 `templates/partials/` 下即可（后加载覆盖前者，日志 `Template init` 顺序可查）；改模板必须 `docker compose restart oj-backend`。
- 该版本 Nunjucks 模板里对 `{% set %}` 出来的值调用 `startsWith` 会失败（`Unable to call ...["startswith"]`），且 `|upper` 会产生 SafeString；复杂判断放后端做，模板只用布尔值。
- 洛谷 `/api/verify/captcha` 会先 302 再返回 **JPEG**（不是 PNG），必须跟随跳转并按 `content-type` 生成 data URL。
- `__client_id` 不一定是 36 位（用户实测 48 位），文案与校验只限制长度区间，不要写死位数。
- 洛谷题号在 Hydro 里可能被 `toHydroPid()` 映射（AT 库），提交到洛谷前必须用 `getSourcePid()` 换回原始题号。
- **Nav 注入**：`nav_item` 用 `url(item.name, item.args)` 生成链接，`item.name` 必须是一个已注册的路由名；显示文本是 `_(item.displayName or item.name)`，但 `injectUI` 只存 `name/args`，所以要靠插件 `locales/*.yaml` 提供翻译键；`args.before` 可控制导航顺序。
- **多用户 cookie 不能共用进程级全局**：`client.ts` 的 `authCookie` 只服务全站拉题；提交 / 记录 / 验证码必须把当前用户的 cookie 作为 `opts.cookie` 逐次传入（`cookieHeader(extra)` 会覆盖 `_uid` / `__client_id` 但保留 C3VK）。
- 洛谷 `/user/{uid}?_contentOnly=1` 会先 302（C3VK 自跳）再返回 200，`fetchText` 已跟随；`data.user` 含 `name/avatar/uid/ranking/passedProblemCount/submittedProblemCount`。头像在 `cdn.luogu.com.cn`，主页拼 `/user/{uid}`。
- **scratchpad**：编辑器组件把 `window.editor` / `window.monaco` 挂到全局，工具栏提交按钮是 `.scratchpad__toolbar__submit`，语言在 `.scratchpad__toolbar select.select`；按钮要等 React 渲染后用 MutationObserver 插入，且不能改 `UiContext.postSubmitUrl`（那是原生递交评测）。
- 插件模板里给前端塞 JSON 用服务端 `JSON.stringify(...).replace(/</g,'\\u003c')` + `| safe`，别依赖 Nunjucks 的 `dump` 过滤器（该版本不可用）。
- **backend 重启后 judge daemon 可能永久断连**（表现为评测机 `Waiting`、本地提交卡 `status=0`）：judge 配置是服务名 `http://oj-backend:8888/`，但断连后不一定自己重连回来。现已加 healthcheck 兜底，见下条；手动 `docker compose restart oj-judge` 仍是即时修复手段。
- **`oj-judge` healthcheck（2026-11-15 19:07 加）**：`scripts/judge-healthcheck.js` 只读挂进容器，判据是「backend `/status` 可达 + `/proc/net/tcp{,6}` 里存在到 8888 的 ESTABLISHED(01) 长连接」。`/status` 的 `stats[type=judge].updateAt` **只在连接建立时上报一次，不是心跳**，不能拿来判活。断连时脚本杀掉 PM2 管着的 `hydrojudge` 子进程，PM2 God Daemon 自动拉起并重新连回 backend（实测 backend 重启后约 6 秒恢复）。**容器内 PID 1 受内核保护，SIGTERM/SIGKILL 都杀不动**，所以不要试图靠 healthcheck `kill 1` 触发 `restart: always`。退出码：0 健康 / 1 backend 暂不可用（只标 unhealthy，不动作）/ 2 断连已触发重启。
- **前端反馈必须足够明显**：提交进原生评测记录表格（洛谷行 + LOCAL 行），按钮即时变「提交中…」并禁用（防重复）、工具栏 inline 提示；只有验证码 / 点行看详情才弹模态。判断「按钮没反应」时先看 backend 日志有没有 `Luogu submit ... -> rid`，有就说明请求已发出，只是 UI 反馈问题。
- **插件动态插 DOM 绝不能配 MutationObserver 自触发**：曾对 `document.body` 挂 subtree observer → 回调 `installButton()` → 插按钮/评测行 → 再次触发 observer → 无限递归，Chrome 弹「多个页面无响应」（用户 2026-11-16 实测截图）。现改为 **500ms 幂等轮询**（`installButton` + `renderRows` 只在缺行/缺按钮时改 DOM）。headless Chrome 对照验证：修复后 mutation 数稳定为 4、两行正确显示。
- **洛谷 AC 状态码是 12，Hydro 的 `STATUS_ACCEPTED` 是 1**：`/luogu/record/{rid}` 返回的是洛谷原始 status（见 `submit.ts` 的 `STATUS_TEXT`），判断 AC 必须用 12（`LUOGU_STATUS_ACCEPTED`）；拿 Hydro 常量比会永远为 false，导致标程不保存、反算不触发（2026-11-16 实测：AC 提交后 `oracle=0`，改完立刻触发）。generate 任务/本地 record 的 status 才用 Hydro 的 1。
- **本地 Format Error（status 31）是预期，不是样例有问题**：用户明确说明——普通提交评测模式下，某题没提交过洛谷、只用样例当评测数据时，本地评测就是 FE。反算理由里**绝不能**写「洛谷 AC 但本地 Format Error」（曾误导用户以为样例坏了）；现在把 FE 与 AC 都视为正常，只有其它本地失败才标注。
- **批量删题接口**：`POST /manage/luogu/cleanup`，body `{domainId, keep:"P1001,P1002"}`，走 `ProblemModel.del` 正确清 statement/testdata/状态。2026-11-16 用它把 211 题删到只剩 P1001（删 210、失败 0）；删完要手动清 `luogu.problems` 标记、`luogu.submissions` 与 `luogu.samplefix/oracle` 里指向已删题的孤儿记录（`ProblemModel.del` 不管插件自己的 collection）。**删题前必须确认没有后台任务在跑**（`luogu.job` 里 `status=running/queued/interrupted`），否则任务会从断点把题重新导回来；实测踩过一次（删到 1 题后旧任务又刷回 89 题）。
- **全量拉题的探测（2026-11-16 加）**：用户明确要求「中间肯定有空位，一定要探测」。① 分页健壮性：`fetchListRobust()` 对空壳页（`count>0 && result=[]`）重试 3 次；末页二次确认（再拉同一页，拿到更多题则补处理）；② 题号补漏：`probeProblemExists(pid)` 用 **HEAD** 请求探测，实测存在的题 200、空号（如 P1172）401，成本极低；每个来源完整跑完后（仅 `maxPages=0 && maxProblems=0 && status=done`），从 `1..最大题号` 对列表未收录的号逐个 HEAD 探测，存在的补抓，`cursor.probeIndex` 记断点可续跑，counts 增 `probed/recovered`。小样模式不触发补漏。
- **反算生成器必须真随机，不能机械 +1**：初版 `luogu_gen.cpp` 只把数字 +1，10 组全相同（P1001 `2 3→5`），P1004 矩阵输入被破坏输出 `0`——用户明确拒绝这种垃圾值。现用 `mt19937_64` 以组号（judge 传 `argv[1]=1..10`）播种，10 组按 profile 变化（最小 / 随机 / 升序 / 降序 / 全值域最大）。
- **不是所有题都该「升档」**：`seedLooksScalable(seed)` 在 TS 侧复刻生成器的结构识别，不可放大的题（A+B 一行两个数、无结构题）`scalable=false`，`finishFix` 只写日志「样例结构无法放大，不会为了碰时限造垃圾数据」，不再二次重跑。实测 P1001：1 轮完成、10 组、std 0.695ms，无升档。
- **「极限」= 按题面数据范围造最大规模，而不是把样例复制几份**：旧版 `scale` 默认 1，样例 n=3 的题就只生成 3 行，半限门限只拒绝太慢、从不往上限推。现从题面解析 `n` 上界（P1003 解析出 10000 后生成 10 组各 ~195KB 的输入，std 全部 AC），并禁止把规模升过题面上界（曾因并发 pending 把 P1003 升到 40000，超出 `n<=10^4` 造出非法数据）。
- **反算生成器的 SEED 必须在调用时替换**：模板里曾残留 `` `.replace('__SEED__', JSON.stringify(''))` ``，导致生成器里 `SEED=""`，10 组输入全是 `1`，但 record 仍显示 AC。现在 `generatorCpp()` 返回带占位符的模板，由 `regenerateSamples()` 用 `seed` 替换；**排查反算数据异常时先看落库的 `luogu_gen.cpp` 里 `SEED` 是否为空**。
- **覆盖导入必须清掉旧数字测试点**：反算会写 `1..10.in/.out`，官方样例只有 1 组时若不清，会残留 `2..10` 的空 `.out`（反算失败留下的残缺组），本地评测直接判错。`importer.ts` 现在覆盖导入时先删所有旧 `\d+.(in|out)` 与 `luogu_gen.cpp`/`luogu_std.cpp` 再写新数据。
- **O(1) 题碰不到时间上限是正常的**：P1001 标程 ~0.6ms，时限 1000ms 差上千倍；时间上限只对有规模的题有意义，别为了「碰上限」盲目放大常量数字。P1003 在 `n<=10^4` 上界下 std 只有 ~3.5ms（0.35% 时限），日志会明确写「已到题面上界，无法通过放大规模更极限」。
- **`record` 文档没有 `type` 字段**：`RecordModel.add(..., {type:'generate'})` 的 `type` 只用于投递判题任务，不落库；按 `{type:'generate'}` 查不到任何记录。要定位反算任务用 `luogu.samplefix.generateRid`。
- **generate 判题器的限制**：std 的沙箱时限用 `ctx.config.time`（插件覆写），memory 沙箱写死 256MB（覆写 memory 只影响记录，不影响沙箱），所以「内存极限」在这里打不满。
- **顶部导航删除方式**：插件覆盖 `templates/partials/nav.html`（从 ui-default 复制），在 `for item in overrideNav|default(ui.getNodes('Nav'))` 里跳过 `item.name == 'record_main' or 'record'`。实测页面里「评测记录」0 次、其它导航项正常。
- **洛谷 P1001 官方样例已改成 `20 30 → 50`**（2026-11-16 只读抓取确认），不是早先的 `2 2 → 4`；别把 20 30/50 误判成反算污染。
- **学生端只看到评测结果，不显示任何反算信息**（用户明确要求「我们是给学生看的」）：`luogu_scratchpad.html` / `luogu_submit.html` 不渲染 sampleFix / sampleFixes / samplePreview；学生接口 `/luogu/record/{rid}` 不返回这些字段。样例内容只在管理员接口 `/manage/luogu/oracle/:pid` 的 `preview` 里。
- **只有 AC 才自动弹评测记录弹窗**：其它终态（WA/TLE/RE…）只出右下角气泡、不弹窗（用户「AC 了就弹」）。headless Chrome 验证：AC → `modalDisplay=block`，WA → `modalDisplay=none`。
- **结构化输入要靠形状规则，不能只靠随机**：P1004（方格取数）早期随机化坐标/权值会让标程 SEGFAULT（`ExitCode: 11`），10 组只有 4~5 组 AC。现在加了 dense grid 规则（`首行 n + 3 列坐标行 + 全 0 哨兵` → 生成 n² 个格子），P1004 实测 10 组全 AC、每组 82 行（81 格 + 哨兵）。其它结构化题型（树/图/矩阵）若仍失败，需要在生成器里补对应形状，而不是加大随机范围。
- **反算 seed 三个致命坑（2026-11-16 全踩过）**：① `RecordModel.add(...,{type:'generate', input})` 的 input **不会存进 record**（只有 pretest 分支存），judge 的 generator stdin 为空 → 必须把 seed 内嵌成生成器源码里的 C++ 字符串常量 `SEED`，stdin 空时用它；② seed **绝不能从 1.in 读**——generate 成功组会覆盖 1.in，反算一次后就以垃圾为 seed 无限迭代，必须从 `problem.statement` 的题面 Markdown 解析「样例输入 #1」；③ `StorageService` 是跨进程 proxy，backend 里 `get()` 的流 for-await 读不到内容，要从 `pdoc.data[].etag`（真实路径 base64）解码直接读文件。
- **judge 上传 403（`PostFile Fail ... Forbidden`）会让整个 generate 记录变 System Error(status 8)、`pairs=0`**：这是评测机会话失效，不是生成器的锅。先看 `docker logs dev-oj-judge` 有没有 `PostFile Fail ... 403`；`docker compose restart oj-judge` 后立刻恢复正常（P1004 实测：重启前 pairs=1/failed，重启后 10 组全 AC）。
- **失败反算必须回滚残缺测试点**：generate 只给 std 成功的组写 `.out`，失败的组留下「有 .in 没 .out」，会导致评测 FE。`finishFix(rid, 'failed')` 会扫题目 data，删掉所有缺 `.out` 的孤儿 `.in`（实测清掉 3.in/6.in/7.in，剩 7 组全成对）。但 finishFix 只在记录轮询或管理员 GET 时调用——触发反算后要调一次 `/manage/luogu/oracle/:pid` 收尾。
- **生成器安全约束**：全 0 行是终止标记（如 P1004 `0 0 0`），必须原样保留不能随机；首行是单个规模数 n 时，每行前两个位置常是坐标，限制在 `1..n`，否则标程数组越界 SEGFAULT。这些只能降低失败率，结构化题仍需专属生成器。
- **原生评测记录面板默认收起**：在线编程的 Records 面板由工具栏 `data-global-hotkey="alt+r"` 按钮切换。提交成功后插件会 `click()` 它展开、滚动并高亮注入的行；终态还会弹出详情模态（用户 2026-11-16 要求「要弹出评测记录」）。
- **右上角状态用气泡 toast，不要长串文字**：用户明确说工具栏里 `#rid 状态 / 本地 AC / 已触发…` 一长串不好看，要像 "You have a new message" 的气泡。现用右下角 fixed toast（`#lg-sp-toast`，5s 自动消失、可点击查看），文案优先用后端 `statusText`（洛谷 AC 是中文「通过 (AC)」，别用前端 Hydro 状态表映射数字 12）。
- **样例内容预览从 etag 解码路径读**：Hydro 本地 storage 的 `pdoc.data[].etag` 就是真实文件路径的 base64。`StorageService` 是跨进程 proxy，在 backend 里 `get()` 拿不到流/临时文件；直接 `Buffer.from(etag,'base64').toString()` 得到路径再 `readFileSync` 才可靠。反算后前 4 个测试点内容随 `/luogu/record/{rid}` 返回 `samplePreview`，在详情弹窗里展示。
- **Hydro `generate` 判题器的 testdata 文件名不能以 `__` 开头**：以 `__luogu_gen.cpp` 命名时 judge 的 `/judge/files` 下载会被过滤，文件进不了缓存，编译报 `no such file or directory`（status=7）。改用 `luogu_gen.cpp` / `luogu_std.cpp` 后正常。
- **`addTestdata` 后 judge 缓存不一定同步**：反算写回新文件后，若 judge 缓存目录（`/root/.cache/hydro/judge/<host>/<domain>/<pid>/`）etags 有记录但实体文件缺失，需要删掉该目录让 judge 重新拉；验证完要清掉这些测试文件并恢复原题样例。
- **`RecordModel.get(domainId, ridString)` 拿不到记录**：它内部用字符串 rid 去匹配 ObjectId 会失败；要么传 `new ObjectId(rid)`，要么直接用 `RecordModel.coll.findOne({_id: new ObjectId(rid)})`。
- **动态创建的浮层绝不能用 `class="section"`**：ui-default 的 `theme-*.css` 里有 `@media (min-width:600px){ .hasjs .section{opacity:0} .hasjs .section.visible{opacity:1} }`，`.visible` 只在页面初始化时由 Hydro 脚本加给已有 `.section`。后插入的 `.section` 永远拿不到 `.visible`，于是**遮罩变灰、面板全透明**，看起来就是「不弹窗」。改用自定义类 + inline `opacity:1;visibility:visible;display:block`。用 headless Chrome 复现必须给 `<html class="hasjs">` 并加载真实 CSS，否则测不出 `opacity:0`。
- **验证码判定不要只认 403**：洛谷要求图形码时可能是 4xx 带 HTML、或 2xx 只回 `{"errorMessage":"验证码错误"}`；用「没拿到 rid + 正文含验证码关键词」判定。`errorMessageOf()` 要递归找嵌套字段，别只读顶层 `errorMessage`。

## 9. 协作约定

- 先读第 5 节参考实现再写登录/提交代码；请求头、cookie、CSRF、语言 id 都照它来，不要另起一套。
- 面向用户文案用中文。
- 每次改动跑第 7 节冒烟测试；动到判题就提交一次验证 AC。
- 登录 cookie 属于敏感数据：只存库、不落日志、不回显、不进 git。
- 全量拉取要克制：限速、断点、上限、可取消，缺一不可。
- **多 AGENTS 协作**：`AGENTS.md` 是唯一的活文档；开工前记下它的哈希与 mtime，变了必须重读全文再动手；同一文件永远只有一个写者。`collaboration.md` 保留为空占位，不再写入内容。
- 未配置真实登录态时全量模式默认拒绝启动；小样验证可显式勾选「允许匿名抓取公开题」降级。
- 真·全量任务（约 45919 题 / 19.5 小时 / 359 MB）**未经用户明确要求不得启动**；本次只跑了 1~2 页小样。
- **真实洛谷提交由用户自己操作**，Agent 只验证不触达洛谷的校验路径；结果解析与验证码重提待用户实测后回填结论。
- 覆盖 `templates/partials/problem_sidebar_normal.html` 的插件文件是从 ui-default v5.1.0 复制并追加一条菜单项，末尾还 include 了 `partials/luogu_scratchpad.html`；升级 ui-default 时必须同步比对，否则会丢原生菜单或 IDE 按钮。
- **拉题账号是管理员专属**：只有 `PRIV_EDIT_SYSTEM` 能在 `/manage/luogu` 维护它；任何用户的第三方账号绑定 / 清除 / 校验都不得写 `luogu.config`。未绑定用户按约定回退共享账号时，UI 必须明确标注。
- 多用户隔离请用第二个 Hydro 账号实测；Agent 不要为了验证而新建 / 删除用户，也不要代为向洛谷发真实提交。

## 10. 发布 1.0.0（2026-11-16）

**产物**：`dist/luogu-import-1.0.0.tar.gz`（68 KB，`dist/` 已 gitignore，可随时重建）

```bash
tar -czf dist/luogu-import-1.0.0.tar.gz -C addons luogu-import
```

**安装到别的 Hydro**：解压到目标实例 addons 目录 → `addon.json` 加 `"/root/.hydro/addons/luogu-import"` → `docker compose restart oj-backend` → 管理员进 `/manage/luogu` 配 `_uid` / `__client_id`。

**包内文件**：`index.ts`、`src/{client,config,accounts,submit,oracle,importer,jobs}.ts`、`locales/{zh,en}.yaml`、`templates/`（3 页 + 3 partial）、`README.md`、`CHANGELOG.md`、`LICENSE`、`package.json`。无 npm 依赖，只用 `hydrooj` 导出（`yaml` / `ObjectId` / `ProblemModel` / `RecordModel` …）。

**发版前冒烟（2026-11-16 全过）**：

| 项 | 结果 |
| --- | --- |
| 未登录访问 `/manage/luogu` | 302（跳登录） |
| 登录后管理页 | 200 |
| `/manage/luogu/tags` | 返回标签字典 |
| `/manage/luogu/config` | 脱敏（uid + clientIdLength，无明文） |
| `/manage/luogu/test-login` | `ok:true`，MarkZhang0520 |
| `/manage/luogu/estimate?sources=P` | 16754 题 / 336 页 / 131MB / 7.1h |
| `/manage/luogu/jobs` / `status` | 正常，含 counts 与 cursor |
| `/manage/luogu/import` 单题（已存在） | job 创建，skipped=1 |
| full 模式（P，1 页 1 题，匿名） | done，16754 total / 1 skipped / 0 failed |
| `job-action` 对已完成任务 pause | 明确报「当前状态 done 不能暂停」 |
| `/manage/luogu/oracle/P1004` | 标程 hash + fixes + preview |
| `/luogu/submit/P1004` | 200 |
| 空代码提交 | 「代码不能为空」 |
| 非法 rid | 「评测记录号格式不正确」 |
| `/luogu/account` + `/profile` | 200 / 已绑定资料 |
| 题目页侧栏 + 在线编程注入 | 6 处「提交到 Luogu」、`lg-sp-panel`、`luogu-scratchpad-submit` |
| 导航「第三方账号」 | 存在 |
| 评测机 | Online |

**分发注意**：`data/backend/luogu.key` 与 `luogu.config` 是运行数据，不在包里；对方需要自己填凭据。`README.md` / `CHANGELOG.md` / `LICENSE` 随包分发。

## 11. 站点品牌：RiverOJ（2026-11-16）

站点已改名为 **RiverOJ**，三处配置都不在代码里：

| 内容 | 位置 | 当前值 |
| --- | --- | --- |
| 站点名（标题 / og:site_name / 登录弹窗） | `system` 集合 `server.name` + `system` 域 `name` | `RiverOJ` |
| 首页简介（置顶 markdown） | `system` 域 `bulletin` | 「欢迎来到 RiverOJ …」 |
| 图标 / 顶栏 logo | `addons/riveroj-brand/public/` + 设置 `ui-default.nav_logo_dark` | 见下 |

图标实现：Hydro 只挂载**各 addon 的 `public/`** 目录，并按 addon 加载顺序倒序挂载，所以 `riveroj-brand/public/` 里的同名文件会覆盖 `@hydrooj/ui-default/public/` 里的 Hydro 图标；`data/backend/static/` 下那套是启动时拷贝的，会被覆盖回去，**不要改那里**。

包内文件：

```
addons/riveroj-brand/
├── package.json / index.ts        # 空 apply，只为了让 public/ 被挂载
└── public/
    ├── favicon-{16,32,96}.png     # 浏览器标签页
    ├── favicon.ico                # 多尺寸 ico
    ├── apple-touch-icon-180x180.png
    ├── android-chrome-192x192.png
    ├── icon-1024.png              # 源图（圆角方块 + 白色 R + 三道水波）
    └── components/navigation/     # 顶栏 logo（图标 + RiverOJ 字标锁排，394×128）
        ├── riveroj-logo.png       # 当前使用（设置 ui-default.nav_logo_dark 指向它）
        └── nav-logo-small_dark.png # 旧字标，保留但不再引用
├── templates/layout/html5.html   # 覆盖 ui-default：只给 5 个 favicon 链接加 ?v=2（破浏览器缓存）
```

顶栏 logo 由系统设置 **`ui-default.nav_logo_dark`** 控制（ui-default 的 Schema 默认值是 `/components/navigation/nav-logo-small_dark.png`），当前设为 `/components/navigation/riveroj-logo.png`。换图时**用新文件名并改这个设置**，可以绕过 `koa-static-cache` 的 24h 浏览器缓存。

改法：

- 只换名字：`db.domain.updateOne({_id:'system'},{$set:{name:'XXX'}})` + `db.system.updateOne({_id:'server.name'},{$set:{value:'XXX'}},{upsert:true})`，然后 `docker compose restart oj-backend`（domain 有进程内缓存）。
- 只换简介：改 `system` 域的 `bulletin`，同样重启。
- 换图标：替换 `addons/riveroj-brand/public/` 下同名文件后重启（静态文件走 koa-static-cache，重启最稳）；换顶栏 logo 建议换新文件名并把 `ui-default.nav_logo_dark` 指过去，避免浏览器缓存旧图。
- 顶栏图标显示不出来时先查：① 设置 `ui-default.nav_logo_dark` 是否指向存在的文件；② `curl -I /components/navigation/<file>.png` 是否 200；③ 浏览器强刷（静态资源 `max-age=86400`）。
- **favicon 在标签页里「一会儿水滴一会儿新图标」**：服务端早已全部是新图标（逐个文件比对过字节数与 `data/backend/static` 一致），问题在浏览器：Chrome/Safari 的 favicon 库按 URL 缓存，`/favicon-32x32.png` 这类固定 URL 会继续命中旧的 Hydro 水滴。解法 = 给图标 URL 加版本参数，已覆盖 `templates/layout/html5.html`（品牌插件内）把 5 个 `<link rel="icon">` 全部改成 `?v=2`。以后换图标要把 `?v=` 再加一。**覆盖了 ui-default 的 layout 模板，升级 ui-default 后要重新 diff 一次**（该文件仅 74 行，改动只有图标那 5 行 + 注释）。

注意：`data-app="Hydro"` 属性和页脚 “Powered by Hydro v5.1.0 Community” 是引擎标识，未改；如需去掉可覆盖 `templates/layout/html5.html` 与页脚模板，但要同步维护 ui-default 升级。

## 12. 数据范围识别模型（2026-11-17）

用户要求「训练一个模型识别，支持中文+英文，只用范围」。已实现并接入。

### 它解决什么

反算的 `targetN` 需要「题面写的数据规模上界」。规则只能靠变量名猜（只认 `n`），
P1048 的 `M ≤ 100`、P1003 的 `n ≤ 10^4` 里前者拿不到，就只能退回默认 20000，
造出违反题面的数据。模型看整段范围文本，判断**哪个变量的上界是规模参数**。

### 形态

- **候选排序**，不是文本分类：抽出所有 `var <= 数值`，给每个候选打分取最高。
- 逻辑回归 + **FNV-1a 确定性特征哈希**（8192 桶，1942 个非零权重）。
- 权重 `addons/luogu-import/src/range-weights.json`（30 KB），运行时由 `rangeModel.ts` 惰性加载。
- 训练脚本在 `tools/range-model/`，纯 numpy（该环境装不了 sklearn：scipy 下载反复超时，
  强装后扩展模块损坏，已卸载）。

### 实测

| 指标 | 值 |
| --- | --- |
| 训练集 | 13003（zh 10984 / en 2019） |
| **测试集 top-1** | **96.0%** |
| 中文覆盖（给出 targetN） | 16753 题中 **64.4%**（纯规则 30.4%） |
| 小于样例规模（错） | 1.2%（已被运行时的「≥样例规模」检查挡住） |
| 英文覆盖 | 14.3% |

英文低是数据问题：14070 份英文题面里 11295 份没有 Constraints 段；中文题面 98.7% 都有。

### 接入点

`oracle.ts` 的 `regenerateSamples()`：

```
targetN 优先级：手工指定 > 模型 > 规则解析的 n > 默认值
且模型输出必须 >= 样例实际计数，否则退回规则
```

日志 `range model for <domain>/<docId>: targetN=… var=… conf=… candidates=[…]`。

### 三个必须记住的坑

1. **文件名不能撞**：权重文件必须叫 `range-weights.json`。曾命名为 `rangemodel.json`，
   与 `rangeModel.ts` 只差大小写，Node 解析 `require('./rangeModel')` 时
   在大小写不敏感的文件系统上直接命中 JSON，静态导入拿到的是 `{version,dim,...}`
   而不是模块 → 报 `predictRange is not a function`。这个 bug 排查了很久。
2. **不能用 `__dirname`**：Hydro 的 `@hydrooj/register` 会把 esbuild 生成的
   `const __dirname = dirname(__filename)` 整行**删除**，运行时为 undefined。
   `rangeModel.ts` 用绝对路径 + `process.cwd()` 候选链兜底。
3. **哈希必须跨语言一致**：Python 内置 `hash()` 对 str 默认加盐，跨进程不可复现。
   训练（`tools/range-model/hasher.py`）与推理（`rangeModel.ts`）都用 FNV-1a 32bit，
   已用 5 条 golden case 对齐验证（norm / bounds / targetN 全部一致）。

### 改模型时

改任何特征名或哈希都要**重新训练**并替换 `range-weights.json`，否则权重错位，
准确率会静默掉到随机水平。

## 13. 多仓库结构（2026-11-17 重构）

**每个插件一个独立 Git 仓库**，主仓库只放部署编排。以后开发新插件**不要**堆进主仓库。

### 三个仓库

| 目录 | GitHub | 内容 |
| --- | --- | --- |
| `.`（主仓库） | `JiangWanZhengChouYv/riveroj` | Docker 编排、镜像、judge 健康检查、模型训练脚本 |
| `addons/luogu-import` | `JiangWanZhengChouYv/luogu-import`（v1.1.0 已发 Release） | 洛谷拉题 / 提交 / 反算 |
| `addons/riveroj-brand` | `JiangWanZhengChouYv/hydro-addon-riveroj-brand` | 站点图标与顶栏 logo |

三个都是 Public，各自 `main` 分支、各自 `.git`。

**主仓库 `.gitignore` 里有 `addons/*/`**，所以主仓库根本不跟踪插件源码；
插件仓库也不会把主仓库的部署文件带进去。两边互不干扰。

### RiverOJ 自动安装全部插件

`backend/entrypoint.sh` 已改为**扫描 `addons/` 目录**：

- 只要子目录里有 `package.json` 就注册进 `addon.json`
- 跳过隐藏目录、`node_modules`、无 `package.json` 的目录
- 保留 `addon.json` 里原有的非本地条目（比如 npm 装的插件）
- 纯 shell 实现（grep/awk），不依赖 python3/node

**所以新增插件不需要改任何代码**：把目录放进 `addons/` → `docker compose restart oj-backend` 即可。

实测：放 3 个插件目录（含 1 个空目录）→ 空的被跳过，3 个都被注册。

### 新建插件的完整流程

```bash
cd addons
mkdir my-addon && cd my-addon
git init -b main
# 写 package.json + index.ts + README（必须含「仅供个人学习使用」声明）
gh repo create hydro-addon-my-addon --public --source=. --remote=origin --push
cd ../.. && docker compose restart oj-backend
```

命名规范与必读坑位见 `CONTRIBUTING-ADDONS.md`。

### 「仅供个人学习使用」声明

**每个插件的 README 开头必须有这段**（主仓库 README 也有）：

```markdown
> ## ⚠️ 仅供个人学习使用
>
> 本项目仅供个人学习与技术研究，不得用于任何商业用途或对外提供服务。
> 使用本项目产生的任何后果由使用者自行承担。
> 本项目与相关平台官方无任何关联，未获其授权或认可。
```

`luogu-import` 的声明额外写明：访问洛谷可能违反其服务条款、题面版权归原作者、
因使用导致的限流/封禁由使用者自行承担。

### 仓库操作速查

```bash
# 查看三处状态
cd /Users/markzhang/Documents/Hydro-Dev && git status --short
cd addons/luogu-import && git status --short
cd addons/riveroj-brand && git status --short

# 推送某个插件
cd addons/luogu-import && git add -A && git commit -m "..." && git push

# 主仓库（部署改动）
cd /Users/markzhang/Documents/Hydro-Dev && git add -A && git commit -m "..." && git push
```

### 注意

- 主仓库**不要** `git add addons/luogu-import`（会被忽略，但也别强行 `-f`）
- 插件仓库**不要**提交 `data/`、密钥、日志
- `tools/range-model/` 属于主仓库（模型训练脚本，与具体插件解耦）

## 14. 公网访问：Cloudflare Tunnel + 缓存（2026-11-17 配置并实测）

站点公网地址 **https://oj.mz0520.de5.net**（zone `mz0520.de5.net`，Free，zone id `875aba9ba064027303316c9aca835de6`）。

```
浏览器 → CF 边缘 → Tunnel 29664482-170c-4265-81ca-9e72332f2562 → 127.0.0.1:8889
```

Tunnel 已常驻（`~/.cloudflared/config.yml`，`oj.` / `dl.` 两个 ingress 都指向本机），不用开端口、不用公网 IP。

### 后端设置

```bash
docker exec dev-oj-backend hydrooj cli system set server.xff cf-connecting-ip
docker compose restart oj-backend
```

`server.ts` 里 `proxy = !!server.xproxy || !!server.xff`；`framework/base.ts` 用 `headers[xff] || ctx.request.ip`。
CF 下填 **`cf-connecting-ip`**，不是 `x-forwarded-for`。

副作用（已实测）：CF 侧 cookie 变 `Secure`；**本地 127.0.0.1:8889 登录不受影响**——
`service/layers/base.ts` 里 `secure` 只在 `session.domain` 有值且 host 匹配时才设，本实例没配该键。

### Cache Rules（zone 级 4 条，按序命中）

`PUT /zones/<id>/rulesets/phases/http_request_cache_settings/entrypoint`

| # | 条件 | 动作 |
| --- | --- | --- |
| R1 | `not`（路径以 css/js/png/ico/svg/jpg/jpeg/gif/webp/woff2/woff/ttf/eot 结尾） | cache=false |
| R2 | `/resource/*`、`/theme-*.css`、`/hydro-*.js`、含 `.chunk.js` | cache=true，edge+browser 1 年 |
| R3 | R1 反向的静态扩展名，排除 `service-worker.js` | cache=true，edge 7 天，browser 尊重源站 |
| R4 | `/service-worker.js` | cache=false |

**R1 是安全底线**：任何非静态路径一律不缓存，将来即使有人开 Cache Everything 也不会把登录页
缓存给别人（Hydro 按登录态渲染、CSRF 只校验 Referer 域名，串号即会话泄露）。

### zone 其它设置

`always_use_https=on`、`min_tls_version=1.2`、`brotli=on`、`http3/tls_1_3=on`；
`rocket_loader` **off**、`minify` 全 **off**（会弄坏 React/Monaco）；`cache_level=aggressive`
（= Standard，**不是** Cache Everything，query 进 cache key，`?v=2` 有效）。
改动前全套备份在 `cf-zone-settings-backup.json`（已 gitignore）。

### 实测（2026-11-17）

匿名 `/`、`/p/P1001`、`/login` 全 `DYNAMIC`；`/theme-4.59.1.css`、`/favicon.ico` 全 `HIT`。
登录态 `/`、`/p/P1001`、`/ranking`、`/status`、`/user/2`、`/record` 全 `DYNAMIC`（正文含用户名）。
插件经公网正常：`/manage/luogu` 200、`/manage/luogu/config` 返回脱敏信息、评测机 Online。

### 坑位

- **CF dashboard 的 `/api/v4` 写操作要带 `X-Cross-Site-Security: dash`**，否则 403 + HTML
  "Attention Required!"（像 WAF/权限问题，实则缺这个头）。读操作不需要。
- 本站 `rewrite_response_headers` **不可用**（`unknown variant for action`），没法用 Transform Rule
  强加 `no-store`，改由 R1 从请求侧兜底。
- 换 favicon / 顶栏 logo 这种**文件名不变**的资源必须 `POST /zones/<id>/purge_cache`
  或继续递增 `?v=N`。
- **CF 免费版请求体上限 100 MB**，而 `server.upload=256m`：大测试点包会 413 且边缘报错、
  Hydro 日志看不到。大包改本地 `hydrooj cli problem upload`。
