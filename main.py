from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager, suppress
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
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
MESSAGE_COOLDOWN_SECONDS = int(os.getenv("MESSAGE_COOLDOWN_SECONDS", "1"))
IMAGE_COOLDOWN_SECONDS = int(os.getenv("IMAGE_COOLDOWN_SECONDS", "20"))
START_PLAN_PRICE_RUB = int(os.getenv("START_PLAN_PRICE_RUB", "499"))
PRO_PLAN_PRICE_RUB = int(os.getenv("PRO_PLAN_PRICE_RUB", "1490"))
START_PLAN_DAYS = int(os.getenv("START_PLAN_DAYS", "30"))
PRO_PLAN_DAYS = int(os.getenv("PRO_PLAN_DAYS", "30"))
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
TBANK_RECEIPT_EMAIL = os.getenv("TBANK_RECEIPT_EMAIL", "").strip()
TBANK_RECEIPT_PHONE = os.getenv("TBANK_RECEIPT_PHONE", "").strip()
TBANK_RECEIPT_TAXATION = os.getenv("TBANK_RECEIPT_TAXATION", "usn_income").strip()
TBANK_RECEIPT_TAX = os.getenv("TBANK_RECEIPT_TAX", "none").strip()
TBANK_RECEIPT_PAYMENT_METHOD = os.getenv("TBANK_RECEIPT_PAYMENT_METHOD", "full_prepayment").strip()
TBANK_RECEIPT_PAYMENT_OBJECT = os.getenv("TBANK_RECEIPT_PAYMENT_OBJECT", "service").strip()
TBANK_RECEIPT_FFD_VERSION = os.getenv("TBANK_RECEIPT_FFD_VERSION", "1.05").strip()
TBANK_CANCEL_STATUSES = {"REJECTED", "CANCELED", "DEADLINE_EXPIRED"}
TBANK_REFUND_STATUSES = {"REFUNDED", "REVERSED", "PARTIAL_REVERSED", "PARTIAL_REFUNDED", "CHARGEDBACK"}
SUPPORT_URL = os.getenv("SUPPORT_URL", "").strip()
SUPPORT_TEXT = os.getenv("SUPPORT_TEXT", "Поддержка: напиши нам, поможем быстро.").strip()
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "").strip()
CONTACT_PHONE = os.getenv("CONTACT_PHONE", "").strip()
ADMIN_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
}

SYSTEM_PROMPT_BASE = (
    "Ты полезный AI-ассистент в мессенджере MAX. "
    "Отвечай по-русски, если пользователь не попросил иначе. "
    "Не упоминай внутренние технические детали без необходимости."
)

STYLE_PROMPTS = {
    "gpt": "Стиль: четко структурируй ответ, хорошо объясняй шаги и варианты.",
    "gemini": "Стиль: отвечай быстро, дружелюбно и с упором на практический результат.",
    "deepseek": "Стиль: делай упор на рассуждение, анализ и техническую точность.",
    "gpt54": "Стиль: отвечай как эксперт-консультант, глубоко и обоснованно.",
}

PLAN_ORDER = {"free": 0, "start": 1, "pro": 2}

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
    "Если нужен список команд, отправь /help.\n"
    "Если проблема с оплатой — нажми «Помощь» или отправь /support."
)

HELP_TEXT = (
    "Команды:\n"
    "/start или /menu — меню\n"
    "/models — версии и описание моделей\n"
    "/plan — твой тариф и остатки\n"
    "/model <alias> — выбрать модель\n"
    "/gpt, /gemini, /deepseek, /gpt54 — быстрый выбор\n"
    "/image <описание> — сгенерировать картинку\n"
    "/tariffs — тарифы\n"
    "/buy <start|pro> — заявка на подписку\n"
    "/payments — мои заявки\n"
    "/support — помощь по оплате и работе бота\n"
    "/clear — очистить контекст"
)

ADMIN_HELP_TEXT = (
    "\n\nАдмин:\n"
    "/admin help\n"
    "/admin user <chat_id>\n"
    "/admin plan <chat_id> <free|start|pro>\n"
    "/admin sub <chat_id> <start|pro> <days>\n"
    "/admin block <chat_id> <on|off>\n"
    "/admin pay <request_id> <paid|cancel>\n"
    "/costs — модели и цены"
)

TARIFFS_TEXT = (
    "Тарифы:\n"
    "• free: 40 сообщений/день, 0 картинок/день\n"
    "• start: 400 сообщений/день, 12 картинок/день\n"
    "• pro: 2500 сообщений/день, 80 картинок/день\n\n"
    "Модели по тарифам:\n"
    "• free: DeepSeek V4 Flash, GPT-4.1 Mini\n"
    "• start: + Gemini 2.5 Flash\n"
    "• pro: + GPT-5.4"
)

