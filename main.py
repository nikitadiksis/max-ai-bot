from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager, suppress
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import html
from io import BytesIO
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sqlite3
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import PlainTextResponse
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
import uvicorn

load_dotenv()


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "models.json"
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
SITE_DIR = BASE_DIR / "site"
LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

MAX_API = "https://platform-api.max.ru"
OPENROUTER_CHAT_API = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MAX_MESSAGE_LEN = 3900

MAX_TOKEN = os.getenv("MAX_TOKEN", "").strip()
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "").strip()
RUN_MODE = os.getenv("RUN_MODE", "polling").strip().lower()
HOST = os.getenv("HOST", "0.0.0.0").strip()
PORT = int(os.getenv("PORT", "8000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", str(LOGS_DIR / "bot.log"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
DEFAULT_TEXT_MODEL_ALIAS = os.getenv("DEFAULT_TEXT_MODEL", "gpt").strip().lower() or "gpt"
DEFAULT_IMAGE_MODEL_ALIAS = os.getenv("DEFAULT_IMAGE_MODEL", "image").strip().lower() or "image"
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "20"))
MAX_MESSAGE_LEN = int(os.getenv("MAX_MESSAGE_LEN", str(DEFAULT_MAX_MESSAGE_LEN)))
DEDUP_CACHE_SIZE = int(os.getenv("DEDUP_CACHE_SIZE", "300"))
DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "bot.sqlite3")))
MAX_TEXT_INPUT_CHARS = int(os.getenv("MAX_TEXT_INPUT_CHARS", "2500"))
MAX_IMAGE_PROMPT_CHARS = int(os.getenv("MAX_IMAGE_PROMPT_CHARS", "800"))
MAX_ASSISTANT_OUTPUT_CHARS = int(os.getenv("MAX_ASSISTANT_OUTPUT_CHARS", "1400"))
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "7000"))
MESSAGE_COOLDOWN_SECONDS = int(os.getenv("MESSAGE_COOLDOWN_SECONDS", "1"))
IMAGE_COOLDOWN_SECONDS = int(os.getenv("IMAGE_COOLDOWN_SECONDS", "20"))
LITE_PLAN_PRICE_RUB = int(os.getenv("LITE_PLAN_PRICE_RUB", "390"))
START_PLAN_PRICE_RUB = int(os.getenv("START_PLAN_PRICE_RUB", "990"))
PRO_PLAN_PRICE_RUB = int(os.getenv("PRO_PLAN_PRICE_RUB", "2490"))
LITE_PLAN_DAYS = int(os.getenv("LITE_PLAN_DAYS", "30"))
START_PLAN_DAYS = int(os.getenv("START_PLAN_DAYS", "30"))
PRO_PLAN_DAYS = int(os.getenv("PRO_PLAN_DAYS", "30"))
FREE_DAILY_MESSAGES_LIMIT = int(os.getenv("FREE_DAILY_MESSAGES_LIMIT", "40"))
LITE_DAILY_MESSAGES_LIMIT = int(os.getenv("LITE_DAILY_MESSAGES_LIMIT", "80"))
START_DAILY_MESSAGES_LIMIT = int(os.getenv("START_DAILY_MESSAGES_LIMIT", "120"))
PRO_DAILY_MESSAGES_LIMIT = int(os.getenv("PRO_DAILY_MESSAGES_LIMIT", "300"))
FREE_DAILY_IMAGES_LIMIT = int(os.getenv("FREE_DAILY_IMAGES_LIMIT", "0"))
LITE_DAILY_IMAGES_LIMIT = int(os.getenv("LITE_DAILY_IMAGES_LIMIT", "1"))
START_DAILY_IMAGES_LIMIT = int(os.getenv("START_DAILY_IMAGES_LIMIT", "3"))
PRO_DAILY_IMAGES_LIMIT = int(os.getenv("PRO_DAILY_IMAGES_LIMIT", "8"))
PRO_DAILY_GPT54_LIMIT = int(os.getenv("PRO_DAILY_GPT54_LIMIT", "0"))
FREE_DAILY_CREDITS = int(os.getenv("FREE_DAILY_CREDITS", "40"))
MAX_COMPLETION_TOKENS_FREE = int(os.getenv("MAX_COMPLETION_TOKENS_FREE", "500"))
MAX_COMPLETION_TOKENS_LITE = int(os.getenv("MAX_COMPLETION_TOKENS_LITE", "550"))
MAX_COMPLETION_TOKENS_START = int(os.getenv("MAX_COMPLETION_TOKENS_START", "650"))
MAX_COMPLETION_TOKENS_PRO = int(os.getenv("MAX_COMPLETION_TOKENS_PRO", "800"))
LITE_PLAN_CREDITS = int(os.getenv("LITE_PLAN_CREDITS", "5500"))
START_PLAN_CREDITS = int(os.getenv("START_PLAN_CREDITS", "15000"))
PRO_PLAN_CREDITS = int(os.getenv("PRO_PLAN_CREDITS", "40000"))
CREDIT_COST_DEEPSEEK = int(os.getenv("CREDIT_COST_DEEPSEEK", "1"))
CREDIT_COST_GPT = int(os.getenv("CREDIT_COST_GPT", "3"))
CREDIT_COST_GPTO = int(os.getenv("CREDIT_COST_GPTO", "4"))
CREDIT_COST_GEMINI = int(os.getenv("CREDIT_COST_GEMINI", "5"))
CREDIT_COST_GPT54 = int(os.getenv("CREDIT_COST_GPT54", "20"))
CREDIT_COST_IMAGE = int(os.getenv("CREDIT_COST_IMAGE", "35"))
CREDIT_COST_IMAGE_EDIT = int(os.getenv("CREDIT_COST_IMAGE_EDIT", "55"))
VAR_CREDITS_PER_1K_DEEPSEEK = int(os.getenv("VAR_CREDITS_PER_1K_DEEPSEEK", "0"))
VAR_CREDITS_PER_1K_GPT = int(os.getenv("VAR_CREDITS_PER_1K_GPT", "1"))
VAR_CREDITS_PER_1K_GPTO = int(os.getenv("VAR_CREDITS_PER_1K_GPTO", "1"))
VAR_CREDITS_PER_1K_GEMINI = int(os.getenv("VAR_CREDITS_PER_1K_GEMINI", "2"))
VAR_CREDITS_PER_1K_GPT54 = int(os.getenv("VAR_CREDITS_PER_1K_GPT54", "4"))
MAX_VARIABLE_CREDITS_PER_TEXT = int(os.getenv("MAX_VARIABLE_CREDITS_PER_TEXT", "4"))
TOPUP_SMALL_PRICE_RUB = int(os.getenv("TOPUP_SMALL_PRICE_RUB", "199"))
TOPUP_SMALL_CREDITS = int(os.getenv("TOPUP_SMALL_CREDITS", "1200"))
TOPUP_MEDIUM_PRICE_RUB = int(os.getenv("TOPUP_MEDIUM_PRICE_RUB", "499"))
TOPUP_MEDIUM_CREDITS = int(os.getenv("TOPUP_MEDIUM_CREDITS", "3200"))
TOPUP_LARGE_PRICE_RUB = int(os.getenv("TOPUP_LARGE_PRICE_RUB", "990"))
TOPUP_LARGE_CREDITS = int(os.getenv("TOPUP_LARGE_CREDITS", "7000"))
TOPUP_QUICK_CODE = os.getenv("TOPUP_QUICK_CODE", "medium").strip().lower() or "medium"
LOW_CREDITS_NUDGE_THRESHOLD_FREE = int(os.getenv("LOW_CREDITS_NUDGE_THRESHOLD_FREE", "10"))
LOW_CREDITS_NUDGE_THRESHOLD_PAID = int(os.getenv("LOW_CREDITS_NUDGE_THRESHOLD_PAID", "120"))
LOW_CREDITS_NUDGE_COOLDOWN_HOURS = int(os.getenv("LOW_CREDITS_NUDGE_COOLDOWN_HOURS", "18"))
PAYMENT_DETAILS_TEXT = os.getenv(
    "PAYMENT_DETAILS_TEXT",
    "Реквизиты не настроены. Напиши администратору для оплаты.",
).replace("\\n", "\n").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
TBANK_TERMINAL_KEY = os.getenv("TBANK_TERMINAL_KEY", "").strip()
TBANK_PASSWORD = os.getenv("TBANK_PASSWORD", "").strip()
TBANK_INIT_URL = os.getenv("TBANK_INIT_URL", "https://securepay.tinkoff.ru/v2/Init").strip()
TBANK_GET_STATE_URL = os.getenv("TBANK_GET_STATE_URL", "https://securepay.tinkoff.ru/v2/GetState").strip()
TBANK_NOTIFICATION_URL = os.getenv("TBANK_NOTIFICATION_URL", "").strip()
TBANK_SUCCESS_URL = os.getenv("TBANK_SUCCESS_URL", "").strip()
TBANK_FAIL_URL = os.getenv("TBANK_FAIL_URL", "").strip()
TBANK_RECEIPT_TAXATION = os.getenv("TBANK_RECEIPT_TAXATION", "usn_income").strip()
TBANK_RECEIPT_TAX = os.getenv("TBANK_RECEIPT_TAX", "none").strip()
TBANK_RECEIPT_PAYMENT_METHOD = os.getenv("TBANK_RECEIPT_PAYMENT_METHOD", "full_prepayment").strip()
TBANK_RECEIPT_PAYMENT_OBJECT = os.getenv("TBANK_RECEIPT_PAYMENT_OBJECT", "service").strip()
TBANK_RECEIPT_FFD_VERSION = os.getenv("TBANK_RECEIPT_FFD_VERSION", "1.05").strip()
TBANK_CANCEL_STATUSES = {"REJECTED", "CANCELED", "DEADLINE_EXPIRED"}
TBANK_REFUND_STATUSES = {"REFUNDED", "REVERSED", "PARTIAL_REVERSED", "PARTIAL_REFUNDED", "CHARGEDBACK"}
TBANK_SUCCESS_STATUSES = {"CONFIRMED"}
PAYMENT_FINAL_STATUSES = {"paid", "canceled", "refunded"}
PAYMENT_STATUS_LABELS = {
    "pending": "Ожидает оплату",
    "claimed": "Проверка оплаты",
    "paid": "Оплачено",
    "canceled": "Отменено",
    "refunded": "Возврат",
    "unknown": "Неизвестно",
}
SUPPORT_URL = os.getenv("SUPPORT_URL", "").strip()
SUPPORT_TEXT = os.getenv("SUPPORT_TEXT", "Поддержка: напиши нам, поможем быстро.").strip()
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "support@aimaxbots.ru").strip()
CONTACT_PHONE = os.getenv("CONTACT_PHONE", "").strip()
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://max.ru/id231128398751_biz").strip()
REFERRAL_BONUS_CREDITS = int(os.getenv("REFERRAL_BONUS_CREDITS", "120"))
PROMO_WELCOME_CREDITS = int(os.getenv("PROMO_WELCOME_CREDITS", "0"))
PROMO_CODES_RAW = os.getenv("PROMO_CODES", "").strip()
CHANNEL_PROMO_ENABLED = os.getenv("CHANNEL_PROMO_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
CHANNEL_PROMO_CODE = os.getenv("CHANNEL_PROMO_CODE", "CHANNEL").strip()
CHANNEL_PROMO_CREDITS = int(os.getenv("CHANNEL_PROMO_CREDITS", "70"))
CHANNEL_PROMO_START_DATE = os.getenv("CHANNEL_PROMO_START_DATE", datetime.utcnow().date().isoformat()).strip()
CHANNEL_PROMO_CAMPAIGN_DAYS = int(os.getenv("CHANNEL_PROMO_CAMPAIGN_DAYS", "7"))
CHANNEL_PROMO_BONUS_TTL_DAYS = int(os.getenv("CHANNEL_PROMO_BONUS_TTL_DAYS", "7"))
ADMIN_PANEL_TOKEN = os.getenv("ADMIN_PANEL_TOKEN", "").strip()
BACKUP_KEEP_FILES = int(os.getenv("BACKUP_KEEP_FILES", "12"))
ERROR_ALERT_COOLDOWN_SEC = int(os.getenv("ERROR_ALERT_COOLDOWN_SEC", "120"))
ERROR_ALERTS_ENABLED = os.getenv("ERROR_ALERTS_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
REENGAGE_DORMANT_DAYS = int(os.getenv("REENGAGE_DORMANT_DAYS", "5"))
REENGAGE_BATCH_LIMIT = int(os.getenv("REENGAGE_BATCH_LIMIT", "30"))
SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "production").strip() or "production"
REFERENCE_IMAGE_TTL_MINUTES = int(os.getenv("REFERENCE_IMAGE_TTL_MINUTES", "180"))
ADMIN_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
}

SYSTEM_PROMPT_BASE = (
    "Ты полезный AI-ассистент в мессенджере MAX. "
    "Отвечай по-русски, если пользователь не попросил иначе. "
    "Не упоминай внутренние технические детали без необходимости. "
    "По умолчанию отвечай кратко и легко для чтения: 2-4 коротких абзаца или 3-5 коротких пунктов. "
    "Не используй длинные нумерованные списки и тяжелое оформление без необходимости. "
    "Старайся писать простым живым языком, без воды. "
    "Если тема большая, дай сжатый ответ и не обрывай фразу на полуслове."
)

STYLE_PROMPTS = {
    "gpt": "Стиль: четко структурируй ответ, хорошо объясняй шаги и варианты.",
    "gpt4o": "Стиль: отвечай живо, понятно и по делу, с хорошими примерами.",
    "gemini": "Стиль: отвечай быстро, дружелюбно и с упором на практический результат.",
    "deepseek": "Стиль: делай упор на рассуждение, анализ и техническую точность.",
    "gpt54": "Стиль: отвечай как эксперт-консультант, глубоко и обоснованно.",
}

PLAN_ORDER = {"free": 0, "lite": 1, "start": 2, "pro": 3}
PAID_PLANS = {"lite", "start", "pro"}
BUYABLE_PLANS = {"lite", "start", "pro"}
IMAGE_STYLE_OPTIONS: dict[str, tuple[str, str]] = {
    "auto": ("Авто", ""),
    "photo": ("Фото", "photorealistic style, natural lighting"),
    "anime": ("Аниме", "anime style, clean line art"),
    "art": ("Арт", "digital art illustration, cinematic composition"),
}
IMAGE_ASPECT_OPTIONS: dict[str, tuple[str, str]] = {
    "square": ("1:1", "square composition"),
    "portrait": ("9:16", "vertical composition"),
    "landscape": ("16:9", "horizontal composition"),
}
DEFAULT_IMAGE_STYLE = "auto"
DEFAULT_IMAGE_ASPECT = "square"

WELCOME_TEXT = (
    "Привет. Это твой AI-бот в MAX.\n\n"
    "Что умею:\n"
    "• ответы через GPT, Gemini и DeepSeek\n"
    "• генерация картинок\n"
    "• сохранение контекста диалога\n\n"
    "Выбери действие кнопками или просто напиши вопрос."
)

MENU_TEXT = (
    "Кнопки ниже — основной способ пользоваться ботом.\n"
    "Для генерации картинки нажми «🎨 Картинка».\n"
    "Если нужен список команд, отправь /help\n"
    "Если проблема с оплатой — нажми «Помощь» или отправь /support\n"
    "Новости и обновления: /channel"
)

HELP_TEXT = (
    "Справка\n\n"
    "Основной способ пользоваться ботом — кнопки ниже.\n"
    "Команды пригодятся, если нужно быстрое действие:\n\n"
    "/start или /menu — меню\n"
    "/id — твой chat_id\n"
    "/models — версии и описание моделей\n"
    "/plan — твой тариф и остатки\n"
    "/preset <fast|balanced|quality|expert> — выбрать режим\n"
    "/model <alias> — выбрать модель вручную\n"
    "/gpt /gpt4o /gemini /deepseek /gpt54 — быстрый выбор модели\n"
    "/image <описание> — сгенерировать картинку\n"
    "/image_ref <описание> — сгенерировать по последнему фото\n"
    "/tariffs — тарифы\n"
    "/topup — пакеты кредитов\n"
    "/buy <lite|start|pro> — заявка на подписку\n"
    "/payments — мои заявки\n"
    "/ref [код] — реферальный код и активация\n"
    "/promo <код> — активировать промокод\n"
    "/channel — наш канал\n"
    "/credits — остаток кредитов\n"
    "/support — помощь по оплате и работе бота\n"
    "/clear — очистить контекст"
)

ADMIN_HELP_TEXT = (
    "\n\nАдмин:\n"
    "/admin help\n"
    "/admin user <chat_id>\n"
    "/admin plan <chat_id> <free|lite|start|pro>\n"
    "/admin sub <chat_id> <lite|start|pro> <days>\n"
    "/admin block <chat_id> <on|off>\n"
    "/admin pay <request_id> <paid|cancel>\n"
    "/admin templates\n"
    "/admin backup\n"
    "/admin nudge [days] [limit]\n"
    "/admin kpi [days]\n"
    "/admin panel\n"
    "/costs — модели и цены\n"
    "/id — твой chat_id"
)

TARIFFS_TEXT = (
    "Тарифы:\n"
    "• free: дневной бонус кредитов\n"
    "• lite/start/pro: доступ по кредитам\n\n"
    "Модели по тарифам:\n"
    "• free: DeepSeek V4 Flash, GPT-4.1 Nano\n"
    "• lite/start: + GPT-4o Mini и Gemini 2.5 Flash\n"
    "• pro: + GPT-5.4"
)

BUY_TEXT = (
    "Покупка (пока в ручном режиме):\n"
    "/buy lite — заявка на Lite\n"
    "/buy start — заявка на Start\n"
    "/buy pro — заявка на Pro\n"
    "/payments — мои заявки\n\n"
    "После заявки админ подтверждает оплату и активирует подписку."
)


@dataclass(slots=True)
class PlanInfo:
    name: str
    daily_messages_limit: int
    daily_images_limit: int
    daily_gpt54_limit: int


PLAN_CONFIGS = {
    "free": PlanInfo(
        name="free",
        daily_messages_limit=FREE_DAILY_MESSAGES_LIMIT,
        daily_images_limit=FREE_DAILY_IMAGES_LIMIT,
        daily_gpt54_limit=0,
    ),
    "lite": PlanInfo(
        name="lite",
        daily_messages_limit=LITE_DAILY_MESSAGES_LIMIT,
        daily_images_limit=LITE_DAILY_IMAGES_LIMIT,
        daily_gpt54_limit=0,
    ),
    "start": PlanInfo(
        name="start",
        daily_messages_limit=START_DAILY_MESSAGES_LIMIT,
        daily_images_limit=START_DAILY_IMAGES_LIMIT,
        daily_gpt54_limit=0,
    ),
    "pro": PlanInfo(
        name="pro",
        daily_messages_limit=PRO_DAILY_MESSAGES_LIMIT,
        daily_images_limit=PRO_DAILY_IMAGES_LIMIT,
        daily_gpt54_limit=PRO_DAILY_GPT54_LIMIT,
    ),
}

PLAN_CREDITS = {
    "free": 0,
    "lite": LITE_PLAN_CREDITS,
    "start": START_PLAN_CREDITS,
    "pro": PRO_PLAN_CREDITS,
}

MODEL_CREDIT_COSTS = {
    "deepseek": CREDIT_COST_DEEPSEEK,
    "gpt": CREDIT_COST_GPT,
    "gpt4o": CREDIT_COST_GPTO,
    "gemini": CREDIT_COST_GEMINI,
    "gpt54": CREDIT_COST_GPT54,
}

MODEL_VAR_CREDITS_PER_1K = {
    "deepseek": VAR_CREDITS_PER_1K_DEEPSEEK,
    "gpt": VAR_CREDITS_PER_1K_GPT,
    "gpt4o": VAR_CREDITS_PER_1K_GPTO,
    "gemini": VAR_CREDITS_PER_1K_GEMINI,
    "gpt54": VAR_CREDITS_PER_1K_GPT54,
}

MODEL_PRESETS: dict[str, dict[str, Any]] = {
    "fast": {
        "label": "⚡ Быстро",
        "description": "короткие и быстрые ответы",
        "aliases": ["deepseek", "gpt"],
    },
    "balanced": {
        "label": "⚖ Баланс",
        "description": "ежедневные задачи и диалог",
        "aliases": ["gpt4o", "gpt", "deepseek"],
    },
    "quality": {
        "label": "🧠 Качество",
        "description": "подробно и аккуратно",
        "aliases": ["gemini", "gpt4o", "gpt"],
    },
    "expert": {
        "label": "🚀 Эксперт",
        "description": "максимум качества для сложных задач",
        "aliases": ["gpt54", "gemini", "gpt4o", "gpt"],
    },
}

TOPUP_PACKS = {
    "small": {
        "label": "Small",
        "price_rub": TOPUP_SMALL_PRICE_RUB,
        "credits": TOPUP_SMALL_CREDITS,
    },
    "medium": {
        "label": "Medium",
        "price_rub": TOPUP_MEDIUM_PRICE_RUB,
        "credits": TOPUP_MEDIUM_CREDITS,
    },
    "large": {
        "label": "Large",
        "price_rub": TOPUP_LARGE_PRICE_RUB,
        "credits": TOPUP_LARGE_CREDITS,
    },
}


@dataclass(slots=True)
class ImageResult:
    image_bytes: bytes
    mime_type: str


@dataclass(slots=True)
class TextAnswerResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(slots=True)
class ModelInfo:
    alias: str
    provider: str
    model: str
    label: str
    kind: str
    version: str
    input_price_usd_per_m: str
    output_price_usd_per_m: str
    min_plan: str
    description: str
    prompt_style: str


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("max_ai_agent")
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger


log = configure_logging()


def to_base36(value: int) -> str:
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if value <= 0:
        return "0"
    out: list[str] = []
    n = value
    while n:
        n, rem = divmod(n, 36)
        out.append(alphabet[rem])
    return "".join(reversed(out))


def referral_code_for_chat(chat_id: int) -> str:
    return f"RF{to_base36(chat_id).zfill(6)}"


def normalize_referral_code(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.strip().upper())


def parse_date_ymd(value: str) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except Exception:
        return None


def channel_promo_meta(today: date | None = None) -> dict[str, Any]:
    promo_code = normalize_referral_code(CHANNEL_PROMO_CODE)
    start = parse_date_ymd(CHANNEL_PROMO_START_DATE) or datetime.utcnow().date()
    duration_days = max(1, CHANNEL_PROMO_CAMPAIGN_DAYS)
    end_exclusive = start + timedelta(days=duration_days)
    current = today or datetime.utcnow().date()
    active = (
        CHANNEL_PROMO_ENABLED
        and bool(promo_code)
        and CHANNEL_PROMO_CREDITS > 0
        and start <= current < end_exclusive
    )
    days_left = max(0, (end_exclusive - current).days)
    return {
        "enabled": False,
        "active": False,
        "code": promo_code,
        "credits": max(0, CHANNEL_PROMO_CREDITS),
        "start": start,
        "end_exclusive": end_exclusive,
        "days_left": days_left,
        "bonus_ttl_days": max(0, CHANNEL_PROMO_BONUS_TTL_DAYS),
    }


def promo_offer_for_code(code: str) -> tuple[int, int, str]:
    promo_code = normalize_referral_code(code)
    if not promo_code:
        return 0, 0, "Пустой промокод."

    channel = channel_promo_meta()
    if promo_code == channel["code"] and channel["enabled"]:
        if channel["active"]:
            return int(channel["credits"]), int(channel["bonus_ttl_days"]), ""
        if datetime.utcnow().date() < channel["start"]:
            return 0, 0, f"Акция еще не началась (старт: {channel['start'].isoformat()})."
        return 0, 0, "Акция по этому промокоду завершена."

    credits = int(promo_catalog().get(promo_code, 0) or 0)
    if credits > 0:
        return credits, 0, ""
    return 0, 0, "Такого промокода нет или он выключен."


def promo_catalog() -> dict[str, int]:
    catalog: dict[str, int] = {}
    if PROMO_WELCOME_CREDITS > 0:
        catalog["WELCOME"] = int(PROMO_WELCOME_CREDITS)
    raw = PROMO_CODES_RAW
    if not raw:
        return {k: v for k, v in catalog.items() if v > 0}
    for chunk in raw.split(","):
        part = chunk.strip()
        if not part or ":" not in part:
            continue
        key_raw, val_raw = part.split(":", 1)
        key = normalize_referral_code(key_raw)
        if not key:
            continue
        try:
            value = int(val_raw.strip())
        except Exception:
            continue
        if value > 0:
            catalog[key] = value
    return {k: v for k, v in catalog.items() if v > 0}


class UserStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    chat_id INTEGER PRIMARY KEY,
                    max_user_id INTEGER NOT NULL DEFAULT 0,
                    plan TEXT NOT NULL DEFAULT 'free',
                    is_blocked INTEGER NOT NULL DEFAULT 0,
                    onboarding_done INTEGER NOT NULL DEFAULT 0,
                    referral_code TEXT NOT NULL DEFAULT '',
                    referred_by_chat_id INTEGER NOT NULL DEFAULT 0,
                    referrals_invited INTEGER NOT NULL DEFAULT 0,
                    receipt_email TEXT NOT NULL DEFAULT '',
                    receipt_phone TEXT NOT NULL DEFAULT '',
                    selected_model_alias TEXT NOT NULL DEFAULT '',
                    selected_preset TEXT NOT NULL DEFAULT '',
                    subscription_expires_at TEXT NOT NULL DEFAULT '',
                    recurring_enabled INTEGER NOT NULL DEFAULT 0,
                    recurring_cancel_from TEXT NOT NULL DEFAULT '',
                    recurring_canceled_at TEXT NOT NULL DEFAULT '',
                    usage_date TEXT NOT NULL DEFAULT '',
                    daily_messages_used INTEGER NOT NULL DEFAULT 0,
                    daily_images_used INTEGER NOT NULL DEFAULT 0,
                    daily_gpt54_used INTEGER NOT NULL DEFAULT 0,
                    free_image_week_key TEXT NOT NULL DEFAULT '',
                    free_image_week_used INTEGER NOT NULL DEFAULT 0,
                    free_image_last_used_at TEXT NOT NULL DEFAULT '',
                    credits_balance INTEGER NOT NULL DEFAULT 0,
                    credits_spent_total INTEGER NOT NULL DEFAULT 0,
                    last_active_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS payment_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    plan TEXT NOT NULL,
                    days INTEGER NOT NULL,
                    amount_rub INTEGER NOT NULL,
                    recurring_consent INTEGER NOT NULL DEFAULT 0,
                    recurring_consent_at TEXT NOT NULL DEFAULT '',
                    recurring_consent_text TEXT NOT NULL DEFAULT '',
                    receipt_email TEXT NOT NULL DEFAULT '',
                    receipt_phone TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    provider TEXT NOT NULL DEFAULT 'manual',
                    provider_ref TEXT NOT NULL DEFAULT '',
                    payment_url TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT '',
                    paid_at TEXT NOT NULL DEFAULT '',
                    activated_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    plan TEXT NOT NULL DEFAULT '',
                    model_alias TEXT NOT NULL DEFAULT '',
                    credits_spent INTEGER NOT NULL DEFAULT 0,
                    rub_amount INTEGER NOT NULL DEFAULT 0,
                    tokens_total INTEGER NOT NULL DEFAULT 0,
                    details TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS promo_activations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    promo_code TEXT NOT NULL,
                    credits INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT '',
                    UNIQUE(chat_id, promo_code)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS promo_bonus_grants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    promo_code TEXT NOT NULL,
                    amount_total INTEGER NOT NULL DEFAULT 0,
                    amount_remaining INTEGER NOT NULL DEFAULT 0,
                    expires_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT '',
                    expired_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            self._ensure_column(conn, "users", "subscription_expires_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "max_user_id", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "recurring_enabled", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "recurring_cancel_from", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "recurring_canceled_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "receipt_email", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "receipt_phone", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "selected_preset", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "onboarding_done", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "referral_code", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "referred_by_chat_id", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "referrals_invited", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "last_active_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "daily_gpt54_used", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "free_image_week_key", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "free_image_week_used", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "free_image_last_used_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "credits_balance", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "credits_spent_total", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "payment_requests", "recurring_consent", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "payment_requests", "recurring_consent_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "payment_requests", "recurring_consent_text", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "payment_requests", "receipt_email", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "payment_requests", "receipt_phone", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "payment_requests", "payment_url", "TEXT NOT NULL DEFAULT ''")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_promo_activations_unique ON promo_activations(chat_id, promo_code)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_max_user_id_unique ON users(max_user_id) WHERE max_user_id > 0"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_promo_bonus_grants_expiry ON promo_bonus_grants(chat_id, expires_at)"
            )
            conn.commit()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, spec: str) -> None:
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        names = {row["name"] for row in info}
        if column not in names:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")

    def _today(self) -> str:
        return date.today().isoformat()

    def _week_key(self) -> str:
        today = date.today()
        year, week, _ = today.isocalendar()
        return f"{year}-W{week:02d}"

    def _expire_bonus_grants_if_needed(self, conn: sqlite3.Connection, chat_id: int, row: sqlite3.Row, now: datetime) -> sqlite3.Row:
        now_iso = now.isoformat()
        grants = conn.execute(
            """
            SELECT id, amount_remaining
            FROM promo_bonus_grants
            WHERE chat_id = ? AND amount_remaining > 0 AND expires_at <> '' AND expires_at <= ?
            ORDER BY expires_at ASC, id ASC
            """,
            (chat_id, now_iso),
        ).fetchall()
        if not grants:
            return row

        balance = int(row["credits_balance"] or 0)
        for grant in grants:
            remaining = int(grant["amount_remaining"] or 0)
            if remaining <= 0:
                continue
            deduction = min(balance, remaining)
            balance -= deduction
            conn.execute(
                "UPDATE promo_bonus_grants SET amount_remaining = 0, expired_at = ? WHERE id = ?",
                (now_iso, int(grant["id"])),
            )

        conn.execute(
            "UPDATE users SET credits_balance = ?, updated_at = ? WHERE chat_id = ?",
            (max(0, balance), now_iso, chat_id),
        )
        conn.commit()
        refreshed = conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
        return refreshed if refreshed is not None else row

    def _insert_new_user(
        self,
        conn: sqlite3.Connection,
        chat_id: int,
        default_model_alias: str,
        now: str,
        today: str,
        max_user_id: int = 0,
    ) -> sqlite3.Row:
        referral_code = referral_code_for_chat(chat_id)
        conn.execute(
            """
            INSERT INTO users (
                chat_id, max_user_id, plan, is_blocked, onboarding_done, referral_code, referred_by_chat_id, referrals_invited,
                selected_model_alias, selected_preset, usage_date,
                daily_messages_used, daily_images_used, daily_gpt54_used,
                free_image_week_key, free_image_week_used, free_image_last_used_at,
                credits_balance, credits_spent_total,
                last_active_at,
                created_at, updated_at
            ) VALUES (?, ?, 'free', 0, 0, ?, 0, 0, ?, '', ?, 0, 0, 0, '', 0, '', ?, 0, ?, ?, ?)
            """,
            (
                chat_id,
                max(0, int(max_user_id or 0)),
                referral_code,
                default_model_alias,
                today,
                FREE_DAILY_CREDITS,
                now,
                now,
                now,
            ),
        )
        return conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()

    def _update_chat_references(self, conn: sqlite3.Connection, old_chat_id: int, new_chat_id: int, now: str) -> None:
        conn.execute(
            "UPDATE users SET chat_id = ?, updated_at = ? WHERE chat_id = ?",
            (new_chat_id, now, old_chat_id),
        )
        conn.execute(
            "UPDATE users SET referred_by_chat_id = ? WHERE referred_by_chat_id = ?",
            (new_chat_id, old_chat_id),
        )
        for table in ("payment_requests", "usage_events", "promo_activations", "promo_bonus_grants"):
            conn.execute(f"UPDATE {table} SET chat_id = ? WHERE chat_id = ?", (new_chat_id, old_chat_id))

    def _merge_rebound_user_rows(
        self,
        existing: sqlite3.Row,
        current: sqlite3.Row | None,
        max_user_id: int,
        now: str,
    ) -> dict[str, Any]:
        merged = dict(existing)
        merged["max_user_id"] = max(0, int(max_user_id or 0))
        if current is None:
            merged["updated_at"] = now
            return merged

        current_dict = dict(current)
        existing_plan = str(merged.get("plan", "free") or "free")
        current_plan = str(current_dict.get("plan", "free") or "free")
        existing_rank = PLAN_ORDER.get(existing_plan, 0)
        current_rank = PLAN_ORDER.get(current_plan, 0)

        def later_iso(left: Any, right: Any) -> str:
            left_s = str(left or "").strip()
            right_s = str(right or "").strip()
            if not left_s:
                return right_s
            if not right_s:
                return left_s
            return max(left_s, right_s)

        merged["is_blocked"] = 1 if int(merged.get("is_blocked", 0) or 0) or int(current_dict.get("is_blocked", 0) or 0) else 0
        merged["onboarding_done"] = 1 if int(merged.get("onboarding_done", 0) or 0) or int(current_dict.get("onboarding_done", 0) or 0) else 0
        merged["referral_code"] = str(merged.get("referral_code", "") or "").strip() or str(current_dict.get("referral_code", "") or "").strip() or referral_code_for_chat(int(existing["chat_id"]))
        merged["referred_by_chat_id"] = int(merged.get("referred_by_chat_id", 0) or 0) or int(current_dict.get("referred_by_chat_id", 0) or 0)
        merged["referrals_invited"] = max(int(merged.get("referrals_invited", 0) or 0), int(current_dict.get("referrals_invited", 0) or 0))
        merged["receipt_email"] = str(merged.get("receipt_email", "") or "").strip() or str(current_dict.get("receipt_email", "") or "").strip()
        merged["receipt_phone"] = str(merged.get("receipt_phone", "") or "").strip() or str(current_dict.get("receipt_phone", "") or "").strip()
        merged["last_active_at"] = later_iso(merged.get("last_active_at", ""), current_dict.get("last_active_at", ""))
        merged["created_at"] = min(str(merged.get("created_at", "") or "").strip() or now, str(current_dict.get("created_at", "") or "").strip() or now)

        if current_rank > existing_rank:
            for key in (
                "plan",
                "selected_model_alias",
                "selected_preset",
                "subscription_expires_at",
                "recurring_enabled",
                "recurring_cancel_from",
                "recurring_canceled_at",
            ):
                merged[key] = current_dict.get(key, merged.get(key))
            merged["credits_balance"] = int(current_dict.get("credits_balance", 0) or 0)
        elif current_rank == existing_rank and existing_plan != "free":
            merged["credits_balance"] = max(int(merged.get("credits_balance", 0) or 0), int(current_dict.get("credits_balance", 0) or 0))
            merged["subscription_expires_at"] = later_iso(merged.get("subscription_expires_at", ""), current_dict.get("subscription_expires_at", ""))
            merged["recurring_enabled"] = 1 if int(merged.get("recurring_enabled", 0) or 0) or int(current_dict.get("recurring_enabled", 0) or 0) else 0
            merged["recurring_cancel_from"] = later_iso(merged.get("recurring_cancel_from", ""), current_dict.get("recurring_cancel_from", ""))
            merged["recurring_canceled_at"] = later_iso(merged.get("recurring_canceled_at", ""), current_dict.get("recurring_canceled_at", ""))
        else:
            merged["credits_balance"] = min(int(merged.get("credits_balance", 0) or 0), int(current_dict.get("credits_balance", 0) or 0))

        if not str(merged.get("selected_model_alias", "") or "").strip():
            merged["selected_model_alias"] = str(current_dict.get("selected_model_alias", "") or "").strip()
        if not str(merged.get("selected_preset", "") or "").strip():
            merged["selected_preset"] = str(current_dict.get("selected_preset", "") or "").strip()

        merged["credits_spent_total"] = max(int(merged.get("credits_spent_total", 0) or 0), int(current_dict.get("credits_spent_total", 0) or 0))
        merged["free_image_last_used_at"] = later_iso(merged.get("free_image_last_used_at", ""), current_dict.get("free_image_last_used_at", ""))
        merged["free_image_week_key"] = later_iso(merged.get("free_image_week_key", ""), current_dict.get("free_image_week_key", ""))
        merged["free_image_week_used"] = max(int(merged.get("free_image_week_used", 0) or 0), int(current_dict.get("free_image_week_used", 0) or 0))

        existing_usage_date = str(merged.get("usage_date", "") or "")
        current_usage_date = str(current_dict.get("usage_date", "") or "")
        if current_usage_date > existing_usage_date:
            merged["usage_date"] = current_usage_date
            for key in ("daily_messages_used", "daily_images_used", "daily_gpt54_used"):
                merged[key] = int(current_dict.get(key, 0) or 0)
        elif current_usage_date == existing_usage_date and current_usage_date:
            for key in ("daily_messages_used", "daily_images_used", "daily_gpt54_used"):
                merged[key] = max(int(merged.get(key, 0) or 0), int(current_dict.get(key, 0) or 0))

        merged["updated_at"] = now
        return merged

    def ensure_user_binding(self, chat_id: int, max_user_id: int | None, default_model_alias: str) -> int | None:
        identity = max(0, int(max_user_id or 0))
        now = datetime.utcnow().isoformat()
        today = self._today()
        with self._connect() as conn:
            current = conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
            if identity <= 0:
                if current is None:
                    self._insert_new_user(conn, chat_id, default_model_alias, now, today, 0)
                    conn.commit()
                return None

            existing = conn.execute("SELECT * FROM users WHERE max_user_id = ? LIMIT 1", (identity,)).fetchone()
            if current is None and existing is None:
                self._insert_new_user(conn, chat_id, default_model_alias, now, today, identity)
                conn.commit()
                return None

            if existing is None:
                conn.execute(
                    "UPDATE users SET max_user_id = ?, updated_at = ? WHERE chat_id = ?",
                    (identity, now, chat_id),
                )
                conn.commit()
                return None

            existing_chat_id = int(existing["chat_id"])
            if existing_chat_id == chat_id:
                if int(existing["max_user_id"] or 0) != identity:
                    conn.execute(
                        "UPDATE users SET max_user_id = ?, updated_at = ? WHERE chat_id = ?",
                        (identity, now, chat_id),
                    )
                    conn.commit()
                return None

            merged = self._merge_rebound_user_rows(existing, current, identity, now)
            if current is not None:
                conn.execute("DELETE FROM users WHERE chat_id = ?", (chat_id,))
            self._update_chat_references(conn, existing_chat_id, chat_id, now)
            conn.execute(
                """
                UPDATE users
                SET max_user_id = ?, plan = ?, is_blocked = ?, onboarding_done = ?, referral_code = ?,
                    referred_by_chat_id = ?, referrals_invited = ?, receipt_email = ?, receipt_phone = ?,
                    selected_model_alias = ?, selected_preset = ?, subscription_expires_at = ?,
                    recurring_enabled = ?, recurring_cancel_from = ?, recurring_canceled_at = ?,
                    usage_date = ?, daily_messages_used = ?, daily_images_used = ?, daily_gpt54_used = ?,
                    free_image_week_key = ?, free_image_week_used = ?, free_image_last_used_at = ?,
                    credits_balance = ?, credits_spent_total = ?, last_active_at = ?, created_at = ?, updated_at = ?
                WHERE chat_id = ?
                """,
                (
                    int(merged.get("max_user_id", 0) or 0),
                    str(merged.get("plan", "free") or "free"),
                    int(merged.get("is_blocked", 0) or 0),
                    int(merged.get("onboarding_done", 0) or 0),
                    str(merged.get("referral_code", "") or ""),
                    int(merged.get("referred_by_chat_id", 0) or 0),
                    int(merged.get("referrals_invited", 0) or 0),
                    str(merged.get("receipt_email", "") or ""),
                    str(merged.get("receipt_phone", "") or ""),
                    str(merged.get("selected_model_alias", "") or ""),
                    str(merged.get("selected_preset", "") or ""),
                    str(merged.get("subscription_expires_at", "") or ""),
                    int(merged.get("recurring_enabled", 0) or 0),
                    str(merged.get("recurring_cancel_from", "") or ""),
                    str(merged.get("recurring_canceled_at", "") or ""),
                    str(merged.get("usage_date", "") or ""),
                    int(merged.get("daily_messages_used", 0) or 0),
                    int(merged.get("daily_images_used", 0) or 0),
                    int(merged.get("daily_gpt54_used", 0) or 0),
                    str(merged.get("free_image_week_key", "") or ""),
                    int(merged.get("free_image_week_used", 0) or 0),
                    str(merged.get("free_image_last_used_at", "") or ""),
                    int(merged.get("credits_balance", 0) or 0),
                    int(merged.get("credits_spent_total", 0) or 0),
                    str(merged.get("last_active_at", "") or ""),
                    str(merged.get("created_at", "") or now),
                    now,
                    chat_id,
                ),
            )
            conn.commit()
            return existing_chat_id

    def get_or_create_user(self, chat_id: int, default_model_alias: str) -> dict[str, Any]:
        now = datetime.utcnow().isoformat()
        today = self._today()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
            if row is None:
                row = self._insert_new_user(conn, chat_id, default_model_alias, now, today, 0)
                conn.commit()

            row = self._expire_bonus_grants_if_needed(conn, chat_id, row, datetime.utcnow())

            day_changed = row["usage_date"] != today
            if day_changed:
                conn.execute(
                    """
                    UPDATE users
                    SET usage_date = ?, daily_messages_used = 0, daily_images_used = 0, daily_gpt54_used = 0, updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (today, now, chat_id),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()

            # Daily free bonus should be topped up only once per day.
            if day_changed and row["plan"] == "free" and int(row["credits_balance"] or 0) < FREE_DAILY_CREDITS:
                conn.execute(
                    """
                    UPDATE users
                    SET credits_balance = ?, updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (FREE_DAILY_CREDITS, now, chat_id),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()

            if not str(row["referral_code"] or "").strip():
                conn.execute(
                    "UPDATE users SET referral_code = ?, updated_at = ? WHERE chat_id = ?",
                    (referral_code_for_chat(chat_id), now, chat_id),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()

            return dict(row)

    def set_selected_model(self, chat_id: int, alias: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET selected_model_alias = ?, updated_at = ? WHERE chat_id = ?",
                (alias, datetime.utcnow().isoformat(), chat_id),
            )
            conn.commit()

    def set_selected_preset(self, chat_id: int, preset: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET selected_preset = ?, updated_at = ? WHERE chat_id = ?",
                (preset.strip(), datetime.utcnow().isoformat(), chat_id),
            )
            conn.commit()

    def set_receipt_contact(self, chat_id: int, email: str, phone: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET receipt_email = ?, receipt_phone = ?, updated_at = ? WHERE chat_id = ?",
                (email.strip(), phone.strip(), datetime.utcnow().isoformat(), chat_id),
            )
            conn.commit()

    def touch_last_active(self, chat_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET last_active_at = ?, updated_at = ? WHERE chat_id = ?",
                (datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), chat_id),
            )
            conn.commit()

    def set_onboarding_done(self, chat_id: int, done: bool = True) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET onboarding_done = ?, updated_at = ? WHERE chat_id = ?",
                (1 if done else 0, datetime.utcnow().isoformat(), chat_id),
            )
            conn.commit()

    def apply_referral_code(self, chat_id: int, referral_code: str, bonus_credits: int) -> tuple[bool, str]:
        code = normalize_referral_code(referral_code)
        if not code:
            return False, "Пустой реферальный код."
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            user = conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
            if not user:
                conn.rollback()
                return False, "Пользователь не найден."
            if int(user["referred_by_chat_id"] or 0) > 0:
                conn.rollback()
                return False, "Реферальный код уже был использован."
            owner = conn.execute("SELECT * FROM users WHERE referral_code = ? LIMIT 1", (code,)).fetchone()
            if not owner:
                conn.rollback()
                return False, "Такого реферального кода нет."
            owner_chat_id = int(owner["chat_id"])
            if owner_chat_id == int(chat_id):
                conn.rollback()
                return False, "Нельзя активировать свой код."

            now = datetime.utcnow().isoformat()
            conn.execute(
                """
                UPDATE users
                SET referred_by_chat_id = ?, updated_at = ?
                WHERE chat_id = ?
                """,
                (owner_chat_id, now, chat_id),
            )
            conn.execute(
                """
                UPDATE users
                SET referrals_invited = referrals_invited + 1, updated_at = ?
                WHERE chat_id = ?
                """,
                (now, owner_chat_id),
            )
            if bonus_credits > 0:
                conn.execute(
                    "UPDATE users SET credits_balance = credits_balance + ?, updated_at = ? WHERE chat_id = ?",
                    (bonus_credits, now, chat_id),
                )
                conn.execute(
                    "UPDATE users SET credits_balance = credits_balance + ?, updated_at = ? WHERE chat_id = ?",
                    (bonus_credits, now, owner_chat_id),
                )
            conn.commit()
            return True, str(owner_chat_id)

    def redeem_promo_code(self, chat_id: int, promo_code: str, credits: int, bonus_ttl_days: int = 0) -> tuple[bool, str]:
        code = normalize_referral_code(promo_code)
        if not code:
            return False, "Пустой промокод."
        if credits <= 0:
            return False, "Промокод сейчас недоступен."
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO promo_activations (chat_id, promo_code, credits, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (chat_id, code, credits, now),
                )
            except sqlite3.IntegrityError:
                return False, "Этот промокод уже активирован."
            conn.execute(
                "UPDATE users SET credits_balance = credits_balance + ?, updated_at = ? WHERE chat_id = ?",
                (credits, now, chat_id),
            )
            ttl_days = max(0, int(bonus_ttl_days))
            if ttl_days > 0:
                expires_at = (datetime.utcnow() + timedelta(days=ttl_days)).replace(microsecond=0).isoformat()
                conn.execute(
                    """
                    INSERT INTO promo_bonus_grants (chat_id, promo_code, amount_total, amount_remaining, expires_at, created_at, expired_at)
                    VALUES (?, ?, ?, ?, ?, ?, '')
                    """,
                    (chat_id, code, credits, credits, expires_at, now),
                )
            conn.commit()
        return True, str(credits)

    def active_bonus_credits_summary(self, chat_id: int) -> tuple[int, str]:
        now_iso = datetime.utcnow().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT amount_remaining, expires_at
                FROM promo_bonus_grants
                WHERE chat_id = ? AND amount_remaining > 0 AND expires_at > ?
                ORDER BY expires_at ASC
                """,
                (chat_id, now_iso),
            ).fetchall()
        if not rows:
            return 0, ""
        total = sum(int(row["amount_remaining"] or 0) for row in rows)
        nearest = str(rows[0]["expires_at"] or "")
        return total, nearest

    def list_recent_users(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT chat_id, plan, is_blocked, onboarding_done, credits_balance,
                       daily_messages_used, daily_images_used, last_active_at, updated_at
                FROM users
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_user(self, chat_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
            return dict(row) if row else None

    def list_recent_payments(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, chat_id, plan, amount_rub, status, provider_ref, created_at, paid_at, activated_at
                FROM payment_requests
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def adjust_credits(self, chat_id: int, delta: int) -> int:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET credits_balance = credits_balance + ?, updated_at = ? WHERE chat_id = ?",
                (delta, now, chat_id),
            )
            conn.commit()
            row = conn.execute("SELECT credits_balance FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
            return int((row["credits_balance"] if row else 0) or 0)

    def reset_daily_counters(self, chat_id: int) -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET daily_messages_used = 0, daily_images_used = 0, daily_gpt54_used = 0, updated_at = ?
                WHERE chat_id = ?
                """,
                (now, chat_id),
            )
            conn.commit()

    def list_reengage_candidates(self, dormant_days: int, limit: int) -> list[dict[str, Any]]:
        if dormant_days <= 0:
            dormant_days = 1
        if limit <= 0:
            limit = 1
        cutoff = (datetime.utcnow() - timedelta(days=dormant_days)).replace(microsecond=0).isoformat()
        free_image_ready_cutoff = (datetime.utcnow() - timedelta(days=7)).replace(microsecond=0).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT chat_id, plan, free_image_last_used_at, last_active_at, credits_balance
                FROM users
                WHERE plan = 'free'
                  AND (last_active_at = '' OR last_active_at <= ?)
                  AND (free_image_last_used_at = '' OR free_image_last_used_at <= ?)
                ORDER BY last_active_at ASC
                LIMIT ?
                """,
                (cutoff, free_image_ready_cutoff, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def set_plan(self, chat_id: int, plan: str) -> None:
        expires = "" if plan == "free" else None
        with self._connect() as conn:
            if expires is None:
                conn.execute(
                    "UPDATE users SET plan = ?, updated_at = ? WHERE chat_id = ?",
                    (plan, datetime.utcnow().isoformat(), chat_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE users
                    SET plan = ?, subscription_expires_at = ?, recurring_enabled = 0,
                        recurring_cancel_from = '', recurring_canceled_at = '',
                        credits_balance = CASE WHEN credits_balance < ? THEN ? ELSE credits_balance END,
                        updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (plan, expires, FREE_DAILY_CREDITS, FREE_DAILY_CREDITS, datetime.utcnow().isoformat(), chat_id),
                )
            conn.commit()

    def set_subscription(
        self,
        chat_id: int,
        plan: str,
        days: int,
        selected_model_alias: str,
        recurring_enabled: bool | None = None,
    ) -> str:
        expires_at = (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat()
        with self._connect() as conn:
            if recurring_enabled is None:
                conn.execute(
                    """
                    UPDATE users
                    SET plan = ?, subscription_expires_at = ?, selected_model_alias = ?,
                        credits_balance = ?, updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (
                        plan,
                        expires_at,
                        selected_model_alias,
                        PLAN_CREDITS.get(plan, 0),
                        datetime.utcnow().isoformat(),
                        chat_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE users
                    SET plan = ?, subscription_expires_at = ?, selected_model_alias = ?,
                        recurring_enabled = ?, recurring_cancel_from = '', recurring_canceled_at = '',
                        credits_balance = ?, updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (
                        plan,
                        expires_at,
                        selected_model_alias,
                        1 if recurring_enabled else 0,
                        PLAN_CREDITS.get(plan, 0),
                        datetime.utcnow().isoformat(),
                        chat_id,
                    ),
                )
            conn.commit()
        return expires_at

    def cancel_recurring(self, chat_id: int, cancel_from: str) -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET recurring_enabled = 0, recurring_cancel_from = ?, recurring_canceled_at = ?, updated_at = ?
                WHERE chat_id = ?
                """,
                (cancel_from, now, now, chat_id),
            )
            conn.commit()

    def create_payment_request(
        self,
        chat_id: int,
        plan: str,
        days: int,
        amount_rub: int,
        recurring_consent: bool = False,
        recurring_consent_text: str = "",
        receipt_email: str = "",
        receipt_phone: str = "",
    ) -> int:
        now = datetime.utcnow().isoformat()
        consent_at = now if recurring_consent else ""
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO payment_requests (
                    chat_id, plan, days, amount_rub, recurring_consent,
                    recurring_consent_at, recurring_consent_text, receipt_email, receipt_phone, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    chat_id,
                    plan,
                    days,
                    amount_rub,
                    1 if recurring_consent else 0,
                    consent_at,
                    recurring_consent_text,
                    receipt_email.strip(),
                    receipt_phone.strip(),
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def set_payment_provider_ref(self, request_id: int, provider_ref: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE payment_requests SET provider_ref = ? WHERE id = ?",
                (provider_ref, request_id),
            )
            conn.commit()

    def set_payment_url(self, request_id: int, payment_url: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE payment_requests SET payment_url = ? WHERE id = ?",
                (payment_url.strip(), request_id),
            )
            conn.commit()

    def list_user_payments(self, chat_id: int, limit: int = 5) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, plan, days, amount_rub, status, created_at
                FROM payment_requests
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_payment(self, request_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM payment_requests WHERE id = ?", (request_id,)).fetchone()
            return dict(row) if row else None

    def set_payment_status(self, request_id: int, status: str) -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            if status == "paid":
                conn.execute(
                    "UPDATE payment_requests SET status = ?, paid_at = ? WHERE id = ?",
                    (status, now, request_id),
                )
            else:
                conn.execute(
                    "UPDATE payment_requests SET status = ? WHERE id = ?",
                    (status, request_id),
                )
            conn.commit()

    def mark_payment_activated(self, request_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE payment_requests SET activated_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), request_id),
            )
            conn.commit()

    def set_blocked(self, chat_id: int, blocked: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET is_blocked = ?, updated_at = ? WHERE chat_id = ?",
                (1 if blocked else 0, datetime.utcnow().isoformat(), chat_id),
            )
            conn.commit()

    def increment_message_usage(self, chat_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET daily_messages_used = daily_messages_used + 1, updated_at = ? WHERE chat_id = ?",
                (datetime.utcnow().isoformat(), chat_id),
            )
            conn.commit()

    def increment_image_usage(self, chat_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET daily_images_used = daily_images_used + 1, updated_at = ? WHERE chat_id = ?",
                (datetime.utcnow().isoformat(), chat_id),
            )
            conn.commit()

    def increment_free_week_image_usage(self, chat_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET free_image_week_used = 1, free_image_last_used_at = ?, updated_at = ?
                WHERE chat_id = ?
                """,
                (datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), chat_id),
            )
            conn.commit()

    def increment_gpt54_usage(self, chat_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET daily_gpt54_used = daily_gpt54_used + 1, updated_at = ? WHERE chat_id = ?",
                (datetime.utcnow().isoformat(), chat_id),
            )
            conn.commit()

    def consume_credits(self, chat_id: int, amount: int) -> bool:
        if amount <= 0:
            return True
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE users
                SET credits_balance = credits_balance - ?, credits_spent_total = credits_spent_total + ?, updated_at = ?
                WHERE chat_id = ? AND credits_balance >= ?
                """,
                (amount, amount, datetime.utcnow().isoformat(), chat_id, amount),
            )
            conn.commit()
            return cur.rowcount > 0

    def refund_credits(self, chat_id: int, amount: int) -> None:
        if amount <= 0:
            return
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET credits_balance = credits_balance + ?,
                    credits_spent_total = CASE WHEN credits_spent_total >= ? THEN credits_spent_total - ? ELSE 0 END,
                    updated_at = ?
                WHERE chat_id = ?
                """,
                (amount, amount, amount, datetime.utcnow().isoformat(), chat_id),
            )
            conn.commit()

    def set_credits(self, chat_id: int, amount: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET credits_balance = ?, updated_at = ? WHERE chat_id = ?",
                (max(0, int(amount)), datetime.utcnow().isoformat(), chat_id),
            )
            conn.commit()

    def record_usage_event(
        self,
        chat_id: int,
        event_type: str,
        plan: str = "",
        model_alias: str = "",
        credits_spent: int = 0,
        rub_amount: int = 0,
        tokens_total: int = 0,
        details: str = "",
    ) -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO usage_events (
                    chat_id, event_type, plan, model_alias, credits_spent, rub_amount, tokens_total, details, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(chat_id),
                    str(event_type),
                    str(plan),
                    str(model_alias),
                    int(credits_spent),
                    int(rub_amount),
                    int(tokens_total),
                    str(details)[:500],
                    now,
                ),
            )
            conn.commit()

    def kpi_report(self, days: int = 30) -> dict[str, Any]:
        period_days = max(1, min(int(days), 365))
        since = (datetime.utcnow() - timedelta(days=period_days)).isoformat()
        with self._connect() as conn:
            summary = conn.execute(
                """
                SELECT
                    COUNT(*) AS events_total,
                    COUNT(DISTINCT chat_id) AS active_users,
                    SUM(CASE WHEN event_type = 'payment' THEN rub_amount ELSE 0 END) AS revenue_rub,
                    SUM(CASE WHEN event_type = 'refund' THEN rub_amount ELSE 0 END) AS refunds_rub,
                    SUM(CASE WHEN event_type = 'text_request' THEN 1 ELSE 0 END) AS text_requests,
                    SUM(CASE WHEN event_type = 'image_request' THEN 1 ELSE 0 END) AS image_requests,
                    SUM(CASE WHEN event_type = 'text_request' THEN credits_spent ELSE 0 END) AS text_credits,
                    SUM(CASE WHEN event_type = 'image_request' THEN credits_spent ELSE 0 END) AS image_credits,
                    SUM(CASE WHEN event_type IN ('text_request','image_request') THEN credits_spent ELSE 0 END) AS total_credits_spent,
                    SUM(CASE WHEN event_type = 'text_request' THEN tokens_total ELSE 0 END) AS text_tokens
                FROM usage_events
                WHERE created_at >= ?
                """,
                (since,),
            ).fetchone()

            payers_row = conn.execute(
                """
                SELECT COUNT(DISTINCT chat_id) AS payers
                FROM usage_events
                WHERE created_at >= ? AND event_type = 'payment' AND rub_amount > 0
                """,
                (since,),
            ).fetchone()

            model_rows = conn.execute(
                """
                SELECT model_alias, COUNT(*) AS cnt, SUM(credits_spent) AS credits
                FROM usage_events
                WHERE created_at >= ? AND event_type = 'text_request'
                GROUP BY model_alias
                ORDER BY cnt DESC
                LIMIT 10
                """,
                (since,),
            ).fetchall()

            return {
                "days": period_days,
                "since": since,
                "events_total": int((summary["events_total"] or 0) if summary else 0),
                "active_users": int((summary["active_users"] or 0) if summary else 0),
                "revenue_rub": int((summary["revenue_rub"] or 0) if summary else 0),
                "refunds_rub": int((summary["refunds_rub"] or 0) if summary else 0),
                "text_requests": int((summary["text_requests"] or 0) if summary else 0),
                "image_requests": int((summary["image_requests"] or 0) if summary else 0),
                "text_credits": int((summary["text_credits"] or 0) if summary else 0),
                "image_credits": int((summary["image_credits"] or 0) if summary else 0),
                "total_credits_spent": int((summary["total_credits_spent"] or 0) if summary else 0),
                "text_tokens": int((summary["text_tokens"] or 0) if summary else 0),
                "payers": int((payers_row["payers"] or 0) if payers_row else 0),
                "models": [dict(row) for row in model_rows],
            }


class BotState:
    def __init__(self) -> None:
        self.user_histories: dict[int, deque[dict[str, str]]] = {}
        self.pending_receipt_plan: dict[int, str] = {}
        self.pending_image_prompt: set[int] = set()
        self.pending_image_ref_prompt: set[int] = set()
        self.pending_promo_code_input: set[int] = set()
        self.pending_referral_code_input: set[int] = set()
        self.image_request_prefs: dict[int, dict[str, str]] = {}
        self.last_reference_image_data_url: dict[int, str] = {}
        self.last_reference_image_at: dict[int, datetime] = {}
        self.processed_updates: deque[str] = deque()
        self.processed_lookup: set[str] = set()
        self.last_message_at: dict[int, datetime] = {}
        self.last_image_at: dict[int, datetime] = {}
        self.last_low_credits_nudge_at: dict[int, datetime] = {}
        self.error_alert_last_at: dict[str, datetime] = {}
        self.ui_message_mid: dict[int, str] = {}
        self.onboarding_message_mid: dict[int, str] = {}
        self.ui_current_page: dict[int, str] = {}
        self.ui_back_stack: dict[int, list[str]] = {}
        self.ui_forward_stack: dict[int, list[str]] = {}
        self.session: aiohttp.ClientSession | None = None
        self.polling_task: asyncio.Task[None] | None = None
        self.user_store = UserStore(DB_PATH)

    def history(self, chat_id: int) -> deque[dict[str, str]]:
        if chat_id not in self.user_histories:
            self.user_histories[chat_id] = deque(maxlen=HISTORY_LIMIT)
        return self.user_histories[chat_id]


state = BotState()


def clear_growth_pending_inputs(chat_id: int) -> None:
    state.pending_referral_code_input.discard(chat_id)
    state.pending_promo_code_input.discard(chat_id)


def migrate_runtime_chat_state(old_chat_id: int, new_chat_id: int) -> None:
    if old_chat_id == new_chat_id:
        return

    history = state.user_histories.pop(old_chat_id, None)
    if history is not None:
        target = state.user_histories.get(new_chat_id)
        if target is None:
            state.user_histories[new_chat_id] = history
        else:
            for item in history:
                target.append(item)

    dict_attrs = (
        "pending_receipt_plan",
        "image_request_prefs",
        "last_reference_image_data_url",
        "last_reference_image_at",
        "last_message_at",
        "last_image_at",
        "last_low_credits_nudge_at",
        "ui_message_mid",
        "onboarding_message_mid",
        "ui_current_page",
        "ui_back_stack",
        "ui_forward_stack",
    )
    for attr in dict_attrs:
        mapping = getattr(state, attr)
        if old_chat_id not in mapping:
            continue
        value = mapping.pop(old_chat_id)
        if new_chat_id not in mapping:
            mapping[new_chat_id] = value

    set_attrs = (
        "pending_image_prompt",
        "pending_image_ref_prompt",
        "pending_promo_code_input",
        "pending_referral_code_input",
    )
    for attr in set_attrs:
        items = getattr(state, attr)
        if old_chat_id in items:
            items.discard(old_chat_id)
            items.add(new_chat_id)


def ensure_update_user_binding(chat_id: int, update: dict[str, Any]) -> None:
    actor_user_id = parse_actor_user_id(update)
    rebound_from = state.user_store.ensure_user_binding(chat_id, actor_user_id, best_default_alias_for_plan("free"))
    if rebound_from and rebound_from != chat_id:
        log.info("Rebound MAX user_id=%s from chat_id=%s to chat_id=%s", actor_user_id, rebound_from, chat_id)
        migrate_runtime_chat_state(rebound_from, chat_id)


def handoff_onboarding_to_ui(chat_id: int, source_mid: str | None) -> None:
    onboarding_mid = state.onboarding_message_mid.get(chat_id)
    target_mid = onboarding_mid or source_mid
    if target_mid:
        state.ui_message_mid[chat_id] = target_mid
    state.onboarding_message_mid.pop(chat_id, None)


def looks_like_bonus_code(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    return bool(re.fullmatch(r"[A-Za-zА-Яа-я0-9_-]{3,40}", value))


def init_sentry_if_enabled() -> None:
    if not SENTRY_DSN:
        return
    try:
        import sentry_sdk  # type: ignore

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=SENTRY_ENVIRONMENT,
            traces_sample_rate=0.0,
        )
        log.info("Sentry initialized")
    except Exception:
        log.exception("Failed to initialize Sentry")


def capture_exception_safe(exc: Exception) -> None:
    if not SENTRY_DSN:
        return
    try:
        import sentry_sdk  # type: ignore

        sentry_sdk.capture_exception(exc)
    except Exception:
        pass


