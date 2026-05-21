# AGENTS.md

## Project

MAX AI bot with:
- text answers through OpenRouter
- image generation
- tariffs, credits, promo/referral mechanics
- T-Bank payments
- static website in `site/`

Main app entrypoint:
- `C:\Users\nikit\Desktop\max_ai_agent\main.py`

Important folders:
- `C:\Users\nikit\Desktop\max_ai_agent\site` — public website pages
- `C:\Users\nikit\Desktop\max_ai_agent\deploy` — nginx/deploy config
- `C:\Users\nikit\Desktop\max_ai_agent\data` — runtime DB/data
- `C:\Users\nikit\Desktop\max_ai_agent\.github\workflows` — VPS autodeploy

## Stack

- Python 3
- FastAPI / Uvicorn
- SQLite
- Docker / Docker Compose
- OpenRouter
- MAX Bot API
- T-Bank payments

## Local checks

Before finishing code changes, run:

```powershell
@'
import py_compile
py_compile.compile("main.py", doraise=True)
print("OK")
'@ | python -
```

If UI/payment text was changed, also grep key strings to ensure old copy is not left behind.

## Deploy

Production deploy is triggered by push to `master`.

Workflow:
- GitHub Actions connects to VPS over SSH
- clones repo into `/root/max_ai_agent/.deploy_tmp`
- preserves server-only files and folders:
  - `.env`
  - `data`
  - `logs`
- rebuilds and restarts Docker service `bot`

Important:
- repo changes do **not** update VPS `.env`
- if pricing, limits, or flags are overridden in VPS `.env`, user must update them manually

## Secrets

Never commit real secrets.

Do not print or rewrite:
- `MAX_TOKEN`
- `OPENROUTER_KEY`
- `TBANK_PASSWORD`
- SSH private keys

Use `.env.example` only for documented placeholders/defaults.

## Product rules

These are important project-specific UX rules:

- User identity must be bound to stable MAX `user_id`; `chat_id` is only the current dialog route
- If MAX creates a new `chat_id` after chat deletion/restart, subscription and free-credit state must follow the same user
- Only model answers should create a fresh new message
- UI screens should update/replace the current managed message
- Replies after model output may open a new managed screen
- Onboarding should not remain interactive after completion/skip
- If a flow requests promo/ref code input, leaving that flow must clear pending input state
- Payment flows should avoid duplicate “back” actions; every page should have access to `Меню`
- Do not enable bonuses that cannot be verified honestly
- Channel subscription gate must use MAX membership verification; promo codes are for attribution, not proof of subscription
- Referral flow should keep the primary UX simple: MAX share sheet + `Бонусы` -> `Ввести реф-код`
- Referral analytics should surface top referrers and suspicious invite clusters before adding any automated anti-fraud actions
- Ads that lead to the channel should be measured with campaign promo codes, not many different bot links

## Payments

T-Bank flow requirements:
- do not start payment without buyer contact for receipt
- recurring consent must be explicit before subscription payment
- payment status screen should keep payment URL available
- refund-related changes must keep plan/credits consistent

## Website

If changing pricing, support, offer, refund, or help logic, verify matching copy in:
- `site/index.html`
- `site/offer.html`
- `site/support.html`
- `site/contacts.html`
- `site/privacy.html`
- `site/refund.html`

## Editing guidance

- Prefer targeted fixes over broad rewrites
- Keep Russian user-facing copy concise and clear
- Avoid hidden product behavior that changes economics without being reflected in UI text
- When changing callbacks or button flows, verify:
  - current screen replacement
  - back navigation
  - pending state cleanup
  - no duplicate callback responses