BUY_TEXT = (
    "Покупка (пока в ручном режиме):\n"
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


PLAN_CONFIGS = {
    "free": PlanInfo(name="free", daily_messages_limit=40, daily_images_limit=0),
    "start": PlanInfo(name="start", daily_messages_limit=400, daily_images_limit=12),
    "pro": PlanInfo(name="pro", daily_messages_limit=2500, daily_images_limit=80),
}


@dataclass(slots=True)
class ImageResult:
    image_bytes: bytes
    mime_type: str


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
                    plan TEXT NOT NULL DEFAULT 'free',
                    is_blocked INTEGER NOT NULL DEFAULT 0,
                    receipt_email TEXT NOT NULL DEFAULT '',
                    receipt_phone TEXT NOT NULL DEFAULT '',
                    selected_model_alias TEXT NOT NULL DEFAULT '',
                    subscription_expires_at TEXT NOT NULL DEFAULT '',
                    recurring_enabled INTEGER NOT NULL DEFAULT 0,
                    recurring_cancel_from TEXT NOT NULL DEFAULT '',
                    recurring_canceled_at TEXT NOT NULL DEFAULT '',
                    usage_date TEXT NOT NULL DEFAULT '',
                    daily_messages_used INTEGER NOT NULL DEFAULT 0,
                    daily_images_used INTEGER NOT NULL DEFAULT 0,
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
                    created_at TEXT NOT NULL DEFAULT '',
                    paid_at TEXT NOT NULL DEFAULT '',
                    activated_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            self._ensure_column(conn, "users", "subscription_expires_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "recurring_enabled", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "recurring_cancel_from", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "recurring_canceled_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "receipt_email", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "receipt_phone", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "payment_requests", "recurring_consent", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "payment_requests", "recurring_consent_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "payment_requests", "recurring_consent_text", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "payment_requests", "receipt_email", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "payment_requests", "receipt_phone", "TEXT NOT NULL DEFAULT ''")
            conn.commit()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, spec: str) -> None:
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        names = {row["name"] for row in info}
        if column not in names:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")

    def _today(self) -> str:
        return date.today().isoformat()

    def get_or_create_user(self, chat_id: int, default_model_alias: str) -> dict[str, Any]:
        now = datetime.utcnow().isoformat()
        today = self._today()

        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO users (
                        chat_id, plan, is_blocked, selected_model_alias, usage_date,
                        daily_messages_used, daily_images_used, created_at, updated_at
                    ) VALUES (?, 'free', 0, ?, ?, 0, 0, ?, ?)
                    """,
                    (chat_id, default_model_alias, today, now, now),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()

            if row["usage_date"] != today:
                conn.execute(
                    """
                    UPDATE users
                    SET usage_date = ?, daily_messages_used = 0, daily_images_used = 0, updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (today, now, chat_id),
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

    def set_receipt_contact(self, chat_id: int, email: str, phone: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET receipt_email = ?, receipt_phone = ?, updated_at = ? WHERE chat_id = ?",
                (email.strip(), phone.strip(), datetime.utcnow().isoformat(), chat_id),
            )
            conn.commit()

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
                        recurring_cancel_from = '', recurring_canceled_at = '', updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (plan, expires, datetime.utcnow().isoformat(), chat_id),
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
                    SET plan = ?, subscription_expires_at = ?, selected_model_alias = ?, updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (plan, expires_at, selected_model_alias, datetime.utcnow().isoformat(), chat_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE users
                    SET plan = ?, subscription_expires_at = ?, selected_model_alias = ?,
                        recurring_enabled = ?, recurring_cancel_from = '', recurring_canceled_at = '',
                        updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (
                        plan,
                        expires_at,
                        selected_model_alias,
                        1 if recurring_enabled else 0,
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


class BotState:
    def __init__(self) -> None:
        self.user_histories: dict[int, deque[dict[str, str]]] = {}
        self.pending_receipt_plan: dict[int, str] = {}
        self.processed_updates: deque[str] = deque()
        self.processed_lookup: set[str] = set()
        self.last_message_at: dict[int, datetime] = {}
        self.last_image_at: dict[int, datetime] = {}
        self.session: aiohttp.ClientSession | None = None
        self.polling_task: asyncio.Task[None] | None = None
        self.user_store = UserStore(DB_PATH)

    def history(self, chat_id: int) -> deque[dict[str, str]]:
        if chat_id not in self.user_histories:
            self.user_histories[chat_id] = deque(maxlen=HISTORY_LIMIT)
        return self.user_histories[chat_id]


state = BotState()


def require_env() -> None:
    missing = []
    if not MAX_TOKEN:
        missing.append("MAX_TOKEN")
    if not OPENROUTER_KEY:
        missing.append("OPENROUTER_KEY")
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")


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
        "Если не проходит оплата или что-то работает не так:\n"
        "1. Открой «Тарифы» и создай новую заявку.\n"
        "2. После оплаты подожди 1-2 минуты.\n"
        "3. Открой «Мой план» и проверь статус.\n\n"
        f"{SUPPORT_TEXT}\n"
        f"Ссылка: {support_url_value()}\n\n"
        "FAQ: страница «Помощь»"
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
    preferred = [DEFAULT_TEXT_MODEL.alias, "gpt", "deepseek"]
    for alias in preferred:
        info = TEXT_MODELS.get(alias)
        if info and plan_allowed(plan, info.min_plan):
            return alias
    for alias, info in TEXT_MODELS.items():
        if plan_allowed(plan, info.min_plan):
            return alias
    return DEFAULT_TEXT_MODEL.alias


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


def build_keyboard() -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {"type": "callback", "text": "GPT", "payload": "set_model:gpt"},
                        {"type": "callback", "text": "Gemini", "payload": "set_model:gemini"},
                        {"type": "callback", "text": "DeepSeek", "payload": "set_model:deepseek"},
                    ],
                    [
                        {"type": "callback", "text": "Тарифы", "payload": "action:tariffs"},
                        {"type": "callback", "text": "Мой план", "payload": "action:plan"},
                        {"type": "callback", "text": "Модели", "payload": "action:models"},
                    ],
                    [
                        {"type": "callback", "text": "Меню", "payload": "action:menu"},
                        {"type": "callback", "text": "Сброс", "payload": "action:clear"},
                        {"type": "callback", "text": "Помощь", "payload": "action:support"},
                    ],
                ]
            },
        }
    ]


