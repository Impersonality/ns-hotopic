# ns-hotopic

Hot-topic tracker for the NodeSeek homepage.

[简体中文 README](./README.md)

## What It Does

- Crawls the NodeSeek homepage list view on a schedule
- Stores title, URL, views, comments, and position snapshots in SQLite
- Computes hot-topic rankings
- Provides a lottery-post list
- Exposes data through a Telegram bot
- Supports Docker Compose deployment

## Before You Deploy

This project currently needs one manual Cloudflare verification step before automated crawling can run.  
That step produces:

```text
state/storage_state.json
```

The Docker container will reuse that file later.

## 1. Generate `storage_state.json` Locally

```bash
git clone https://github.com/Impersonality/ns-hotopic.git
cd ns-hotopic
uv sync
cp .env.example .env
uv run ns-hotopic trial-once
```

Then:

1. Complete the Cloudflare check in the opened browser window
2. Wait until the homepage is visible
3. Let the command finish

The file will be saved to:

```text
state/storage_state.json
```

Validate it:

```bash
uv run ns-hotopic fetch-once
```

## 2. Deploy with Docker Compose on VPS

On the VPS:

```bash
git clone https://github.com/Impersonality/ns-hotopic.git
cd ns-hotopic
mkdir -p data state artifacts
cp .env.example .env
```

Set at least:

```dotenv
TELEGRAM_BOT_TOKEN=your_bot_token
```

Upload the file you generated locally:

```bash
scp state/storage_state.json user@your-vps:~/ns-hotopic/state/storage_state.json
```

## How `storage_state.json` Works with Docker Compose

The compose file mounts these host directories into the container:

- `./state:/app/state`
- `./data:/app/data`
- `./artifacts:/app/artifacts`

So if the file exists on the VPS at:

```text
./state/storage_state.json
```

it becomes available inside the container at:

```text
/app/state/storage_state.json
```

You do not need to copy it into the container manually.

## Start the Service

Build from source:

```bash
docker compose up -d --build
```

Use the GHCR image instead:

```dotenv
NS_HOTOPIC_IMAGE=ghcr.io/impersonality/ns-hotopic:latest
```

```bash
docker compose pull
docker compose up -d
```

## Useful Commands

Local debugging:

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

Compose logs:

```bash
docker compose logs -f
```

Stop the service:

```bash
docker compose down
```

## Telegram Bot

- `/hot`
- `/lottery`
- `/subscribe`
- `/unsubscribe`
- `/help`

## Common Questions

### Does `storage_state.json` expire?

Yes. If it stops working, run:

```bash
uv run ns-hotopic trial-once
```

Then upload the new file again.

### Why don't I see a Docker image yet?

The Docker publish workflow runs on:

- pushes to `main`
- version tags like `v0.1.0`

To publish the first version image manually:

```bash
git tag v0.1.0
git push origin v0.1.0
```