async def notify_admin_alert(key: str, text: str) -> None:
    if not ERROR_ALERTS_ENABLED or not ADMIN_IDS:
        return
    now = datetime.utcnow()
    last = state.error_alert_last_at.get(key)
    if last and (now - last).total_seconds() < max(10, ERROR_ALERT_COOLDOWN_SEC):
        return
    state.error_alert_last_at[key] = now
    for admin_id in ADMIN_IDS:
        with suppress(Exception):
            await max_send_message(admin_id, f"⚠️ ALERT [{key}]\n{text}", notify=False)


def require_env() -> None:
    missing = []
    if not MAX_TOKEN:
        missing.append("MAX_TOKEN")
    if not OPENROUTER_KEY:
        missing.append("OPENROUTER_KEY")
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")


def validate_pricing_sanity() -> None:
    if PRO_PLAN_PRICE_RUB <= 0 or credits_for_plan("pro") <= 0:
        log.warning("Pricing sanity skipped: invalid Pro plan price/credits.")
        return

    pro_ratio = credits_for_plan("pro") / float(PRO_PLAN_PRICE_RUB)
    for code, pack in TOPUP_PACKS.items():
        price = int(pack.get("price_rub", 0) or 0)
        credits = int(pack.get("credits", 0) or 0)
        if price <= 0 or credits <= 0:
            log.warning("Top-up pack %s has invalid config: price=%s credits=%s", code, price, credits)
            continue
        ratio = credits / float(price)
        if ratio >= pro_ratio:
            log.warning(
                "Top-up pack %s is too generous: %.4f credits/RUB >= Pro %.4f credits/RUB",
                code,
                ratio,
                pro_ratio,
            )


def load_model_registry() -> tuple[dict[str, ModelInfo], dict[str, ModelInfo]]:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    text_models: dict[str, ModelInfo] = {}
    image_models: dict[str, ModelInfo] = {}

    for alias, payload in raw.get("text_models", {}).items():
        text_models[alias] = ModelInfo(
            alias=alias,
            provider=payload["provider"],
            model=payload["model"],
            label=payload["label"],
            kind="text",
            version=payload.get("version", ""),
            input_price_usd_per_m=payload.get("input_price_usd_per_m", ""),
            output_price_usd_per_m=payload.get("output_price_usd_per_m", ""),
            min_plan=payload.get("min_plan", "free"),
            description=payload.get("description", ""),
            prompt_style=payload.get("prompt_style", ""),
        )

    for alias, payload in raw.get("image_models", {}).items():
        image_models[alias] = ModelInfo(
            alias=alias,
            provider=payload["provider"],
            model=payload["model"],
            label=payload["label"],
            kind="image",
            version=payload.get("version", ""),
            input_price_usd_per_m=payload.get("input_price_usd_per_m", ""),
            output_price_usd_per_m=payload.get("output_price_usd_per_m", ""),
            min_plan=payload.get("min_plan", "free"),
            description=payload.get("description", ""),
            prompt_style=payload.get("prompt_style", ""),
        )

    return text_models, image_models


TEXT_MODELS, IMAGE_MODELS = load_model_registry()
DEFAULT_TEXT_MODEL = TEXT_MODELS.get(DEFAULT_TEXT_MODEL_ALIAS, TEXT_MODELS["gpt"])
DEFAULT_IMAGE_MODEL = IMAGE_MODELS.get(DEFAULT_IMAGE_MODEL_ALIAS, IMAGE_MODELS["image"])


def max_headers() -> dict[str, str]:
    return {"Authorization": MAX_TOKEN, "Content-Type": "application/json"}


def openrouter_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://max.ru",
        "X-Title": "MAX Multi AI Bot",
    }


def tbank_enabled() -> bool:
    return bool(TBANK_TERMINAL_KEY and TBANK_PASSWORD)


def tbank_order_id(request_id: int) -> str:
    suffix = datetime.utcnow().strftime("%y%m%d%H%M%S")
    return f"MAXBOT-{request_id}-{suffix}"


def parse_request_id_from_order_id(order_id: str) -> int | None:
    value = order_id.strip().upper()
    if not value.startswith("MAXBOT-"):
        return None
    payload = value.split("-", 1)[1]
    request_part = payload.split("-", 1)[0]
    return int(request_part) if request_part.isdigit() else None


def add_request_id_to_url(url: str, request_id: int) -> str:
    if not url:
        return ""
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["request_id"] = str(request_id)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query),
            parsed.fragment,
        )
    )


def tbank_payment_id_from_provider_ref(provider_ref: str) -> str:
    value = provider_ref.strip()
    if not value:
        return ""
    if value.startswith("tbank:"):
        return value.split(":", 1)[1].strip()
    return value


def build_tbank_receipt(
    amount_rub: int,
    description: str,
    receipt_email: str = "",
    receipt_phone: str = "",
) -> dict[str, Any]:
    amount_kop = int(amount_rub) * 100
    item_name = (description or "Подписка").strip()[:128] or "Подписка"
    receipt: dict[str, Any] = {
        "Taxation": TBANK_RECEIPT_TAXATION or "usn_income",
        "Items": [
            {
                "Name": item_name,
                "Price": amount_kop,
                "Quantity": 1,
                "Amount": amount_kop,
                "Tax": TBANK_RECEIPT_TAX or "none",
                "PaymentMethod": TBANK_RECEIPT_PAYMENT_METHOD or "full_prepayment",
                "PaymentObject": TBANK_RECEIPT_PAYMENT_OBJECT or "service",
            }
        ],
    }
    if TBANK_RECEIPT_FFD_VERSION:
        receipt["FfdVersion"] = TBANK_RECEIPT_FFD_VERSION
    if receipt_email:
        receipt["Email"] = receipt_email
    if receipt_phone:
        receipt["Phone"] = receipt_phone
    return receipt


def scalar_string(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def tbank_token_from_payload(payload: dict[str, Any], password: str) -> str:
    # T-Bank token uses only root scalar fields (+ Password), excluding Token and nested objects.
    values: dict[str, str] = {}
    for key, value in payload.items():
        if key == "Token":
            continue
        if isinstance(value, (dict, list)):
            continue
        values[key] = scalar_string(value)
    values["Password"] = password
    raw = "".join(values[key] for key in sorted(values.keys()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def tbank_notification_is_valid(payload: dict[str, Any]) -> bool:
    if TBANK_TERMINAL_KEY:
        terminal_key = scalar_string(payload.get("TerminalKey"))
        if terminal_key != TBANK_TERMINAL_KEY:
            return False
    if not TBANK_PASSWORD:
        return True
    received = scalar_string(payload.get("Token")).lower()
    if not received:
        return False
    expected = tbank_token_from_payload(payload, TBANK_PASSWORD).lower()
    return received == expected


def tbank_is_cancel_status(status: str) -> bool:
    return status.strip().upper() in TBANK_CANCEL_STATUSES


def tbank_is_refund_status(status: str) -> bool:
    return status.strip().upper() in TBANK_REFUND_STATUSES


def site_file(name: str) -> Path:
    path = SITE_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="page not found")
    return path


def support_url_value() -> str:
    if SUPPORT_URL:
        return SUPPORT_URL
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL}/support"
    return "/support"


def support_help_text() -> str:
    return (
        "Помощь\n\n"
        "Если что-то не работает:\n"
        "1. Открой «Тарифы» и создай новую заявку\n"
        "2. После оплаты подожди 1-2 минуты\n"
        "3. Открой «Мой план» или «Мои оплаты» и проверь статус\n\n"
        f"{SUPPORT_TEXT}\n"
        f"Email: {CONTACT_EMAIL}\n"
        f"FAQ: {support_url_value()}\n\n"
        "Что прислать в поддержку:\n"
        "• номер заявки\n"
        "• что произошло\n"
        "• скрин ошибки или оплаты, если он есть"
    )


def channel_url_value() -> str:
    return CHANNEL_URL or "https://max.ru/id231128398751_biz"


def support_admin_templates_text() -> str:
    return (
        "Шаблоны для спорных кейсов\n\n"
        "1) Оплата есть, доступа нет:\n"
        "«Проверили оплату по заявке #{request_id}. Статус в банке: {bank_status}. "
        "Доступ обновлен, проверь раздел “Мой план”. Если не обновилось — напишите нам, проверим вручную.»\n\n"
        "2) Оплата не прошла:\n"
        "«По заявке #{request_id} банк вернул статус {bank_status}. Оплата не завершена. "
        "Создайте новую заявку в разделе “Тарифы” и повторите оплату.»\n\n"
        "3) Возврат подтвержден:\n"
        "«По заявке #{request_id} оформлен возврат. Подписка переведена на free, автопродление отключено. "
        "Срок зачисления средств зависит от банка-эмитента.»\n\n"
        "4) Чарджбэк/спор:\n"
        "«Получили запрос на оспаривание платежа по заявке #{request_id}. "
        "Для проверки пришлите дату/время оплаты и скрин подтверждения операции.»"
    )


def admin_panel_enabled() -> bool:
    return bool(ADMIN_PANEL_TOKEN)


def admin_panel_authorized(token: str) -> bool:
    return bool(ADMIN_PANEL_TOKEN) and token.strip() == ADMIN_PANEL_TOKEN


def backups_dir() -> Path:
    path = DATA_DIR / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_db_backup() -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    target = backups_dir() / f"bot-{stamp}.sqlite3"
    with sqlite3.connect(DB_PATH) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    files = sorted(backups_dir().glob("bot-*.sqlite3"))
    keep = max(3, BACKUP_KEEP_FILES)
    if len(files) > keep:
        for old in files[: len(files) - keep]:
            with suppress(Exception):
                old.unlink()
    return target


def payment_status_label(status: str) -> str:
    return PAYMENT_STATUS_LABELS.get(status.strip().lower(), "Статус обновляется")


def payment_status_title_message(status: str) -> tuple[str, str]:
    key = status.strip().lower()
    titles = {
        "pending": "Платеж создан",
        "claimed": "Проверяем оплату",
        "paid": "Оплата подтверждена",
        "canceled": "Оплата не завершена",
        "refunded": "Оформлен возврат",
    }
    messages = {
        "pending": "Платеж в обработке. Обычно подтверждение приходит в течение 1-2 минут.",
        "claimed": "Банк прислал сигнал, подтверждаем оплату. Обычно это занимает до 1-2 минут.",
        "paid": "Подписка уже активирована. Можно возвращаться в бот.",
        "canceled": "Оплата не была завершена. Вернись в бот и попробуй еще раз.",
        "refunded": "Возврат подтвержден. Подписка отключена, действует тариф free.",
    }
    return (
        titles.get(key, "Статус обновляется"),
        messages.get(key, "Подожди немного и обнови страницу."),
    )


def payment_user_status_text(payment: dict[str, Any], bank_status: str = "") -> str:
    request_id = int(payment.get("id", 0) or 0)
    status = str(payment.get("status", "pending")).lower()
    status_human = payment_status_label(status)
    plan = str(payment.get("plan", ""))
    amount = int(payment.get("amount_rub", 0) or 0)
    payment_url = str(payment.get("payment_url", "") or "").strip()
    bank_line = f"\nСтатус банка: {bank_status}" if bank_status else ""
    pay_line = f"\nСсылка на оплату: {payment_url}" if payment_url and status in {"pending", "claimed"} else ""

    if status == "paid":
        return (
            f"✅ Заявка #{request_id}: {status_human}\n"
            f"Тариф/пакет: {plan}, сумма: {amount} ₽.\n"
            "Доступ уже активирован. Можно возвращаться в меню."
        )
    if status == "refunded":
        return (
            f"↩️ Заявка #{request_id}: {status_human}\n"
            f"Тариф/пакет: {plan}, сумма: {amount} ₽.{bank_line}\n"
            "Возврат подтвержден. Если деньги долго не приходят, напиши в поддержку."
        )
    if status == "canceled":
        return (
            f"❌ Заявка #{request_id}: {status_human}\n"
            f"Тариф/пакет: {plan}, сумма: {amount} ₽.{bank_line}\n"
            "Оплата не завершена. Можно создать новую заявку в «Тарифы»."
        )
    if status == "claimed":
        return (
            f"🕒 Заявка #{request_id}: {status_human}\n"
            f"Тариф/пакет: {plan}, сумма: {amount} ₽.{bank_line}{pay_line}\n"
            "Платеж уже отправлен на проверку. Обычно это занимает 1-2 минуты."
        )
    return (
        f"⏳ Заявка #{request_id}: {status_human}\n"
        f"Тариф/пакет: {plan}, сумма: {amount} ₽.{bank_line}{pay_line}\n"
        "Открой ссылку на оплату. Если уже оплатил — нажми «Проверить статус»."
    )


def plan_allowed(plan: str, min_plan: str) -> bool:
    if min_plan not in PLAN_ORDER:
        log.warning("Unknown min_plan=%r in model config; denying access", min_plan)
        return False
    if plan not in PLAN_ORDER:
        return False
    return PLAN_ORDER[plan] >= PLAN_ORDER[min_plan]


def is_admin(chat_id: int) -> bool:
    return chat_id in ADMIN_IDS


def best_default_alias_for_plan(plan: str) -> str:
    preferred = ["gpt4o", DEFAULT_TEXT_MODEL.alias, "gpt", "deepseek"]
    for alias in preferred:
        info = TEXT_MODELS.get(alias)
        if info and plan_allowed(plan, info.min_plan):
            return alias
    for alias, info in TEXT_MODELS.items():
        if plan_allowed(plan, info.min_plan):
            return alias
    return DEFAULT_TEXT_MODEL.alias


def resolve_preset_alias_for_plan(plan: str, preset: str) -> str:
    preset_cfg = MODEL_PRESETS.get(preset)
    if not preset_cfg:
        return best_default_alias_for_plan(plan)
    for alias in preset_cfg.get("aliases", []):
        info = TEXT_MODELS.get(alias)
        if info and plan_allowed(plan, info.min_plan):
            return alias
    return best_default_alias_for_plan(plan)


def resolve_preset_alias_for_chat(chat_id: int, preset: str) -> str:
    plan = str(user_profile(chat_id).get("plan", "free"))
    return resolve_preset_alias_for_plan(plan, preset)


def build_preset_block(plan: str) -> str:
    lines = ["🎛 Режимы ответов:"]
    for key in ("fast", "balanced", "quality", "expert"):
        cfg = MODEL_PRESETS[key]
        aliases = list(cfg.get("aliases", []))
        primary_alias = str(aliases[0]) if aliases else ""
        primary_info = TEXT_MODELS.get(primary_alias)
        alias = resolve_preset_alias_for_plan(plan, key)
        label = TEXT_MODELS.get(alias, DEFAULT_TEXT_MODEL).label
        if primary_info and not plan_allowed(plan, primary_info.min_plan):
            lines.append(
                f"• {cfg['label']} — {cfg['description']} (сейчас: {label}; полная версия с {primary_info.min_plan})"
            )
            continue
        lines.append(f"• {cfg['label']} — {cfg['description']} ({label})")
    return "\n".join(lines)


def normalize_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part).strip()
    return ""


def split_message(text: str, limit: int = MAX_MESSAGE_LEN) -> list[str]:
    content = text.strip()
    if not content:
        return []
    if len(content) <= limit:
        return [content]

    chunks: list[str] = []
    remaining = content
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].strip()
    return chunks


def truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    candidate = text[:limit].rstrip()
    sentence_marks = [candidate.rfind(mark) for mark in (". ", "! ", "? ", ".\n", "!\n", "?\n")]
    split_at = max(sentence_marks)
    if split_at >= int(limit * 0.65):
        return candidate[: split_at + 1].rstrip()
    split_at = candidate.rfind("\n")
    if split_at >= int(limit * 0.65):
        return candidate[:split_at].rstrip() + "…"
    split_at = candidate.rfind(" ")
    if split_at >= int(limit * 0.65):
        return candidate[:split_at].rstrip() + "…"
    return candidate.rstrip() + "…"


def extract_first_http_url(text: str) -> str:
    match = re.search(r"https?://[^\s]+", text or "")
    if not match:
        return ""
    return match.group(0).rstrip(").,]>")


def trim_history_by_chars(history: list[dict[str, str]], budget_chars: int) -> list[dict[str, str]]:
    if budget_chars <= 0:
        return []
    kept: list[dict[str, str]] = []
    used = 0
    for item in reversed(history):
        content = str(item.get("content", ""))
        role = str(item.get("role", ""))
        size = len(content) + len(role) + 8
        if used + size > budget_chars:
            break
        kept.append({"role": role, "content": content})
        used += size
    kept.reverse()
    return kept


def completion_tokens_for_plan(plan: str) -> int:
    if plan == "pro":
        return MAX_COMPLETION_TOKENS_PRO
    if plan == "start":
        return MAX_COMPLETION_TOKENS_START
    if plan == "lite":
        return MAX_COMPLETION_TOKENS_LITE
    return MAX_COMPLETION_TOKENS_FREE


def credits_for_plan(plan: str) -> int:
    return int(PLAN_CREDITS.get(plan, 0))


def topup_plan_code(code: str) -> str:
    return f"topup_{code}"


def topup_code_from_plan(plan: str) -> str:
    if not plan.startswith("topup_"):
        return ""
    return plan.split("_", 1)[1]


def is_topup_plan(plan: str) -> bool:
    return topup_code_from_plan(plan) in TOPUP_PACKS


def topup_spec(code: str) -> dict[str, Any] | None:
    return TOPUP_PACKS.get(code)


def text_credit_cost(alias: str) -> int:
    return int(MODEL_CREDIT_COSTS.get(alias, CREDIT_COST_GPT))


def image_credit_cost() -> int:
    return CREDIT_COST_IMAGE


def text_var_credits_per_1k(alias: str) -> int:
    return int(MODEL_VAR_CREDITS_PER_1K.get(alias, 0))


def estimate_tokens_from_messages(messages: list[dict[str, Any]]) -> int:
    total_chars = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            total_chars += len(content)
            continue
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        total_chars += len(text)
    # Safe-side approximation: 1 token ~= 3 chars for mixed RU/EN chats.
    return max(1, (total_chars + 2) // 3)


def variable_text_credits(alias: str, total_tokens: int) -> int:
    rate = text_var_credits_per_1k(alias)
    if rate <= 0 or total_tokens <= 0:
        return 0
    value = (total_tokens * rate + 999) // 1000
    if MAX_VARIABLE_CREDITS_PER_TEXT > 0:
        value = min(value, MAX_VARIABLE_CREDITS_PER_TEXT)
    return max(0, value)


def parse_usage_tokens(data: dict[str, Any]) -> tuple[int, int, int]:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return 0, 0, 0
    prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
    completion_tokens = int(usage.get("completion_tokens", 0) or 0)
    total_tokens = int(usage.get("total_tokens", 0) or 0)
    if total_tokens <= 0:
        total_tokens = max(0, prompt_tokens) + max(0, completion_tokens)
    return max(0, prompt_tokens), max(0, completion_tokens), max(0, total_tokens)


def build_keyboard() -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {"type": "callback", "text": "⚡ Быстро", "payload": "set_preset:fast"},
                        {"type": "callback", "text": "⚖ Баланс", "payload": "set_preset:balanced"},
                    ],
                    [
                        {"type": "callback", "text": "🧠 Качество", "payload": "set_preset:quality"},
                        {"type": "callback", "text": "🚀 Эксперт", "payload": "set_preset:expert"},
                    ],
                    [
                        {"type": "callback", "text": "Тарифы", "payload": "action:tariffs"},
                        {"type": "callback", "text": "Мой план", "payload": "action:plan"},
                        {"type": "callback", "text": "Модели", "payload": "action:models"},
                    ],
                    [
                        {"type": "callback", "text": "🎨 Картинка", "payload": "action:image_menu"},
                        {"type": "callback", "text": "🎁 Бонусы", "payload": "action:growth"},
                    ],
                    [
                        {"type": "callback", "text": "Меню", "payload": "action:menu"},
                        {"type": "callback", "text": "Сброс", "payload": "action:clear"},
                        {"type": "callback", "text": "Помощь", "payload": "action:support"},
                    ],
                    [
                        {"type": "callback", "text": "📣 Канал", "payload": "action:channel"},
                    ],
                ]
            },
        }
    ]


def build_reply_shortcuts_keyboard(chat_id: int) -> list[dict[str, Any]]:
    row = user_profile(chat_id)
    buttons: list[list[dict[str, Any]]] = [
        [
            {"type": "callback", "text": "Меню", "payload": "reply_action:menu"},
            {"type": "callback", "text": "🎨 Картинка", "payload": "reply_action:image_menu"},
        ]
    ]
    if str(row.get("plan", "free")) == "free":
        buttons[0].append({"type": "callback", "text": "Тарифы", "payload": "reply_action:tariffs"})
    buttons.append([{"type": "callback", "text": "Сброс", "payload": "reply_action:clear"}])
    return [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]


def build_growth_keyboard() -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {"type": "callback", "text": "👥 Мой реф-код", "payload": "growth:ref_show"},
                        {"type": "callback", "text": "🎟 Ввести реф-код", "payload": "growth:ref_enter"},
                    ],
                    [
                        {"type": "callback", "text": "📣 Канал", "payload": "action:channel"},
                        {"type": "callback", "text": "🎁 Промокод", "payload": "growth:promo_enter"},
                    ],
                    [
                        {"type": "callback", "text": "Меню", "payload": "action:menu"},
                    ],
                ]
            },
        }
    ]


def build_growth_input_keyboard() -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [{"type": "callback", "text": "Отмена", "payload": "growth:input_cancel"}],
                    [{"type": "callback", "text": "Меню", "payload": "action:menu"}],
                ]
            },
        }
    ]


def build_receipt_contact_keyboard() -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [{"type": "callback", "text": "Отмена", "payload": "payment:input_cancel"}],
                    [
                        {"type": "callback", "text": "Меню", "payload": "action:menu"},
                        {"type": "callback", "text": "Помощь", "payload": "action:support"},
                    ],
                ]
            },
        }
    ]


def build_onboarding_keyboard(step: int) -> list[dict[str, Any]]:
    if step == 1:
        buttons = [
            [{"type": "callback", "text": "Дальше", "payload": "onboard:2"}],
            [{"type": "callback", "text": "Пропустить", "payload": "onboard:skip"}],
        ]
    elif step == 2:
        buttons = [
            [{"type": "callback", "text": "💬 Задать вопрос", "payload": "onboard:scenario:text"}],
            [{"type": "callback", "text": "🎨 Генерировать картинку", "payload": "onboard:scenario:image"}],
            [{"type": "callback", "text": "💎 Выбрать тариф", "payload": "onboard:scenario:tariff"}],
            [{"type": "callback", "text": "Дальше", "payload": "onboard:3"}],
        ]
    else:
        buttons = [
            [{"type": "callback", "text": "Готово, начать", "payload": "onboard:done"}],
            [{"type": "link", "text": "📣 Канал с обновлениями", "url": channel_url_value()}],
        ]
    return [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]


def get_image_prefs(chat_id: int) -> dict[str, str]:
    prefs = state.image_request_prefs.get(chat_id)
    if not isinstance(prefs, dict):
        prefs = {}
    style = str(prefs.get("style", DEFAULT_IMAGE_STYLE)).strip().lower()
    aspect = str(prefs.get("aspect", DEFAULT_IMAGE_ASPECT)).strip().lower()
    if style not in IMAGE_STYLE_OPTIONS:
        style = DEFAULT_IMAGE_STYLE
    if aspect not in IMAGE_ASPECT_OPTIONS:
        aspect = DEFAULT_IMAGE_ASPECT
    normalized = {"style": style, "aspect": aspect}
    state.image_request_prefs[chat_id] = normalized
    return normalized


def build_image_menu_keyboard(chat_id: int) -> list[dict[str, Any]]:
    prefs = get_image_prefs(chat_id)
    current_style = prefs["style"]
    current_aspect = prefs["aspect"]

    style_buttons: list[dict[str, Any]] = []
    for key in ("auto", "photo", "anime", "art"):
        label = IMAGE_STYLE_OPTIONS[key][0]
        prefix = "● " if key == current_style else ""
        style_buttons.append({"type": "callback", "text": f"{prefix}{label}", "payload": f"image_style:{key}"})

    aspect_buttons: list[dict[str, Any]] = []
    for key in ("square", "portrait", "landscape"):
        label = IMAGE_ASPECT_OPTIONS[key][0]
        prefix = "● " if key == current_aspect else ""
        aspect_buttons.append({"type": "callback", "text": f"{prefix}{label}", "payload": f"image_aspect:{key}"})

    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    style_buttons[:2],
                    style_buttons[2:],
                    aspect_buttons,
                    [
                        {"type": "callback", "text": "✅ Сгенерировать", "payload": "image_prompt:start"},
                    ],
                    [
                        {"type": "callback", "text": "🖼 По фото", "payload": "image_ref:start"},
                    ],
                    [
                        {"type": "callback", "text": "Меню", "payload": "action:menu"},
                        {"type": "callback", "text": "Помощь", "payload": "action:support"},
                    ],
                ]
            },
        }
    ]


def build_image_prompt_keyboard() -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {"type": "callback", "text": "Отмена", "payload": "image_prompt:cancel"},
                    ],
                ]
            },
        }
    ]


def image_params_summary(chat_id: int) -> str:
    prefs = get_image_prefs(chat_id)
    style_label = IMAGE_STYLE_OPTIONS[prefs["style"]][0]
    aspect_label = IMAGE_ASPECT_OPTIONS[prefs["aspect"]][0]
    return f"Стиль: {style_label}\nФормат: {aspect_label}"


def build_image_prompt(user_text: str, chat_id: int) -> str:
    prefs = get_image_prefs(chat_id)
    style_instruction = IMAGE_STYLE_OPTIONS[prefs["style"]][1]
    aspect_instruction = IMAGE_ASPECT_OPTIONS[prefs["aspect"]][1]
    instructions = [part for part in (style_instruction, aspect_instruction) if part]
    if not instructions:
        return user_text
    return f"{user_text}\n\nStyle constraints: {', '.join(instructions)}."


def build_tariffs_keyboard() -> list[dict[str, Any]]:
    return build_tariffs_keyboard_pricing()


def build_tariffs_keyboard_v2() -> list[dict[str, Any]]:
    buy_row_1: list[dict[str, Any]] = [
        {"type": "callback", "text": "Купить Lite", "payload": "buy:lite"},
        {"type": "callback", "text": "Купить Start", "payload": "buy:start"},
    ]
    buy_row_2: list[dict[str, Any]] = [
        {"type": "callback", "text": "Купить Pro", "payload": "buy:pro"},
    ]
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    buy_row_1,
                    buy_row_2,
                    [
                        {"type": "callback", "text": "⭐ Пакеты кредитов", "payload": "action:topups"},
                        {"type": "callback", "text": "Мои оплаты", "payload": "action:payments"},
                    ],
                    [
                        {"type": "callback", "text": "Меню", "payload": "action:menu"},
                        {"type": "callback", "text": "Помощь", "payload": "action:support"},
                    ],
                ]
            },
        }
    ]


def build_payment_request_keyboard(request_id: int, payment_url: str = "") -> list[dict[str, Any]]:
    buttons: list[list[dict[str, Any]]] = []
    buttons.append([{"type": "callback", "text": "Проверить статус", "payload": f"payment_status:{request_id}"}])
    buttons.append([{"type": "callback", "text": "Я оплатил", "payload": f"paid:{request_id}"}])
    buttons.append(
        [
            {"type": "callback", "text": "Меню", "payload": "action:menu"},
            {"type": "callback", "text": "Помощь", "payload": "action:support"},
        ]
    )
    return [
        {
            "type": "inline_keyboard",
            "payload": {"buttons": buttons},
        }
    ]


def build_payments_keyboard(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buttons: list[list[dict[str, Any]]] = []
    for item in rows[:5]:
        request_id = int(item.get("id", 0) or 0)
        if request_id <= 0:
            continue
        status = str(item.get("status", "")).lower()
        if status in {"pending", "claimed"}:
            buttons.append(
                [
                    {
                        "type": "callback",
                        "text": f"Проверить #{request_id}",
                        "payload": f"payment_status:{request_id}",
                    }
                ]
            )

    buttons.append(
        [
            {"type": "callback", "text": "Меню", "payload": "action:menu"},
            {"type": "callback", "text": "Помощь", "payload": "action:support"},
        ]
    )
    return [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]


def build_quick_topup_keyboard(code: str) -> list[dict[str, Any]]:
    pack = topup_spec(code) or topup_spec("medium")
    payload_code = code if topup_spec(code) else "medium"
    label = str(pack.get("label", "Medium")) if pack else "Medium"
    price_rub = int(pack.get("price_rub", TOPUP_MEDIUM_PRICE_RUB)) if pack else TOPUP_MEDIUM_PRICE_RUB
    credits = int(pack.get("credits", TOPUP_MEDIUM_CREDITS)) if pack else TOPUP_MEDIUM_CREDITS
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {
                            "type": "callback",
                            "text": f"⚡ Быстро докупить {label} ({credits} кр / {price_rub}₽)",
                            "payload": f"topup_quick:{payload_code}",
                        }
                    ],
                    [
                        {"type": "callback", "text": "⭐ Все пакеты", "payload": "action:topups"},
                        {"type": "callback", "text": "Тарифы", "payload": "action:tariffs"},
                    ],
                ]
            },
        }
    ]


def build_consent_keyboard(plan: str) -> list[dict[str, Any]]:
    amount, days = plan_price_and_days(plan)
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {
                            "type": "callback",
                            "text": f"Согласен: {amount}₽ каждые {days} дн",
                            "payload": f"buy_consent:{plan}",
                        },
                    ],
                    [
                        {"type": "callback", "text": "Меню", "payload": "action:menu"},
                        {"type": "callback", "text": "Помощь", "payload": "action:support"},
                    ],
                ]
            },
        }
    ]


def build_tariffs_keyboard_pricing() -> list[dict[str, Any]]:
    buy_row_1: list[dict[str, Any]] = [
        {"type": "callback", "text": f"🍬 Lite {LITE_PLAN_PRICE_RUB}₽", "payload": "buy:lite"},
        {"type": "callback", "text": f"👌 Start {START_PLAN_PRICE_RUB}₽", "payload": "buy:start"},
    ]
    buy_row_2: list[dict[str, Any]] = [
        {"type": "callback", "text": f"🚀 Pro {PRO_PLAN_PRICE_RUB}₽", "payload": "buy:pro"},
    ]
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    buy_row_1,
                    buy_row_2,
                    [
                        {"type": "callback", "text": "⭐ Пакеты кредитов", "payload": "action:topups"},
                        {"type": "callback", "text": "Мои оплаты", "payload": "action:payments"},
                    ],
                    [
                        {"type": "callback", "text": "Меню", "payload": "action:menu"},
                        {"type": "callback", "text": "Помощь", "payload": "action:support"},
                    ],
                ]
            },
        }
    ]


def build_topups_keyboard() -> list[dict[str, Any]]:
    small = TOPUP_PACKS["small"]
    medium = TOPUP_PACKS["medium"]
    large = TOPUP_PACKS["large"]
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {
                            "type": "callback",
                            "text": f"🪙 Small {small['credits']} кр • {small['price_rub']}₽",
                            "payload": "topup:small",
                        },
                    ],
                    [
                        {
                            "type": "callback",
                            "text": f"💎 Medium {medium['credits']} кр • {medium['price_rub']}₽",
                            "payload": "topup:medium",
                        },
                    ],
                    [
                        {
                            "type": "callback",
                            "text": f"🚀 Large {large['credits']} кр • {large['price_rub']}₽",
                            "payload": "topup:large",
                        },
                    ],
                    [
                        {"type": "callback", "text": "Меню", "payload": "action:menu"},
                        {"type": "callback", "text": "Помощь", "payload": "action:support"},
                    ],
                ]
            },
        }
    ]


