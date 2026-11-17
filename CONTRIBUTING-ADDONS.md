# RiverOJ 插件开发约定

RiverOJ 的每个插件都是**独立仓库**，不放在主仓库里。主仓库只负责把 `addons/` 下的插件挂进容器。

## 目录与仓库的对应关系

```
Hydro-Dev/                      ← 主仓库（本目录，仅放部署编排）
├── docker-compose.yml
├── backend/  judge/  scripts/
├── addons/                     ← ★ 每个子目录是一个独立 Git 仓库
│   ├── luogu-import/           → github.com/<you>/luogu-import
│   ├── riveroj-brand/          → github.com/<you>/hydro-addon-riveroj-brand
│   └── <新插件>/               → github.com/<you>/hydro-addon-<name>
└── tools/                      ← 工具与训练脚本（可独立成仓库）
```

`addons/<name>/` 有自己的 `.git`，主仓库的 `.gitignore` 会把它们整个忽略掉：
主仓库不跟踪插件源码，插件也不会把主仓库的部署文件带进去。

## 新增一个插件的流程

1. 在主目录下建目录并初始化独立仓库：

   ```bash
   cd addons
   mkdir my-addon && cd my-addon
   git init -b main
   ```

2. 写最小插件骨架（`package.json` + `index.ts`），必须包含：

   ```json
   {
     "name": "my-addon",
     "version": "0.1.0",
     "main": "./index.ts",
     "hydro": { "addon": true }
   }
   ```

3. 加 `README.md`（**必须含「仅供个人学习使用」声明**，模板见下）与 `LICENSE`。

4. 建 GitHub Public 仓库并推送：

   ```bash
   gh repo create hydro-addon-my-addon --public --source=. --remote=origin --push
   ```

5. **不需要**改 `backend/entrypoint.sh` 或 `addon.json`：
   容器启动时会扫描 `addons/`，凡是有 `package.json` 的子目录都会自动注册。

6. 重启生效：

   ```bash
   cd /Users/markzhang/Documents/Hydro-Dev
   docker compose restart oj-backend
   ```

## 命名规范

| 项 | 约定 |
| --- | --- |
| 目录名 | kebab-case，如 `luogu-import` |
| GitHub 仓库名 | `hydro-addon-<目录名>` |
| `package.json` 的 `name` | 与目录名一致 |
| 版本号 | 语义化；接入 RiverOJ 时用 1.0.0 起 |

## README 必带声明

每个插件 README 开头都要有这段（可按插件调整，但要点不能少）：

```markdown
> ## ⚠️ 仅供个人学习使用
>
> 本项目仅供个人学习与技术研究，不得用于任何商业用途或对外提供服务。
> 使用本项目产生的任何后果由使用者自行承担。
> 本项目与相关平台官方无任何关联，未获其授权或认可。
```

## 硬性约束（踩过的坑）

- **不要依赖 `__dirname`**：Hydro 的 `@hydrooj/register` 会把 esbuild 生成的
  `const __dirname = dirname(__filename)` 整行删掉，运行时是 `undefined`。
  需要文件路径时用绝对路径 + `process.cwd()` 候选链。
- **同名资源文件大小写不能只差一个字母**：例如 `rangeModel.ts` 与 `rangemodel.json`
  在大小写不敏感的文件系统上会被 `require` 解析成同一个，拿到 JSON 而不是模块。
- **插件加载顺序**：`addon.json` 里靠后的插件优先级更高（`public/` 目录倒序挂载、
  模板后加载覆盖前者）。要覆盖 ui-default 的资源就排在它后面。
- **改模板/静态资源后必须 `docker compose restart oj-backend`**，热重载不生效。
- **插件无 npm 依赖时最省心**：只用 `hydrooj` 导出，避免在容器里装包。

## 提交前检查

```bash
# 1. 语法能过
docker compose restart oj-backend && docker logs --tail 30 dev-oj-backend | grep -i error

# 2. 仓库干净（没有把 data/、密钥、日志带进去）
git status --short

# 3. 敏感信息扫描
git grep -nE "luogu\.cn/user/[0-9]+|__client_id=[A-Za-z0-9]|Hydro123|Hydro7890" || echo "clean"
```

## 现有插件

| 插件 | 仓库 | 说明 |
| --- | --- | --- |
| `luogu-import` | `luogu-import` | 洛谷拉题 / 提交 / 反算，含中英范围识别模型 |
| `riveroj-brand` | `hydro-addon-riveroj-brand` | RiverOJ 图标与顶栏 logo |
