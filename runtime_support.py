from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import suppress
from typing import Any, Callable
import json
import os
import shutil
import sqlite3


@dataclass(slots=True)
class RuntimeSupportDeps:
    data_dir: Path
    db_path: Path
    backup_keep_files: int
    max_token: str
    openrouter_key: str
    run_mode: str
    auto_backup_enabled: bool
    service_monitor_enabled: bool
    config_path: Path
    site_index_path: Path
    tbank_terminal_key: str
    tbank_password: str
    channel_gate_enabled: bool
    channel_chat_id: str
    channel_membership_cache_hours: int
    alert_high_errors_window_minutes: int
    alert_low_payments_lookback_hours: int
    alert_spend_spike_lookback_hours: int
    channel_url_resolver: Callable[[], str]
    system_snapshot_provider: Callable[[], dict[str, Any]]


def backups_dir(data_dir: Path) -> Path:
    path = data_dir / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def latest_backup_file(data_dir: Path) -> Path | None:
    files = sorted(backups_dir(data_dir).glob("bot-*"))
    return files[-1] if files else None


def create_db_backup(
    *,
    data_dir: Path,
    db_path: Path,
    backup_keep_files: int,
    user_store: Any,
) -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    target = backups_dir(data_dir) / f"bot-{stamp}{user_store.backend.backup_suffix()}"
    if user_store.backend.kind == "postgres":
        snapshot = user_store.export_logical_backup()
        target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        with sqlite3.connect(db_path) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
    files = sorted(backups_dir(data_dir).glob("bot-*"))
    keep = max(3, backup_keep_files)
    if len(files) > keep:
        for old in files[: len(files) - keep]:
            with suppress(Exception):
                old.unlink()
    return target


def format_timedelta_short(delta: timedelta) -> str:
    total_seconds = max(0, int(delta.total_seconds()))
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def system_resource_snapshot(data_dir: Path) -> dict[str, Any]:
    cpu_count = max(1, int(os.cpu_count() or 1))
    load1 = 0.0
    try:
        load1 = float(os.getloadavg()[0])
    except Exception:
        load1 = 0.0
    cpu_per_core = load1 / cpu_count if cpu_count > 0 else load1

    mem_total_kb = 0
    mem_available_kb = 0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    mem_total_kb = int(parts[1]) if len(parts) > 1 else 0
                elif line.startswith("MemAvailable:"):
                    parts = line.split()
                    mem_available_kb = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        mem_total_kb = 0
        mem_available_kb = 0
    mem_used_pct = 0.0
    if mem_total_kb > 0:
        mem_used_pct = max(0.0, min(100.0, (1.0 - (mem_available_kb / mem_total_kb)) * 100.0))

    disk_total = 0
    disk_used = 0
    disk_used_pct = 0.0
    try:
        usage = shutil.disk_usage(str(data_dir))
        disk_total = int(usage.total)
        disk_used = int(usage.used)
        disk_used_pct = (disk_used * 100.0 / disk_total) if disk_total > 0 else 0.0
    except Exception:
        disk_total = 0
        disk_used = 0
        disk_used_pct = 0.0

    return {
        "cpu_count": cpu_count,
        "cpu_load_1m": round(load1, 3),
        "cpu_load_1m_per_core": round(cpu_per_core, 3),
        "memory_total_kb": mem_total_kb,
        "memory_available_kb": mem_available_kb,
        "memory_used_pct": round(mem_used_pct, 2),
        "disk_total_bytes": disk_total,
        "disk_used_bytes": disk_used,
        "disk_used_pct": round(disk_used_pct, 2),
    }