def build_topup_consent_keyboard(code: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {"type": "callback", "text": "Подтверждаю покупку", "payload": f"topup_consent:{code}"},
                    ],
                    [
                        {"type": "callback", "text": "Меню", "payload": "action:menu"},
                        {"type": "callback", "text": "Помощь", "payload": "action:support"},
                    ],
                ]
            },
        }
    ]


def build_plan_keyboard(row: dict[str, Any]) -> list[dict[str, Any]]:
    keyboard = build_keyboard()
    if row.get("plan") != "free" and recurring_enabled_for_row(row):
        keyboard[0]["payload"]["buttons"].append(
            [
                {"type": "callback", "text": "Отменить подписку", "payload": "sub_cancel:start"},
            ]
        )
    return keyboard


def build_cancel_subscription_keyboard() -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {"type": "callback", "text": "Подтвердить отмену", "payload": "sub_cancel:confirm"},
                    ],
                    [
                        {"type": "callback", "text": "Не отменять", "payload": "sub_cancel:back"},
                    ],
                ]
            },
        }
    ]


def plan_access_human(min_plan: str) -> str:
    if min_plan == "free":
        return "free/lite/start/pro"
    if min_plan == "lite":
        return "lite/start/pro"
    if min_plan == "start":
        return "start/pro"
    if min_plan == "pro":
        return "pro"
    return f"{min_plan}+"


def model_line(model: ModelInfo, include_prices: bool) -> str:
    lines = [
        f"{model.alias} — {model.label} ({model.provider})",
        f"версия: {model.version}, доступ: {plan_access_human(model.min_plan)}",
        f"для чего: {model.description}",
    ]
    if model.kind == "text" and model.alias in MODEL_CREDIT_COSTS:
        lines.append(f"списание: {MODEL_CREDIT_COSTS[model.alias]} кредитов/запрос")
    if model.kind == "image":
        lines.append(
            f"списание: {CREDIT_COST_IMAGE} кредитов/картинка, "
            f"{CREDIT_COST_IMAGE_EDIT} кредитов/картинка по фото"
        )
    if include_prices:
        lines.append(f"цена: in ${model.input_price_usd_per_m}/M, out ${model.output_price_usd_per_m}/M")
    return "\n".join(lines)


def build_models_text(user_plan: str, include_prices: bool = False) -> str:
    lines = [f"Текстовые модели (твой план: {user_plan}):"]
    for model in TEXT_MODELS.values():
        prefix = "✅" if plan_allowed(user_plan, model.min_plan) else f"нужно {plan_access_human(model.min_plan)}"
        lines.append(f"\n[{prefix}]\n{model_line(model, include_prices)}")
    image_model = DEFAULT_IMAGE_MODEL
    if user_plan == "free":
        image_prefix = "✅ 1 раз в 7 дней"
    else:
        image_prefix = "✅" if plan_allowed(user_plan, image_model.min_plan) else f"нужно {plan_access_human(image_model.min_plan)}"
    lines.append("\nКартинки:")
    lines.append(f"\n[{image_prefix}]\n{model_line(image_model, include_prices)}")
    return "\n".join(lines)


def build_update_fingerprint(update: dict[str, Any]) -> str:
    try:
        payload = json.dumps(update, sort_keys=True, ensure_ascii=False).encode("utf-8")
    except Exception:
        payload = repr(update).encode("utf-8", errors="ignore")
    return hashlib.sha1(payload).hexdigest()


def remember_update(update: dict[str, Any]) -> bool:
    fingerprint = build_update_fingerprint(update)
    if fingerprint in state.processed_lookup:
        return False
    state.processed_updates.append(fingerprint)
    state.processed_lookup.add(fingerprint)
    while len(state.processed_updates) > DEDUP_CACHE_SIZE:
        old = state.processed_updates.popleft()
        state.processed_lookup.discard(old)
    return True


def image_extension(mime_type: str) -> str:
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
    }.get(mime_type, "png")


def decode_data_url(data_url: str) -> ImageResult:
    header, encoded = data_url.split(",", 1)
    mime_type = "image/png"
    if ";" in header and ":" in header:
        mime_type = header.split(":", 1)[1].split(";", 1)[0]
    return ImageResult(image_bytes=base64.b64decode(encoded), mime_type=mime_type)


def encode_data_url(image: ImageResult) -> str:
    encoded = base64.b64encode(image.image_bytes).decode("ascii")
    return f"data:{image.mime_type};base64,{encoded}"


def parse_incoming_text(update: dict[str, Any]) -> tuple[int | None, str]:
    message = update.get("message") or {}
    recipient = message.get("recipient") or {}
    body = message.get("body") or {}
    chat_id = update.get("chat_id")
    if not isinstance(chat_id, int):
        chat_id = recipient.get("chat_id")
    text = body.get("text")
    if not isinstance(chat_id, int):
        return None, ""
    if not isinstance(text, str):
        return chat_id, ""
    return chat_id, text.strip()


def _extract_nested_int(node: Any, *path: str) -> int | None:
    current = node
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current if isinstance(current, int) else None


def parse_actor_user_id(update: dict[str, Any]) -> int | None:
    candidates = [
        _extract_nested_int(update, "user", "user_id"),
        _extract_nested_int(update, "sender", "user_id"),
        _extract_nested_int(update, "chat", "dialog_with_user", "user_id"),
        _extract_nested_int(update, "message", "sender", "user_id"),
        _extract_nested_int(update, "callback", "user", "user_id"),
        _extract_nested_int(update, "callback", "sender", "user_id"),
        _extract_nested_int(update, "callback", "initiator", "user_id"),
        _extract_nested_int(update, "callback", "message", "recipient", "dialog_with_user", "user_id"),
    ]
    for candidate in candidates:
        if isinstance(candidate, int) and candidate > 0:
            return candidate
    return None


def _walk_for_image_urls(node: Any, found: list[str]) -> None:
    if isinstance(node, dict):
        node_type = str(node.get("type", "")).lower()
        payload = node.get("payload")
        if node_type in {"image", "photo"} and isinstance(payload, dict):
            for key in ("url", "image_url", "imageUrl", "file_url", "src"):
                value = payload.get(key)
                if isinstance(value, str) and value.startswith(("http://", "https://")):
                    found.append(value)
            return

        # Explicit image fields in alternative schemas.
        for key in ("image_url", "imageUrl", "photo_url"):
            value = node.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                found.append(value)
                return

        attachments = node.get("attachments")
        if isinstance(attachments, list):
            for item in attachments:
                _walk_for_image_urls(item, found)
            return

        # Fallback for nested image payloads only.
        if "photo" in node:
            _walk_for_image_urls(node.get("photo"), found)
            return

        if "image" in node:
            _walk_for_image_urls(node.get("image"), found)
            return
    elif isinstance(node, list):
        for item in node:
            _walk_for_image_urls(item, found)


def parse_incoming_image_url(update: dict[str, Any]) -> str:
    found: list[str] = []
    message = update.get("message") if isinstance(update, dict) else None
    if isinstance(message, dict):
        _walk_for_image_urls(message.get("body"), found)
        _walk_for_image_urls(message.get("attachments"), found)
    else:
        _walk_for_image_urls(update, found)
    for url in found:
        low = url.lower()
        if any(ext in low for ext in (".jpg", ".jpeg", ".png", ".webp", "/image", "content-type=image")):
            return url
    return found[0] if found else ""


