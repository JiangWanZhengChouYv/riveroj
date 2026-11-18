# AGENTS.md — RiverOJ

## 项目简介

用 Docker Compose 跑的 **HydroOJ v5.1.0** 实例，站点名 **RiverOJ**，外加一套自研洛谷插件。

- **本地**：http://127.0.0.1:8889  ·  **公网**：https://oj.mz0520.de5.net
- **账号**：见 `data/backend/CREDENTIALS.txt`（已改为强随机密码，不得写进本文件或任何会提交的地方）
  - `JWZCY`（uid 2，superadmin，用于所有测试）、`hydro`（uid 1，评测机）、`JiangWanZCY`（uid 3，superadmin）
- **容器**：`dev-oj-backend`、`dev-oj-judge`、`dev-oj-mongo`（compose project `hydro-dev`）

三个 Git 仓库，插件各自独立、都是 Public：

| 目录 | GitHub | 内容 |
| --- | --- | --- |
| `.` | `JiangWanZhengChouYv/riveroj` | Docker 编排、镜像、judge 健康检查、模型训练脚本 |
| `addons/luogu-import` | `JiangWanZhengChouYv/luogu-import` | 洛谷拉题 / 提交 / 反算（1.2.0(1) 已发 Release） |
| `addons/riveroj-brand` | `JiangWanZhengChouYv/hydro-addon-riveroj-brand` | 站点图标与顶栏 logo |

主仓库 `.gitignore` 里有 `addons/*/`，所以插件源码不在主仓库；**开发新插件不要堆进主仓库**，按 `CONTRIBUTING-ADDONS.md` 的约定另开仓库。

常用命令：

```bash
docker compose up -d
docker compose restart oj-backend      # 改 addons/ 后必须重启（插件在启动时加载）
docker compose restart oj-judge        # 评测机断连时（判断依据见 docs/DEVLOG.md）
```

新增插件不需要改任何代码：目录放进 `addons/` 且含 `package.json`，`backend/entrypoint.sh` 会自动注册。

> **完整的实现细节、验收记录与踩坑清单在 [`docs/DEVLOG.md`](docs/DEVLOG.md)**。改代码前先按主题在里面搜一遍——那里记了大量 Hydro 与洛谷的隐性约束（`__dirname` 不可用、AC 状态码 12 与 1 的区别、`.section` 透明、CF API 需要 `X-Cross-Site-Security` 头等），不知道就会重踩。

---

## 已完成的 10 件事

### 1. 本地 OJ 实例

Docker Compose 三容器编排，backend 暴露 `8889:8888`。`backend/entrypoint.sh` 首次启动自动建 `hydro` / `JWZCY` 账号、写 `addon.json`。judge 带 healthcheck（`scripts/judge-healthcheck.js`），backend 重启导致的断连会在数秒内自动恢复。

### 2. 洛谷插件：登录态

后台 `/manage/luogu` 配 `_uid` + `__client_id`，`__client_id` 用 AES-256-GCM 加密存 Mongo，密钥在 `data/backend/luogu.key`（600）。API / 日志 / 页面只出现 uid 与长度，绝不回显原值。

### 3. 洛谷插件：全量拉题

按来源 `P/B/CF/SP/AT/UVA` 逐页遍历。任务持久化在 `luogu.job`，每题落一次进度，支持 **pause / resume / cancel**，backend 重启后从断点自动续跑；已存在的题跳过、不请求题面。限速默认 1500ms，实测 P 库 16754 题 / 336 页 / 131MB / 7.1h。分页有健壮性重试，全量跑完还会对 `1..最大题号` 用 HEAD 逐个探测补漏。多语言题面走 Hydro 官方 statement 机制（`?lang=zh|en` 切换）。

### 4. 洛谷插件：远端提交

题目页侧栏与在线编程里都有「提交到 Luogu」。`GET /ranking` 取 CSRF → `POST /fe/api/problem/submit/{pid}`；从 302 或 JSON 任一层取 rid → 轮询 `/record/{rid}?_contentOnly=1` 拿状态、分数、时空、逐测试点。要验证码时弹图重提（最多 3 次）。**不写 Hydro record**，结果只在插件自己的页面展示。

### 5. 账号体系与在线编程入口

两套账号完全隔离：`luogu.config`（全站拉题，仅管理员可维护）与 `luogu.accounts`（每人自己的提交账号，导航「第三方账号」页绑定）。提交时按 `resolveSubmitCredentials(uid)` 取本人的 cookie 逐次传入，不用进程级全局，避免多用户并发串号。scratchpad 工具栏插入同款按钮，结果按原生评测记录表格的 `<tr>` 结构插入，洛谷行与 LOCAL 行并列。

### 6. 反算样例

洛谷 AC 后把该代码存为标程（`luogu.oracle`，hash 幂等），触发 Hydro 自带 generate 判题器**按题面数据范围造极限数据**重算测试点。解析「提示 / 数据范围」里的上界，识别输入结构（单个数 / 行内数组 / n 行 / n m 行 / 坐标题 / n² 方格题），生成 10 组 profile（最小边界、随机、升序、降序、全值域最大）。时限取题面的 90%，成功 ≥6 组即 done，并支持按上界自动升降档。失败组留下的残缺 `.in` 会自动回滚。

### 7. 数据范围识别模型

规则只能靠变量名猜 `n`，拿不到 `M ≤ 100` 这类写法。改成**候选排序**：抽出所有 `var <= 数值`，用逻辑回归 + FNV-1a 确定性特征哈希（8192 桶）给每个候选打分取最高。实测测试集 **top-1 96.0%**，中文覆盖从规则版 30.4% 提到 **64.4%**，小于样例规模的错误率 1.2%（已被运行时检查挡住）。训练脚本在 `tools/range-model/`，纯 numpy。

### 8. 站点品牌

改名 RiverOJ（`server.name` + system 域 `name`），首页简介改 `bulletin`。图标做成独立插件 `riveroj-brand`：只放 `public/` 静态资源，靠 addon 挂载顺序覆盖 ui-default 的同名文件，升级 ui-default 不会冲掉。favicon「一会儿水滴一会儿新图标」是浏览器按 URL 缓存导致的，用覆盖 `templates/layout/html5.html` 加 `?v=2` 解决。

### 9. 多仓库拆分与发布

从单仓库拆成三个独立仓库，主仓库只留编排。`luogu-import` 当前为 **1.2.0(1)**（tag `v1.2.0(1)`），附 `luogu-import-1.2.0(1).tar.gz`。版本号规则：基准版本(修订号)，修 bug 只加括号。每个插件 README 开头都有「仅供个人学习使用」声明。插件安装无需改代码，`entrypoint.sh` 扫描 `addons/` 自动注册。

### 10. 公网访问与 Cloudflare 缓存

经已有的 CF Tunnel 暴露到 `https://oj.mz0520.de5.net`，不用开端口、不用公网 IP。后端设 `server.xff=cf-connecting-ip` 拿真实 IP（实测**不影响**本地 HTTP 登录）。配了 4 条 Cache Rules，核心是 **R1：除静态扩展名外一律不缓存**——白名单式判定，将来即使有人开 Cache Everything 也不会把登录用户的页面缓存给别人（Hydro 按登录态渲染、CSRF 只校验 Referer 域名，串号即会话泄露）。另开 Always HTTPS、TLS 最低 1.2。实测匿名与登录态页面全 `DYNAMIC`、静态资源 `HIT`。