def smoke_check_report(
    *,
    deps: RuntimeSupportDeps,
    user_store: Any,
    state: Any,
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    def add_check(name: str, ok: bool, details: str) -> None:
        checks.append({"name": name, "ok": "ok" if ok else "fail", "details": details})

    add_check("MAX token", bool(deps.max_token), "Настроен" if deps.max_token else "Пустой MAX_TOKEN")
    add_check("OpenRouter key", bool(deps.openrouter_key), "Настроен" if deps.openrouter_key else "Пустой OPENROUTER_KEY")
    db_backend = user_store.backend
    add_check("DB backend", db_backend.exists(), f"{db_backend.kind}: {db_backend.label} ({db_backend.size_bytes()} bytes)")
    add_check(
        "HTTP session",
        state.session is not None and not state.session.closed,
        "aiohttp session ready" if state.session and not state.session.closed else "session closed",
    )
    add_check(
        "Polling task",
        deps.run_mode != "polling" or (state.polling_task is not None and not state.polling_task.done()),
        "active" if deps.run_mode != "polling" or (state.polling_task and not state.polling_task.done()) else "not running",
    )
    add_check(
        "Backup task",
        (not deps.auto_backup_enabled) or (state.backup_task is not None and not state.backup_task.done()),
        "active" if deps.auto_backup_enabled and state.backup_task and not state.backup_task.done() else ("disabled" if not deps.auto_backup_enabled else "not running"),
    )
    add_check(
        "Monitor task",
        (not deps.service_monitor_enabled) or (state.monitor_task is not None and not state.monitor_task.done()),
        "active" if deps.service_monitor_enabled and state.monitor_task and not state.monitor_task.done() else ("disabled" if not deps.service_monitor_enabled else "not running"),
    )
    add_check("Models config", deps.config_path.exists(), str(deps.config_path))
    add_check("Site index", deps.site_index_path.exists(), str(deps.site_index_path))
    add_check(
        "T-Bank",
        bool(deps.tbank_terminal_key and deps.tbank_password),
        "Терминал и пароль настроены" if deps.tbank_terminal_key and deps.tbank_password else "Проверь TBANK_TERMINAL_KEY / TBANK_PASSWORD",
    )
    channel_source = "manual" if deps.channel_chat_id else "auto"
    channel_configured = deps.channel_chat_id if deps.channel_chat_id else deps.channel_url_resolver()
    add_check(
        "Channel gate",
        (not deps.channel_gate_enabled) or bool(deps.max_token and channel_configured),
        f"Включен, source={channel_source}, configured={channel_configured}" if deps.channel_gate_enabled and channel_configured else ("Выключен" if not deps.channel_gate_enabled else "Нет CHANNEL_CHAT_ID / CHANNEL_URL"),
    )
    return checks


def service_status_report(
    *,
    deps: RuntimeSupportDeps,
    user_store: Any,
    state: Any,
) -> dict[str, Any]:
    now = datetime.utcnow()
    db_backend = user_store.backend
    db_exists = db_backend.exists()
    db_size = db_backend.size_bytes()
    backup_file = latest_backup_file(deps.data_dir)
    backup_mtime = datetime.utcfromtimestamp(backup_file.stat().st_mtime) if backup_file and backup_file.exists() else None
    error_cutoff = now - timedelta(minutes=max(1, deps.alert_high_errors_window_minutes))
    recent_errors = sum(1 for ts in state.runtime_error_events if ts >= error_cutoff)
    monitor = user_store.service_monitor_report(
        payments_hours=deps.alert_low_payments_lookback_hours,
        spend_hours=deps.alert_spend_spike_lookback_hours,
        baseline_hours=max(24, deps.alert_spend_spike_lookback_hours * 24),
    )
    return {
        "generated_at": now.isoformat(),
        "run_mode": deps.run_mode,
        "uptime": format_timedelta_short(now - state.started_at),
        "db_exists": db_exists,
        "db_backend": db_backend.kind,
        "db_path": db_backend.label,
        "db_size_bytes": db_size,
        "session_ready": bool(state.session and not state.session.closed),
        "polling_task": bool(state.polling_task and not state.polling_task.done()),
        "backup_task": bool(state.backup_task and not state.backup_task.done()),
        "monitor_task": bool(state.monitor_task and not state.monitor_task.done()),
        "latest_backup_path": str(backup_file) if backup_file else "",
        "latest_backup_at": backup_mtime.isoformat() if backup_mtime else "",
        "latest_backup_age_hours": round((now - backup_mtime).total_seconds() / 3600.0, 2) if backup_mtime else None,
        "recent_runtime_errors": recent_errors,
        "system": deps.system_snapshot_provider(),
        "channel_gate": {
            "enabled": deps.channel_gate_enabled,
            "configured_channel": deps.channel_chat_id if deps.channel_chat_id else deps.channel_url_resolver(),
            "resolved_channel_chat_id": state.channel_chat_id_cache,
            "cache_hours": deps.channel_membership_cache_hours,
        },
        "monitor": monitor,
        "smoke_checks": smoke_check_report(deps=deps, user_store=user_store, state=state),
    }