def parse_callback_source_mid(update: dict[str, Any]) -> str | None:
    callback = update.get("callback") if isinstance(update, dict) else None
    if not isinstance(callback, dict):
        return None
    message = callback.get("message")
    if not isinstance(message, dict):
        return None

    candidates: list[Any] = [
        message.get("mid"),
        (message.get("body") or {}).get("mid") if isinstance(message.get("body"), dict) else None,
        message.get("message_id"),
        (message.get("body") or {}).get("message_id") if isinstance(message.get("body"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, (int, str)) and str(candidate).strip():
            return str(candidate).strip()
    return None


def parse_callback_payload(update: dict[str, Any]) -> tuple[int | None, str | None, str | None, str | None]:
    chat_id, _ = parse_incoming_text(update)
    callback = update.get("callback") or {}
    callback_id = callback.get("callback_id")
    payload = callback.get("payload")
    source_mid = parse_callback_source_mid(update)
    if isinstance(payload, dict):
        payload = payload.get("value") or payload.get("payload") or payload.get("data")
    if not isinstance(callback_id, str):
        callback_id = None
    if not isinstance(payload, str):
        payload = None
    return chat_id, callback_id, payload, source_mid


def is_supported_update(update: dict[str, Any]) -> bool:
    return update.get("update_type") in {
        "message_created",
        "message_callback",
        "bot_started",
        "user_added",
        "bot_added",
    }


def parse_admin_target(value: str) -> int | None:
    value = value.strip()
    if value.startswith("@"):
        value = value[1:]
    if value.isdigit():
        return int(value)
    return None


def normalize_receipt_phone(raw: str) -> str:
    value = raw.strip()
    has_plus = value.startswith("+")
    digits = "".join(ch for ch in value if ch.isdigit())
    if not (10 <= len(digits) <= 15):
        return ""
    return f"+{digits}" if has_plus else digits


def normalize_receipt_email(raw: str) -> str:
    value = raw.strip().lower()
    if not value:
        return ""
    if len(value) > 254:
        return ""
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
        return ""
    return value


def parse_receipt_contact(raw: str) -> tuple[str, str]:
    text = raw.strip()
    if not text:
        return "", ""
    if "@" in text:
        email = normalize_receipt_email(text)
        return email, ""
    phone = normalize_receipt_phone(text)
    return "", phone


def parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def format_msk_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return (value + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M МСК")


def format_remaining_time(target: datetime | None) -> str:
    if target is None:
        return "0 ч."
    delta = target - datetime.utcnow()
    total_seconds = max(0, int(delta.total_seconds()))
    if total_seconds <= 0:
        return "0 ч."
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts: list[str] = []
    if days > 0:
        parts.append(f"{days} д.")
    if hours > 0 or days > 0:
        parts.append(f"{hours} ч.")
    elif minutes > 0:
        parts.append(f"{minutes} мин.")
    else:
        parts.append("1 мин.")
    return " ".join(parts[:2])


def free_image_next_available_at(row: dict[str, Any]) -> datetime | None:
    last_used = parse_iso_datetime(str(row.get("free_image_last_used_at", "") or ""))
    if last_used is None:
        return None
    return last_used + timedelta(days=7)


def free_image_is_available(row: dict[str, Any]) -> bool:
    next_at = free_image_next_available_at(row)
    return next_at is None or datetime.utcnow() >= next_at


def plan_price_and_days(plan: str) -> tuple[int, int]:
    if plan == "lite":
        return LITE_PLAN_PRICE_RUB, LITE_PLAN_DAYS
    if plan == "start":
        return START_PLAN_PRICE_RUB, START_PLAN_DAYS
    if plan == "pro":
        return PRO_PLAN_PRICE_RUB, PRO_PLAN_DAYS
    return 0, 0


def build_tariffs_text() -> str:
    pro_cfg = PLAN_CONFIGS["pro"]
    pro_gpt54_line = f" (GPT-5.4: до {pro_cfg.daily_gpt54_limit}/день)" if pro_cfg.daily_gpt54_limit > 0 else ""
    free_nano_approx = max(0, FREE_DAILY_CREDITS // max(1, CREDIT_COST_GPT))
    free_ds_approx = max(0, FREE_DAILY_CREDITS // max(1, CREDIT_COST_DEEPSEEK))
    return (
        "💠 Тарифы:\n"
        f"• 🆓 free: {FREE_DAILY_CREDITS} кредитов/день (примерно {free_nano_approx} GPT-4.1 Nano или {free_ds_approx} DeepSeek запросов) + 1 картинка / 7 дней\n"
        f"• 🍬 lite: {LITE_PLAN_PRICE_RUB} ₽ / {LITE_PLAN_DAYS} дней, {credits_for_plan('lite')} кредитов\n"
        f"• 👌 start: {START_PLAN_PRICE_RUB} ₽ / {START_PLAN_DAYS} дней, {credits_for_plan('start')} кредитов\n"
        f"• 🚀 pro: {PRO_PLAN_PRICE_RUB} ₽ / {PRO_PLAN_DAYS} дней, {credits_for_plan('pro')} кредитов{pro_gpt54_line}\n\n"
        "🪙 Обычно списывается:\n"
        f"• DeepSeek: ~{CREDIT_COST_DEEPSEEK + 1}\n"
        f"• GPT-4.1 Nano: ~{CREDIT_COST_GPT + 1}\n"
        f"• GPT-4o Mini: ~{CREDIT_COST_GPTO + 1}\n"
        f"• Gemini 2.5 Flash: ~{CREDIT_COST_GEMINI + 1}\n"
        f"• GPT-5.4: ~{CREDIT_COST_GPT54 + 2}\n"
        f"• Картинка: {CREDIT_COST_IMAGE}\n"
        f"• По фото (image-to-image): {CREDIT_COST_IMAGE_EDIT}\n\n"
        "Точное списание за текст зависит от длины и сложности ответа.\n"
        "Для платных тарифов действует автопродление.\n"
        "Перед оплатой мы отдельно попросим согласие с суммой и периодичностью.\n"
        "Отменить автопродление можно в разделе «Мой план».\n\n"
        "Модели по тарифам:\n"
        "• free: DeepSeek V4 Flash, GPT-4.1 Nano, Gemini 2.5 Flash Image (1 раз в 7 дней)\n"
        "• lite/start: + GPT-4o Mini и Gemini 2.5 Flash\n"
        "• pro: + GPT-5.4"
    )


def format_kpi_report(report: dict[str, Any]) -> str:
    days = int(report.get("days", 30) or 30)
    active_users = int(report.get("active_users", 0) or 0)
    payers = int(report.get("payers", 0) or 0)
    revenue_rub = int(report.get("revenue_rub", 0) or 0)
    refunds_rub = int(report.get("refunds_rub", 0) or 0)
    net_rub = revenue_rub + refunds_rub
    text_requests = int(report.get("text_requests", 0) or 0)
    image_requests = int(report.get("image_requests", 0) or 0)
    text_credits = int(report.get("text_credits", 0) or 0)
    image_credits = int(report.get("image_credits", 0) or 0)
    total_credits_spent = int(report.get("total_credits_spent", 0) or 0)
    text_tokens = int(report.get("text_tokens", 0) or 0)

    arpu_active = (net_rub / active_users) if active_users > 0 else 0.0
    arppu = (net_rub / payers) if payers > 0 else 0.0
    pay_share = (payers * 100.0 / active_users) if active_users > 0 else 0.0
    avg_tokens = (text_tokens / text_requests) if text_requests > 0 else 0.0

    lines = [
        f"📊 KPI за {days} дней",
        f"• Активные пользователи: {active_users}",
        f"• Плательщики: {payers} ({pay_share:.1f}%)",
        f"• Выручка: {revenue_rub} ₽",
        f"• Возвраты: {refunds_rub} ₽",
        f"• Чистая выручка: {net_rub} ₽",
        f"• ARPU (по активным): {arpu_active:.1f} ₽",
        f"• ARPPU (по плательщикам): {arppu:.1f} ₽",
        "",
        f"🧠 Текст: {text_requests} запросов, {text_credits} кредитов, ср. токены/запрос: {avg_tokens:.0f}",
        f"🎨 Картинки: {image_requests} запросов, {image_credits} кредитов",
        f"🪙 Всего списано кредитов: {total_credits_spent}",
    ]

    models = report.get("models") or []
    if isinstance(models, list) and models:
        lines.append("")
        lines.append("Топ моделей по текстовым запросам:")
        for item in models[:5]:
            alias = str(item.get("model_alias", "") or "-")
            cnt = int(item.get("cnt", 0) or 0)
            credits = int(item.get("credits", 0) or 0)
            lines.append(f"• {alias}: {cnt} запросов, {credits} кредитов")

    return "\n".join(lines)


def recurring_terms_for_plan(plan: str) -> str:
    amount, days = plan_price_and_days(plan)
    return (
        f"Подписка {plan}: {amount} ₽ каждые {days} дней. "
        "Пользователь подтверждает регулярные списания до отмены. "
        "Отменить автопродление можно в разделе «Мой план»."
    )


async def get_session() -> aiohttp.ClientSession:
    if state.session is None or state.session.closed:
        timeout = aiohttp.ClientTimeout(total=180)
        state.session = aiohttp.ClientSession(timeout=timeout)
    return state.session


def user_profile(chat_id: int) -> dict[str, Any]:
    row = state.user_store.get_or_create_user(chat_id, best_default_alias_for_plan("free"))
    plan = row["plan"]
    expires_at = parse_iso_datetime(row.get("subscription_expires_at", ""))
    if plan != "free" and (expires_at is None or expires_at <= datetime.utcnow()):
        state.user_store.set_plan(chat_id, "free")
        state.user_store.set_selected_model(chat_id, best_default_alias_for_plan("free"))
        row = state.user_store.get_or_create_user(chat_id, best_default_alias_for_plan("free"))
        plan = row["plan"]

    selected = row["selected_model_alias"] or best_default_alias_for_plan(plan)
    info = TEXT_MODELS.get(selected)
    if info is None or not plan_allowed(plan, info.min_plan):
        selected = best_default_alias_for_plan(plan)
        state.user_store.set_selected_model(chat_id, selected)
        state.user_store.set_selected_preset(chat_id, "")
        row = state.user_store.get_or_create_user(chat_id, selected)
    return row


def usage_text(row: dict[str, Any]) -> str:
    plan_name = row["plan"]
    cfg = PLAN_CONFIGS[plan_name]
    gpt54_used = int(row.get("daily_gpt54_used", 0) or 0)
    gpt54_left = max(0, cfg.daily_gpt54_limit - gpt54_used)
    expires_raw = row.get("subscription_expires_at", "")
    expires_at = parse_iso_datetime(expires_raw)
    expires_text = "-"
    if plan_name != "free":
        expires_text = expires_at.strftime("%Y-%m-%d %H:%M UTC") if expires_at else "не задан"
    balance = int(row.get("credits_balance", 0) or 0)
    bonus_total, bonus_expires = state.user_store.active_bonus_credits_summary(int(row.get("chat_id", 0) or 0))
    text = (
        f"План: {plan_name}\n"
        f"Подписка до: {expires_text}\n"
        f"Кредиты: {balance}"
    )
    if bonus_total > 0 and bonus_expires:
        bonus_dt = parse_iso_datetime(bonus_expires)
        bonus_until = bonus_dt.strftime("%Y-%m-%d %H:%M UTC") if bonus_dt else bonus_expires
        text += f"\n🎁 Временный бонус: {bonus_total} кредитов (сгорит {bonus_until})"
    if plan_name == "free":
        text += f"\nДневной бонус free: {FREE_DAILY_CREDITS} кредитов"
        next_at = free_image_next_available_at(row)
        if free_image_is_available(row):
            text += "\nКартинки на free: 1/1 доступна сейчас"
        else:
            text += (
                f"\nКартинки на free: лимит исчерпан. "
                f"Осталось {format_remaining_time(next_at)}. "
                f"Новая будет доступна с {format_msk_datetime(next_at)}."
            )
    if cfg.daily_gpt54_limit > 0:
        text += f"\nGPT-5.4 сегодня: {gpt54_used}/{cfg.daily_gpt54_limit} (осталось {gpt54_left})"
    return text


def recurring_enabled_for_row(row: dict[str, Any]) -> bool:
    return int(row.get("recurring_enabled", 0) or 0) == 1


def recurring_status_text(row: dict[str, Any]) -> str:
    plan_name = str(row.get("plan", "free"))
    if plan_name == "free":
        return ""

    expires_at = parse_iso_datetime(str(row.get("subscription_expires_at", "")))
    expires_text = expires_at.strftime("%Y-%m-%d %H:%M UTC") if expires_at else "не задано"

    if recurring_enabled_for_row(row):
        return (
            "\n\nАвтопродление: включено.\n"
            f"Текущий период действует до {expires_text}.\n"
            "Если хочешь отключить списания — нажми кнопку «Отменить подписку»."
        )

    canceled_at_raw = str(row.get("recurring_canceled_at", ""))
    if not canceled_at_raw:
        return "\n\nАвтопродление: не подключено."

    cancel_from = parse_iso_datetime(str(row.get("recurring_cancel_from", "")))
    cancel_text = cancel_from.strftime("%Y-%m-%d %H:%M UTC") if cancel_from else expires_text
    return (
        "\n\nАвтопродление: отключено.\n"
        f"Подписка действует до конца оплаченного периода: до {expires_text}.\n"
        f"Отмена автопродления с {cancel_text}."
    )


def low_credits_threshold_for_plan(plan_name: str) -> int:
    if plan_name == "free":
        return max(1, LOW_CREDITS_NUDGE_THRESHOLD_FREE)
    return max(1, LOW_CREDITS_NUDGE_THRESHOLD_PAID)


def should_nudge_low_credits(row: dict[str, Any]) -> bool:
    plan_name = str(row.get("plan", "free"))
    balance = int(row.get("credits_balance", 0) or 0)
    threshold = low_credits_threshold_for_plan(plan_name)
    if balance > threshold:
        return False
    chat_id = int(row.get("chat_id", 0) or 0)
    if chat_id <= 0:
        return False
    cooldown = timedelta(hours=max(1, LOW_CREDITS_NUDGE_COOLDOWN_HOURS))
    last = state.last_low_credits_nudge_at.get(chat_id)
    if last and (datetime.utcnow() - last) < cooldown:
        return False
    return True


async def maybe_send_low_credits_nudge(chat_id: int) -> None:
    row = user_profile(chat_id)
    if not should_nudge_low_credits(row):
        return
    plan_name = str(row.get("plan", "free"))
    balance = int(row.get("credits_balance", 0) or 0)
    threshold = low_credits_threshold_for_plan(plan_name)
    state.last_low_credits_nudge_at[chat_id] = datetime.utcnow()
    await max_send_message(
        chat_id,
        (
            f"⚠️ Осталось мало кредитов: {balance} (порог уведомления: {threshold}).\n"
            "Чтобы не прерывать диалог, можно быстро докупить пакет в 1 тап."
        ),
        attachments=build_quick_topup_keyboard(TOPUP_QUICK_CODE),
        notify=False,
    )


def purchase_help_keyboard_for_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    plan_name = str(row.get("plan", "free"))
    if plan_name == "free":
        return build_tariffs_keyboard_pricing()
    return build_quick_topup_keyboard(TOPUP_QUICK_CODE)


def can_use_model(plan: str, model_alias: str) -> tuple[bool, str]:
    info = TEXT_MODELS.get(model_alias)
    if not info:
        return False, "Неизвестная модель. Используй /models"
    if not plan_allowed(plan, info.min_plan):
        return False, f"Модель {info.label} доступна с тарифа {info.min_plan}."
    return True, ""


def check_and_consume_credits(chat_id: int, amount: int, operation_name: str) -> tuple[bool, str]:
    row = user_profile(chat_id)
    plan_name = str(row.get("plan", "free"))
    if amount <= 0:
        return True, ""
    balance = int(row.get("credits_balance", 0) or 0)
    if balance < amount:
        if plan_name == "free":
            return (
                False,
                f"На сегодня free-кредиты закончились для операции «{operation_name}». Нужно {amount}, доступно {balance}. Завтра бонус обновится, либо открой «Тарифы».",
            )
        return (
            False,
            f"Недостаточно кредитов для операции «{operation_name}». Нужно {amount}, доступно {balance}. Открой «Тарифы».",
        )
    ok = state.user_store.consume_credits(chat_id, amount)
    if not ok:
        row = user_profile(chat_id)
        balance = int(row.get("credits_balance", 0) or 0)
        return (
            False,
            f"Недостаточно кредитов для операции «{operation_name}». Нужно {amount}, доступно {balance}. Открой «Тарифы».",
        )
    return True, ""


def check_limit_only(chat_id: int, limit_type: str) -> tuple[bool, str]:
    row = user_profile(chat_id)
    if row["is_blocked"]:
        return False, "Доступ к боту временно ограничен. Напиши в поддержку."
    plan_name = row["plan"]
    cfg = PLAN_CONFIGS[plan_name]

    if limit_type == "messages":
        selected_alias = str(row.get("selected_model_alias") or "")
        if selected_alias == "gpt54" and cfg.daily_gpt54_limit > 0:
            gpt54_used = int(row.get("daily_gpt54_used", 0) or 0)
            if gpt54_used >= cfg.daily_gpt54_limit:
                return False, "Лимит GPT-5.4 на сегодня исчерпан. Выбери другую модель."
        return True, ""

    if limit_type == "images":
        if plan_name == "free":
            if not free_image_is_available(row):
                next_at = free_image_next_available_at(row)
                return (
                    False,
                    f"На free доступна 1 картинка каждые 7 дней. Новая генерация будет доступна с {format_msk_datetime(next_at)}. "
                    "Хочешь больше — открой «Тарифы».",
                )
            return True, ""

        daily_limit = int(cfg.daily_images_limit or 0)
        if daily_limit > 0:
            used = int(row.get("daily_images_used", 0) or 0)
            if used >= daily_limit:
                left = max(0, daily_limit - used)
                return False, f"Лимит картинок на сегодня исчерпан: {used}/{daily_limit} (осталось {left})."
        return True, ""

    return True, ""


def consume_limit(chat_id: int, limit_type: str) -> None:
    row = user_profile(chat_id)
    if limit_type == "messages":
        cfg = PLAN_CONFIGS[row["plan"]]
        if str(row.get("selected_model_alias") or "") == "gpt54" and cfg.daily_gpt54_limit > 0:
            state.user_store.increment_gpt54_usage(chat_id)
        return

    if limit_type == "images":
        if str(row.get("plan", "free")) == "free":
            state.user_store.increment_free_week_image_usage(chat_id)
            return
        state.user_store.increment_image_usage(chat_id)
        return


def check_and_consume_limit(chat_id: int, limit_type: str) -> tuple[bool, str]:
    ok, reason = check_limit_only(chat_id, limit_type)
    if not ok:
        return False, reason
    consume_limit(chat_id, limit_type)
    return True, ""


def check_cooldown(chat_id: int, kind: str) -> tuple[bool, str]:
    now = datetime.utcnow()
    if kind == "message":
        last = state.last_message_at.get(chat_id)
        if last and (now - last).total_seconds() < MESSAGE_COOLDOWN_SECONDS:
            return False, f"Слишком часто. Подожди {MESSAGE_COOLDOWN_SECONDS} сек."
        state.last_message_at[chat_id] = now
        return True, ""

    last = state.last_image_at.get(chat_id)
    if last and (now - last).total_seconds() < IMAGE_COOLDOWN_SECONDS:
        return False, f"Картинки можно запрашивать раз в {IMAGE_COOLDOWN_SECONDS} сек."
    state.last_image_at[chat_id] = now
    return True, ""


async def max_send_message(
    chat_id: int,
    text: str,
    attachments: list[dict[str, Any]] | None = None,
    notify: bool = True,
    text_format: str | None = None,
) -> str | None:
    session = await get_session()
    chunks = split_message(text)
    if not chunks and attachments:
        chunks = [""]

    first_mid: str | None = None
    for index, chunk in enumerate(chunks):
        payload: dict[str, Any] = {
            "type": "text",
            "text": chunk,
            "notify": notify,
        }
        if text_format:
            payload["format"] = text_format
        if attachments and index == 0:
            payload["attachments"] = attachments

        async with session.post(
            f"{MAX_API}/messages",
            headers=max_headers(),
            params={"chat_id": str(chat_id)},
            json=payload,
        ) as resp:
            body_json: Any = None
            with suppress(Exception):
                body_json = await resp.json(content_type=None)
            if resp.status >= 400:
                body = await resp.text()
                raise RuntimeError(f"MAX send error {resp.status}: {body[:500]}")
            if index == 0 and isinstance(body_json, dict):
                first_mid = extract_message_mid(body_json)
    return first_mid


def extract_message_mid(node: Any) -> str | None:
    if isinstance(node, dict):
        for key in ("mid", "message_id", "messageId"):
            value = node.get(key)
            if isinstance(value, (str, int)) and str(value).strip():
                return str(value).strip()
        for key in ("message", "body", "payload", "result", "data"):
            if key in node:
                found = extract_message_mid(node.get(key))
                if found:
                    return found
    elif isinstance(node, list):
        for item in node:
            found = extract_message_mid(item)
            if found:
                return found
    return None


async def max_edit_message(
    chat_id: int,
    message_mid: str,
    text: str,
    attachments: list[dict[str, Any]] | None = None,
    text_format: str | None = None,
) -> bool:
    session = await get_session()
    payload: dict[str, Any] = {
        "type": "text",
        "text": text,
    }
    if text_format:
        payload["format"] = text_format
    if attachments is not None:
        payload["attachments"] = attachments

    async with session.put(
        f"{MAX_API}/messages",
        headers=max_headers(),
        params={"chat_id": str(chat_id), "message_id": str(message_mid)},
        json=payload,
    ) as resp:
        if resp.status >= 400:
            body = await resp.text()
            log.warning("MAX edit error %s (chat_id=%s, mid=%s): %s", resp.status, chat_id, message_mid, body[:300])
            return False
    return True


async def answer_callback(
    callback_id: str,
    notification: str,
    text: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> bool:
    session = await get_session()
    payload: dict[str, Any] = {"notification": notification}
    if text is not None:
        message_payload: dict[str, Any] = {"text": text}
        if attachments:
            message_payload["attachments"] = attachments
        payload["message"] = message_payload
    async with session.post(
        f"{MAX_API}/answers",
        headers=max_headers(),
        params={"callback_id": callback_id},
        json=payload,
    ) as resp:
        response_json: Any = None
        with suppress(Exception):
            response_json = await resp.json(content_type=None)
        if resp.status >= 400:
            body = await resp.text()
            log.warning("Callback answer failed %s: %s", resp.status, body[:300])
            return False
        if isinstance(response_json, dict) and response_json.get("success") is False:
            log.warning("Callback answer returned success=false: %s", response_json)
            return False
    return True


async def get_upload_url(upload_type: str = "image") -> str:
    session = await get_session()
    async with session.post(
        f"{MAX_API}/uploads",
        headers=max_headers(),
        params={"type": upload_type},
    ) as resp:
        body = await resp.json(content_type=None)
        if resp.status >= 400:
            raise RuntimeError(f"MAX uploads error {resp.status}: {body}")
        upload_url = body.get("url")
        if not upload_url:
            raise RuntimeError(f"MAX uploads response has no url: {body}")
        return upload_url


async def upload_image_to_max(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    session = await get_session()
    upload_url = await get_upload_url("image")
    ext = image_extension(mime_type)
    form = aiohttp.FormData()
    form.add_field("data", BytesIO(image_bytes), filename=f"generated.{ext}", content_type=mime_type)

    async with session.post(upload_url, data=form) as resp:
        body = await resp.json(content_type=None)
        if resp.status >= 400:
            raise RuntimeError(f"MAX file upload error {resp.status}: {body}")
        return body


async def send_generated_image(chat_id: int, prompt: str, image: ImageResult, display_prompt: str | None = None) -> None:
    attachment_payload = await upload_image_to_max(image.image_bytes, image.mime_type)
    attachment = {"type": "image", "payload": attachment_payload}
    shown_prompt = display_prompt or prompt
    await max_send_message(
        chat_id,
        f"Готово. Вот картинка по запросу:\n{shown_prompt}",
        attachments=[attachment, *build_reply_shortcuts_keyboard(chat_id)],
    )


async def fetch_image_bytes(url: str, use_max_auth: bool = False) -> ImageResult:
    session = await get_session()
    headers = max_headers() if use_max_auth else None
    async with session.get(url, headers=headers) as resp:
        data = await resp.read()
        if resp.status >= 400:
            raise RuntimeError(f"Image fetch error {resp.status}")
        mime_type = resp.headers.get("Content-Type", "image/png").split(";", 1)[0]
        return ImageResult(image_bytes=data, mime_type=mime_type)


def remember_reference_image(chat_id: int, data_url: str) -> None:
    state.last_reference_image_data_url[chat_id] = data_url
    state.last_reference_image_at[chat_id] = datetime.utcnow()


def get_recent_reference_image(chat_id: int) -> str:
    data_url = state.last_reference_image_data_url.get(chat_id, "")
    ts = state.last_reference_image_at.get(chat_id)
    if not data_url or not ts:
        return ""
    age = datetime.utcnow() - ts
    if age > timedelta(minutes=max(1, REFERENCE_IMAGE_TTL_MINUTES)):
        state.last_reference_image_data_url.pop(chat_id, None)
        state.last_reference_image_at.pop(chat_id, None)
        return ""
    return data_url


def looks_like_image_ref_request(text: str) -> bool:
    value = text.strip().lower()
    if not value:
        return False
    verb = re.search(r"\b(нарисуй|перерисуй|сделай|измени|отрисуй|сгенерируй)\b", value)
    ref = re.search(r"\b(фото|фотк|картинк|из нее|из неё|ее|её|эту|этого человека)\b", value)
    return bool(verb and ref)


def build_text_request(chat_id: int, user_text: str, selected_alias: str | None = None) -> tuple[str, str, ModelInfo, list[dict[str, Any]]]:
    row = user_profile(chat_id)
    plan_name = str(row.get("plan", "free"))
    alias = selected_alias or row["selected_model_alias"] or best_default_alias_for_plan(row["plan"])
    model_info = TEXT_MODELS.get(alias, DEFAULT_TEXT_MODEL)
    history = trim_history_by_chars(list(state.history(chat_id)), MAX_CONTEXT_CHARS)
    messages: list[dict[str, Any]] = [{"role": "system", "content": f"{SYSTEM_PROMPT_BASE} {STYLE_PROMPTS.get(alias, '')}".strip()}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})
    return plan_name, alias, model_info, messages


async def ask_text_model(chat_id: int, user_text: str, selected_alias: str | None = None) -> TextAnswerResult:
    session = await get_session()
    plan_name, alias, model_info, messages = build_text_request(chat_id, user_text, selected_alias=selected_alias)

    payload = {
        "model": model_info.model,
        "messages": messages,
        "max_tokens": completion_tokens_for_plan(plan_name),
    }
    async with session.post(OPENROUTER_CHAT_API, headers=openrouter_headers(), json=payload) as resp:
        data = await resp.json(content_type=None)
        if resp.status >= 400:
            message = data.get("error", {}).get("message", "Unknown OpenRouter error")
            raise RuntimeError(message)

    choice = data["choices"][0]["message"]
    answer = normalize_text_content(choice.get("content")) or "Не удалось получить текстовый ответ."
    answer = truncate_text(answer, MAX_ASSISTANT_OUTPUT_CHARS)
    state.history(chat_id).append({"role": "user", "content": user_text})
    state.history(chat_id).append({"role": "assistant", "content": answer})

    prompt_tokens, completion_tokens, total_tokens = parse_usage_tokens(data)
    if total_tokens <= 0:
        estimated_prompt = estimate_tokens_from_messages(messages)
        total_tokens = estimated_prompt + max(0, completion_tokens)
        prompt_tokens = max(prompt_tokens, estimated_prompt)

    return TextAnswerResult(
        text=answer,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


async def generate_image(prompt: str) -> ImageResult:
    session = await get_session()
    payload = {
        "model": DEFAULT_IMAGE_MODEL.model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
    }

    async with session.post(OPENROUTER_CHAT_API, headers=openrouter_headers(), json=payload) as resp:
        data = await resp.json(content_type=None)
        if resp.status >= 400:
            message = data.get("error", {}).get("message", "Unknown OpenRouter error")
            raise RuntimeError(message)

    message = data["choices"][0]["message"]
    images = message.get("images") or []
    for image in images:
        if not isinstance(image, dict):
            continue
        image_url = image.get("image_url") or image.get("imageUrl") or {}
        if isinstance(image_url, dict):
            url = image_url.get("url")
            if isinstance(url, str) and url.startswith("data:"):
                return decode_data_url(url)
            if isinstance(url, str) and url.startswith("http"):
                return await fetch_image_bytes(url)
    raise RuntimeError("Image was not returned by the selected model.")


async def generate_image_from_reference(prompt: str, reference_image_data_url: str) -> ImageResult:
    session = await get_session()
    payload = {
        "model": DEFAULT_IMAGE_MODEL.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": reference_image_data_url}},
                ],
            }
        ],
        "modalities": ["image", "text"],
    }

    async with session.post(OPENROUTER_CHAT_API, headers=openrouter_headers(), json=payload) as resp:
        data = await resp.json(content_type=None)
        if resp.status >= 400:
            message = data.get("error", {}).get("message", "Unknown OpenRouter error")
            raise RuntimeError(message)

    message = data["choices"][0]["message"]
    images = message.get("images") or []
    for image in images:
        if not isinstance(image, dict):
            continue
        image_url = image.get("image_url") or image.get("imageUrl") or {}
        if isinstance(image_url, dict):
            url = image_url.get("url")
            if isinstance(url, str) and url.startswith("data:"):
                return decode_data_url(url)
            if isinstance(url, str) and url.startswith("http"):
                return await fetch_image_bytes(url)
    raise RuntimeError("Edited image was not returned by the selected model.")


def current_model_label(chat_id: int) -> str:
    row = user_profile(chat_id)
    selected = row["selected_model_alias"] or best_default_alias_for_plan(row["plan"])
    model = TEXT_MODELS.get(selected, DEFAULT_TEXT_MODEL)
    return model.label


def current_model_display(chat_id: int) -> str:
    row = user_profile(chat_id)
    plan = str(row.get("plan", "free"))
    selected = str(row.get("selected_model_alias") or best_default_alias_for_plan(plan))
    model = TEXT_MODELS.get(selected, DEFAULT_TEXT_MODEL)
    preset = str(row.get("selected_preset", "") or "").strip().lower()
    preset_cfg = MODEL_PRESETS.get(preset)
    if preset_cfg and selected == resolve_preset_alias_for_plan(plan, preset):
        return f"{preset_cfg['label']} — {model.label}"
    return model.label


async def send_image_menu(chat_id: int, notify: bool = False) -> None:
    row = user_profile(chat_id)
    plan_name = str(row.get("plan", "free"))
    availability_line = f"Доступно с тарифа {DEFAULT_IMAGE_MODEL.min_plan}."
    if plan_name == "free":
        if not free_image_is_available(row):
            next_at = free_image_next_available_at(row)
            availability_line = (
                f"На free лимит: 1 картинка каждые 7 дней. "
                f"Осталось {format_remaining_time(next_at)}. "
                f"Новая будет доступна с {format_msk_datetime(next_at)}."
            )
        else:
            availability_line = "На free доступна 1 картинка каждые 7 дней."
    else:
        cfg = PLAN_CONFIGS.get(plan_name)
        if cfg and int(cfg.daily_images_limit or 0) > 0:
            used = int(row.get("daily_images_used", 0) or 0)
            daily_limit = int(cfg.daily_images_limit or 0)
            left = max(0, daily_limit - used)
            availability_line = f"Лимит на сегодня: {used}/{daily_limit} (осталось {left})."

    text = (
        "Генерация картинки\n\n"
        f"{image_params_summary(chat_id)}\n\n"
        f"{availability_line}\n"
        f"Стоимость: {CREDIT_COST_IMAGE} кредитов за 1 генерацию.\n\n"
        f"По фото (image-to-image): {CREDIT_COST_IMAGE_EDIT} кредитов (с тарифа {DEFAULT_IMAGE_MODEL.min_plan}).\n\n"
        "Выбери стиль и формат, затем нажми «Сгенерировать» или «По фото»."
    )
    await show_managed_content(
        chat_id,
        text,
        attachments=build_image_menu_keyboard(chat_id),
        page=UI_PAGE_IMAGE_MENU,
        push_history=False,
        force_new=False,
    )


async def process_image_generation(chat_id: int, user_prompt: str, model_prompt: str | None = None) -> bool:
    prompt = user_prompt.strip()
    if not prompt:
        await max_send_message(chat_id, "Опиши, что нужно сгенерировать.", attachments=build_image_prompt_keyboard())
        return True
    if len(prompt) > MAX_IMAGE_PROMPT_CHARS:
        await max_send_message(
            chat_id,
            f"Слишком длинный промпт. Максимум {MAX_IMAGE_PROMPT_CHARS} символов.",
            attachments=build_keyboard(),
        )
        return True

    ok_cd, reason_cd = check_cooldown(chat_id, "image")
    if not ok_cd:
        await max_send_message(chat_id, reason_cd, attachments=build_keyboard())
        return True

    row = user_profile(chat_id)
    if row["plan"] != "free" and not plan_allowed(row["plan"], DEFAULT_IMAGE_MODEL.min_plan):
        await max_send_message(
            chat_id,
            f"Картинки доступны с тарифа {DEFAULT_IMAGE_MODEL.min_plan}. Открой «Тарифы».",
            attachments=build_tariffs_keyboard_pricing(),
        )
        return True

    ok, reason = check_limit_only(chat_id, "images")
    if not ok:
        await max_send_message(chat_id, reason, attachments=build_keyboard())
        return True

    img_cost = image_credit_cost()
    ok_credit, reason_credit = check_and_consume_credits(chat_id, img_cost, "картинка")
    if not ok_credit:
        await max_send_message(chat_id, reason_credit, attachments=purchase_help_keyboard_for_row(row))
        return True

    ok, reason = check_and_consume_limit(chat_id, "images")
    if not ok:
        state.user_store.refund_credits(chat_id, img_cost)
        await max_send_message(chat_id, reason, attachments=build_keyboard())
        return True

    await max_send_message(chat_id, "Генерирую картинку, это может занять немного времени...")
    request_for_model = model_prompt or prompt
    try:
        image = await generate_image(request_for_model)
        await send_generated_image(chat_id, request_for_model, image, display_prompt=prompt)
        final_row = user_profile(chat_id)
        state.user_store.record_usage_event(
            chat_id=chat_id,
            event_type="image_request",
            plan=str(final_row.get("plan", "")),
            model_alias=DEFAULT_IMAGE_MODEL.alias,
            credits_spent=img_cost,
            tokens_total=0,
            details=f"style={get_image_prefs(chat_id).get('style','')};aspect={get_image_prefs(chat_id).get('aspect','')}",
        )
        with suppress(Exception):
            await maybe_send_low_credits_nudge(chat_id)
    except Exception:
        state.user_store.refund_credits(chat_id, img_cost)
        raise
    return True


async def process_image_edit_generation(chat_id: int, user_prompt: str, reference_image_data_url: str) -> bool:
    prompt = user_prompt.strip()
    if not prompt:
        await max_send_message(chat_id, "Опиши, что изменить на фото.", attachments=build_image_prompt_keyboard())
        return True
    if len(prompt) > MAX_IMAGE_PROMPT_CHARS:
        await max_send_message(
            chat_id,
            f"Слишком длинный промпт. Максимум {MAX_IMAGE_PROMPT_CHARS} символов.",
            attachments=build_keyboard(),
        )
        return True

    row = user_profile(chat_id)
    if row["plan"] == "free" or not plan_allowed(row["plan"], DEFAULT_IMAGE_MODEL.min_plan):
        await max_send_message(
            chat_id,
            f"Режим «по фото» доступен с тарифа {DEFAULT_IMAGE_MODEL.min_plan}. Открой «Тарифы».",
            attachments=build_tariffs_keyboard_pricing(),
        )
        return True

    ok_cd, reason_cd = check_cooldown(chat_id, "image")
    if not ok_cd:
        await max_send_message(chat_id, reason_cd, attachments=build_keyboard())
        return True

    ok, reason = check_limit_only(chat_id, "images")
    if not ok:
        await max_send_message(chat_id, reason, attachments=build_keyboard())
        return True

    edit_cost = max(CREDIT_COST_IMAGE_EDIT, CREDIT_COST_IMAGE + 1)
    ok_credit, reason_credit = check_and_consume_credits(chat_id, edit_cost, "картинка по фото")
    if not ok_credit:
        await max_send_message(chat_id, reason_credit, attachments=purchase_help_keyboard_for_row(row))
        return True

    ok, reason = check_and_consume_limit(chat_id, "images")
    if not ok:
        state.user_store.refund_credits(chat_id, edit_cost)
        await max_send_message(chat_id, reason, attachments=build_keyboard())
        return True

    await max_send_message(chat_id, "Обрабатываю фото и генерирую вариант, это может занять немного времени...")
    prepared_prompt = build_image_prompt(prompt, chat_id)
    try:
        image = await generate_image_from_reference(prepared_prompt, reference_image_data_url)
        await send_generated_image(chat_id, prepared_prompt, image, display_prompt=prompt)
        final_row = user_profile(chat_id)
        state.user_store.record_usage_event(
            chat_id=chat_id,
            event_type="image_request",
            plan=str(final_row.get("plan", "")),
            model_alias=f"{DEFAULT_IMAGE_MODEL.alias}:edit",
            credits_spent=edit_cost,
            tokens_total=0,
            details=f"mode=image_edit;style={get_image_prefs(chat_id).get('style','')};aspect={get_image_prefs(chat_id).get('aspect','')}",
        )
        with suppress(Exception):
            await maybe_send_low_credits_nudge(chat_id)
    except Exception:
        state.user_store.refund_credits(chat_id, edit_cost)
        raise
    return True


async def handle_pending_image_prompt_input(chat_id: int, text: str) -> bool:
    if chat_id not in state.pending_image_prompt:
        return False

    lowered = text.strip().lower()
    if lowered in {"отмена", "cancel", "/cancel", "стоп", "/stop"}:
        state.pending_image_prompt.discard(chat_id)
        await max_send_message(chat_id, "Ок, генерацию отменил.", attachments=build_image_menu_keyboard(chat_id))
        return True

    if text.strip().startswith("/"):
        state.pending_image_prompt.discard(chat_id)
        return False

    state.pending_image_prompt.discard(chat_id)
    prepared_prompt = build_image_prompt(text.strip(), chat_id)
    await process_image_generation(chat_id, text.strip(), model_prompt=prepared_prompt)
    return True


async def handle_pending_image_ref_prompt_input(chat_id: int, text: str) -> bool:
    if chat_id not in state.pending_image_ref_prompt:
        return False

    lowered = text.strip().lower()
    if lowered in {"отмена", "cancel", "/cancel", "стоп", "/stop"}:
        state.pending_image_ref_prompt.discard(chat_id)
        await max_send_message(chat_id, "Ок, режим «по фото» отменил.", attachments=build_image_menu_keyboard(chat_id))
        return True

    if text.strip().startswith("/"):
        state.pending_image_ref_prompt.discard(chat_id)
        return False

    reference = get_recent_reference_image(chat_id)
    if not reference:
        await max_send_message(
            chat_id,
            "Сначала отправь фото, потом напиши, что с ним сделать.",
            attachments=build_image_menu_keyboard(chat_id),
        )
        return True

    state.pending_image_ref_prompt.discard(chat_id)
    await process_image_edit_generation(chat_id, text.strip(), reference)
    return True


async def send_help(chat_id: int) -> None:
    help_base = HELP_TEXT
    admin_part = ADMIN_HELP_TEXT if is_admin(chat_id) else ""
    text = (
        f"{help_base}"
        f"{admin_part}"
    )
    await send_managed_message(chat_id, text, attachments=build_keyboard(), page=UI_PAGE_MENU)


async def send_menu(chat_id: int) -> None:
    row = user_profile(chat_id)
    preset_block = build_preset_block(str(row.get("plan", "free")))
    capabilities = (
        "Что умею:\n"
        "• ⚡ ответы через GPT, Gemini и DeepSeek\n"
        f"• 🎨 {image_capability_line().replace('• ', '')}\n"
        "• 🧠 сохранение контекста диалога"
    )
    text = (
        "Главное меню\n\n"
        "Выбери режим кнопками или просто напиши вопрос.\n\n"
        f"{capabilities}\n\n"
        f"{preset_block}\n\n"
        f"{current_model_focus_block(chat_id)}\n"
        f"{usage_text(row)}\n\n"
        f"{MENU_TEXT}"
    )
    await send_managed_message(chat_id, text, attachments=build_keyboard(), page=UI_PAGE_MENU)


UI_PAGE_MENU = "menu"
UI_PAGE_MODELS = "models"
UI_PAGE_PLAN = "plan"
UI_PAGE_TARIFFS = "tariffs"
UI_PAGE_TOPUPS = "topups"
UI_PAGE_PAYMENTS = "payments"
UI_PAGE_GROWTH = "growth"
UI_PAGE_SUPPORT = "support"
UI_PAGE_IMAGE_MENU = "image_menu"

UI_PAGE_KEYS = {
    UI_PAGE_MENU,
    UI_PAGE_MODELS,
    UI_PAGE_PLAN,
    UI_PAGE_TARIFFS,
    UI_PAGE_TOPUPS,
    UI_PAGE_PAYMENTS,
    UI_PAGE_GROWTH,
    UI_PAGE_SUPPORT,
    UI_PAGE_IMAGE_MENU,
}

UI_HISTORY_LIMIT = 20


def ui_back_stack(chat_id: int) -> list[str]:
    return state.ui_back_stack.setdefault(chat_id, [])


def ui_forward_stack(chat_id: int) -> list[str]:
    return state.ui_forward_stack.setdefault(chat_id, [])


def ui_can_go_back(chat_id: int) -> bool:
    return bool(ui_back_stack(chat_id))


def ui_can_go_forward(chat_id: int) -> bool:
    return bool(ui_forward_stack(chat_id))


def ui_set_page(chat_id: int, page: str, push_history: bool = True) -> None:
    current = state.ui_current_page.get(chat_id)
    if push_history and current is None and page != UI_PAGE_MENU:
        back = ui_back_stack(chat_id)
        back.append(UI_PAGE_MENU)
        ui_forward_stack(chat_id).clear()
    if push_history and current and current != page:
        back = ui_back_stack(chat_id)
        back.append(current)
        if len(back) > UI_HISTORY_LIMIT:
            del back[:-UI_HISTORY_LIMIT]
        ui_forward_stack(chat_id).clear()
    state.ui_current_page[chat_id] = page


def ui_nav_back(chat_id: int) -> str | None:
    back = ui_back_stack(chat_id)
    if not back:
        return None
    target = back.pop()
    current = state.ui_current_page.get(chat_id)
    if current:
        fwd = ui_forward_stack(chat_id)
        fwd.append(current)
        if len(fwd) > UI_HISTORY_LIMIT:
            del fwd[:-UI_HISTORY_LIMIT]
    state.ui_current_page[chat_id] = target
    return target


def ui_nav_forward(chat_id: int) -> str | None:
    fwd = ui_forward_stack(chat_id)
    if not fwd:
        return None
    target = fwd.pop()
    current = state.ui_current_page.get(chat_id)
    if current:
        back = ui_back_stack(chat_id)
        back.append(current)
        if len(back) > UI_HISTORY_LIMIT:
            del back[:-UI_HISTORY_LIMIT]
    state.ui_current_page[chat_id] = target
    return target


def add_ui_nav_buttons(chat_id: int, attachments: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    result = json.loads(json.dumps(attachments or []))
    nav_row: list[dict[str, Any]] = []
    if ui_can_go_back(chat_id):
        nav_row.append({"type": "callback", "text": "◀ Назад", "payload": "ui_nav:back"})
    if ui_can_go_forward(chat_id):
        nav_row.append({"type": "callback", "text": "↩ Откат", "payload": "ui_nav:forward"})
    if not nav_row:
        return result

    if result and isinstance(result[0], dict) and result[0].get("type") == "inline_keyboard":
        keyboard_payload = result[0].setdefault("payload", {})
        buttons = keyboard_payload.setdefault("buttons", [])
        if isinstance(buttons, list):
            buttons.append(nav_row)
            return result
    return [{"type": "inline_keyboard", "payload": {"buttons": [nav_row]}}]


def resolve_edit_target_mid(chat_id: int, source_mid: str | None, force_new: bool = False) -> str | None:
    if force_new:
        return None
    if source_mid:
        return source_mid
    return state.ui_message_mid.get(chat_id)


def current_model_focus_block(chat_id: int) -> str:
    return (
        "────────────\n"
        f"**Сейчас выбрана модель:** {current_model_display(chat_id)}\n"
        "────────────"
    )


def build_topups_text() -> str:
    small = TOPUP_PACKS["small"]
    medium = TOPUP_PACKS["medium"]
    large = TOPUP_PACKS["large"]

    def approx_images(credits: int) -> int:
        if CREDIT_COST_IMAGE <= 0:
            return 0
        return credits // CREDIT_COST_IMAGE

    return (
        "⭐ Пакеты кредитов\n\n"
        f"• Small: {small['credits']} кредитов за {small['price_rub']} ₽ (~{approx_images(int(small['credits']))} картинок)\n"
        f"• Medium: {medium['credits']} кредитов за {medium['price_rub']} ₽ (~{approx_images(int(medium['credits']))} картинок)\n"
        f"• Large: {large['credits']} кредитов за {large['price_rub']} ₽ (~{approx_images(int(large['credits']))} картинок)\n\n"
        "Кредиты списываются за запросы к моделям и генерацию картинок.\n"
        "Перед созданием оплаты бот попросит подтверждение покупки пакета."
    )


def build_payments_text(chat_id: int) -> tuple[str, list[dict[str, Any]]]:
    rows = state.user_store.list_user_payments(chat_id, limit=8)
    if not rows:
        return "Заявок пока нет. Используй кнопку «Тарифы».", build_keyboard()
    lines = ["Мои оплаты:"]
    for item in rows:
        status = str(item["status"]).lower()
        status_human = payment_status_label(status)
        lines.append(
            f"#{item['id']} • {item['plan']} • {item['amount_rub']} ₽ • {status_human}"
        )
    lines.append("\nНажми «Проверить #...», чтобы обновить статус.")
    return "\n".join(lines), build_payments_keyboard(rows)


def build_ui_page_payload(chat_id: int, page: str) -> tuple[str, list[dict[str, Any]]]:
    row = user_profile(chat_id)
    if page == UI_PAGE_MENU:
        preset_block = build_preset_block(str(row.get("plan", "free")))
        capabilities = (
            "Что умею:\n"
            "• ⚡ ответы через GPT, Gemini и DeepSeek\n"
            f"• 🎨 {image_capability_line().replace('• ', '')}\n"
            "• 🧠 сохранение контекста диалога"
        )
        text = (
            "Главное меню\n\n"
            "Выбери режим кнопками или просто напиши вопрос.\n\n"
            f"{capabilities}\n\n"
            f"{preset_block}\n\n"
            f"{current_model_focus_block(chat_id)}\n"
            f"{usage_text(row)}\n\n"
            f"{MENU_TEXT}"
        )
        return text, build_keyboard()
    if page == UI_PAGE_MODELS:
        return build_models_text(row["plan"], include_prices=False), build_keyboard()
    if page == UI_PAGE_PLAN:
        return f"{usage_text(row)}{recurring_status_text(row)}", build_plan_keyboard(row)
    if page == UI_PAGE_TARIFFS:
        return build_tariffs_text(), build_tariffs_keyboard_pricing()
    if page == UI_PAGE_TOPUPS:
        return build_topups_text(), build_topups_keyboard()
    if page == UI_PAGE_PAYMENTS:
        return build_payments_text(chat_id)
    if page == UI_PAGE_GROWTH:
        referral_code = str(row.get("referral_code", "")).strip() or referral_code_for_chat(chat_id)
        invited = int(row.get("referrals_invited", 0) or 0)
        referred_by = int(row.get("referred_by_chat_id", 0) or 0)
        promo_items = sorted(promo_catalog().items())
        promo_lines = [f"• {code}: +{credits} кредитов" for code, credits in promo_items[:6]]
        channel = channel_promo_meta()
        channel_block = "Бонус за подписку на канал пока отключен: в боте еще нет честной автопроверки подписки."
        if channel["enabled"]:
            if channel["active"]:
                promo_lines.append(
                    f"• {channel['code']}: +{channel['credits']} кредитов (акция {channel['days_left']} дн, бонус на {channel['bonus_ttl_days']} дн)"
                )
                channel_block = (
                    f"Бонус за канал: +{channel['credits']} кредитов.\n"
                    f"Срок акции: еще {channel['days_left']} дн.\n"
                    f"Срок бонуса: {channel['bonus_ttl_days']} дн.\n"
                    "Автопроверка подписки пока не подключена, поэтому выдача бонуса отключена."
                )
            else:
                promo_lines.append(f"• {channel['code']}: акция завершена")
                channel_block = "Акция с бонусом за канал уже завершена."
        promo_block = "\n".join(promo_lines) if promo_lines else "• Сейчас активных промокодов нет"
        text = (
            "🎁 Бонусы и приглашения\n\n"
            f"Твой реф-код: {referral_code}\n"
            f"Приглашено друзей: {invited}\n"
            f"Ты приглашен по реф-коду: {'да' if referred_by > 0 else 'нет'}\n"
            f"Бонус за друга: {REFERRAL_BONUS_CREDITS} кредитов тебе и другу.\n"
            "Друг активирует код командой: /ref <код>\n\n"
            f"{channel_block}\n\n"
            "Доступные промокоды:\n"
            f"{promo_block}\n\n"
            f"{f'Базовый промокод: /promo WELCOME (+{PROMO_WELCOME_CREDITS} кредитов, 1 раз)\\n' if PROMO_WELCOME_CREDITS > 0 else ''}"
            "Обновления и кейсы: в нашем канале."
        )
        return text, build_growth_keyboard()
    if page == UI_PAGE_SUPPORT:
        return support_help_text(), build_keyboard()
    if page == UI_PAGE_IMAGE_MENU:
        text = (
            "Режим «Картинка»\n"
            "Переключи стиль и формат, потом нажми «Сгенерировать».\n"
            f"Списание: {CREDIT_COST_IMAGE} кредитов/картинка.\n"
            f"По фото: {CREDIT_COST_IMAGE_EDIT} кредитов.\n"
            "На Free действует дополнительный лимит: не более 1 картинки каждые 7 дней.\n\n"
            f"{image_params_summary(chat_id)}\n\n"
            "Можно ввести /image <описание> или /image_ref <описание>."
        )
        return text, build_image_menu_keyboard(chat_id)
    return "Открой меню и выбери раздел.", build_keyboard()


async def show_ui_page(
    chat_id: int,
    page: str,
    callback_id: str | None = None,
    source_mid: str | None = None,
    push_history: bool = True,
    notification: str = "Открываю",
    force_new: bool = False,
) -> None:
    text, attachments = build_ui_page_payload(chat_id, page)
    ui_set_page(chat_id, page, push_history=push_history)
    attachments = add_ui_nav_buttons(chat_id, attachments)

    target_mid = resolve_edit_target_mid(chat_id, source_mid, force_new=force_new)
    if target_mid:
        ok = await max_edit_message(chat_id, target_mid, text, attachments=attachments)
        if ok:
            state.ui_message_mid[chat_id] = target_mid
            if callback_id:
                await answer_callback(callback_id, notification)
            return

    sent_mid = await max_send_message(chat_id, text, attachments=attachments, notify=False)
    if sent_mid:
        state.ui_message_mid[chat_id] = sent_mid
    if callback_id:
        await answer_callback(callback_id, notification)


async def show_managed_content(
    chat_id: int,
    text: str,
    attachments: list[dict[str, Any]] | None = None,
    callback_id: str | None = None,
    source_mid: str | None = None,
    page: str | None = None,
    push_history: bool = False,
    notification: str = "Открываю",
    force_new: bool = False,
) -> None:
    if page in UI_PAGE_KEYS:
        ui_set_page(chat_id, str(page), push_history=push_history)
    attachments = add_ui_nav_buttons(chat_id, attachments)

    target_mid = resolve_edit_target_mid(chat_id, source_mid, force_new=force_new)
    if target_mid:
        ok = await max_edit_message(chat_id, target_mid, text, attachments=attachments)
        if ok:
            state.ui_message_mid[chat_id] = target_mid
            if callback_id:
                await answer_callback(callback_id, notification)
            return

    sent_mid = await max_send_message(chat_id, text, attachments=attachments, notify=False)
    if sent_mid:
        state.ui_message_mid[chat_id] = sent_mid
    if callback_id:
        await answer_callback(callback_id, notification)


async def send_managed_message(
    chat_id: int,
    text: str,
    attachments: list[dict[str, Any]] | None = None,
    notify: bool = False,
    page: str | None = None,
    push_history: bool = False,
) -> str | None:
    if page in UI_PAGE_KEYS:
        ui_set_page(chat_id, page, push_history=push_history)
    sent_mid = await max_send_message(chat_id, text, attachments=attachments, notify=notify)
    if sent_mid:
        state.ui_message_mid[chat_id] = sent_mid
    return sent_mid


async def send_onboarding(chat_id: int, step: int = 1, notify: bool = False) -> None:
    row = user_profile(chat_id)
    if step <= 1:
        text = (
            "👋 Добро пожаловать!\n\n"
            "Это AI-бот в MAX:\n"
            "• ответы через GPT, Gemini и DeepSeek\n"
            "• генерация картинок\n"
            "• кредиты и прозрачные лимиты\n\n"
            "Давай за 3 коротких шага покажу как пользоваться."
        )
    elif step == 2:
        text = (
            "⚡ Шаг 2/3: выбери быстрый сценарий\n\n"
            "• вопрос/текст\n"
            "• картинка\n"
            "• выбор тарифа\n\n"
            "Можно нажать кнопку ниже или просто написать сообщение."
        )
    else:
        text = (
            "✅ Шаг 3/3: всё готово\n\n"
            f"Сейчас модель: {current_model_label(chat_id)}\n"
            f"{usage_text(row)}\n\n"
            "Нажми «Готово, начать», и открою основное меню."
        )
    sent_mid = await max_send_message(chat_id, text, attachments=build_onboarding_keyboard(step), notify=notify)
    if sent_mid:
        state.onboarding_message_mid[chat_id] = sent_mid


async def show_onboarding_step(
    chat_id: int,
    step: int,
    callback_id: str | None = None,
    source_mid: str | None = None,
    notification: str = "Открываю",
) -> None:
    row = user_profile(chat_id)
    if step <= 1:
        text = (
            "👋 Добро пожаловать!\n\n"
            "Это AI-бот в MAX:\n"
            "• ответы через GPT, Gemini и DeepSeek\n"
            "• генерация картинок\n"
            "• кредиты и прозрачные лимиты\n\n"
            "Давай за 3 коротких шага покажу как пользоваться."
        )
    elif step == 2:
        text = (
            "⚡ Шаг 2/3: выбери быстрый сценарий\n\n"
            "• вопрос/текст\n"
            "• картинка\n"
            "• выбор тарифа\n\n"
            "Можно нажать кнопку ниже или просто написать сообщение."
        )
    else:
        text = (
            "✅ Шаг 3/3: всё готово\n\n"
            f"Сейчас модель: {current_model_label(chat_id)}\n"
            f"{usage_text(row)}\n\n"
            "Нажми «Готово, начать», и открою основное меню."
        )
    target_mid = source_mid or state.onboarding_message_mid.get(chat_id)
    if target_mid:
        ok = await max_edit_message(chat_id, target_mid, text, attachments=build_onboarding_keyboard(step))
        if ok:
            state.onboarding_message_mid[chat_id] = target_mid
            if callback_id:
                await answer_callback(callback_id, notification)
            return
    sent_mid = await max_send_message(chat_id, text, attachments=build_onboarding_keyboard(step), notify=False)
    if sent_mid:
        state.onboarding_message_mid[chat_id] = sent_mid
    if callback_id:
        await answer_callback(callback_id, notification)


async def close_onboarding_message(chat_id: int, source_mid: str | None, text: str = " ") -> None:
    target_mid = source_mid or state.onboarding_message_mid.get(chat_id)
    if not target_mid:
        return
    with suppress(Exception):
        await max_edit_message(chat_id, target_mid, text, attachments=[])
    state.onboarding_message_mid.pop(chat_id, None)


async def send_growth_menu(chat_id: int) -> None:
    row = user_profile(chat_id)
    referral_code = str(row.get("referral_code", "")).strip() or referral_code_for_chat(chat_id)
    invited = int(row.get("referrals_invited", 0) or 0)
    referred_by = int(row.get("referred_by_chat_id", 0) or 0)
    promo_items = sorted(promo_catalog().items())
    promo_lines = [f"• {code}: +{credits} кредитов" for code, credits in promo_items[:6]]
    channel = channel_promo_meta()
    if channel["enabled"]:
        if channel["active"]:
            promo_lines.append(
                f"• {channel['code']}: +{channel['credits']} кредитов (акция {channel['days_left']} дн, бонус на {channel['bonus_ttl_days']} дн)"
            )
        else:
            promo_lines.append(f"• {channel['code']}: акция завершена")
    promo_block = "\n".join(promo_lines) if promo_lines else "• Сейчас активных промокодов нет"
    text = (
        "🎁 Бонусы и приглашения\n\n"
        f"Твой реф-код: {referral_code}\n"
        f"Приглашено друзей: {invited}\n"
        f"Ты приглашен по реф-коду: {'да' if referred_by > 0 else 'нет'}\n"
        f"Бонус за друга: {REFERRAL_BONUS_CREDITS} кредитов тебе и другу.\n"
        "Друг активирует код командой: /ref <код>\n\n"
        "Доступные промокоды:\n"
        f"{promo_block}\n\n"
        f"{f'Базовый промокод: /promo WELCOME (+{PROMO_WELCOME_CREDITS} кредитов, 1 раз)\\n' if PROMO_WELCOME_CREDITS > 0 else ''}"
        "Обновления и кейсы: в нашем канале."
    )
    await send_managed_message(chat_id, text, attachments=build_growth_keyboard(), page=UI_PAGE_GROWTH)


async def send_channel(chat_id: int) -> None:
    await send_managed_message(
        chat_id,
        f"📣 Канал проекта:\n{channel_url_value()}",
        attachments=build_keyboard(),
    )


async def send_reengage_nudges(days: int, limit: int) -> tuple[int, int]:
    targets = state.user_store.list_reengage_candidates(days, limit)
    sent = 0
    total = len(targets)
    for item in targets:
        target = int(item.get("chat_id", 0) or 0)
        if target <= 0:
            continue
        with suppress(Exception):
            await max_send_message(
                target,
                (
                    "👋 Возвращайся, у тебя снова доступна 1 бесплатная картинка.\n"
                    "Нажми «🎨 Картинка» и отправь идею."
                ),
                attachments=build_keyboard(),
                notify=False,
            )
            sent += 1
    return sent, total


async def send_models(chat_id: int) -> None:
    row = user_profile(chat_id)
    await send_managed_message(chat_id, build_models_text(row["plan"], include_prices=False), attachments=build_keyboard(), page=UI_PAGE_MODELS)


async def send_costs(chat_id: int) -> None:
    row = user_profile(chat_id)
    await send_managed_message(chat_id, build_models_text(row["plan"], include_prices=True), attachments=build_keyboard())


async def send_plan(chat_id: int) -> None:
    row = user_profile(chat_id)
    text = f"{usage_text(row)}{recurring_status_text(row)}"
    await send_managed_message(chat_id, text, attachments=build_plan_keyboard(row), page=UI_PAGE_PLAN)


async def send_credits(chat_id: int) -> None:
    row = user_profile(chat_id)
    plan_name = str(row.get("plan", "free"))
    if plan_name not in PAID_PLANS:
        await send_managed_message(
            chat_id,
            f"🆓 На free каждый день доступно {FREE_DAILY_CREDITS} кредитов.\nСейчас у тебя: {int(row.get('credits_balance', 0) or 0)}.",
            attachments=build_tariffs_keyboard_pricing(),
            page=UI_PAGE_TARIFFS,
        )
        return
    text = (
        f"🪙 Твой баланс: {int(row.get('credits_balance', 0) or 0)} кредитов.\n\n"
        "Обычно списывается:\n"
        f"• DeepSeek: ~{CREDIT_COST_DEEPSEEK + 1}\n"
        f"• GPT-4.1 Nano: ~{CREDIT_COST_GPT + 1}\n"
        f"• GPT-4o Mini: ~{CREDIT_COST_GPTO + 1}\n"
        f"• Gemini 2.5 Flash: ~{CREDIT_COST_GEMINI + 1}\n"
        f"• GPT-5.4: ~{CREDIT_COST_GPT54 + 2}\n"
        f"• Картинка: {CREDIT_COST_IMAGE}\n"
        f"• По фото: {CREDIT_COST_IMAGE_EDIT}"
    )
    await send_managed_message(chat_id, text, attachments=build_keyboard(), page=UI_PAGE_PLAN)


async def send_topups(chat_id: int) -> None:
    small = TOPUP_PACKS["small"]
    medium = TOPUP_PACKS["medium"]
    large = TOPUP_PACKS["large"]

    def approx_images(credits: int) -> int:
        if CREDIT_COST_IMAGE <= 0:
            return 0
        return credits // CREDIT_COST_IMAGE

    text = (
        "⭐ Пакеты кредитов\n\n"
        f"• Small: {small['credits']} кредитов за {small['price_rub']} ₽ (~{approx_images(int(small['credits']))} картинок)\n"
        f"• Medium: {medium['credits']} кредитов за {medium['price_rub']} ₽ (~{approx_images(int(medium['credits']))} картинок)\n"
        f"• Large: {large['credits']} кредитов за {large['price_rub']} ₽ (~{approx_images(int(large['credits']))} картинок)\n\n"
        "Кредиты списываются за запросы к моделям и генерацию картинок.\n"
        "Перед созданием оплаты бот попросит подтверждение покупки пакета."
    )
    await send_managed_message(chat_id, text, attachments=build_topups_keyboard(), page=UI_PAGE_TOPUPS)


async def send_topup_consent(
    chat_id: int,
    code: str,
    notify: bool = False,
    callback_id: str | None = None,
    source_mid: str | None = None,
) -> bool:
    pack = topup_spec(code)
    if not pack:
        await max_send_message(chat_id, "Неизвестный пакет кредитов.", attachments=build_topups_keyboard(), notify=notify)
        return False
    text = (
        f"Пакет: {pack['label']}\n"
        f"Кредитов: {int(pack['credits'])}\n"
        f"Стоимость: {int(pack['price_rub'])} ₽\n\n"
        "Это разовая покупка без автосписаний.\n"
        "Подтверди покупку кнопкой ниже."
    )
    await show_managed_content(
        chat_id,
        text,
        attachments=build_topup_consent_keyboard(code),
        callback_id=callback_id,
        source_mid=source_mid,
        notification="Открываю покупку",
    )
    return True


async def send_payments(chat_id: int) -> None:
    rows = state.user_store.list_user_payments(chat_id, limit=8)
    if not rows:
        await send_managed_message(chat_id, "Заявок пока нет. Используй кнопку «Тарифы».", attachments=build_keyboard(), page=UI_PAGE_PAYMENTS)
        return
    lines = ["Твои последние заявки:"]
    for item in rows:
        status = str(item["status"]).lower()
        status_human = payment_status_label(status)
        lines.append(
            f"#{item['id']} | {item['plan']} | {item['days']} дн | {item['amount_rub']} RUB | {status_human} | {item['created_at'][:19]}"
        )
    lines.append("\nНажми «Проверить #...», чтобы обновить статус по банку.")
    await send_managed_message(chat_id, "\n".join(lines), attachments=build_payments_keyboard(rows), page=UI_PAGE_PAYMENTS)


def effective_receipt_contact(row: dict[str, Any]) -> tuple[str, str]:
    email = str(row.get("receipt_email", "")).strip()
    phone = str(row.get("receipt_phone", "")).strip()
    return email, phone


def receipt_return_page(plan: str) -> str:
    return UI_PAGE_TOPUPS if plan.startswith("topup") else UI_PAGE_TARIFFS


async def request_receipt_contact(
    chat_id: int,
    plan: str,
    notify: bool = False,
    callback_id: str | None = None,
    source_mid: str | None = None,
) -> None:
    state.pending_receipt_plan[chat_id] = plan
    target_label = "подписки" if not plan.startswith("topup") else "пакета кредитов"
    await show_managed_content(
        chat_id,
        (
            f"Перед оплатой {target_label} нужен контакт для отправки чека.\n"
            "Отправь одним сообщением email или телефон.\n\n"
            "Пример email: user@example.com\n"
            "Пример телефона: +79991234567\n\n"
            "Можно нажать «Отмена» ниже."
        ),
        attachments=build_receipt_contact_keyboard(),
        callback_id=callback_id,
        source_mid=source_mid,
        notification="Нужен контакт для чека",
        page=UI_PAGE_SUPPORT,
    )


async def start_buy_flow(
    chat_id: int,
    plan: str,
    notify: bool = False,
    callback_id: str | None = None,
    source_mid: str | None = None,
) -> bool:
    if plan not in BUYABLE_PLANS:
        await max_send_message(chat_id, "Доступно: lite, start или pro.", attachments=build_tariffs_keyboard_pricing(), notify=notify)
        return False
    row = user_profile(chat_id)
    email, phone = effective_receipt_contact(row)
    if not (email or phone):
        await request_receipt_contact(chat_id, plan, notify=notify, callback_id=callback_id, source_mid=source_mid)
        return False
    return await send_buy_consent(chat_id, plan, notify=notify, callback_id=callback_id, source_mid=source_mid)


async def send_buy_consent(
    chat_id: int,
    plan: str,
    notify: bool = False,
    callback_id: str | None = None,
    source_mid: str | None = None,
) -> bool:
    if plan not in BUYABLE_PLANS:
        await max_send_message(chat_id, "Доступно: lite, start или pro.", attachments=build_tariffs_keyboard_pricing(), notify=notify)
        return False

    amount, days = plan_price_and_days(plan)
    row = user_profile(chat_id)
    receipt_email, receipt_phone = effective_receipt_contact(row)
    receipt_label = receipt_email or receipt_phone or "не указан"
    text = (
        "Перед оплатой нужно согласие на автопродление.\n\n"
        f"Тариф: {plan}\n"
        f"Списание: {amount} ₽\n"
        f"Периодичность: каждые {days} дней\n\n"
        f"Чек придет на: {receipt_label}\n\n"
        "После согласия откроется оплата.\n"
        "Отменить автопродление можно в «Мой план»."
    )
    await show_managed_content(
        chat_id,
        text,
        attachments=build_consent_keyboard(plan),
        callback_id=callback_id,
        source_mid=source_mid,
        notification="Проверь условия",
    )
    return True


async def create_buy_request(chat_id: int, plan: str) -> str:
    if plan not in BUYABLE_PLANS:
        return "Доступно: lite, start или pro."
    amount, days = plan_price_and_days(plan)
    request_id = state.user_store.create_payment_request(chat_id, plan, days, amount)
    return (
        f"Заявка #{request_id} создана: {plan}, {days} дн, {amount} RUB.\n"
        "Сейчас подтверждение оплаты делает админ вручную."
    )


async def notify_admin_about_payment_claim(request_id: int, payment: dict[str, Any]) -> None:
    if not ADMIN_IDS:
        return
    target = int(payment["chat_id"])
    plan = str(payment["plan"])
    amount = int(payment["amount_rub"])
    days = int(payment["days"])
    item = plan
    if is_topup_plan(plan):
        code = topup_code_from_plan(plan)
        pack = topup_spec(code)
        if pack:
            item = f"topup:{code} ({pack['credits']} credits)"
    text = (
        f"Пользователь подтвердил оплату по заявке #{request_id}.\n"
        f"user={target}, item={item}, amount={amount} RUB, days={days}\n"
        f"Проверка: /admin pay {request_id} paid\n"
        f"Отмена: /admin pay {request_id} cancel"
    )
    for admin_id in ADMIN_IDS:
        with suppress(Exception):
            await max_send_message(admin_id, text)


def image_capability_line() -> str:
    label = DEFAULT_IMAGE_MODEL.label
    return f"• генерация картинок через {label}"


def resolve_tbank_notification_url() -> str:
    if TBANK_NOTIFICATION_URL:
        return TBANK_NOTIFICATION_URL
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL}/webhook/tbank"
    return ""


def resolve_tbank_success_url() -> str:
    if TBANK_SUCCESS_URL:
        return TBANK_SUCCESS_URL
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL}/payment/success"
    return ""


def resolve_tbank_fail_url() -> str:
    if TBANK_FAIL_URL:
        return TBANK_FAIL_URL
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL}/payment/fail"
    return ""


async def tbank_init_payment(
    request_id: int,
    amount_rub: int,
    description: str,
    receipt_email: str = "",
    receipt_phone: str = "",
) -> tuple[str, str]:
    if not tbank_enabled():
        raise RuntimeError("T-Bank credentials are not configured.")

    order_id = tbank_order_id(request_id)
    payload: dict[str, Any] = {
        "TerminalKey": TBANK_TERMINAL_KEY,
        "Amount": int(amount_rub) * 100,
        "OrderId": order_id,
        "Description": description[:140],
        "PayType": "O",
    }
    final_email = receipt_email.strip()
    final_phone = receipt_phone.strip()
    if not (final_email or final_phone):
        raise RuntimeError("T-Bank Receipt required: buyer email or phone is missing")
    payload["Receipt"] = build_tbank_receipt(
        amount_rub=amount_rub,
        description=description,
        receipt_email=final_email,
        receipt_phone=final_phone,
    )
    notification_url = resolve_tbank_notification_url()
    if notification_url:
        payload["NotificationURL"] = notification_url
    success_url = add_request_id_to_url(resolve_tbank_success_url(), request_id)
    if success_url:
        payload["SuccessURL"] = success_url
    fail_url = add_request_id_to_url(resolve_tbank_fail_url(), request_id)
    if fail_url:
        payload["FailURL"] = fail_url

    payload["Token"] = tbank_token_from_payload(payload, TBANK_PASSWORD)
    session = await get_session()
    async with session.post(TBANK_INIT_URL, json=payload) as resp:
        data = await resp.json(content_type=None)
        if resp.status >= 400:
            raise RuntimeError(f"T-Bank Init HTTP {resp.status}: {data}")
    if not isinstance(data, dict):
        raise RuntimeError("Invalid T-Bank Init response.")
    if not data.get("Success"):
        error_code = scalar_string(data.get("ErrorCode"))
        message = scalar_string(data.get("Message"))
        details = scalar_string(data.get("Details"))
        parts = [part for part in [error_code and f"code={error_code}", message, details] if part]
        reason = " | ".join(parts) if parts else str(data)
        if error_code == "251":
            reason = f"{reason} | Сумма ниже минимальной для терминала."
        raise RuntimeError(f"T-Bank Init failed: {reason}")
    payment_url = data.get("PaymentURL")
    payment_id = data.get("PaymentId")
    if not isinstance(payment_url, str) or not payment_url:
        raise RuntimeError(f"T-Bank Init missing PaymentURL: {data}")
    return payment_url, scalar_string(payment_id)


async def tbank_get_state(payment_id: str) -> dict[str, Any]:
    if not tbank_enabled():
        raise RuntimeError("T-Bank credentials are not configured.")
    if not payment_id:
        raise RuntimeError("Empty PaymentId.")

    payload: dict[str, Any] = {
        "TerminalKey": TBANK_TERMINAL_KEY,
        "PaymentId": payment_id,
    }
    payload["Token"] = tbank_token_from_payload(payload, TBANK_PASSWORD)
    session = await get_session()
    async with session.post(TBANK_GET_STATE_URL, json=payload) as resp:
        data = await resp.json(content_type=None)
        if resp.status >= 400:
            raise RuntimeError(f"T-Bank GetState HTTP {resp.status}: {data}")
    if not isinstance(data, dict):
        raise RuntimeError("Invalid T-Bank GetState response.")
    return data


def cancel_payment_if_open(request_id: int) -> tuple[bool, str]:
    payment = state.user_store.get_payment(request_id)
    if not payment:
        return False, "not found"
    current_status = str(payment.get("status", "")).lower()
    if current_status in PAYMENT_FINAL_STATUSES:
        return False, f"already {current_status}"
    state.user_store.set_payment_status(request_id, "canceled")
    return True, "canceled"


async def refresh_payment_from_tbank(request_id: int, source: str) -> tuple[dict[str, Any] | None, str]:
    payment = state.user_store.get_payment(request_id)
    if not payment:
        return None, ""

    provider_ref = str(payment.get("provider_ref", ""))
    payment_id = tbank_payment_id_from_provider_ref(provider_ref)
    if not payment_id or not tbank_enabled():
        return payment, ""

    payload = await tbank_get_state(payment_id)
    bank_status = scalar_string(payload.get("Status")).upper()
    bank_success_raw = payload.get("Success")
    bank_success = bank_success_raw is True or scalar_string(bank_success_raw).lower() == "true"

    if bank_success and bank_status in TBANK_SUCCESS_STATUSES:
        await activate_payment_request(request_id, source=source)
    elif tbank_is_refund_status(bank_status):
        await process_refund_payment_request(request_id, source=source, bank_status=bank_status)
    elif tbank_is_cancel_status(bank_status):
        cancel_payment_if_open(request_id)

    return state.user_store.get_payment(request_id), bank_status


async def activate_payment_request(request_id: int, source: str) -> tuple[bool, str]:
    payment = state.user_store.get_payment(request_id)
    if not payment:
        return False, f"payment #{request_id} not found"

    status = str(payment.get("status", ""))
    if status in {"paid", "canceled", "refunded"}:
        return False, f"payment #{request_id} already {status}"

    target = int(payment["chat_id"])
    plan = str(payment["plan"])
    days = int(payment["days"])
    amount_rub = int(payment.get("amount_rub", 0) or 0)
    user_profile(target)
    state.user_store.set_payment_status(request_id, "paid")
    state.user_store.record_usage_event(
        chat_id=target,
        event_type="payment",
        plan=plan,
        rub_amount=amount_rub,
        details=f"request_id={request_id};source={source}",
    )

    if is_topup_plan(plan):
        code = topup_code_from_plan(plan)
        pack = topup_spec(code)
        if not pack:
            return False, f"unknown topup code in payment #{request_id}"
        credits = int(pack["credits"])
        row = user_profile(target)
        current = int(row.get("credits_balance", 0) or 0)
        state.user_store.set_credits(target, current + credits)
        state.user_store.mark_payment_activated(request_id)
        with suppress(Exception):
            await max_send_message(
                target,
                f"Оплата подтверждена ({source}). Зачислено {credits} кредитов.",
                attachments=build_keyboard(),
            )
        return True, f"credits+{credits}"

    selected = best_default_alias_for_plan(plan)
    recurring_for_user = source.lower().startswith("t-bank")
    expires_at = state.user_store.set_subscription(
        target,
        plan,
        days,
        selected,
        recurring_enabled=recurring_for_user,
    )
    state.user_store.mark_payment_activated(request_id)

    with suppress(Exception):
        await max_send_message(
            target,
            f"Оплата подтверждена автоматически ({source}). Тариф {plan} активирован до {expires_at[:16]} UTC.",
            attachments=build_keyboard(),
        )
    return True, expires_at


async def process_refund_payment_request(request_id: int, source: str, bank_status: str) -> tuple[bool, str]:
    payment = state.user_store.get_payment(request_id)
    if not payment:
        return False, f"payment #{request_id} not found"

    target = int(payment["chat_id"])
    plan = str(payment.get("plan", ""))
    amount_rub = int(payment.get("amount_rub", 0) or 0)
    current_status = str(payment.get("status", "")).lower()
    if current_status == "refunded":
        return False, "already refunded"
    if current_status != "refunded":
        state.user_store.set_payment_status(request_id, "refunded")
        state.user_store.record_usage_event(
            chat_id=target,
            event_type="refund",
            plan=plan,
            rub_amount=-abs(amount_rub),
            details=f"request_id={request_id};source={source};status={bank_status}",
        )

    if is_topup_plan(plan):
        code = topup_code_from_plan(plan)
        pack = topup_spec(code)
        if not pack:
            return False, "unknown topup for refund"
        credits = int(pack["credits"])
        row = user_profile(target)
        current = int(row.get("credits_balance", 0) or 0)
        state.user_store.set_credits(target, max(0, current - credits))
        with suppress(Exception):
            await max_send_message(
                target,
                (
                    f"Возврат подтвержден ({source}, статус {bank_status}).\n"
                    f"Пакет кредитов отменен, списано {credits} кредитов."
                ),
                attachments=build_keyboard(),
            )
        return True, f"topup credits-{credits}"

    row = user_profile(target)
    changed = False
    if row.get("plan") != "free" or recurring_enabled_for_row(row):
        state.user_store.set_plan(target, "free")
        state.user_store.set_selected_model(target, best_default_alias_for_plan("free"))
        changed = True

    if changed:
        with suppress(Exception):
            await max_send_message(
                target,
                (
                    f"Возврат подтвержден ({source}, статус {bank_status}).\n"
                    "Подписка переведена на free, автопродление отключено."
                ),
                attachments=build_keyboard(),
            )
        return True, "downgraded to free"
    return False, "already free or already canceled"


async def create_buy_request_v2(chat_id: int, plan: str, consent_text: str = "") -> tuple[int | None, str]:
    if plan not in BUYABLE_PLANS:
        return None, "Доступно: lite, start или pro."
    amount, days = plan_price_and_days(plan)
    row = user_profile(chat_id)
    receipt_email, receipt_phone = effective_receipt_contact(row)
    if not (receipt_email or receipt_phone):
        return None, "Нужен email или телефон для чека. Нажми «Тарифы» и начни оплату заново."
    request_id = state.user_store.create_payment_request(
        chat_id,
        plan,
        days,
        amount,
        recurring_consent=bool(consent_text),
        recurring_consent_text=consent_text,
        receipt_email=receipt_email,
        receipt_phone=receipt_phone,
    )
    payment_purpose = f"Оплата подписки, заказ #{request_id}"
    if tbank_enabled():
        try:
            payment_url, payment_id = await tbank_init_payment(
                request_id=request_id,
                amount_rub=amount,
                description=f"Подписка {plan}, заказ #{request_id}",
                receipt_email=receipt_email,
                receipt_phone=receipt_phone,
            )
            state.user_store.set_payment_provider_ref(request_id, f"tbank:{payment_id}")
            state.user_store.set_payment_url(request_id, payment_url)
            text = (
                f"Заявка #{request_id} создана\n"
                f"Тариф: {plan}\n"
                f"Срок: {days} дней\n"
                f"Сумма: {amount} ₽\n\n"
                "Ссылка на оплату:\n"
                f"{payment_url}\n\n"
                "После успешной оплаты тариф активируется автоматически."
            )
            return request_id, text
        except Exception as exc:
            log.exception("T-Bank Init failed for request %s", request_id)
            text = (
                f"Заявка #{request_id} создана\n"
                f"Тариф: {plan}\n"
                f"Срок: {days} дней\n"
                f"Сумма: {amount} ₽\n"
                f"Автооплата сейчас недоступна ({exc}).\n\n"
                "Используй ручную оплату ниже."
            )
            return request_id, text
    text = (
        f"Заявка #{request_id} создана\n"
        f"Тариф: {plan}\n"
        f"Срок: {days} дней\n"
        f"Сумма: {amount} ₽\n\n"
        "Куда оплачивать:\n"
        f"{PAYMENT_DETAILS_TEXT}\n\nНазначение платежа: {payment_purpose}\nchat_id указывать не нужно.\n\n"
        "После оплаты нажми кнопку «Я оплатил»."
    )
    return request_id, text


async def create_topup_request_v2(chat_id: int, code: str) -> tuple[int | None, str]:
    pack = topup_spec(code)
    if not pack:
        return None, "Неизвестный пакет кредитов."

    amount = int(pack["price_rub"])
    credits = int(pack["credits"])
    row = user_profile(chat_id)
    receipt_email, receipt_phone = effective_receipt_contact(row)
    if not (receipt_email or receipt_phone):
        return None, "Нужен email или телефон для чека. Нажми «Пакеты кредитов» и начни покупку заново."

    request_id = state.user_store.create_payment_request(
        chat_id,
        topup_plan_code(code),
        0,
        amount,
        recurring_consent=False,
        recurring_consent_text="",
        receipt_email=receipt_email,
        receipt_phone=receipt_phone,
    )
    payment_purpose = f"Пакет кредитов {pack['label']}, заказ #{request_id}"
    if tbank_enabled():
        try:
            payment_url, payment_id = await tbank_init_payment(
                request_id=request_id,
                amount_rub=amount,
                description=f"Пакет кредитов {pack['label']}, заказ #{request_id}",
                receipt_email=receipt_email,
                receipt_phone=receipt_phone,
            )
            state.user_store.set_payment_provider_ref(request_id, f"tbank:{payment_id}")
            state.user_store.set_payment_url(request_id, payment_url)
            text = (
                f"Заявка #{request_id} создана\n"
                f"Пакет: {pack['label']}\n"
                f"Кредитов: {credits}\n"
                f"Сумма: {amount} ₽\n\n"
                "Ссылка на оплату:\n"
                f"{payment_url}\n\n"
                "После успешной оплаты кредиты зачислятся автоматически."
            )
            return request_id, text
        except Exception as exc:
            log.exception("T-Bank Init failed for topup request %s", request_id)
            text = (
                f"Заявка #{request_id} создана\n"
                f"Пакет: {pack['label']}\n"
                f"Кредитов: {credits}\n"
                f"Сумма: {amount} ₽\n"
                f"Автооплата сейчас недоступна ({exc}).\n\n"
                "Используй ручную оплату ниже."
            )
            return request_id, text

    text = (
        f"Заявка #{request_id} создана\n"
        f"Пакет: {pack['label']}\n"
        f"Кредитов: {credits}\n"
        f"Сумма: {amount} ₽\n\n"
        "Куда оплачивать:\n"
        f"{PAYMENT_DETAILS_TEXT}\n\nНазначение платежа: {payment_purpose}\nchat_id указывать не нужно.\n\n"
        "После оплаты нажми кнопку «Я оплатил»."
    )
    return request_id, text


async def set_user_model(chat_id: int, alias: str) -> str:
    row = user_profile(chat_id)
    ok, reason = can_use_model(row["plan"], alias)
    if not ok:
        raise RuntimeError(reason)
    state.user_store.set_selected_model(chat_id, alias)
    return TEXT_MODELS[alias].label


async def handle_admin(chat_id: int, text: str) -> bool:
    if chat_id not in ADMIN_IDS:
        return False

    parts = text.strip().split()
    if len(parts) < 2 or parts[1] == "help":
        await max_send_message(
            chat_id,
            "Админ-команды:\n"
            "/admin user <chat_id>\n"
            "/admin plan <chat_id> <free|lite|start|pro>\n"
            "/admin sub <chat_id> <lite|start|pro> <days>\n"
            "/admin block <chat_id> <on|off>\n"
            "/admin pay <request_id> <paid|cancel>\n"
            "/admin templates\n"
            "/admin backup\n"
            "/admin nudge [days] [limit]\n"
            "/admin kpi [days]\n"
            "/admin panel",
        )
        return True

    action = parts[1].lower()
    if action == "user" and len(parts) >= 3:
        target = parse_admin_target(parts[2])
        if target is None:
            await max_send_message(chat_id, "Некорректный chat_id")
            return True
        row = user_profile(target)
        await max_send_message(chat_id, f"user {target}\n{usage_text(row)}\nblocked={row['is_blocked']}")
        return True

    if action == "plan" and len(parts) >= 4:
        target = parse_admin_target(parts[2])
        new_plan = parts[3].lower()
        if target is None or new_plan not in PLAN_CONFIGS:
            await max_send_message(chat_id, "Используй: /admin plan <chat_id> <free|lite|start|pro>")
            return True
        user_profile(target)
        state.user_store.set_plan(target, new_plan)
        selected = best_default_alias_for_plan(new_plan)
        state.user_store.set_selected_model(target, selected)
        state.user_store.set_credits(target, credits_for_plan(new_plan))
        await max_send_message(
            chat_id,
            f"План пользователя {target} -> {new_plan}. Модель -> {selected}. Кредиты -> {credits_for_plan(new_plan)}.",
        )
        return True

    if action == "sub" and len(parts) >= 5:
        target = parse_admin_target(parts[2])
        plan = parts[3].lower()
        days_raw = parts[4]
        if target is None or plan not in BUYABLE_PLANS or not days_raw.isdigit():
            await max_send_message(chat_id, "Используй: /admin sub <chat_id> <lite|start|pro> <days>")
            return True
        days = int(days_raw)
        if days <= 0 or days > 365:
            await max_send_message(chat_id, "Дни должны быть в диапазоне 1..365")
            return True
        user_profile(target)
        selected = best_default_alias_for_plan(plan)
        expires_at = state.user_store.set_subscription(target, plan, days, selected)
        await max_send_message(chat_id, f"Подписка активирована: user={target} plan={plan} days={days} until={expires_at}")
        return True

    if action == "block" and len(parts) >= 4:
        target = parse_admin_target(parts[2])
        flag = parts[3].lower()
        if target is None or flag not in {"on", "off"}:
            await max_send_message(chat_id, "Используй: /admin block <chat_id> <on|off>")
            return True
        user_profile(target)
        state.user_store.set_blocked(target, flag == "on")
        await max_send_message(chat_id, f"Пользователь {target}: block={flag}")
        return True

    if action == "pay" and len(parts) >= 4:
        req_raw = parts[2]
        decision = parts[3].lower()
        if not req_raw.isdigit() or decision not in {"paid", "cancel"}:
            await max_send_message(chat_id, "Используй: /admin pay <request_id> <paid|cancel>")
            return True
        req_id = int(req_raw)
        payment = state.user_store.get_payment(req_id)
        if not payment:
            await max_send_message(chat_id, f"Заявка #{req_id} не найдена")
            return True
        if payment["status"] not in {"pending", "claimed"}:
            await max_send_message(chat_id, f"Заявка #{req_id} уже обработана: {payment['status']}")
            return True
        if decision == "cancel":
            state.user_store.set_payment_status(req_id, "canceled")
            await max_send_message(chat_id, f"Заявка #{req_id} отменена")
            return True

        activated, info = await activate_payment_request(req_id, source="admin manual")
        if not activated:
            await max_send_message(chat_id, f"Заявка #{req_id}: {info}")
            return True
        payment = state.user_store.get_payment(req_id) or payment
        await max_send_message(
            chat_id,
            f"Оплата #{req_id} подтверждена. user={payment['chat_id']} item={payment['plan']} result={info}",
        )
        return True

    if action == "kpi":
        days = 30
        if len(parts) >= 3 and parts[2].isdigit():
            days = int(parts[2])
        report = state.user_store.kpi_report(days=days)
        await max_send_message(chat_id, format_kpi_report(report))
        return True

    if action == "templates":
        await max_send_message(chat_id, support_admin_templates_text())
        return True

    if action == "backup":
        try:
            backup_file = create_db_backup()
            await max_send_message(chat_id, f"Бэкап создан: {backup_file}")
        except Exception as exc:
            capture_exception_safe(exc)
            await max_send_message(chat_id, f"Не удалось создать бэкап: {exc}")
        return True

    if action == "nudge":
        days = REENGAGE_DORMANT_DAYS
        limit = REENGAGE_BATCH_LIMIT
        if len(parts) >= 3 and parts[2].isdigit():
            days = max(1, int(parts[2]))
        if len(parts) >= 4 and parts[3].isdigit():
            limit = max(1, int(parts[3]))
        sent, total = await send_reengage_nudges(days=days, limit=limit)
        await max_send_message(chat_id, f"Реактивация: отправлено {sent}/{total} (dormant_days={days}, limit={limit})")
        return True

    if action == "panel":
        if not admin_panel_enabled():
            await max_send_message(chat_id, "ADMIN_PANEL_TOKEN не задан. Панель выключена.")
            return True
        if not PUBLIC_BASE_URL:
            await max_send_message(chat_id, "PUBLIC_BASE_URL не задан, ссылку на панель сформировать нельзя.")
            return True
        await max_send_message(chat_id, f"Панель: {PUBLIC_BASE_URL}/admin/panel?token={ADMIN_PANEL_TOKEN}")
        return True

    await max_send_message(chat_id, "Неизвестная админ-команда. Используй /admin help")
    return True


async def handle_callback(update: dict[str, Any]) -> bool:
    chat_id, callback_id, payload, source_mid = parse_callback_payload(update)
    if chat_id is None or not payload:
        return False
    ensure_update_user_binding(chat_id, update)

    if payload.startswith("reply_action:"):
        reply_action = payload.split(":", 1)[1].strip()
        reply_page_map = {
            "menu": UI_PAGE_MENU,
            "image_menu": UI_PAGE_IMAGE_MENU,
            "tariffs": UI_PAGE_TARIFFS,
        }
        if reply_action == "clear":
            state.history(chat_id).clear()
            if callback_id:
                await answer_callback(callback_id, "Контекст очищен")
            await send_managed_message(chat_id, "Контекст диалога очищен.", attachments=build_keyboard(), page=UI_PAGE_MENU)
            return True
        target_page = reply_page_map.get(reply_action)
        if target_page:
            await show_ui_page(
                chat_id,
                target_page,
                callback_id=callback_id,
                source_mid=source_mid,
                push_history=True,
                force_new=True,
            )
            return True

    if payload.startswith("onboard:") and int(user_profile(chat_id).get("onboarding_done", 0) or 0) == 1:
        if callback_id:
            await answer_callback(callback_id, "Онбординг уже завершен")
        await close_onboarding_message(chat_id, source_mid, "Онбординг уже завершен. Используй меню ниже.")
        return True

    if payload not in {"growth:ref_enter", "growth:promo_enter", "growth:input_cancel"}:
        clear_growth_pending_inputs(chat_id)

    if payload == "ui_nav:back":
        target = ui_nav_back(chat_id)
        if target:
            await show_ui_page(chat_id, target, callback_id=callback_id, source_mid=source_mid, push_history=False)
        elif callback_id:
            await answer_callback(callback_id, "Назад недоступен")
        return True

    if payload == "ui_nav:forward":
        target = ui_nav_forward(chat_id)
        if target:
            await show_ui_page(chat_id, target, callback_id=callback_id, source_mid=source_mid, push_history=False)
        elif callback_id:
            await answer_callback(callback_id, "Откат недоступен")
        return True

    action_page_map = {
        "action:menu": UI_PAGE_MENU,
        "action:models": UI_PAGE_MODELS,
        "action:plan": UI_PAGE_PLAN,
        "action:tariffs": UI_PAGE_TARIFFS,
        "action:topups": UI_PAGE_TOPUPS,
        "action:payments": UI_PAGE_PAYMENTS,
        "action:growth": UI_PAGE_GROWTH,
        "action:support": UI_PAGE_SUPPORT,
        "action:image_menu": UI_PAGE_IMAGE_MENU,
    }
    if payload in action_page_map:
        await show_ui_page(chat_id, action_page_map[payload], callback_id=callback_id, source_mid=source_mid, push_history=True)
        return True

    if payload.startswith("set_preset:"):
        preset = payload.split(":", 1)[1].strip().lower()
        preset_cfg = MODEL_PRESETS.get(preset)
        if not preset_cfg:
            if callback_id:
                await answer_callback(callback_id, "Неизвестный режим")
            return True
        try:
            alias = resolve_preset_alias_for_chat(chat_id, preset)
            label = await set_user_model(chat_id, alias)
            state.user_store.set_selected_preset(chat_id, preset)
            await show_ui_page(
                chat_id,
                UI_PAGE_MENU,
                callback_id=callback_id,
                source_mid=source_mid,
                push_history=False,
                notification=f"{preset_cfg['label']} → {label}",
            )
        except Exception as exc:
            if callback_id:
                await answer_callback(callback_id, str(exc)[:120])
            await max_send_message(chat_id, f"Ошибка: {exc}", attachments=build_keyboard(), notify=False)
        return True

    if payload.startswith("set_model:"):
        alias = payload.split(":", 1)[1]
        try:
            label = await set_user_model(chat_id, alias)
            state.user_store.set_selected_preset(chat_id, "")
            target_page = state.ui_current_page.get(chat_id, UI_PAGE_MENU)
            if target_page not in UI_PAGE_KEYS:
                target_page = UI_PAGE_MENU
            await show_ui_page(
                chat_id,
                target_page,
                callback_id=callback_id,
                source_mid=source_mid,
                push_history=False,
                notification=f"Модель: {label}",
            )
        except Exception as exc:
            if callback_id:
                await answer_callback(callback_id, str(exc)[:120])
            await max_send_message(chat_id, f"Ошибка: {exc}", attachments=build_keyboard(), notify=False)
        return True

    if payload == "action:clear":
        state.history(chat_id).clear()
        if callback_id:
            await answer_callback(callback_id, "Контекст очищен")
        await send_managed_message(chat_id, "Контекст диалога очищен.", attachments=build_keyboard(), notify=False, page=UI_PAGE_MENU)
        return True

    if payload == "action:models":
        if callback_id:
            await answer_callback(callback_id, "Показываю модели")
        await send_models(chat_id)
        return True

    if payload == "action:plan":
        if callback_id:
            await answer_callback(callback_id, "Показываю план")
        await send_plan(chat_id)
        return True

    if payload == "action:tariffs":
        if callback_id:
            await answer_callback(callback_id, "Показываю тарифы")
        await max_send_message(chat_id, build_tariffs_text(), attachments=build_tariffs_keyboard_pricing(), notify=False)
        return True

    if payload == "action:topups":
        if callback_id:
            await answer_callback(callback_id, "Показываю пакеты")
        await send_topups(chat_id)
        return True

    if payload == "action:payments":
        if callback_id:
            await answer_callback(callback_id, "Показываю оплаты")
        await send_payments(chat_id)
        return True

    if payload == "action:menu":
        if callback_id:
            await answer_callback(callback_id, "Открываю меню")
        await send_menu(chat_id)
        return True

    if payload == "action:growth":
        if callback_id:
            await answer_callback(callback_id, "Бонусы")
        await send_growth_menu(chat_id)
        return True

    if payload == "action:channel":
        await show_managed_content(
            chat_id,
            f"📣 Канал проекта:\n{channel_url_value()}",
            attachments=build_growth_keyboard(),
            callback_id=callback_id,
            source_mid=source_mid,
            page=UI_PAGE_GROWTH,
            notification="Канал",
        )
        return True

    if payload == "growth:ref_show":
        row = user_profile(chat_id)
        code = str(row.get("referral_code", "")).strip() or referral_code_for_chat(chat_id)
        invited = int(row.get("referrals_invited", 0) or 0)
        await show_managed_content(
            chat_id,
            (
                f"👥 Твой реф-код: {code}\n"
                f"Приглашено друзей: {invited}\n\n"
                f"Пригласи друга: он вводит /ref {code}\n"
                f"После активации — бонус +{REFERRAL_BONUS_CREDITS} кредитов вам обоим."
            ),
            attachments=build_growth_keyboard(),
            callback_id=callback_id,
            source_mid=source_mid,
            page=UI_PAGE_GROWTH,
            notification="Твой реф-код",
        )
        return True

    if payload == "growth:ref_enter":
        state.pending_referral_code_input.add(chat_id)
        await show_managed_content(
            chat_id,
            "Введи реферальный код одним сообщением (пример: RFABC123). Для отмены отправь «отмена».",
            attachments=build_growth_input_keyboard(),
            callback_id=callback_id,
            source_mid=source_mid,
            page=UI_PAGE_GROWTH,
            notification="Жду код",
        )
        return True

    if payload == "growth:promo_enter":
        state.pending_promo_code_input.add(chat_id)
        await show_managed_content(
            chat_id,
            "Введи промокод одним сообщением. Для отмены отправь «отмена».",
            attachments=build_growth_input_keyboard(),
            callback_id=callback_id,
            source_mid=source_mid,
            page=UI_PAGE_GROWTH,
            notification="Жду промокод",
        )
        return True

    if payload == "growth:input_cancel":
        clear_growth_pending_inputs(chat_id)
        await show_ui_page(chat_id, UI_PAGE_GROWTH, callback_id=callback_id, source_mid=source_mid, push_history=False)
        return True

    if payload == "payment:input_cancel":
        pending_plan = state.pending_receipt_plan.pop(chat_id, "")
        await show_ui_page(
            chat_id,
            receipt_return_page(pending_plan or ""),
            callback_id=callback_id,
            source_mid=source_mid,
            push_history=False,
        )
        return True

    if payload == "growth:channel_bonus":
        await show_managed_content(
            chat_id,
            "Бонус за подписку на канал пока отключен: в боте еще нет честной автопроверки подписки.",
            attachments=build_growth_keyboard(),
            callback_id=callback_id,
            source_mid=source_mid,
            page=UI_PAGE_GROWTH,
            notification="Бонус пока недоступен",
        )
        return True

    if payload == "onboard:skip":
        state.user_store.set_onboarding_done(chat_id, True)
        handoff_onboarding_to_ui(chat_id, source_mid)
        await show_ui_page(chat_id, UI_PAGE_MENU, callback_id=callback_id, source_mid=source_mid, push_history=False)
        return True

    if payload == "onboard:2":
        await show_onboarding_step(chat_id, step=2, callback_id=callback_id, source_mid=source_mid, notification="Шаг 2")
        return True

    if payload == "onboard:3":
        await show_onboarding_step(chat_id, step=3, callback_id=callback_id, source_mid=source_mid, notification="Шаг 3")
        return True

    if payload == "onboard:done":
        state.user_store.set_onboarding_done(chat_id, True)
        handoff_onboarding_to_ui(chat_id, source_mid)
        await show_ui_page(chat_id, UI_PAGE_MENU, callback_id=callback_id, source_mid=source_mid, push_history=False)
        return True

    if payload == "onboard:scenario:text":
        state.user_store.set_onboarding_done(chat_id, True)
        handoff_onboarding_to_ui(chat_id, source_mid)
        await show_managed_content(
            chat_id,
            "Супер, просто напиши вопрос в чат — отвечу сразу.",
            attachments=build_keyboard(),
            callback_id=callback_id,
            source_mid=source_mid,
            page=UI_PAGE_MENU,
            notification="Текст",
        )
        return True

    if payload == "onboard:scenario:image":
        state.user_store.set_onboarding_done(chat_id, True)
        handoff_onboarding_to_ui(chat_id, source_mid)
        await show_ui_page(chat_id, UI_PAGE_IMAGE_MENU, callback_id=callback_id, source_mid=source_mid, push_history=False)
        return True

    if payload == "onboard:scenario:tariff":
        state.user_store.set_onboarding_done(chat_id, True)
        handoff_onboarding_to_ui(chat_id, source_mid)
        await show_ui_page(chat_id, UI_PAGE_TARIFFS, callback_id=callback_id, source_mid=source_mid, push_history=False)
        return True

    if payload == "action:image_menu":
        if callback_id:
            await answer_callback(callback_id, "Параметры картинки")
        await send_image_menu(chat_id)
        return True

    if payload.startswith("image_style:"):
        style = payload.split(":", 1)[1].strip().lower()
        if style not in IMAGE_STYLE_OPTIONS:
            if callback_id:
                await answer_callback(callback_id, "Неизвестный стиль")
            return True
        prefs = get_image_prefs(chat_id)
        prefs["style"] = style
        state.image_request_prefs[chat_id] = prefs
        await show_ui_page(chat_id, UI_PAGE_IMAGE_MENU, callback_id=callback_id, source_mid=source_mid, push_history=False)
        return True

    if payload.startswith("image_aspect:"):
        aspect = payload.split(":", 1)[1].strip().lower()
        if aspect not in IMAGE_ASPECT_OPTIONS:
            if callback_id:
                await answer_callback(callback_id, "Неизвестный формат")
            return True
        prefs = get_image_prefs(chat_id)
        prefs["aspect"] = aspect
        state.image_request_prefs[chat_id] = prefs
        await show_ui_page(chat_id, UI_PAGE_IMAGE_MENU, callback_id=callback_id, source_mid=source_mid, push_history=False)
        return True

    if payload == "image_prompt:start":
        row = user_profile(chat_id)
        if row["plan"] != "free" and not plan_allowed(row["plan"], DEFAULT_IMAGE_MODEL.min_plan):
            if callback_id:
                await answer_callback(callback_id, "Недоступно на текущем тарифе")
            await max_send_message(
                chat_id,
                f"Картинки доступны с тарифа {DEFAULT_IMAGE_MODEL.min_plan}. Открой «Тарифы».",
                attachments=build_tariffs_keyboard_pricing(),
                notify=False,
            )
            return True

        ok_limit, reason_limit = check_limit_only(chat_id, "images")
        if not ok_limit:
            if callback_id:
                await answer_callback(callback_id, "Лимит достигнут")
            await max_send_message(chat_id, reason_limit, attachments=build_tariffs_keyboard_pricing(), notify=False)
            return True
        state.pending_image_prompt.add(chat_id)
        if callback_id:
            await answer_callback(callback_id, "Жду описание")
        await max_send_message(
            chat_id,
            "Напиши, что нарисовать одним сообщением.\n\n"
            f"{image_params_summary(chat_id)}\n"
            f"Стоимость: {CREDIT_COST_IMAGE} кредитов.\n"
            "Чтобы отменить — нажми «Отмена» или отправь /cancel",
            attachments=build_image_prompt_keyboard(),
            notify=False,
        )
        return True

    if payload == "image_ref:start":
        row = user_profile(chat_id)
        if row["plan"] == "free" or not plan_allowed(row["plan"], DEFAULT_IMAGE_MODEL.min_plan):
            if callback_id:
                await answer_callback(callback_id, "Недоступно на текущем тарифе")
            await max_send_message(
                chat_id,
                f"Режим «по фото» доступен с тарифа {DEFAULT_IMAGE_MODEL.min_plan}. Открой «Тарифы».",
                attachments=build_tariffs_keyboard_pricing(),
                notify=False,
            )
            return True
        state.pending_image_ref_prompt.add(chat_id)
        if callback_id:
            await answer_callback(callback_id, "Жду фото")
        await max_send_message(
            chat_id,
            (
                "Пришли фото и коротко опиши, что сделать.\n"
                f"Стоимость: {CREDIT_COST_IMAGE_EDIT} кредитов.\n"
                "Если фото уже отправлено — просто напиши описание (например: «нарисуй её в стиле аниме»)."
            ),
            attachments=build_image_prompt_keyboard(),
            notify=False,
        )
        return True

    if payload == "image_prompt:cancel":
        state.pending_image_prompt.discard(chat_id)
        state.pending_image_ref_prompt.discard(chat_id)
        if callback_id:
            await answer_callback(callback_id, "Отменено")
        await send_image_menu(chat_id)
        return True

    if payload == "sub_cancel:start":
        row = user_profile(chat_id)
        if row.get("plan") == "free" or not recurring_enabled_for_row(row):
            if callback_id:
                await answer_callback(callback_id, "Нечего отменять")
            await max_send_message(chat_id, "Автопродление уже отключено или подписка не активна.", attachments=build_plan_keyboard(row), notify=False)
            return True

        expires_at = parse_iso_datetime(str(row.get("subscription_expires_at", "")))
        expires_text = expires_at.strftime("%Y-%m-%d %H:%M UTC") if expires_at else "конца текущего периода"
        if callback_id:
            await answer_callback(callback_id, "Подтверди отмену")
        await max_send_message(
            chat_id,
            "Подтвердить отмену автопродления?\n\n"
            f"Подписка будет работать до {expires_text}.\n"
            f"Отмена автосписаний вступит в силу с {expires_text}.",
            attachments=build_cancel_subscription_keyboard(),
            notify=False,
        )
        return True

    if payload == "sub_cancel:confirm":
        row = user_profile(chat_id)
        if row.get("plan") == "free" or not recurring_enabled_for_row(row):
            if callback_id:
                await answer_callback(callback_id, "Уже отключено")
            await send_plan(chat_id)
            return True

        expires_at = parse_iso_datetime(str(row.get("subscription_expires_at", "")))
        cancel_from = expires_at.replace(microsecond=0).isoformat() if expires_at else datetime.utcnow().replace(microsecond=0).isoformat()
        state.user_store.cancel_recurring(chat_id, cancel_from)
        row = user_profile(chat_id)
        cancel_dt = parse_iso_datetime(cancel_from)
        cancel_text = cancel_dt.strftime("%Y-%m-%d %H:%M UTC") if cancel_dt else cancel_from
        if callback_id:
            await answer_callback(callback_id, "Отменено")
        await max_send_message(
            chat_id,
            f"Автопродление отключено.\nПодписка действует до конца оплаченного периода.\nОтмена с {cancel_text}.",
            attachments=build_plan_keyboard(row),
            notify=False,
        )
        return True

    if payload == "sub_cancel:back":
        if callback_id:
            await answer_callback(callback_id, "Без отмены")
        await send_plan(chat_id)
        return True

    if payload.startswith("buy_consent:"):
        plan = payload.split(":", 1)[1].lower().strip()
        if plan not in BUYABLE_PLANS:
            if callback_id:
                await answer_callback(callback_id, "Неверный тариф")
            return True
        terms = recurring_terms_for_plan(plan)
        request_id, msg = await create_buy_request_v2(chat_id, plan, consent_text=terms)
        if request_id is None:
            await max_send_message(chat_id, msg, attachments=build_tariffs_keyboard_pricing(), notify=False)
            return True
        await show_managed_content(
            chat_id,
            msg,
            attachments=build_payment_request_keyboard(request_id, payment_url=extract_first_http_url(msg)),
            callback_id=callback_id,
            source_mid=source_mid,
            notification="Открываю оплату",
        )
        return True

    if payload.startswith("buy:"):
        plan = payload.split(":", 1)[1].lower()
        if plan == "free":
            user_profile(chat_id)
            state.user_store.set_plan(chat_id, "free")
            state.user_store.set_selected_model(chat_id, best_default_alias_for_plan("free"))
            if callback_id:
                await answer_callback(callback_id, "Переключено на Free")
            await max_send_message(chat_id, "Тариф переключен на free.", attachments=build_tariffs_keyboard_pricing(), notify=False)
            return True

        if plan not in BUYABLE_PLANS:
            if callback_id:
                await answer_callback(callback_id, "Неверный тариф")
            await max_send_message(chat_id, "Доступно: Lite, Start или Pro.", attachments=build_tariffs_keyboard_pricing(), notify=False)
            return True
        ok = await start_buy_flow(chat_id, plan, notify=False, callback_id=callback_id, source_mid=source_mid)
        if not ok:
            return True
        return True

    if payload.startswith("topup:"):
        code = payload.split(":", 1)[1].lower().strip()
        pack = topup_spec(code)
        if not pack:
            if callback_id:
                await answer_callback(callback_id, "Неверный пакет")
            await max_send_message(chat_id, "Неизвестный пакет кредитов.", attachments=build_topups_keyboard(), notify=False)
            return True

        row = user_profile(chat_id)
        email, phone = effective_receipt_contact(row)
        if not (email or phone):
            state.pending_receipt_plan[chat_id] = f"topup_consent:{code}"
            await request_receipt_contact(
                chat_id,
                f"topup_consent:{code}",
                notify=False,
                callback_id=callback_id,
                source_mid=source_mid,
            )
            return True

        await send_topup_consent(chat_id, code, notify=False, callback_id=callback_id, source_mid=source_mid)
        return True

    if payload.startswith("topup_quick:"):
        code = payload.split(":", 1)[1].lower().strip() or TOPUP_QUICK_CODE
        row = user_profile(chat_id)
        email, phone = effective_receipt_contact(row)
        if not (email or phone):
            state.pending_receipt_plan[chat_id] = f"topup_consent:{code}"
            await request_receipt_contact(
                chat_id,
                f"topup_consent:{code}",
                notify=False,
                callback_id=callback_id,
                source_mid=source_mid,
            )
            return True

        request_id, msg = await create_topup_request_v2(chat_id, code)
        if request_id is None:
            await max_send_message(chat_id, msg, attachments=build_topups_keyboard(), notify=False)
            return True
        await show_managed_content(
            chat_id,
            msg,
            attachments=build_payment_request_keyboard(request_id, payment_url=extract_first_http_url(msg)),
            callback_id=callback_id,
            source_mid=source_mid,
            notification="Открываю быструю покупку",
        )
        return True

    if payload.startswith("topup_consent:"):
        code = payload.split(":", 1)[1].lower().strip()
        request_id, msg = await create_topup_request_v2(chat_id, code)
        if request_id is None:
            await max_send_message(chat_id, msg, attachments=build_topups_keyboard(), notify=False)
            return True
        await show_managed_content(
            chat_id,
            msg,
            attachments=build_payment_request_keyboard(request_id, payment_url=extract_first_http_url(msg)),
            callback_id=callback_id,
            source_mid=source_mid,
            notification="Открываю оплату",
        )
        return True

    if payload.startswith("payment_status:"):
        request_raw = payload.split(":", 1)[1].strip()
        if not request_raw.isdigit():
            if callback_id:
                await answer_callback(callback_id, "Ошибка номера заявки")
            return True
        request_id = int(request_raw)
        payment = state.user_store.get_payment(request_id)
        if not payment or int(payment.get("chat_id", 0) or 0) != chat_id:
            if callback_id:
                await answer_callback(callback_id, "Заявка не найдена")
            await max_send_message(chat_id, "Заявка не найдена.", attachments=build_tariffs_keyboard_pricing(), notify=False)
            return True

        bank_status = ""
        status = str(payment.get("status", "pending")).lower()
        provider_ref = str(payment.get("provider_ref", ""))
        if provider_ref.startswith("tbank:") and status in {"pending", "claimed"}:
            try:
                payment, bank_status = await refresh_payment_from_tbank(request_id, source="T-Bank GetState (status button)")
                payment = payment or state.user_store.get_payment(request_id) or payment
            except Exception:
                log.exception("T-Bank GetState failed from status button for request_id=%s", request_id)

        refreshed_status = str((payment or {}).get("status", "pending")).lower()
        await show_managed_content(
            chat_id,
            payment_user_status_text(payment or {}, bank_status=bank_status),
            attachments=build_payment_request_keyboard(request_id) if refreshed_status in {"pending", "claimed"} else build_keyboard(),
            callback_id=callback_id,
            source_mid=source_mid,
            notification=payment_status_label(refreshed_status),
        )
        return True

    if payload.startswith("paid:"):
        request_raw = payload.split(":", 1)[1].strip()
        if not request_raw.isdigit():
            if callback_id:
                await answer_callback(callback_id, "Ошибка номера заявки")
            return True
        request_id = int(request_raw)
        payment = state.user_store.get_payment(request_id)
        if not payment or int(payment["chat_id"]) != chat_id:
            if callback_id:
                await answer_callback(callback_id, "Заявка не найдена")
            await max_send_message(chat_id, "Заявка не найдена.", attachments=build_tariffs_keyboard_pricing(), notify=False)
            return True
        status = str(payment["status"]).lower()
        provider_ref = str(payment.get("provider_ref", ""))
        if provider_ref.startswith("tbank:") and status == "pending":
            try:
                payment, bank_status = await refresh_payment_from_tbank(request_id, source="T-Bank GetState (user button)")
            except Exception:
                log.exception("T-Bank GetState failed from paid button for request_id=%s", request_id)
                if callback_id:
                    await answer_callback(callback_id, "проверка банка")
                await max_send_message(
                    chat_id,
                    (
                        "Не удалось мгновенно получить ответ от банка.\n"
                        "Платеж продолжает проверяться автоматически, обычно до 1-2 минут."
                    ),
                    attachments=build_tariffs_keyboard_pricing(),
                    notify=False,
                )
                return True

            refreshed_status = str((payment or {}).get("status", "pending")).lower()
            if refreshed_status == "paid":
                if callback_id:
                    await answer_callback(callback_id, "Оплата подтверждена")
                await max_send_message(chat_id, "Оплата подтверждена. Подписка уже активирована.", attachments=build_keyboard(), notify=False)
                return True
            if refreshed_status == "refunded":
                if callback_id:
                    await answer_callback(callback_id, "Возврат")
                await max_send_message(chat_id, "Банк отметил возврат по этой заявке.", attachments=build_keyboard(), notify=False)
                return True
            if refreshed_status == "canceled":
                if callback_id:
                    await answer_callback(callback_id, "Оплата отменена")
                await max_send_message(
                    chat_id,
                    "Оплата по этой заявке не завершена. Создай новую заявку в «Тарифы».",
                    attachments=build_tariffs_keyboard_pricing(),
                    notify=False,
                )
                return True
            if callback_id:
                await answer_callback(callback_id, "ожидаем банк")
            await max_send_message(
                chat_id,
                (
                    "Платеж еще в обработке банка.\n"
                    f"Текущий статус банка: {bank_status or 'pending'}.\n"
                    "Обычно подтверждение приходит в течение 1-2 минут."
                ),
                attachments=build_tariffs_keyboard_pricing(),
                notify=False,
            )
            return True
        if status == "paid":
            if callback_id:
                await answer_callback(callback_id, "Уже подтверждено")
            await max_send_message(chat_id, "Эта заявка уже подтверждена.", attachments=build_keyboard(), notify=False)
            return True
        if status == "claimed":
            if callback_id:
                await answer_callback(callback_id, "already sent")
            await max_send_message(chat_id, "Заявка уже отправлена админу на проверку.", attachments=build_tariffs_keyboard_pricing(), notify=False)
            return True
        if status == "canceled":
            if callback_id:
                await answer_callback(callback_id, "Заявка отменена")
            await max_send_message(chat_id, "Эта заявка уже отменена.", attachments=build_tariffs_keyboard_pricing(), notify=False)
            return True
        state.user_store.set_payment_status(request_id, "claimed")
        payment = state.user_store.get_payment(request_id) or payment
        await notify_admin_about_payment_claim(request_id, payment)
        if callback_id:
            await answer_callback(callback_id, "Передано админу")
        await max_send_message(
            chat_id,
            "Отметили оплату. Админ проверит платеж и активирует тариф.",
            attachments=build_tariffs_keyboard_pricing(),
            notify=False,
        )
        return True

    return False


async def handle_command(chat_id: int, text: str) -> bool:
    lowered = text.strip().lower()
    parts = text.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if lowered in {"gpt", "gpt4o", "gemini", "deepseek", "gpt54"}:
        command = "/model"
        arg = lowered
    elif command in {"/gpt", "/gpt4o", "/gemini", "/deepseek", "/gpt54"}:
        command = "/model"
        arg = command[1:]

    if command in {"/start", "/menu"}:
        row = user_profile(chat_id)
        if command == "/start" and int(row.get("onboarding_done", 0) or 0) == 0:
            await send_onboarding(chat_id, step=1)
            return True
        await send_menu(chat_id)
        return True

    if command == "/help":
        await send_help(chat_id)
        return True

    if command == "/models":
        await send_models(chat_id)
        return True

    if command == "/costs":
        if not is_admin(chat_id):
            await max_send_message(chat_id, "Команда доступна только администратору.")
            return True
        await send_costs(chat_id)
        return True

    if command == "/id":
        await max_send_message(chat_id, f"Твой chat_id: {chat_id}")
        return True

    if command == "/tariffs":
        await send_managed_message(chat_id, build_tariffs_text(), attachments=build_tariffs_keyboard_pricing(), page=UI_PAGE_TARIFFS)
        return True

    if command == "/topup":
        await send_topups(chat_id)
        return True

    if command == "/plan":
        await send_plan(chat_id)
        return True

    if command == "/credits":
        await send_credits(chat_id)
        return True

    if command == "/support":
        await send_managed_message(chat_id, support_help_text(), attachments=build_keyboard(), page=UI_PAGE_SUPPORT)
        return True

    if command == "/channel":
        await send_channel(chat_id)
        return True

    if command == "/buy":
        if not arg:
            await max_send_message(chat_id, "Выбери тариф кнопками ниже.", attachments=build_tariffs_keyboard_pricing())
            return True
        plan = arg.lower().strip()
        if plan == "free":
            user_profile(chat_id)
            state.user_store.set_plan(chat_id, "free")
            state.user_store.set_selected_model(chat_id, best_default_alias_for_plan("free"))
            await max_send_message(chat_id, "Тариф переключен на free.", attachments=build_tariffs_keyboard_pricing())
            return True
        if plan not in BUYABLE_PLANS:
            await max_send_message(chat_id, "Доступно: Lite, Start или Pro.", attachments=build_tariffs_keyboard_pricing())
            return True
        ok = await start_buy_flow(chat_id, plan)
        if not ok:
            return True
        return True

    if command == "/payments":
        await send_payments(chat_id)
        return True

    if command == "/ref":
        row = user_profile(chat_id)
        if not arg:
            code = str(row.get("referral_code", "")).strip() or referral_code_for_chat(chat_id)
            invited = int(row.get("referrals_invited", 0) or 0)
            await max_send_message(
                chat_id,
                (
                    f"👥 Твой реф-код: {code}\n"
                    f"Приглашено друзей: {invited}\n"
                    f"Бонус за каждого друга: +{REFERRAL_BONUS_CREDITS} кредитов вам обоим.\n\n"
                    f"Другу нужно отправить: /ref {code}"
                ),
                attachments=build_growth_keyboard(),
            )
            return True

        ok, info = state.user_store.apply_referral_code(chat_id, arg, REFERRAL_BONUS_CREDITS)
        if not ok:
            await max_send_message(chat_id, info, attachments=build_growth_keyboard())
            return True
        owner_chat_id = int(info)
        await max_send_message(
            chat_id,
            f"Готово! Реферальный код принят. Тебе начислено +{REFERRAL_BONUS_CREDITS} кредитов.",
            attachments=build_growth_keyboard(),
        )
        with suppress(Exception):
            await max_send_message(
                owner_chat_id,
                f"🎉 По твоему коду зарегистрировался друг. Начислено +{REFERRAL_BONUS_CREDITS} кредитов.",
                attachments=build_keyboard(),
                notify=False,
            )
        return True

    if command == "/promo":
        if not arg:
            state.pending_promo_code_input.add(chat_id)
            await max_send_message(chat_id, "Введи промокод одним сообщением.", attachments=build_growth_keyboard())
            return True
        code = normalize_referral_code(arg)
        credits, bonus_ttl_days, reason = promo_offer_for_code(code)
        if credits <= 0:
            await max_send_message(chat_id, reason or "Такого промокода нет или он выключен.", attachments=build_growth_keyboard())
            return True
        ok, info = state.user_store.redeem_promo_code(chat_id, code, credits, bonus_ttl_days=bonus_ttl_days)
        if not ok:
            await max_send_message(chat_id, info, attachments=build_growth_keyboard())
            return True
        ttl_tail = f" Срок действия бонуса: {bonus_ttl_days} дн." if bonus_ttl_days > 0 else ""
        await max_send_message(chat_id, f"Промокод активирован: +{info} кредитов.{ttl_tail}", attachments=build_growth_keyboard())
        return True

    if command == "/preset":
        if not arg:
            await max_send_message(
                chat_id,
                "Выбери режим: /preset fast|balanced|quality|expert",
                attachments=build_keyboard(),
            )
            return True
        preset = arg.lower().strip()
        preset_cfg = MODEL_PRESETS.get(preset)
        if not preset_cfg:
            await max_send_message(
                chat_id,
                "Неизвестный режим. Доступно: fast, balanced, quality, expert.",
                attachments=build_keyboard(),
            )
            return True
        alias = resolve_preset_alias_for_chat(chat_id, preset)
        label = await set_user_model(chat_id, alias)
        state.user_store.set_selected_preset(chat_id, preset)
        await max_send_message(
            chat_id,
            f"Режим: {preset_cfg['label']}\nМодель: {label}",
            attachments=build_keyboard(),
        )
        return True

    if command == "/model":
        if not arg:
            await max_send_message(chat_id, "Укажи модель: /model deepseek|gpt|gpt4o|gemini|gpt54", attachments=build_keyboard())
            return True
        label = await set_user_model(chat_id, arg)
        state.user_store.set_selected_preset(chat_id, "")
        await max_send_message(chat_id, f"Выбрана модель: {label}", attachments=build_keyboard())
        return True

    if command in {"/clear", "/reset"}:
        state.history(chat_id).clear()
        await max_send_message(chat_id, "Контекст диалога очищен.", attachments=build_keyboard())
        return True

    if command == "/image":
        if not arg:
            await send_image_menu(chat_id)
            return True
        prepared_prompt = build_image_prompt(arg, chat_id)
        return await process_image_generation(chat_id, arg, model_prompt=prepared_prompt)

    if command == "/image_ref":
        row = user_profile(chat_id)
        if row["plan"] == "free" or not plan_allowed(row["plan"], DEFAULT_IMAGE_MODEL.min_plan):
            await max_send_message(
                chat_id,
                f"Режим «по фото» доступен с тарифа {DEFAULT_IMAGE_MODEL.min_plan}. Открой «Тарифы».",
                attachments=build_tariffs_keyboard_pricing(),
            )
            return True
        reference = get_recent_reference_image(chat_id)
        if not reference:
            state.pending_image_ref_prompt.add(chat_id)
            await max_send_message(
                chat_id,
                f"Сначала отправь фото. Стоимость режима «по фото»: {CREDIT_COST_IMAGE_EDIT} кредитов.",
                attachments=build_image_prompt_keyboard(),
            )
            return True
        if not arg:
            state.pending_image_ref_prompt.add(chat_id)
            await max_send_message(
                chat_id,
                "Опиши, что сделать с фото (например: «нарисуй её в стиле киберпанк»).",
                attachments=build_image_prompt_keyboard(),
            )
            return True
        return await process_image_edit_generation(chat_id, arg, reference)

    if command.startswith("/admin"):
        return await handle_admin(chat_id, text)

    return False


async def handle_pending_receipt_input(chat_id: int, text: str) -> bool:
    plan = state.pending_receipt_plan.get(chat_id)
    if not plan:
        return False

    lowered = text.strip().lower()
    if text.strip().startswith("/") and lowered != "/cancel":
        return False
    if lowered in {"отмена", "cancel", "/cancel"}:
        state.pending_receipt_plan.pop(chat_id, None)
        await show_ui_page(chat_id, receipt_return_page(plan), push_history=False)
        return True

    email, phone = parse_receipt_contact(text)
    if not (email or phone):
        target_label = "подписки" if not plan.startswith("topup") else "пакета кредитов"
        await show_managed_content(
            chat_id,
            (
                f"Не удалось распознать контакт для {target_label}.\n"
                "Отправь email (user@example.com) или телефон (+79991234567).\n\n"
                "Можно нажать «Отмена» ниже."
            ),
            attachments=build_receipt_contact_keyboard(),
            page=UI_PAGE_SUPPORT,
        )
        return True

    user_profile(chat_id)
    state.user_store.set_receipt_contact(chat_id, email=email, phone=phone)
    state.pending_receipt_plan.pop(chat_id, None)
    if plan.startswith("topup_consent:"):
        code = plan.split(":", 1)[1].lower().strip()
        await send_topup_consent(chat_id, code)
        return True
    if plan.startswith("topup:"):
        code = plan.split(":", 1)[1].lower().strip()
        await send_topup_consent(chat_id, code)
        return True
    await send_buy_consent(chat_id, plan)
    return True


async def handle_pending_referral_input(chat_id: int, text: str) -> bool:
    if chat_id not in state.pending_referral_code_input:
        return False
    lowered = text.strip().lower()
    if lowered in {"отмена", "cancel", "/cancel"}:
        state.pending_referral_code_input.discard(chat_id)
        await show_ui_page(chat_id, UI_PAGE_GROWTH, push_history=False)
        return True
    if text.strip().startswith("/"):
        state.pending_referral_code_input.discard(chat_id)
        return False
    if not looks_like_bonus_code(text):
        state.pending_referral_code_input.discard(chat_id)
        return False

    state.pending_referral_code_input.discard(chat_id)
    ok, info = state.user_store.apply_referral_code(chat_id, text, REFERRAL_BONUS_CREDITS)
    if not ok:
        await show_managed_content(chat_id, info, attachments=build_growth_keyboard(), page=UI_PAGE_GROWTH)
        return True
    owner_chat_id = int(info)
    await show_managed_content(
        chat_id,
        f"Готово! Реферальный код принят. Начислено +{REFERRAL_BONUS_CREDITS} кредитов.",
        attachments=build_growth_keyboard(),
        page=UI_PAGE_GROWTH,
    )
    with suppress(Exception):
        await max_send_message(
            owner_chat_id,
            f"🎉 По твоему коду зарегистрировался друг. Начислено +{REFERRAL_BONUS_CREDITS} кредитов.",
            attachments=build_keyboard(),
            notify=False,
        )
    return True


async def handle_pending_promo_input(chat_id: int, text: str) -> bool:
    if chat_id not in state.pending_promo_code_input:
        return False
    lowered = text.strip().lower()
    if lowered in {"отмена", "cancel", "/cancel"}:
        state.pending_promo_code_input.discard(chat_id)
        await show_ui_page(chat_id, UI_PAGE_GROWTH, push_history=False)
        return True
    if text.strip().startswith("/"):
        state.pending_promo_code_input.discard(chat_id)
        return False
    if not looks_like_bonus_code(text):
        state.pending_promo_code_input.discard(chat_id)
        return False
    state.pending_promo_code_input.discard(chat_id)

    code = normalize_referral_code(text)
    credits, bonus_ttl_days, reason = promo_offer_for_code(code)
    if credits <= 0:
        await show_managed_content(
            chat_id,
            reason or "Такого промокода нет или он выключен.",
            attachments=build_growth_keyboard(),
            page=UI_PAGE_GROWTH,
        )
        return True
    ok, info = state.user_store.redeem_promo_code(chat_id, code, credits, bonus_ttl_days=bonus_ttl_days)
    if not ok:
        await show_managed_content(chat_id, info, attachments=build_growth_keyboard(), page=UI_PAGE_GROWTH)
        return True
    ttl_tail = f" Срок действия бонуса: {bonus_ttl_days} дн." if bonus_ttl_days > 0 else ""
    await show_managed_content(
        chat_id,
        f"Промокод активирован: +{info} кредитов.{ttl_tail}",
        attachments=build_growth_keyboard(),
        page=UI_PAGE_GROWTH,
    )
    return True


async def process_update(update: dict[str, Any]) -> None:
    if not isinstance(update, dict) or not is_supported_update(update):
        return
    if not remember_update(update):
        log.info("Duplicate update skipped")
        return

    update_type = update.get("update_type")
    if update_type == "message_callback":
        await handle_callback(update)
        return

    chat_id, text = parse_incoming_text(update)
    incoming_image_url = parse_incoming_image_url(update)
    if chat_id is None:
        return

    ensure_update_user_binding(chat_id, update)
    row = user_profile(chat_id)
    state.user_store.touch_last_active(chat_id)
    if row["is_blocked"]:
        return

    if incoming_image_url:
        try:
            try:
                incoming_image = await fetch_image_bytes(incoming_image_url, use_max_auth=True)
            except Exception:
                incoming_image = await fetch_image_bytes(incoming_image_url, use_max_auth=False)
            remember_reference_image(chat_id, encode_data_url(incoming_image))
        except Exception as exc:
            log.exception("Failed to save incoming reference image for chat_id=%s", chat_id)
            with suppress(Exception):
                await max_send_message(chat_id, f"Не удалось обработать фото: {exc}", attachments=build_image_menu_keyboard(chat_id))
            return

        if text and (chat_id in state.pending_image_ref_prompt or looks_like_image_ref_request(text)):
            state.pending_image_ref_prompt.discard(chat_id)
            await process_image_edit_generation(chat_id, text, get_recent_reference_image(chat_id))
            return

        if not text:
            state.pending_image_ref_prompt.add(chat_id)
            await max_send_message(
                chat_id,
                (
                    "Фото получил ✅\n"
                    "Теперь напиши, что с ним сделать (например: «нарисуй её в стиле аниме»).\n"
                    f"Стоимость режима «по фото»: {CREDIT_COST_IMAGE_EDIT} кредитов."
                ),
                attachments=build_image_prompt_keyboard(),
            )
            return

    if update_type in {"bot_started", "user_added", "bot_added"} and not text:
        if int(row.get("onboarding_done", 0) or 0) == 0:
            await send_onboarding(chat_id, step=1)
        else:
            await send_menu(chat_id)
        return
    if not text:
        return

    log.info("Incoming update=%s chat_id=%s text=%r", update_type, chat_id, text[:120])
    if int(row.get("onboarding_done", 0) or 0) == 0 and text.strip().lower() not in {"/start"}:
        state.user_store.set_onboarding_done(chat_id, True)
    try:
        if await handle_pending_referral_input(chat_id, text):
            return
        if await handle_pending_promo_input(chat_id, text):
            return
        if await handle_pending_receipt_input(chat_id, text):
            return
        if await handle_pending_image_ref_prompt_input(chat_id, text):
            return
        if await handle_pending_image_prompt_input(chat_id, text):
            return
        recent_reference = get_recent_reference_image(chat_id)
        if recent_reference and looks_like_image_ref_request(text) and not text.strip().startswith("/"):
            await process_image_edit_generation(chat_id, text, recent_reference)
            return
        if await handle_command(chat_id, text):
            return

        if len(text) > MAX_TEXT_INPUT_CHARS:
            await max_send_message(
                chat_id,
                f"Слишком длинное сообщение. Максимум {MAX_TEXT_INPUT_CHARS} символов.",
                attachments=build_keyboard(),
            )
            return

        ok_cd, reason_cd = check_cooldown(chat_id, "message")
        if not ok_cd:
            await max_send_message(chat_id, reason_cd, attachments=build_keyboard())
            return

        ok, reason = check_limit_only(chat_id, "messages")
        if not ok:
            await max_send_message(chat_id, reason, attachments=build_keyboard())
            return

        selected_alias = str(user_profile(chat_id).get("selected_model_alias") or DEFAULT_TEXT_MODEL.alias)
        model_label = TEXT_MODELS.get(selected_alias, DEFAULT_TEXT_MODEL).label
        fixed_text_cost = text_credit_cost(selected_alias)
        plan_name, _, _, estimated_messages = build_text_request(chat_id, text, selected_alias=selected_alias)
        estimated_prompt_tokens = estimate_tokens_from_messages(estimated_messages)
        estimated_total_tokens = estimated_prompt_tokens + completion_tokens_for_plan(plan_name)
        reserved_var_cost = variable_text_credits(selected_alias, estimated_total_tokens)
        reserved_total_cost = fixed_text_cost + reserved_var_cost

        ok_credit, reason_credit = check_and_consume_credits(
            chat_id,
            reserved_total_cost,
            f"текст ({model_label})",
        )
        if not ok_credit:
            await max_send_message(chat_id, reason_credit, attachments=purchase_help_keyboard_for_row(user_profile(chat_id)))
            return

        ok, reason = check_and_consume_limit(chat_id, "messages")
        if not ok:
            state.user_store.refund_credits(chat_id, reserved_total_cost)
            await max_send_message(chat_id, reason, attachments=build_keyboard())
            return

        await max_send_message(chat_id, f"Думаю... Модель: {current_model_label(chat_id)}", notify=False)
        try:
            result = await ask_text_model(chat_id, text, selected_alias=selected_alias)
            actual_var_cost = variable_text_credits(selected_alias, result.total_tokens)
            actual_total_cost = fixed_text_cost + actual_var_cost
            if reserved_var_cost > actual_var_cost:
                state.user_store.refund_credits(chat_id, reserved_var_cost - actual_var_cost)
            elif actual_var_cost > reserved_var_cost:
                extra_cost = actual_var_cost - reserved_var_cost
                ok_extra, _ = check_and_consume_credits(chat_id, extra_cost, f"сложность ({model_label})")
                if not ok_extra:
                    log.warning(
                        "Variable credits under-reserved chat_id=%s alias=%s reserved_var=%s actual_var=%s tokens=%s",
                        chat_id,
                        selected_alias,
                        reserved_var_cost,
                        actual_var_cost,
                        result.total_tokens,
                    )
            final_row = user_profile(chat_id)
            state.user_store.record_usage_event(
                chat_id=chat_id,
                event_type="text_request",
                plan=str(final_row.get("plan", "")),
                model_alias=selected_alias,
                credits_spent=actual_total_cost,
                tokens_total=int(result.total_tokens),
                details=f"prompt={int(result.prompt_tokens)};completion={int(result.completion_tokens)}",
            )
            await max_send_message(
                chat_id,
                result.text,
                attachments=build_reply_shortcuts_keyboard(chat_id),
                text_format="markdown",
            )
            with suppress(Exception):
                await maybe_send_low_credits_nudge(chat_id)
        except Exception:
            state.user_store.refund_credits(chat_id, reserved_total_cost)
            raise
    except Exception as exc:
        log.exception("Failed to process update")
        capture_exception_safe(exc)
        await notify_admin_alert("process_update", f"chat_id={chat_id}\nerror={exc}")
        with suppress(Exception):
            await max_send_message(chat_id, f"Ошибка: {exc}")


async def get_updates(marker: int | None = None) -> tuple[list[dict[str, Any]], int | None]:
    session = await get_session()
    params: list[tuple[str, str]] = [("limit", "100"), ("timeout", "25")]
    if marker is not None:
        params.append(("marker", str(marker)))

    async with session.get(
        f"{MAX_API}/updates",
        headers={"Authorization": MAX_TOKEN},
        params=params,
    ) as resp:
        data = await resp.json(content_type=None)
        if resp.status >= 400:
            raise RuntimeError(f"MAX updates error {resp.status}: {data}")

    updates = data.get("updates")
    next_marker = data.get("marker")
    if not isinstance(updates, list):
        updates = []
    if next_marker is not None and not isinstance(next_marker, int):
        try:
            next_marker = int(next_marker)
        except Exception:
            next_marker = marker
    return updates, next_marker


async def polling_loop() -> None:
    marker: int | None = None
    log.info("Polling mode started")
    while True:
        try:
            updates, marker = await get_updates(marker)
            for update in updates:
                await process_update(update)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("Polling loop error")
            capture_exception_safe(exc)
            await notify_admin_alert("polling_loop", f"Polling loop error: {exc}")
            await asyncio.sleep(3)


@asynccontextmanager
async def lifespan(_: FastAPI):
    require_env()
    validate_pricing_sanity()
    init_sentry_if_enabled()
    await get_session()
    if RUN_MODE == "polling":
        state.polling_task = asyncio.create_task(polling_loop())
    try:
        yield
    finally:
        if state.polling_task:
            state.polling_task.cancel()
            with suppress(asyncio.CancelledError):
                await state.polling_task
        if state.session and not state.session.closed:
            await state.session.close()


app = FastAPI(title="MAX Multi AI Bot", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=str(SITE_DIR / "assets")), name="assets")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "run_mode": RUN_MODE}


