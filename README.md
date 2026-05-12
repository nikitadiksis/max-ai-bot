# MAX Multi AI Bot

Production-ready bot for MAX messenger with OpenRouter models, image generation, plans, limits, and admin controls.

## Features

- Text models via OpenRouter (`DeepSeek`, `GPT`, `Gemini`, `GPT-5.4`)
- Image generation
- Per-user plans (`free`, `start`, `pro`)
- Daily limits for text and images
- Model access by plan
- SQLite persistence for users, plan, usage counters
- Webhook deduplication
- Inline menu and onboarding
- Admin commands

## Files

- `main.py` — bot app
- `models.json` — model catalog (versions, prices, plan access)
- `.env` — secrets and runtime config
- `.env.example` — env template
- `docker-compose.yml` — runtime
- `Dockerfile` — container build

## Setup

```bash
pip install -r requirements.txt
```

## Environment

```env
MAX_TOKEN=your_max_token
OPENROUTER_KEY=your_openrouter_key

RUN_MODE=webhook
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log

DEFAULT_TEXT_MODEL=gpt
DEFAULT_IMAGE_MODEL=image
HISTORY_LIMIT=20
MAX_MESSAGE_LEN=3900
DEDUP_CACHE_SIZE=300
DB_PATH=data/bot.sqlite3
ADMIN_IDS=123456789

WEBHOOK_SECRET=strong_random_secret
```

## Commands

- `/start`, `/menu`, `/help`
- `/models`
- `/plan`
- `/tariffs`
- `/model <alias>`
- `/gpt`, `/gemini`, `/deepseek`, `/gpt54`
- `/image <prompt>`
- `/clear`

Admin (`ADMIN_IDS` only):
- `/admin help`
- `/admin user <chat_id>`
- `/admin plan <chat_id> <free|start|pro>`
- `/admin block <chat_id> <on|off>`

## Deploy (Docker)

```bash
docker compose up -d --build bot
```

Health check:

```bash
curl https://your-domain/health
```

## MAX Webhook Subscription

Create subscription:

```bash
curl -X POST "https://platform-api.max.ru/subscriptions" \
  -H "Authorization: YOUR_MAX_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-domain/webhook/max",
    "update_types": ["message_created", "message_callback", "bot_started", "user_added", "bot_added"],
    "secret": "your_strong_secret"
  }'
```

Check subscriptions:

```bash
curl -X GET "https://platform-api.max.ru/subscriptions" \
  -H "Authorization: YOUR_MAX_TOKEN"
```
