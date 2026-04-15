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
Automated fetches only read it by default and do not overwrite it after headless runs.

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

The [docker-compose.yml](/home/kg/Code/python/ns_hotopic/docker-compose.yml) file mounts these host directories into the container:

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

By default the compose file uses the image published by GitHub Actions:

```bash
docker compose pull
docker compose up -d
```

You can override the image in `.env` if needed:

```dotenv
NS_HOTOPIC_IMAGE=ghcr.io/impersonality/ns-hotopic:latest
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

### Why does a locally generated `storage_state.json` only work once on my VPS?

This is usually not a Docker volume problem. Cloudflare may evaluate:

- egress IP
- browser fingerprint
- whether the browser is headless
- cookie / clearance context

So a state file exported from your local browser and copied to a different VPS can only be treated as a best-effort reuse. It is not guaranteed to remain stable across IP and environment changes.

The project now avoids rewriting `storage_state.json` during `fetch-once` and `service-run`, so a headless fetch does not poison a previously working state file. If the copied file still works only once on your VPS, the more likely issue is that the VPS egress IP or runtime fingerprint is being challenged again. In that case, the more reliable options are:

- generate `storage_state.json` in an environment closer to the final egress IP
- switch to a cleaner VPS or proxy egress

### Why don't I see a Docker image yet?

The Docker publish workflow runs on:

- pushes to `main`
- version tags like `v0.1.0`

To publish the first version image manually:

```bash
git tag v0.1.0
git push origin v0.1.0
```