@app.get("/", response_class=FileResponse)
async def landing_index() -> FileResponse:
    return FileResponse(site_file("index.html"))


@app.get("/offer", response_class=FileResponse)
async def landing_offer() -> FileResponse:
    return FileResponse(site_file("offer.html"))


@app.get("/privacy", response_class=FileResponse)
async def landing_privacy() -> FileResponse:
    return FileResponse(site_file("privacy.html"))


@app.get("/refund", response_class=FileResponse)
async def landing_refund() -> FileResponse:
    return FileResponse(site_file("refund.html"))


@app.get("/contacts", response_class=FileResponse)
async def landing_contacts() -> FileResponse:
    return FileResponse(site_file("contacts.html"))


@app.get("/contacts/meta")
async def contacts_meta() -> dict[str, str]:
    return {
        "email": CONTACT_EMAIL,
        "phone": CONTACT_PHONE,
        "support_url": support_url_value(),
        "support_text": SUPPORT_TEXT,
    }


@app.get("/support", response_class=FileResponse)
async def landing_support() -> FileResponse:
    return FileResponse(site_file("support.html"))


@app.get("/support/meta")
async def support_meta() -> dict[str, str]:
    return {"url": support_url_value(), "text": SUPPORT_TEXT, "email": CONTACT_EMAIL}