def build_tariffs_keyboard() -> list[dict[str, Any]]:
    return build_tariffs_keyboard_pricing()


def build_tariffs_keyboard_v2() -> list[dict[str, Any]]:
    buy_row: list[dict[str, Any]] = [
        {"type": "callback", "text": "Купить Start", "payload": "buy:start"},
        {"type": "callback", "text": "Купить Pro", "payload": "buy:pro"},
    ]
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    buy_row,
                    [
                        {"type": "callback", "text": "Назад", "payload": "action:menu"},
                        {"type": "callback", "text": "Помощь", "payload": "action:support"},
                    ],
                ]
            },
        }
    ]


def build_payment_request_keyboard(request_id: int) -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {"type": "callback", "text": "Я оплатил", "payload": f"paid:{request_id}"},
                    ],
                    [
                        {"type": "callback", "text": "Назад к тарифам", "payload": "action:tariffs"},
                        {"type": "callback", "text": "Помощь", "payload": "action:support"},
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
                        {"type": "callback", "text": "Назад к тарифам", "payload": "action:tariffs"},
                    ],
                ]
            },
        }
    ]


def build_tariffs_keyboard_pricing() -> list[dict[str, Any]]:
    buy_row: list[dict[str, Any]] = [
        {"type": "callback", "text": f"Купить Start — {START_PLAN_PRICE_RUB}₽", "payload": "buy:start"},
        {"type": "callback", "text": f"Купить Pro — {PRO_PLAN_PRICE_RUB}₽", "payload": "buy:pro"},
    ]
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    buy_row,
                    [
                        {"type": "callback", "text": "Назад", "payload": "action:menu"},
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


def model_line(model: ModelInfo, include_prices: bool) -> str:
    lines = [
        f"{model.alias} — {model.label} ({model.provider})",
        f"версия: {model.version}, план: {model.min_plan}+",
        f"для чего: {model.description}",
    ]
    if include_prices:
        lines.append(f"цена: in ${model.input_price_usd_per_m}/M, out ${model.output_price_usd_per_m}/M")
    return "\n".join(lines)


def build_models_text(user_plan: str, include_prices: bool = False) -> str:
    lines = ["Текстовые модели:"]
    for model in TEXT_MODELS.values():
        prefix = "доступно" if plan_allowed(user_plan, model.min_plan) else f"нужно {model.min_plan}+"
        lines.append(f"\n[{prefix}]\n{model_line(model, include_prices)}")
    image_model = DEFAULT_IMAGE_MODEL
    image_prefix = "доступно" if plan_allowed(user_plan, image_model.min_plan) else f"нужно {image_model.min_plan}+"
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


def parse_callback_payload(update: dict[str, Any]) -> tuple[int | None, str | None, str | None]:
    chat_id, _ = parse_incoming_text(update)
    callback = update.get("callback") or {}
    callback_id = callback.get("callback_id")
    payload = callback.get("payload")
    if isinstance(payload, dict):
        payload = payload.get("value") or payload.get("payload") or payload.get("data")
    if not isinstance(callback_id, str):
        callback_id = None
    if not isinstance(payload, str):
        payload = None
    return chat_id, callback_id, payload


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


def plan_price_and_days(plan: str) -> tuple[int, int]:
    if plan == "start":
        return START_PLAN_PRICE_RUB, START_PLAN_DAYS
    if plan == "pro":
        return PRO_PLAN_PRICE_RUB, PRO_PLAN_DAYS
    return 0, 0


def build_tariffs_text() -> str:
    return (
        "Тарифы:\n"
        "• free: 40 сообщений/день, 0 картинок/день — бесплатно\n"
        f"• start: 400 сообщений/день, 12 картинок/день — {START_PLAN_PRICE_RUB} ₽ / {START_PLAN_DAYS} дней\n"
        f"• pro: 2500 сообщений/день, 80 картинок/день — {PRO_PLAN_PRICE_RUB} ₽ / {PRO_PLAN_DAYS} дней\n\n"
        "Для платных тарифов действует автопродление.\n"
        "Перед оплатой мы отдельно попросим согласие с суммой и периодичностью.\n"
        "Отменить автопродление можно в разделе «Мой план».\n\n"
        "Модели по тарифам:\n"
        "• free: DeepSeek V4 Flash, GPT-4.1 Mini\n"
        "• start: + Gemini 2.5 Flash\n"
        "• pro: + GPT-5.4"
    )


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
        row = state.user_store.get_or_create_user(chat_id, selected)
    return row


def usage_text(row: dict[str, Any]) -> str:
    plan_name = row["plan"]
    cfg = PLAN_CONFIGS[plan_name]
    msg_left = max(0, cfg.daily_messages_limit - row["daily_messages_used"])
    img_left = max(0, cfg.daily_images_limit - row["daily_images_used"])
    expires_raw = row.get("subscription_expires_at", "")
    expires_at = parse_iso_datetime(expires_raw)
    expires_text = "-"
    if plan_name != "free":
        expires_text = expires_at.strftime("%Y-%m-%d %H:%M UTC") if expires_at else "не задан"
    return (
        f"План: {plan_name}\n"
        f"Подписка до: {expires_text}\n"
        f"Сегодня сообщений: {row['daily_messages_used']}/{cfg.daily_messages_limit} (осталось {msg_left})\n"
        f"Сегодня картинок: {row['daily_images_used']}/{cfg.daily_images_limit} (осталось {img_left})"
    )


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


def can_use_model(plan: str, model_alias: str) -> tuple[bool, str]:
    info = TEXT_MODELS.get(model_alias)
    if not info:
        return False, "Неизвестная модель. Используй /models."
    if not plan_allowed(plan, info.min_plan):
        return False, f"Модель {info.label} доступна с тарифа {info.min_plan}."
    return True, ""


def check_and_consume_limit(chat_id: int, limit_type: str) -> tuple[bool, str]:
    row = user_profile(chat_id)
    if row["is_blocked"]:
        return False, "Доступ к боту временно ограничен. Напиши в поддержку."
    plan_name = row["plan"]
    cfg = PLAN_CONFIGS[plan_name]

    if limit_type == "messages":
        if row["daily_messages_used"] >= cfg.daily_messages_limit:
            return False, "Лимит сообщений на сегодня исчерпан. Открой «Тарифы»."
        state.user_store.increment_message_usage(chat_id)
        return True, ""

    if row["daily_images_used"] >= cfg.daily_images_limit:
        return False, "Лимит генераций картинок на сегодня исчерпан. Открой «Тарифы»."
    state.user_store.increment_image_usage(chat_id)
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
) -> None:
    session = await get_session()
    chunks = split_message(text)
    if not chunks and attachments:
        chunks = [""]

    for index, chunk in enumerate(chunks):
        payload: dict[str, Any] = {
            "text": chunk,
            "notify": notify,
        }
        if attachments and index == 0:
            payload["attachments"] = attachments

        async with session.post(
            f"{MAX_API}/messages",
            headers=max_headers(),
            params={"chat_id": str(chat_id)},
            json=payload,
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise RuntimeError(f"MAX send error {resp.status}: {body[:500]}")


async def answer_callback(callback_id: str, notification: str) -> None:
    session = await get_session()
    async with session.post(
        f"{MAX_API}/answers",
        headers=max_headers(),
        params={"callback_id": callback_id},
        json={"notification": notification},
    ) as resp:
        if resp.status >= 400:
            body = await resp.text()
            log.warning("Callback answer failed %s: %s", resp.status, body[:300])


async def get_upload_url(upload_type: str = "image") -> str:
    session = await get_session()
    async with session.post(
        f"{MAX_API}/uploads",
        headers=max_headers(),
        json={"type": upload_type},
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
    form.add_field("file", BytesIO(image_bytes), filename=f"generated.{ext}", content_type=mime_type)

    async with session.post(upload_url, data=form) as resp:
        body = await resp.json(content_type=None)
        if resp.status >= 400:
            raise RuntimeError(f"MAX file upload error {resp.status}: {body}")
        return body


async def send_generated_image(chat_id: int, prompt: str, image: ImageResult) -> None:
    attachment_payload = await upload_image_to_max(image.image_bytes, image.mime_type)
    attachment = {"type": "image", "payload": attachment_payload}
    await max_send_message(chat_id, f"Готово. Вот картинка по запросу:\n{prompt}", attachments=[attachment])


async def fetch_image_bytes(url: str) -> ImageResult:
    session = await get_session()
    async with session.get(url) as resp:
        data = await resp.read()
        if resp.status >= 400:
            raise RuntimeError(f"Image fetch error {resp.status}")
        mime_type = resp.headers.get("Content-Type", "image/png").split(";", 1)[0]
        return ImageResult(image_bytes=data, mime_type=mime_type)


async def ask_text_model(chat_id: int, user_text: str) -> str:
    session = await get_session()
    row = user_profile(chat_id)
    selected_alias = row["selected_model_alias"] or best_default_alias_for_plan(row["plan"])
    model_info = TEXT_MODELS.get(selected_alias, DEFAULT_TEXT_MODEL)
    history = list(state.history(chat_id))

    messages: list[dict[str, Any]] = [{"role": "system", "content": f"{SYSTEM_PROMPT_BASE} {STYLE_PROMPTS.get(selected_alias, '')}".strip()}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    payload = {"model": model_info.model, "messages": messages}
    async with session.post(OPENROUTER_CHAT_API, headers=openrouter_headers(), json=payload) as resp:
        data = await resp.json(content_type=None)
        if resp.status >= 400:
            message = data.get("error", {}).get("message", "Unknown OpenRouter error")
            raise RuntimeError(message)

    choice = data["choices"][0]["message"]
    answer = normalize_text_content(choice.get("content")) or "Не удалось получить текстовый ответ."
    state.history(chat_id).append({"role": "user", "content": user_text})
    state.history(chat_id).append({"role": "assistant", "content": answer})
    return answer


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


def current_model_label(chat_id: int) -> str:
    row = user_profile(chat_id)
    selected = row["selected_model_alias"] or best_default_alias_for_plan(row["plan"])
    model = TEXT_MODELS.get(selected, DEFAULT_TEXT_MODEL)
    return model.label


async def send_help(chat_id: int) -> None:
    help_base = HELP_TEXT
    if not is_admin(chat_id):
        help_base = "\n".join(line for line in HELP_TEXT.splitlines() if "/payments" not in line)
    admin_part = ADMIN_HELP_TEXT if is_admin(chat_id) else ""
    text = (
        f"Справка\n\n"
        f"{help_base}"
        f"{admin_part}"
    )
    await max_send_message(chat_id, text, attachments=build_keyboard())


async def send_menu(chat_id: int) -> None:
    capabilities = (
        "Что умею:\n"
        "• ответы через GPT, Gemini и DeepSeek\n"
        f"{image_capability_line()}\n"
        "• сохранение контекста диалога"
    )
    text = (
        "Привет. Это твой AI-бот в MAX.\n\n"
        f"{capabilities}\n\n"
        "Выбери действие кнопками или просто напиши вопрос.\n\n"
        f"Сейчас выбрана модель: {current_model_label(chat_id)}\n"
        f"{usage_text(user_profile(chat_id))}\n\n"
        f"{MENU_TEXT}"
    )
    await max_send_message(chat_id, text, attachments=build_keyboard())


async def send_models(chat_id: int) -> None:
    row = user_profile(chat_id)
    await max_send_message(chat_id, build_models_text(row["plan"], include_prices=False), attachments=build_keyboard())


async def send_costs(chat_id: int) -> None:
    row = user_profile(chat_id)
    await max_send_message(chat_id, build_models_text(row["plan"], include_prices=True), attachments=build_keyboard())


async def send_plan(chat_id: int) -> None:
    row = user_profile(chat_id)
    text = f"{usage_text(row)}{recurring_status_text(row)}"
    await max_send_message(chat_id, text, attachments=build_plan_keyboard(row))


async def send_payments(chat_id: int) -> None:
    rows = state.user_store.list_user_payments(chat_id, limit=8)
    if not rows:
        await max_send_message(chat_id, "Заявок пока нет. Используй кнопку «Тарифы».", attachments=build_keyboard())
        return
    lines = ["Твои последние заявки:"]
    for item in rows:
        lines.append(
            f"#{item['id']} | {item['plan']} | {item['days']} дн | {item['amount_rub']} RUB | {item['status']} | {item['created_at'][:19]}"
        )
    await max_send_message(chat_id, "\n".join(lines), attachments=build_keyboard())


def effective_receipt_contact(row: dict[str, Any]) -> tuple[str, str]:
    email = str(row.get("receipt_email", "")).strip() or TBANK_RECEIPT_EMAIL
    phone = str(row.get("receipt_phone", "")).strip() or TBANK_RECEIPT_PHONE
    return email, phone


async def request_receipt_contact(chat_id: int, plan: str, notify: bool = False) -> None:
    state.pending_receipt_plan[chat_id] = plan
    await max_send_message(
        chat_id,
        (
            "Перед оплатой нужен контакт для отправки чека.\n"
            "Отправь одним сообщением email или телефон.\n\n"
            "Пример email: user@example.com\n"
            "Пример телефона: +79991234567\n\n"
            "Чтобы отменить — отправь «отмена»."
        ),
        attachments=build_tariffs_keyboard_pricing(),
        notify=notify,
    )


async def start_buy_flow(chat_id: int, plan: str, notify: bool = False) -> bool:
    if plan not in {"start", "pro"}:
        await max_send_message(chat_id, "Доступно: start или pro.", attachments=build_tariffs_keyboard_pricing(), notify=notify)
        return False
    row = user_profile(chat_id)
    email, phone = effective_receipt_contact(row)
    if not (email or phone):
        await request_receipt_contact(chat_id, plan, notify=notify)
        return False
    return await send_buy_consent(chat_id, plan, notify=notify)


async def send_buy_consent(chat_id: int, plan: str, notify: bool = False) -> bool:
    if plan not in {"start", "pro"}:
        await max_send_message(chat_id, "Доступно: start или pro.", attachments=build_tariffs_keyboard_pricing(), notify=notify)
        return False

    amount, days = plan_price_and_days(plan)
    text = (
        "Перед оплатой нужно согласие на автопродление.\n\n"
        f"Тариф: {plan}\n"
        f"Сумма списания: {amount} ₽\n"
        f"Периодичность: каждые {days} дней\n\n"
        "Нажимая кнопку согласия ниже, ты подтверждаешь регулярные списания по этим условиям.\n"
        "После согласия откроется оплата.\n"
        "Отменить автопродление можно в «Мой план»."
    )
    await max_send_message(chat_id, text, attachments=build_consent_keyboard(plan), notify=notify)
    return True


async def create_buy_request(chat_id: int, plan: str) -> str:
    if plan not in {"start", "pro"}:
        return "Доступно: start или pro."
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
    text = (
        f"Пользователь подтвердил оплату по заявке #{request_id}.\n"
        f"user={target}, plan={plan}, amount={amount} RUB, days={days}\n"
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
    final_email = receipt_email.strip() or TBANK_RECEIPT_EMAIL
    final_phone = receipt_phone.strip() or TBANK_RECEIPT_PHONE
    if not (final_email or final_phone):
        raise RuntimeError(
            "T-Bank Receipt required: set TBANK_RECEIPT_EMAIL or TBANK_RECEIPT_PHONE in .env"
        )
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
    selected = best_default_alias_for_plan(plan)
    user_profile(target)
    state.user_store.set_payment_status(request_id, "paid")
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
    current_status = str(payment.get("status", "")).lower()
    if current_status != "refunded":
        state.user_store.set_payment_status(request_id, "refunded")

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
    if plan not in {"start", "pro"}:
        return None, "Доступно: start или pro."
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
            text = (
                f"Заявка #{request_id} создана: {plan}, {days} дн, {amount} RUB.\n\n"
                "Оплати по ссылке Т-Банка:\n"
                f"{payment_url}\n\n"
                f"Назначение платежа: {payment_purpose}\n"
                "После успешной оплаты тариф активируется автоматически."
            )
            return request_id, text
        except Exception as exc:
            log.exception("T-Bank Init failed for request %s", request_id)
            text = (
                f"Заявка #{request_id} создана: {plan}, {days} дн, {amount} RUB.\n"
                f"Автооплата сейчас недоступна ({exc}).\n\n"
                "Используй ручную оплату ниже."
            )
            return request_id, text
    text = (
        f"Заявка #{request_id} создана: {plan}, {days} дн, {amount} RUB.\n\n"
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
            "/admin plan <chat_id> <free|start|pro>\n"
            "/admin sub <chat_id> <start|pro> <days>\n"
            "/admin block <chat_id> <on|off>\n"
            "/admin pay <request_id> <paid|cancel>",
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
            await max_send_message(chat_id, "Используй: /admin plan <chat_id> <free|start|pro>")
            return True
        user_profile(target)
        state.user_store.set_plan(target, new_plan)
        selected = best_default_alias_for_plan(new_plan)
        state.user_store.set_selected_model(target, selected)
        await max_send_message(chat_id, f"План пользователя {target} -> {new_plan}. Модель -> {selected}.")
        return True

    if action == "sub" and len(parts) >= 5:
        target = parse_admin_target(parts[2])
        plan = parts[3].lower()
        days_raw = parts[4]
        if target is None or plan not in {"start", "pro"} or not days_raw.isdigit():
            await max_send_message(chat_id, "Используй: /admin sub <chat_id> <start|pro> <days>")
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

        target = int(payment["chat_id"])
        plan = str(payment["plan"])
        days = int(payment["days"])
        provider_ref = str(payment.get("provider_ref", ""))
        selected = best_default_alias_for_plan(plan)
        user_profile(target)
        state.user_store.set_payment_status(req_id, "paid")
        expires_at = state.user_store.set_subscription(
            target,
            plan,
            days,
            selected,
            recurring_enabled=provider_ref.startswith("tbank:"),
        )
        state.user_store.mark_payment_activated(req_id)
        await max_send_message(chat_id, f"Оплата #{req_id} подтверждена. user={target} plan={plan} until={expires_at}")
        with suppress(Exception):
            await max_send_message(
                target,
                f"Оплата подтверждена. Тариф {plan} активирован до {expires_at[:16]} UTC.",
                attachments=build_keyboard(),
            )
        return True

    await max_send_message(chat_id, "Неизвестная админ-команда. Используй /admin help")
    return True


async def handle_callback(update: dict[str, Any]) -> bool:
    chat_id, callback_id, payload = parse_callback_payload(update)
    if chat_id is None or not payload:
        return False

    if payload.startswith("set_model:"):
        alias = payload.split(":", 1)[1]
        try:
            label = await set_user_model(chat_id, alias)
            if callback_id:
                await answer_callback(callback_id, f"Модель: {label}")
            await max_send_message(chat_id, f"Выбрана модель: {label}", attachments=build_keyboard(), notify=False)
        except Exception as exc:
            if callback_id:
                await answer_callback(callback_id, str(exc)[:120])
            await max_send_message(chat_id, f"Ошибка: {exc}", attachments=build_keyboard(), notify=False)
        return True

    if payload == "action:clear":
        state.history(chat_id).clear()
        if callback_id:
            await answer_callback(callback_id, "Контекст очищен")
        await max_send_message(chat_id, "Контекст диалога очищен.", attachments=build_keyboard(), notify=False)
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

    if payload == "action:menu":
        if callback_id:
            await answer_callback(callback_id, "Открываю меню")
        await send_menu(chat_id)
        return True

    if payload == "action:support":
        if callback_id:
            await answer_callback(callback_id, "Открываю помощь")
        await max_send_message(chat_id, support_help_text(), attachments=build_keyboard(), notify=False)
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
        if plan not in {"start", "pro"}:
            if callback_id:
                await answer_callback(callback_id, "Неверный тариф")
            return True
        if callback_id:
            await answer_callback(callback_id, "Согласие получено")
        terms = recurring_terms_for_plan(plan)
        request_id, msg = await create_buy_request_v2(chat_id, plan, consent_text=terms)
        if request_id is None:
            await max_send_message(chat_id, msg, attachments=build_tariffs_keyboard_pricing(), notify=False)
            return True
        await max_send_message(chat_id, msg, attachments=build_payment_request_keyboard(request_id), notify=False)
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

        if plan not in {"start", "pro"}:
            if callback_id:
                await answer_callback(callback_id, "Неверный тариф")
            await max_send_message(chat_id, "Доступно: Start или Pro.", attachments=build_tariffs_keyboard_pricing(), notify=False)
            return True
        if callback_id:
            await answer_callback(callback_id, "Проверь условия")
        ok = await start_buy_flow(chat_id, plan, notify=False)
        if not ok:
            return True
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
        status = str(payment["status"])
        provider_ref = str(payment.get("provider_ref", ""))
        if provider_ref.startswith("tbank:") and status == "pending":
            if callback_id:
                await answer_callback(callback_id, "ожидаем банк")
            await max_send_message(
                chat_id,
                "Платеж проверяется автоматически через Т-Банк. Обычно это занимает до 1-2 минут.",
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

    if lowered in {"gpt", "gemini", "deepseek", "gpt54"}:
        command = "/model"
        arg = lowered
    elif command in {"/gpt", "/gemini", "/deepseek", "/gpt54"}:
        command = "/model"
        arg = command[1:]

    if command in {"/start", "/menu"}:
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

    if command == "/tariffs":
        await max_send_message(chat_id, build_tariffs_text(), attachments=build_tariffs_keyboard_pricing())
        return True

    if command == "/plan":
        await send_plan(chat_id)
        return True

    if command == "/support":
        await max_send_message(chat_id, support_help_text(), attachments=build_keyboard())
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
        if plan not in {"start", "pro"}:
            await max_send_message(chat_id, "Доступно: Start или Pro.", attachments=build_tariffs_keyboard_pricing())
            return True
        ok = await start_buy_flow(chat_id, plan)
        if not ok:
            return True
        return True

    if command == "/payments":
        if not is_admin(chat_id):
            await max_send_message(chat_id, "Для пользователей команда скрыта. Используй кнопки в разделе «Тарифы».", attachments=build_tariffs_keyboard_pricing())
            return True
        await send_payments(chat_id)
        return True

    if command == "/model":
        if not arg:
            await max_send_message(chat_id, "Укажи модель: /model deepseek|gpt|gemini|gpt54", attachments=build_keyboard())
            return True
        label = await set_user_model(chat_id, arg)
        await max_send_message(chat_id, f"Выбрана модель: {label}", attachments=build_keyboard())
        return True

    if command in {"/clear", "/reset"}:
        state.history(chat_id).clear()
        await max_send_message(chat_id, "Контекст диалога очищен.", attachments=build_keyboard())
        return True

    if command == "/image":
        if not arg:
            await max_send_message(chat_id, "Пример: /image неоновый город под дождем", attachments=build_keyboard())
            return True
        if len(arg) > MAX_IMAGE_PROMPT_CHARS:
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
        if not plan_allowed(row["plan"], DEFAULT_IMAGE_MODEL.min_plan):
            await max_send_message(
                chat_id,
                f"Картинки доступны с тарифа {DEFAULT_IMAGE_MODEL.min_plan}. Открой «Тарифы».",
                attachments=build_keyboard(),
            )
            return True

        ok, reason = check_and_consume_limit(chat_id, "images")
        if not ok:
            await max_send_message(chat_id, reason, attachments=build_keyboard())
            return True

        await max_send_message(chat_id, "Генерирую картинку, это может занять немного времени...")
        image = await generate_image(arg)
        await send_generated_image(chat_id, arg, image)
        return True

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
        await max_send_message(chat_id, "Покупка отменена. Можно снова выбрать тариф.", attachments=build_tariffs_keyboard_pricing())
        return True

    email, phone = parse_receipt_contact(text)
    if not (email or phone):
        await max_send_message(
            chat_id,
            "Не удалось распознать контакт. Отправь email (user@example.com) или телефон (+79991234567).",
            attachments=build_tariffs_keyboard_pricing(),
        )
        return True

    user_profile(chat_id)
    state.user_store.set_receipt_contact(chat_id, email=email, phone=phone)
    state.pending_receipt_plan.pop(chat_id, None)
    label = email or phone
    await max_send_message(chat_id, f"Контакт для чека сохранен: {label}")
    await send_buy_consent(chat_id, plan)
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
    if chat_id is None:
        return

    row = user_profile(chat_id)
    if row["is_blocked"]:
        return

    if update_type in {"bot_started", "user_added", "bot_added"} and not text:
        await send_menu(chat_id)
        return
    if not text:
        return

    log.info("Incoming update=%s chat_id=%s text=%r", update_type, chat_id, text[:120])
    try:
        if await handle_pending_receipt_input(chat_id, text):
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

        ok, reason = check_and_consume_limit(chat_id, "messages")
        if not ok:
            await max_send_message(chat_id, reason, attachments=build_keyboard())
            return

        await max_send_message(chat_id, f"Думаю... Модель: {current_model_label(chat_id)}", notify=False)
        answer = await ask_text_model(chat_id, text)
        await max_send_message(chat_id, answer)
    except Exception as exc:
        log.exception("Failed to process update")
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
        except Exception:
            log.exception("Polling loop error")
            await asyncio.sleep(3)


@asynccontextmanager
async def lifespan(_: FastAPI):
    require_env()
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
    return {"url": support_url_value(), "text": SUPPORT_TEXT}


@app.get("/mailru-domainMB5PESlCeJQEXuoC.html", response_class=FileResponse)
async def mailru_domain_verify() -> FileResponse:
    return FileResponse(site_file("mailru-domainMB5PESlCeJQEXuoC.html"))


def payment_status_view(request_id: int | None) -> dict[str, Any]:
    if request_id is None:
        return {
            "known": False,
            "status": "unknown",
            "title": "Заявка не найдена",
            "message": "Не удалось определить номер заявки. Вернись в бот и нажми «Тарифы».",
        }

    payment = state.user_store.get_payment(request_id)
    if not payment:
        return {
            "known": False,
            "request_id": request_id,
            "status": "unknown",
            "title": "Заявка не найдена",
            "message": "Такой заявки нет. Создай новую оплату в боте.",
        }

    status = str(payment.get("status", "pending")).lower()
    titles = {
        "pending": "Платеж создан",
        "claimed": "Проверяем оплату",
        "paid": "Оплата подтверждена",
        "canceled": "Оплата отменена",
        "refunded": "Оформлен возврат",
    }
    messages = {
        "pending": "Платеж в обработке. Обычно подтверждение приходит в течение 1-2 минут.",
        "claimed": "Банк прислал сигнал, подтверждаем оплату. Обычно это занимает до 1-2 минут.",
        "paid": "Подписка уже активирована. Можно возвращаться в бот.",
        "canceled": "Оплата не была завершена. Вернись в бот и попробуй еще раз.",
        "refunded": "Возврат подтвержден. Подписка отключена, действует тариф free.",
    }
    return {
        "known": True,
        "request_id": request_id,
        "status": status,
        "title": titles.get(status, "Статус обновляется"),
        "message": messages.get(status, "Подожди немного и обнови страницу."),
        "plan": str(payment.get("plan", "")),
        "amount_rub": int(payment.get("amount_rub", 0)),
    }


@app.get("/payment/status")
async def payment_status(request_id: int | None = None) -> dict[str, Any]:
    view = payment_status_view(request_id)
    if request_id is None or not view.get("known"):
        return view

    if view["status"] not in {"pending", "claimed", "paid"}:
        return view

    payment = state.user_store.get_payment(request_id)
    if not payment:
        return payment_status_view(request_id)

    payment_id = tbank_payment_id_from_provider_ref(str(payment.get("provider_ref", "")))
    if not payment_id or not tbank_enabled():
        return view

    try:
        state_payload = await tbank_get_state(payment_id)
        bank_status = scalar_string(state_payload.get("Status")).upper()
        bank_success_raw = state_payload.get("Success")
        bank_success = bank_success_raw is True or scalar_string(bank_success_raw).lower() == "true"

        if bank_success and bank_status == "CONFIRMED":
            await activate_payment_request(request_id, source="T-Bank GetState")
        elif tbank_is_refund_status(bank_status):
            await process_refund_payment_request(request_id, source="T-Bank GetState", bank_status=bank_status)
        elif tbank_is_cancel_status(bank_status):
            state.user_store.set_payment_status(request_id, "canceled")

        refreshed = payment_status_view(request_id)
        refreshed["bank_status"] = bank_status.lower() if bank_status else ""
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
        except Exception:
            log.exception("Unhandled webhook processing error")
    return {"ok": True}


@app.post("/webhook/tbank")
async def tbank_webhook(request: Request) -> PlainTextResponse:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")

    if not tbank_notification_is_valid(payload):
        log.warning("Invalid T-Bank webhook signature or terminal")
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
        state.user_store.set_payment_status(request_id, "canceled")
        log.info("T-Bank payment canceled request_id=%s status=%s", request_id, status)

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
