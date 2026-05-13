# MAX Multi AI Bot

Production-ready bot for MAX messenger with OpenRouter models, image generation, plans, limits, and admin controls.

## Features

- Text models via OpenRouter (`DeepSeek`, `GPT`, `Gemini`, `GPT-5.4`)
- Image generation
- Public landing pages (`/`, `/offer`, `/privacy`, `/refund`, `/contacts`, `/support`)
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
MAX_TEXT_INPUT_CHARS=2500
MAX_IMAGE_PROMPT_CHARS=800
MAX_ASSISTANT_OUTPUT_CHARS=1800
MAX_CONTEXT_CHARS=7000
MESSAGE_COOLDOWN_SECONDS=1
IMAGE_COOLDOWN_SECONDS=20
FREE_DAILY_MESSAGES_LIMIT=40
START_DAILY_MESSAGES_LIMIT=120
PRO_DAILY_MESSAGES_LIMIT=300
FREE_DAILY_IMAGES_LIMIT=0
START_DAILY_IMAGES_LIMIT=3
PRO_DAILY_IMAGES_LIMIT=8
PRO_DAILY_GPT54_LIMIT=8
MAX_COMPLETION_TOKENS_FREE=500
MAX_COMPLETION_TOKENS_START=650
MAX_COMPLETION_TOKENS_PRO=800
START_PLAN_PRICE_RUB=990
PRO_PLAN_PRICE_RUB=2990
START_PLAN_DAYS=30
PRO_PLAN_DAYS=30

WEBHOOK_SECRET=strong_random_secret
PAYMENT_DETAILS_TEXT=Оплата на ИП ...\\nБанк: ...\\nР/с: ...
PUBLIC_BASE_URL=https://your-domain
TBANK_TERMINAL_KEY=
TBANK_PASSWORD=
TBANK_INIT_URL=https://securepay.tinkoff.ru/v2/Init
TBANK_NOTIFICATION_URL=
TBANK_SUCCESS_URL=
TBANK_FAIL_URL=
SUPPORT_URL=
SUPPORT_TEXT=Поддержка: напиши нам, поможем быстро.
```

## Commands

- `/start`, `/menu`, `/help`
- `/models`
- `/plan`
- `/tariffs`
- `/buy <start|pro>`
- `/payments`
- `/support`
- `/model <alias>`
- `/gpt`, `/gemini`, `/deepseek`, `/gpt54`
- `/image <prompt>`
- `/clear`

Admin (`ADMIN_IDS` only):
- `/admin help`
- `/admin user <chat_id>`
- `/admin plan <chat_id> <free|start|pro>`
- `/admin sub <chat_id> <start|pro> <days>`
- `/admin block <chat_id> <on|off>`
- `/admin pay <request_id> <paid|cancel>`
- `/costs`

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

## T-Bank Webhook

Use webhook URL:

```text
https://your-domain/webhook/tbank
```