@app.get("/mailru-domainMB5PESlCeJQEXuoC.html", response_class=FileResponse)
async def mailru_domain_verify() -> FileResponse:
    return FileResponse(site_file("mailru-domainMB5PESlCeJQEXuoC.html"))


@app.get("/admin/panel", response_class=HTMLResponse)
async def admin_panel(token: str = "", chat_id: int | None = None, request_id: int | None = None) -> HTMLResponse:
    if not admin_panel_authorized(token):
        raise HTTPException(status_code=403, detail="forbidden")
    return HTMLResponse(render_admin_panel_html(token=token, chat_id=chat_id, request_id=request_id))


@app.get("/admin/panel/action", response_class=HTMLResponse)
async def admin_panel_action(
    token: str = "",
    type: str = "",
    chat_id: int | None = None,
    request_id: int | None = None,
    plan: str = "",
    amount: int = 0,
    value: str = "",
) -> HTMLResponse:
    if not admin_panel_authorized(token):
        raise HTTPException(status_code=403, detail="forbidden")
    message = "Готово"
    action = type.strip().lower()
    try:
        if action == "backup":
            backup_file = create_db_backup()
            message = f"Бэкап создан: {backup_file}"
        elif action == "nudge":
            sent, total = await send_reengage_nudges(days=REENGAGE_DORMANT_DAYS, limit=REENGAGE_BATCH_LIMIT)
            message = f"Реактивация: отправлено {sent}/{total}"
        elif action == "set_plan" and chat_id is not None and plan in PLAN_CONFIGS:
            user_profile(chat_id)
            state.user_store.set_plan(chat_id, plan)
            state.user_store.set_selected_model(chat_id, best_default_alias_for_plan(plan))
            if plan in PAID_PLANS:
                state.user_store.set_credits(chat_id, credits_for_plan(plan))
            message = f"План пользователя {chat_id} -> {plan}"
        elif action == "add_credits" and chat_id is not None and amount != 0:
            user_profile(chat_id)
            balance = state.user_store.adjust_credits(chat_id, amount)
            message = f"Баланс пользователя {chat_id}: {balance}"
        elif action == "reset_daily" and chat_id is not None:
            state.user_store.reset_daily_counters(chat_id)
            message = f"Дневные лимиты пользователя {chat_id} сброшены"
        elif action == "block" and chat_id is not None and value in {"on", "off"}:
            state.user_store.set_blocked(chat_id, value == "on")
            message = f"Пользователь {chat_id}: block={value}"
        elif action == "payment" and request_id is not None and value in {"paid", "cancel"}:
            if value == "paid":
                ok, info = await activate_payment_request(request_id, source="admin panel")
                message = f"Платеж #{request_id}: {info}" if ok else f"Платеж #{request_id}: {info}"
            else:
                changed, info = cancel_payment_if_open(request_id)
                message = f"Платеж #{request_id}: {'отменен' if changed else info}"
        else:
            message = "Некорректные параметры действия."
    except Exception as exc:
        capture_exception_safe(exc)
        message = f"Ошибка: {exc}"

    return HTMLResponse(render_admin_panel_html(token=token, chat_id=chat_id, request_id=request_id, message=message))


