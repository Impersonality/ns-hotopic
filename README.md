# ns-hotopic

NodeSeek 首页热点追踪工具。

[English README](./README.en.md)

## 它能做什么

- 每隔一段时间抓取 NodeSeek 首页列表页
- 保存标题、链接、浏览数、评论数等快照到 SQLite
- 计算热点榜
- 输出抽奖贴列表
- 提供 Telegram Bot 查看和订阅热点推送
- 提供 Docker Compose 部署方式

## 部署前你需要知道

这个项目当前依赖 Playwright 抓 NodeSeek 首页。  
首次使用前，需要先人工完成一次 Cloudflare 验证，并生成：

```text
state/storage_state.json
```

后续 Docker 容器会直接复用这个文件。  
自动抓取默认只会读取它，不会在 headless 抓取后覆盖它。

## 1. 本地生成 `storage_state.json`

先在本地准备环境：

```bash
git clone https://github.com/Impersonality/ns-hotopic.git
cd ns-hotopic
uv sync
cp .env.example .env
```

然后运行：

```bash
uv run ns-hotopic trial-once
```

会打开一个独立浏览器窗口。你只需要：

1. 完成 Cloudflare 验证
2. 确认页面已经进入 NodeSeek 首页
3. 等命令结束

成功后会生成：

```text
state/storage_state.json
```

建议马上验证一次：

```bash
uv run ns-hotopic fetch-once
```

如果能抓取成功，说明这个文件可以用。

## 2. 用 Docker Compose 部署到 VPS

在 VPS 上执行：

```bash
git clone https://github.com/Impersonality/ns-hotopic.git
cd ns-hotopic
mkdir -p data state artifacts
cp .env.example .env
```

编辑 `.env`，至少填入：

```dotenv
TELEGRAM_BOT_TOKEN=你的_bot_token
```

然后把你本地生成好的 `storage_state.json` 上传到 VPS：

```bash
scp state/storage_state.json user@your-vps:~/ns-hotopic/state/storage_state.json
```

这里的远端路径要对应你的项目目录，例如你把项目放在 `~/ns-hotopic`，那上传目标就应该是：

```text
~/ns-hotopic/state/storage_state.json
```

### 这份文件在 Docker Compose 里怎么用？

因为 [docker-compose.yml](/home/kg/Code/python/ns_hotopic/docker-compose.yml) 已经把宿主机目录挂载进容器：

- `./state:/app/state`
- `./data:/app/data`
- `./artifacts:/app/artifacts`

所以：

- 你上传到 VPS 的 `./state/storage_state.json`
- 会在容器里变成 `/app/state/storage_state.json`
- 程序启动后会自动读取它

不用再手动复制到容器内部。

### 启动服务

默认直接使用 GitHub Actions 发布的镜像：

```bash
docker compose pull
docker compose up -d
```

如需手动指定镜像版本，可在 `.env` 里设置：

```dotenv
NS_HOTOPIC_IMAGE=ghcr.io/impersonality/ns-hotopic:latest
```

## 常用命令

本地调试：

```bash
uv run ns-hotopic trial-once
uv run ns-hotopic fetch-once
uv run ns-hotopic show-last-run
uv run ns-hotopic show-hot-topics
uv run ns-hotopic bot-run
uv run ns-hotopic bot-send-due
uv run ns-hotopic cleanup
uv run ns-hotopic service-run
```

Docker 查看日志：

```bash
docker compose logs -f
```

停止服务：

```bash
docker compose down
```

## Telegram Bot 功能

- `/hot` 查看热点榜
- `/lottery` 查看抽奖贴
- `/subscribe` 订阅热点推送
- `/unsubscribe` 取消热点推送
- `/help` 查看帮助

## 配置项

`.env` 常用配置：

```dotenv
NODESEEK_HOME_URL=https://www.nodeseek.com/
TELEGRAM_BOT_TOKEN=replace-me

NS_HOTOPIC_CRAWL_RETENTION_DAYS=60
NS_HOTOPIC_HOT_RETENTION_DAYS=180
NS_HOTOPIC_BOT_LOG_RETENTION_DAYS=30
NS_HOTOPIC_ARTIFACT_RETENTION_DAYS=7

NS_HOTOPIC_FETCH_INTERVAL_MINUTES=30
NS_HOTOPIC_DELIVERY_CHECK_INTERVAL_MINUTES=5
NS_HOTOPIC_CLEANUP_INTERVAL_MINUTES=1440

TZ=Asia/Hong_Kong
NS_HOTOPIC_IMAGE=ghcr.io/impersonality/ns-hotopic:latest
```

## 常见问题

### `storage_state.json` 会过期吗？

会。失效后重新执行：

```bash
uv run ns-hotopic trial-once
```

然后重新上传新的 `state/storage_state.json` 到 VPS。

### 为什么本地生成的 `storage_state.json` 传到 VPS 后只能成功一次？

这通常不是 SQLite 或 Docker 挂载问题，而是 Cloudflare 会综合看：

- 出口 IP
- 浏览器指纹
- 是否 headless
- cookie / clearance 的上下文

也就是说：

- 本地浏览器过盾后导出的状态，复制到另一台 VPS 上
- 只能算“尽量复用”
- 不保证跨 IP、跨环境后还能长期稳定使用

项目现在默认不会在 `fetch-once` / `service-run` 时回写 `storage_state.json`，避免 headless 抓取把原本还能用的状态覆盖坏。  
如果你上传到 VPS 后依然只能成功一次，通常说明这台 VPS 的出口 IP 或指纹本身已经被 Cloudflare 重点校验。更稳的办法是：

- 在和最终抓取出口更接近的环境里生成 `storage_state.json`
- 或者直接更换更干净的 VPS / 代理出口

### 一定要本机生成 `storage_state.json` 吗？

不一定。任何有界面的环境都可以生成。  
本地通常最方便，所以 README 默认按这个路径写。

### 为什么我没看到 Docker 镜像？

现在 GitHub Actions 的镜像发布规则是：

- `push` 到 `main`：发布 `latest` 和 `sha-*`
- `push` 一个版本 tag，例如 `v0.1.0`：发布版本镜像和 `sha-*`

也就是说，镜像不是“创建仓库就自动有”，而是需要至少一次代码 push 到 `main`，或者推一个版本 tag。

如果你想发布第一个正式版本镜像，可以执行：

```bash
git tag v0.1.0
git push origin v0.1.0
```
