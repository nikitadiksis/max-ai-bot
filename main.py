from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager, suppress
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
from io import BytesIO
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sqlite3
from typing import Any

import aiohttp
from dotenv import load_dotenv
from fastapi import FastAPI, Request
import uvicorn

load_dotenv()


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "models.json"
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
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

HELP_TEXT = (
    "Команды:\n"
    "/start или /menu — меню\n"
    "/models — версии моделей и цены\n"
    "/plan — твой тариф и остатки\n"
    "/model <alias> — выбрать модель\n"
    "/gpt, /gemini, /deepseek, /gpt54 — быстрый выбор\n"
    "/image <описание> — сгенерировать картинку\n"
    "/tariffs — тарифы\n"
    "/clear — очистить контекст"
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
                    selected_model_alias TEXT NOT NULL DEFAULT '',
                    usage_date TEXT NOT NULL DEFAULT '',
                    daily_messages_used INTEGER NOT NULL DEFAULT 0,
                    daily_images_used INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.commit()

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

    def set_plan(self, chat_id: int, plan: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET plan = ?, updated_at = ? WHERE chat_id = ?",
                (plan, datetime.utcnow().isoformat(), chat_id),
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
        self.processed_updates: deque[str] = deque(maxlen=DEDUP_CACHE_SIZE)
        self.processed_lookup: set[str] = set()
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


def plan_allowed(plan: str, min_plan: str) -> bool:
    return PLAN_ORDER.get(plan, 0) >= PLAN_ORDER.get(min_plan, 0)


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
                        {"type": "callback", "text": "Очистить", "payload": "action:clear"},
                    ],
                ]
            },
        }
    ]


def model_line(model: ModelInfo) -> str:
    return (
        f"{model.alias} — {model.label} ({model.provider})\n"
        f"версия: {model.version}, план: {model.min_plan}+\n"
        f"цена: in ${model.input_price_usd_per_m}/M, out ${model.output_price_usd_per_m}/M\n"
        f"для чего: {model.description}"
    )


def build_models_text(user_plan: str) -> str:
    lines = ["Текстовые модели:"]
    for model in TEXT_MODELS.values():
        prefix = "доступно" if plan_allowed(user_plan, model.min_plan) else f"нужно {model.min_plan}+"
        lines.append(f"\n[{prefix}]\n{model_line(model)}")
    image_model = DEFAULT_IMAGE_MODEL
    image_prefix = "доступно" if plan_allowed(user_plan, image_model.min_plan) else f"нужно {image_model.min_plan}+"
    lines.append("\nКартинки:")
    lines.append(f"\n[{image_prefix}]\n{model_line(image_model)}")
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


async def get_session() -> aiohttp.ClientSession:
    if state.session is None or state.session.closed:
        timeout = aiohttp.ClientTimeout(total=180)
        state.session = aiohttp.ClientSession(timeout=timeout)
    return state.session


def user_profile(chat_id: int) -> dict[str, Any]:
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
    return (
        f"План: {plan_name}\n"
        f"Сегодня сообщений: {row['daily_messages_used']}/{cfg.daily_messages_limit} (осталось {msg_left})\n"
        f"Сегодня картинок: {row['daily_images_used']}/{cfg.daily_images_limit} (осталось {img_left})"
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
            return False, "Лимит сообщений на сегодня исчерпан. Проверь /tariffs."
        state.user_store.increment_message_usage(chat_id)
        return True, ""

    if row["daily_images_used"] >= cfg.daily_images_limit:
        return False, "Лимит генераций картинок на сегодня исчерпан. Проверь /tariffs."
    state.user_store.increment_image_usage(chat_id)
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
    text = (
        f"{WELCOME_TEXT}\n\n"
        f"Сейчас выбрана модель: {current_model_label(chat_id)}\n"
        f"{usage_text(user_profile(chat_id))}\n\n"
        f"{HELP_TEXT}"
    )
    await max_send_message(chat_id, text, attachments=build_keyboard())


async def send_models(chat_id: int) -> None:
    row = user_profile(chat_id)
    await max_send_message(chat_id, build_models_text(row["plan"]), attachments=build_keyboard())


async def send_plan(chat_id: int) -> None:
    row = user_profile(chat_id)
    await max_send_message(chat_id, usage_text(row), attachments=build_keyboard())


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
            "/admin block <chat_id> <on|off>",
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
        await max_send_message(chat_id, TARIFFS_TEXT, attachments=build_keyboard(), notify=False)
        return True

    if payload == "action:menu":
        if callback_id:
            await answer_callback(callback_id, "Открываю меню")
        await send_help(chat_id)
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

    if command in {"/start", "/menu", "/help"}:
        await send_help(chat_id)
        return True

    if command == "/models":
        await send_models(chat_id)
        return True

    if command == "/tariffs":
        await max_send_message(chat_id, TARIFFS_TEXT, attachments=build_keyboard())
        return True

    if command == "/plan":
        await send_plan(chat_id)
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

        row = user_profile(chat_id)
        if not plan_allowed(row["plan"], DEFAULT_IMAGE_MODEL.min_plan):
            await max_send_message(
                chat_id,
                f"Картинки доступны с тарифа {DEFAULT_IMAGE_MODEL.min_plan}. Открой /tariffs.",
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
        await send_help(chat_id)
        return
    if not text:
        return

    log.info("Incoming update=%s chat_id=%s text=%r", update_type, chat_id, text[:120])
    try:
        if await handle_command(chat_id, text):
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "run_mode": RUN_MODE}


@app.post("/webhook/max")
async def max_webhook(request: Request) -> dict[str, bool]:
    if WEBHOOK_SECRET:
        header_secret = request.headers.get("X-Max-Bot-Api-Secret", "")
        if header_secret != WEBHOOK_SECRET:
            log.warning("Webhook secret mismatch")
            return {"ok": False}

    payload = await request.json()
    updates = payload if isinstance(payload, list) else [payload]
    for update in updates:
        try:
            await process_update(update)
        except Exception:
            log.exception("Unhandled webhook processing error")
    return {"ok": True}


def run() -> None:
    if RUN_MODE == "webhook":
        require_env()
        uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
        return
    require_env()
    asyncio.run(polling_loop())


if __name__ == "__main__":
    run()
