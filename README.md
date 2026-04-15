# ns-hotopic

NodeSeek 首页热点追踪工具。项目定时抓取首页列表页，保存快照到 SQLite，计算热点榜，并通过 Telegram Bot 提供查看与订阅功能。

## 功能简介

- 定时抓取 NodeSeek 首页列表页，不抓详情页
- 保存帖子标题、链接、浏览数、评论数、位置等首页快照
- 计算“最近 6 小时升温榜”
- 单独输出“抽奖贴”列表
- Telegram Bot 支持查看热点、查看抽奖贴、订阅热点推送
- SQLite 持久化存储，内置数据清理策略
- 提供 Docker Compose 部署方式

## 工作原理

`ns-hotopic` 当前使用 Playwright 抓取 NodeSeek 首页。由于目标站点可能出现 Cloudflare 验证，首次运行需要人工完成一次验证，并把 Playwright 浏览器状态保存为 `state/storage_state.json`。之后定时抓取会复用这份状态文件。

注意：

- `storage_state.json` 不是你日常浏览器的配置目录
- 它来自 Playwright 独立浏览器上下文
- 文件中通常包含 cookie / localStorage 等状态信息
- 状态文件可能失效，失效后重新执行一次初始化即可

## 快速开始

### 1. 本地开发环境

要求：

- Python 3.12+
- `uv`

安装依赖：

```bash
uv sync
```

复制环境变量模板：

```bash
cp .env.example .env
```

至少需要配置：

```dotenv
TELEGRAM_BOT_TOKEN=replace-me
```

### 2. 初始化 Cloudflare 状态

首次需要在可见浏览器里完成一次验证：

```bash
uv run ns-hotopic trial-once
```

执行后会打开一个独立浏览器窗口。你在窗口里完成 Cloudflare 验证，并进入 NodeSeek 首页后，程序会自动保存状态文件：

```text
state/storage_state.json
```

可以用下面的命令确认状态文件可用：

```bash
uv run ns-hotopic fetch-once
```

如果抓取成功，说明后续定时任务可以复用这份状态。

## 本地使用

### 单次命令

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

其中：

- `trial-once`：打开浏览器，人工完成首次验证并抓取一次
- `fetch-once`：复用状态文件，执行一次无头抓取
- `service-run`：同时运行 Telegram Bot 和后台定时任务

## Docker Compose 部署

### 方案 A：从源码构建并部署

1. 在 VPS 上克隆仓库
2. 复制环境变量模板
3. 上传 `storage_state.json`
4. 启动服务

远端目录准备：

```bash
mkdir -p ~/ns-hotopic/{data,state,artifacts}
```

从本地上传状态文件：

```bash
scp state/storage_state.json user@your-vps:~/ns-hotopic/state/storage_state.json
```

在 VPS 上启动：

```bash
cd ~/ns-hotopic
cp .env.example .env
docker compose up -d --build
```

### 方案 B：使用 GHCR 镜像

项目在打 tag 时会发布 GHCR 镜像。你可以在 `.env` 或 shell 环境中指定镜像：

```dotenv
NS_HOTOPIC_IMAGE=ghcr.io/impersonality/ns-hotopic:latest
```

然后执行：

```bash
docker compose pull
docker compose up -d
```

### Compose 挂载目录

Compose 会持久化以下目录：

- `./data`：SQLite 数据库
- `./state`：Playwright 浏览器状态
- `./artifacts`：抓取页面 HTML 归档

## Telegram Bot

Bot 命令：

- `/hot`：查看热点榜
- `/lottery`：查看最近一轮抓取中的抽奖贴
- `/subscribe`：订阅热点推送
- `/unsubscribe`：取消热点推送
- `/help`：查看帮助

热点推送支持的间隔：

- 30 分钟
- 1 小时
- 6 小时
- 24 小时

## 配置项

### 应用配置

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
```

### Compose 额外变量

```dotenv
TZ=Asia/Hong_Kong
NS_HOTOPIC_IMAGE=ghcr.io/impersonality/ns-hotopic:latest
```

## 热点算法概览

当前热点榜是“最近 6 小时升温榜”：

- 默认排除置顶帖
- 默认排除抽奖 / 评论送鸡腿等活动帖
- 6 小时窗口内出现 2 次及以上的帖子，按评论增量和浏览增量计算
- 只出现 1 次但信号足够强的新进帖子，也可以进入榜单
- 新帖会得到温和加成，老帖仍可上榜

## 常见问题

### `storage_state.json` 一定要本机生成吗？

不一定。只要是在任意有界面的环境里运行 `trial-once` 并完成验证，都可以生成这份文件。本地通常最方便。

### `storage_state.json` 会过期吗？

会。Cookie 或 Cloudflare 会话失效后，需要重新执行一次：

```bash
uv run ns-hotopic trial-once
```

然后把新的状态文件重新上传到 VPS。

### 为什么不是一键自动过 Cloudflare？

当前版本选择的是最务实、最稳定的方案：首次人工验证一次，后续复用状态。对这类站点来说，这通常比“尝试完全自动绕过验证”更可维护。

---

## English

`ns-hotopic` tracks hot topics from the NodeSeek homepage. It periodically crawls the homepage list view, stores snapshots in SQLite, computes hot-topic rankings, and exposes the data through a Telegram bot.

### Features

- Crawl the NodeSeek homepage list only
- Store homepage snapshots in SQLite
- Compute a rolling 6-hour hot-topic ranking
- Expose a dedicated lottery-post list
- Telegram bot commands for viewing and subscribing
- Built-in retention cleanup
- Docker Compose deployment support

### Initialization

The project currently relies on Playwright plus a saved browser state file:

```text
state/storage_state.json
```

Generate it once in a visible browser:

```bash
uv run ns-hotopic trial-once
```

After you complete the Cloudflare check, verify it works:

```bash
uv run ns-hotopic fetch-once
```

### Docker Compose

From source:

```bash
cp .env.example .env
docker compose up -d --build
```

With GHCR image:

```dotenv
NS_HOTOPIC_IMAGE=ghcr.io/impersonality/ns-hotopic:latest
```

```bash
docker compose pull
docker compose up -d
```

Make sure the following directories are persisted:

- `data/`
- `state/`
- `artifacts/`

### Service mode

The container runs:

```bash
ns-hotopic service-run
```

This starts the Telegram bot plus background jobs for crawling, due-message delivery, and cleanup.