def payment_status_view(request_id: int | None) -> dict[str, Any]:
    if request_id is None:
        return {
            "known": False,
            "status": "unknown",
            "status_label": payment_status_label("unknown"),
            "title": "Заявка не найдена",
            "message": "Не удалось определить номер заявки. Вернись в бот и нажми «Тарифы».",
        }

    payment = state.user_store.get_payment(request_id)
    if not payment:
        return {
            "known": False,
            "request_id": request_id,
            "status": "unknown",
            "status_label": payment_status_label("unknown"),
            "title": "Заявка не найдена",
            "message": "Такой заявки нет. Создай новую оплату в боте.",
        }

    status = str(payment.get("status", "pending")).lower()
    title, message = payment_status_title_message(status)
    return {
        "known": True,
        "request_id": request_id,
        "status": status,
        "status_label": payment_status_label(status),
        "title": title,
        "message": message,
        "plan": str(payment.get("plan", "")),
        "amount_rub": int(payment.get("amount_rub", 0)),
    }


def render_admin_panel_html(
    token: str,
    chat_id: int | None = None,
    request_id: int | None = None,
    message: str = "",
) -> str:
    users = state.user_store.list_recent_users(limit=25)
    payments = state.user_store.list_recent_payments(limit=25)
    selected_user = state.user_store.get_user(chat_id) if chat_id else None
    selected_payment = state.user_store.get_payment(request_id) if request_id else None
    esc = html.escape
    info_block = ""
    if message:
        info_block += f"<p style='padding:10px;border:1px solid #dbe3f0;border-radius:8px;background:#f8fbff'>{esc(message)}</p>"
    if selected_user:
        info_block += (
            "<h3>Пользователь</h3>"
            f"<pre>{esc(json.dumps(selected_user, ensure_ascii=False, indent=2))}</pre>"
        )
    if selected_payment:
        info_block += (
            "<h3>Платеж</h3>"
            f"<pre>{esc(json.dumps(selected_payment, ensure_ascii=False, indent=2))}</pre>"
        )

    user_rows = []
    for row in users:
        cid = int(row.get("chat_id", 0) or 0)
        user_rows.append(
            "<tr>"
            f"<td>{cid}</td><td>{esc(str(row.get('plan', '')))}</td>"
            f"<td>{int(row.get('credits_balance', 0) or 0)}</td>"
            f"<td>{int(row.get('daily_messages_used', 0) or 0)}/{int(row.get('daily_images_used', 0) or 0)}</td>"
            f"<td>{int(row.get('is_blocked', 0) or 0)}</td>"
            f"<td>{esc(str(row.get('last_active_at', '') or '-'))}</td>"
            f"<td><a href='/admin/panel?token={esc(token)}&chat_id={cid}'>Открыть</a></td>"
            "</tr>"
        )

    payment_rows = []
    for row in payments:
        rid = int(row.get("id", 0) or 0)
        payment_rows.append(
            "<tr>"
            f"<td>{rid}</td><td>{int(row.get('chat_id', 0) or 0)}</td>"
            f"<td>{esc(str(row.get('plan', '')))}</td>"
            f"<td>{int(row.get('amount_rub', 0) or 0)}</td>"
            f"<td>{esc(payment_status_label(str(row.get('status', ''))))}</td>"
            f"<td><a href='/admin/panel?token={esc(token)}&request_id={rid}'>Открыть</a></td>"
            "</tr>"
        )

    action_block = ""
    if selected_user:
        cid = int(selected_user["chat_id"])
        action_block = (
            "<h3>Ручная корректировка</h3>"
            "<p>"
            f"<a href='/admin/panel/action?token={esc(token)}&type=set_plan&chat_id={cid}&plan=free'>План free</a> | "
            f"<a href='/admin/panel/action?token={esc(token)}&type=set_plan&chat_id={cid}&plan=lite'>План lite</a> | "
            f"<a href='/admin/panel/action?token={esc(token)}&type=set_plan&chat_id={cid}&plan=start'>План start</a> | "
            f"<a href='/admin/panel/action?token={esc(token)}&type=set_plan&chat_id={cid}&plan=pro'>План pro</a>"
            "</p>"
            "<p>"
            f"<a href='/admin/panel/action?token={esc(token)}&type=add_credits&chat_id={cid}&amount=500'>+500 кредитов</a> | "
            f"<a href='/admin/panel/action?token={esc(token)}&type=add_credits&chat_id={cid}&amount=-500'>-500 кредитов</a> | "
            f"<a href='/admin/panel/action?token={esc(token)}&type=reset_daily&chat_id={cid}'>Сброс дневных лимитов</a>"
            "</p>"
            "<p>"
            f"<a href='/admin/panel/action?token={esc(token)}&type=block&chat_id={cid}&value=on'>Block ON</a> | "
            f"<a href='/admin/panel/action?token={esc(token)}&type=block&chat_id={cid}&value=off'>Block OFF</a>"
            "</p>"
        )
    if selected_payment:
        rid = int(selected_payment["id"])
        action_block += (
            "<h3>Платеж</h3>"
            "<p>"
            f"<a href='/admin/panel/action?token={esc(token)}&type=payment&request_id={rid}&value=paid'>Подтвердить оплату</a> | "
            f"<a href='/admin/panel/action?token={esc(token)}&type=payment&request_id={rid}&value=cancel'>Отменить</a>"
            "</p>"
        )

    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Admin Panel</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#f6f8fb;color:#13213a;margin:0;padding:20px}}
.card{{background:#fff;border:1px solid #dbe3f0;border-radius:14px;padding:16px;margin-bottom:14px}}
table{{width:100%;border-collapse:collapse}} th,td{{border-bottom:1px solid #ecf1fa;padding:8px;text-align:left;font-size:13px}}
a{{color:#1458d4;text-decoration:none}}
pre{{white-space:pre-wrap;word-break:break-word;background:#fbfdff;border:1px solid #e1e8f5;border-radius:8px;padding:10px}}
</style></head>
<body>
<div class="card"><h2>Admin Panel</h2>
<p><a href="/admin/panel/action?token={esc(token)}&type=backup">Создать бэкап БД</a> |
<a href="/admin/panel/action?token={esc(token)}&type=nudge">Реактивировать free-пользователей</a></p>
{info_block}
{action_block}
</div>
<div class="card"><h3>Последние пользователи</h3>
<table><tr><th>chat_id</th><th>plan</th><th>credits</th><th>usage d</th><th>blocked</th><th>last_active_at</th><th></th></tr>
{''.join(user_rows)}
</table></div>
<div class="card"><h3>Последние платежи</h3>
<table><tr><th>id</th><th>chat_id</th><th>plan</th><th>amount</th><th>status</th><th></th></tr>
{''.join(payment_rows)}
</table></div>
</body></html>"""


@app.get("/payment/status")
async def payment_status(request_id: int | None = None) -> dict[str, Any]:
    view = payment_status_view(request_id)
    if request_id is None or not view.get("known"):
        return view

    if view["status"] not in {"pending", "claimed", "paid"}:
        return view

    try:
        _, bank_status = await refresh_payment_from_tbank(request_id, source="T-Bank GetState")
        refreshed = payment_status_view(request_id)
        refreshed["bank_status"] = bank_status
        return refreshed
    except Exception:
        log.exception("T-Bank GetState failed for request_id=%s", request_id)
        return view


@app.get("/payment/success", response_class=FileResponse)
async def payment_success_page() -> FileResponse:
    return FileResponse(site_file("payment_success.html"))


@app.get("/payment/fail", response_class=FileResponse)
async def payment_fail_page() -> FileResponse:
    return FileResponse(site_file("payment_fail.html"))


@app.post("/webhook/max")
async def max_webhook(request: Request) -> dict[str, bool]:
    if WEBHOOK_SECRET:
        header_secret = request.headers.get("X-Max-Bot-Api-Secret", "")
        if header_secret != WEBHOOK_SECRET:
            log.warning("Webhook secret mismatch")
            raise HTTPException(status_code=403, detail="forbidden")

    payload = await request.json()
    updates = payload if isinstance(payload, list) else [payload]
    for update in updates:
        try:
            await process_update(update)
        except Exception as exc:
            log.exception("Unhandled webhook processing error")
            capture_exception_safe(exc)
            await notify_admin_alert("max_webhook", f"Unhandled webhook error: {exc}")
    return {"ok": True}


@app.post("/webhook/tbank")
async def tbank_webhook(request: Request) -> PlainTextResponse:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")

    if not tbank_notification_is_valid(payload):
        log.warning("Invalid T-Bank webhook signature or terminal")
        with suppress(Exception):
            await notify_admin_alert("tbank_webhook", "Invalid webhook signature or terminal key.")
        raise HTTPException(status_code=403, detail="forbidden")

    order_id = scalar_string(payload.get("OrderId"))
    status = scalar_string(payload.get("Status")).upper()
    success_raw = payload.get("Success")
    success = success_raw is True or scalar_string(success_raw).lower() == "true"

    request_id = parse_request_id_from_order_id(order_id)
    if request_id is not None and success and status == "CONFIRMED":
        activated, info = await activate_payment_request(request_id, source="T-Bank webhook")
        if activated:
            log.info("T-Bank payment activated request_id=%s until=%s", request_id, info)
        else:
            log.info("T-Bank payment skipped request_id=%s reason=%s", request_id, info)
    elif request_id is not None and tbank_is_refund_status(status):
        changed, info = await process_refund_payment_request(request_id, source="T-Bank webhook", bank_status=status)
        if changed:
            log.info("T-Bank payment refunded request_id=%s result=%s", request_id, info)
        else:
            log.info("T-Bank refund ignored request_id=%s reason=%s", request_id, info)
    elif request_id is not None and tbank_is_cancel_status(status):
        changed, info = cancel_payment_if_open(request_id)
        if changed:
            log.info("T-Bank payment canceled request_id=%s status=%s", request_id, status)
        else:
            log.info("T-Bank cancel ignored request_id=%s reason=%s", request_id, info)

    return PlainTextResponse("OK")


def run() -> None:
    if RUN_MODE == "webhook":
        require_env()
        uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
        return
    require_env()
    asyncio.run(polling_loop())


if __name__ == "__main__":
    run()
