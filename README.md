# RiverOJ

一个跑在 Docker Compose 上的 HydroOJ 实例，外加一组自研插件。

> ## ⚠️ 仅供个人学习使用
>
> 本项目仅供个人学习与技术研究，不得用于任何商业用途或对外提供服务。
> 使用本项目产生的任何后果由使用者自行承担。
> 本项目与 HydroOJ、洛谷等官方无任何关联，未获其授权或认可。

## 仓库结构

**本仓库只放部署编排，不放插件源码。每个插件是独立仓库。**

```
Hydro-Dev/                     ← 你在这里
├── docker-compose.yml         三容器编排（backend / judge / mongo）
├── backend/                   backend 镜像与首次初始化
├── judge/                     评测机镜像
├── scripts/                   judge 健康检查
├── addons/                    ★ 每个子目录是一个独立的 Git 仓库
│   ├── luogu-import/          → luogu-import
│   └── riveroj-brand/         → hydro-addon-riveroj-brand
├── tools/range-model/         数据范围识别模型的训练脚本
├── AGENTS.md                  项目现状、计划、坑位（给后续 AGENTS 看）
└── CONTRIBUTING-ADDONS.md     插件开发约定
```

`addons/*/` 被主仓库 `.gitignore` 忽略，插件各有自己的 `.git` 和远端。

## 插件

| 插件 | 仓库 | 说明 |
| --- | --- | --- |
| `luogu-import` | [luogu-import](https://github.com/JiangWanZhengChouYv/luogu-import) | 洛谷拉题 / 提交 / 反算极限测试点，含中英双语范围识别模型 |
| `riveroj-brand` | [hydro-addon-riveroj-brand](https://github.com/JiangWanZhengChouYv/hydro-addon-riveroj-brand) | RiverOJ 图标与顶栏 logo |

**RiverOJ 会自动安装 `addons/` 下的全部插件**：容器启动时扫描该目录，
凡是有 `package.json` 的子目录都会写进 `addon.json`。新增插件不需要改任何代码。

## 启动

```bash
docker compose up -d
docker compose ps
docker compose logs -f oj-backend
```

- 地址：http://127.0.0.1:8889
- 测试账号：`JWZCY` / `Hydro123`（超级管理员，uid 2）
- 评测机账号：`hydro` / `Hydro7890`（uid 1，`setJudge`）

## 新增插件

```bash
cd addons
mkdir my-addon && cd my-addon
git init -b main
# 写 package.json + index.ts（见 CONTRIBUTING-ADDONS.md）
gh repo create hydro-addon-my-addon --public --source=. --remote=origin --push
cd ../.. && docker compose restart oj-backend   # 自动注册，无需改代码
```

## 改代码后怎么生效

| 改了什么 | 怎么做 |
| --- | --- |
| `addons/` 下的插件 | `docker compose restart oj-backend` |
| `backend/entrypoint.sh` 或 `Dockerfile` | `docker build -t hydro-dev-backend:latest ./backend` + `docker compose up -d --force-recreate oj-backend` |
| `judge/` | 别重建（镜像 7GB+），改配置优先用挂载 |

## 数据

`./data/{mongo,file,backend,judge}` 保存运行时数据（gitignore）。

`data/backend/luogu.key` 是插件凭据的加密密钥，**权限 600，绝不入库**。
删掉 `data/` 后需要在后台重新配置洛谷登录态。

## 文档

- [`AGENTS.md`](AGENTS.md)：项目全貌、已完成功能、踩过的坑（篇幅较长但信息密度高）
- [`CONTRIBUTING-ADDONS.md`](CONTRIBUTING-ADDONS.md)：插件开发约定与命名规范
- [`tools/range-model/README.md`](tools/range-model/README.md)：范围识别模型的训练流程
