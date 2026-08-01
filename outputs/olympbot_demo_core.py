from __future__ import annotations

import json
import logging
import math
import os
import re
import signal
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    from flask import Flask, jsonify, request
    from playwright.sync_api import sync_playwright
except ImportError as exc:
    raise SystemExit(
        "Asılılıqlar tapılmadı. Bu əmrləri işlədin:\n"
        "  python -m pip install -r requirements.txt\n"
        "  python -m playwright install chromium"
    ) from exc


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, str(default)))


BOT_DIR = Path(os.environ.get("BOT_DIR", Path.home() / "Desktop" / "Olymptrade"))
PANEL_HOST = os.environ.get("PANEL_HOST", "127.0.0.1")
PANEL_PORT = int(os.environ.get("PANEL_PORT", "5000"))
USER_DATA_DIR = Path(os.environ.get("USER_DATA_DIR", BOT_DIR / "olymp_user_data"))
DEMO_DATA_DIR = Path(os.environ.get("DEMO_DATA_DIR", BOT_DIR / "demo_data"))
LOG_DIR = Path(os.environ.get("LOG_DIR", DEMO_DATA_DIR / "logs"))
DB_PATH = Path(os.environ.get("DEMO_DB_PATH", DEMO_DATA_DIR / "olympbot_demo.sqlite3"))

# Təhlükəsizlik: real hesab heç vaxt qəbul edilmir. Platforma icrası yalnız
# ekranda seçilmiş hesabın OlympTrade Deneme/Demo hesabı olduğu təsdiqlənəndə işləyir.
LIVE_TRADING = False
START_BALANCE = _env_float("DEMO_START_BALANCE", 10_000.0)
START_AMOUNT = _env_float("START_AMOUNT", 1.0)
PAYOUT_RATE = _env_float("DEMO_PAYOUT_RATE", 0.90)
TRADE_DURATION_SEC = int(os.environ.get("TRADE_DURATION_SEC", "60"))
COOLDOWN_SEC = int(os.environ.get("COOLDOWN_SEC", "60"))
MARTINGALE_ENABLED = False
DEMO_RISK_LIMITS_ENABLED = _env_bool("DEMO_RISK_LIMITS_ENABLED", False)
MAX_DAILY_LOSS = max(1.0, _env_float("MAX_DAILY_LOSS", 5.0))
MAX_DAILY_TRADES = max(1, int(os.environ.get("MAX_DAILY_TRADES", "5")))
MAX_CONSECUTIVE_LOSSES = max(
    1, int(os.environ.get("MAX_CONSECUTIVE_LOSSES", "3"))
)
MAX_STAKE_PERCENT = min(
    100.0, max(0.1, _env_float("MAX_STAKE_PERCENT", 1.0))
)
# Demo avtomatik icrası başlanğıcdan hazırdır. Faktiki klik yenə də yalnız
# OlympTrade hesabı hər əmrdən əvvəl Deneme/Demo kimi təsdiqlənəndə edilir.
PLATFORM_DEMO_DEFAULT = _env_bool("PLATFORM_DEMO_EXECUTION", True)

CANDLE_INTERVAL_SEC = int(os.environ.get("CANDLE_INTERVAL_SEC", "60"))
MAX_CANDLES = int(os.environ.get("MAX_CANDLES", "1000"))
MAX_TICKS = int(os.environ.get("MAX_TICKS", "300"))
RSI_PERIOD = int(os.environ.get("RSI_PERIOD", "9"))
EMA_FAST = int(os.environ.get("EMA_FAST", "3"))
EMA_SLOW = int(os.environ.get("EMA_SLOW", "8"))
TREND_EMA_FAST = int(os.environ.get("TREND_EMA_FAST", "15"))
TREND_EMA_SLOW = int(os.environ.get("TREND_EMA_SLOW", "50"))
ENTRY_RSI_MIN = _env_float("ENTRY_RSI_MIN", 54.0)
ENTRY_RSI_MAX = _env_float("ENTRY_RSI_MAX", 72.0)
MIN_CANDLE_BODY = _env_float("MIN_CANDLE_BODY", 0.25)
RSI_OVERSOLD = _env_float("RSI_OVERSOLD", 35.0)
RSI_OVERBOUGHT = _env_float("RSI_OVERBOUGHT", 65.0)
RSI_MIDLINE = _env_float("RSI_MIDLINE", 50.0)
SIGNAL_COOLDOWN_CANDLES = max(
    1, int(os.environ.get("SIGNAL_COOLDOWN_CANDLES", "8"))
)
SIGNAL_SCORE_THRESHOLD = min(
    95, max(60, int(os.environ.get("SIGNAL_SCORE_THRESHOLD", "75")))
)
DEMO_LEARNING_MODE = _env_bool("DEMO_LEARNING_MODE", True)
DEMO_LEARNING_MIN_SCORE = min(
    100,
    max(
        SIGNAL_SCORE_THRESHOLD,
        int(os.environ.get("DEMO_LEARNING_MIN_SCORE", "90")),
    ),
)
SCAN_ROTATION_ENABLED = _env_bool("SCAN_ROTATION_ENABLED", True)
SCAN_ROTATION_SEC = max(
    10, int(os.environ.get("SCAN_ROTATION_SEC", "15"))
)
AI_CONFIRMATION_ENABLED = _env_bool(
    "AI_CONFIRMATION_ENABLED",
    bool(os.environ.get("OPENAI_API_KEY")),
)
AI_DEMO_FALLBACK_ENABLED = _env_bool("AI_DEMO_FALLBACK_ENABLED", True)
AI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6").strip() or "gpt-5.6"
AI_MIN_CONFIDENCE = _env_float("AI_MIN_CONFIDENCE", 0.65)
AI_TIMEOUT_SEC = _env_float("AI_TIMEOUT_SEC", 20.0)

# Gold qəsdən daxil edilməyib. Hər sətirdə birinci tapılan və kifayət qədər
# şamı olan kod həmin aktivin analiz axını kimi istifadə edilir.
WATCH_ASSETS = (
    {
        "name": "BNB OTC",
        "pairs": ("BNBUSD_OTC", "BNBUSD"),
    },
    {
        "name": "EUR/USD",
        "pairs": ("EURUSD_OTC", "EURUSD"),
    },
    {
        "name": "Bitcoin",
        "pairs": ("BTCUSD_OTC", "BTCUSD"),
    },
    {
        "name": "Ethereum",
        "pairs": ("ETHUSD_OTC", "ETHUSD"),
    },
    {
        "name": "AUD/CAD",
        "pairs": ("AUDCAD_OTC", "AUDCAD"),
    },
)
WATCH_PAIR_LABELS = {
    "BNBUSD_OTC": ("BNB OTC",),
    "BNBUSD": ("BNB", "BNB/USD"),
    "EURUSD_OTC": ("EUR/USD OTC", "EURUSD OTC"),
    "EURUSD": ("EUR/USD", "EURUSD"),
    "BTCUSD_OTC": ("Bitcoin OTC", "BTC OTC", "BTC/USD OTC"),
    "BTCUSD": ("Bitcoin", "BTC/USD", "BTCUSD"),
    "ETHUSD_OTC": ("Ethereum OTC", "ETH OTC", "ETH/USD OTC"),
    "ETHUSD": ("Ethereum", "ETH/USD", "ETHUSD"),
    "AUDCAD_OTC": ("AUD/CAD OTC", "AUDCAD OTC"),
    "AUDCAD": ("AUD/CAD", "AUDCAD"),
}
WATCH_PAIR_CODES = frozenset(
    pair for asset in WATCH_ASSETS for pair in asset["pairs"]
)

if START_BALANCE <= 0 or START_AMOUNT <= 0:
    raise ValueError("Demo balansı və başlanğıc məbləği müsbət olmalıdır")
if not 0 < PAYOUT_RATE <= 1:
    raise ValueError("DEMO_PAYOUT_RATE 0 ilə 1 arasında olmalıdır")
if TRADE_DURATION_SEC <= 0 or CANDLE_INTERVAL_SEC <= 0:
    raise ValueError("Müddətlər müsbət olmalıdır")
if (
    EMA_FAST <= 0
    or EMA_SLOW <= EMA_FAST
    or TREND_EMA_FAST <= EMA_SLOW
    or TREND_EMA_SLOW <= TREND_EMA_FAST
    or RSI_PERIOD <= 1
):
    raise ValueError("RSI/EMA parametrləri düzgün deyil")
if not 50 <= ENTRY_RSI_MIN < ENTRY_RSI_MAX < 100:
    raise ValueError("1 dəqiqəlik RSI giriş sərhədləri düzgün deyil")
if not 0 <= MIN_CANDLE_BODY <= 1:
    raise ValueError("Şam gövdəsi filtri 0–1 arasında olmalıdır")
if not 0 <= RSI_OVERSOLD < RSI_OVERBOUGHT <= 100:
    raise ValueError("RSI sərhədləri düzgün deyil")
if not RSI_OVERSOLD < RSI_MIDLINE < RSI_OVERBOUGHT:
    raise ValueError("RSI orta xətti oversold/overbought arasında olmalıdır")
if not 0 <= AI_MIN_CONFIDENCE <= 1:
    raise ValueError("AI_MIN_CONFIDENCE 0 ilə 1 arasında olmalıdır")

for directory in (USER_DATA_DIR, DEMO_DATA_DIR, LOG_DIR):
    directory.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "olympbot-demo.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("olympbot.demo")
SESSION_LOG = LOG_DIR / f"session-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
_event_lock = threading.Lock()


def _event(event: str, **fields) -> None:
    record = {
        "time": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    with _event_lock:
        with SESSION_LOG.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


class DemoDatabase:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self._initialise()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialise(self) -> None:
        with self.lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    pair TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    candle_bucket INTEGER NOT NULL,
                    rsi REAL NOT NULL,
                    ema_fast REAL NOT NULL,
                    ema_slow REAL NOT NULL,
                    accepted INTEGER NOT NULL,
                    reason TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    pair TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    amount REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    entry_ts REAL NOT NULL,
                    expiry_ts REAL NOT NULL,
                    exit_price REAL,
                    exit_ts REAL,
                    result TEXT NOT NULL DEFAULT 'OPEN',
                    pnl REAL NOT NULL DEFAULT 0,
                    rsi REAL NOT NULL,
                    ema_fast REAL NOT NULL,
                    ema_slow REAL NOT NULL,
                    martingale_step INTEGER NOT NULL DEFAULT 0,
                    platform_status TEXT NOT NULL DEFAULT 'SIMULATED',
                    platform_error TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS market_candles (
                    pair TEXT NOT NULL,
                    bucket INTEGER NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    ticks INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (pair, bucket)
                );

                CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(result);
                CREATE INDEX IF NOT EXISTS idx_trades_pair ON trades(pair, created_at);
                CREATE INDEX IF NOT EXISTS idx_signals_pair ON signals(pair, created_at);
                CREATE INDEX IF NOT EXISTS idx_market_candles_pair
                    ON market_candles(pair, bucket);
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(trades)").fetchall()
            }
            if "platform_status" not in columns:
                connection.execute(
                    "ALTER TABLE trades ADD COLUMN platform_status TEXT NOT NULL DEFAULT 'SIMULATED'"
                )
            if "platform_error" not in columns:
                connection.execute(
                    "ALTER TABLE trades ADD COLUMN platform_error TEXT NOT NULL DEFAULT ''"
                )

    def insert_signal(
        self,
        pair: str,
        direction: str,
        candle_bucket: int,
        rsi: float,
        ema_fast: float,
        ema_slow: float,
        accepted: bool,
        reason: str = "",
    ) -> int:
        with self.lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO signals
                    (created_at, pair, direction, candle_bucket, rsi, ema_fast, ema_slow, accepted, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    pair,
                    direction,
                    candle_bucket,
                    rsi,
                    ema_fast,
                    ema_slow,
                    int(accepted),
                    reason,
                ),
            )
            return int(cursor.lastrowid)

    def insert_trade(self, trade: "DemoTrade") -> int:
        with self.lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO trades
                    (created_at, pair, direction, amount, entry_price, entry_ts, expiry_ts,
                     rsi, ema_fast, ema_slow, martingale_step, result,
                     platform_status, platform_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.created_at,
                    trade.pair,
                    trade.direction,
                    trade.amount,
                    trade.entry_price,
                    trade.entry_ts,
                    trade.expiry_ts,
                    trade.rsi,
                    trade.ema_fast,
                    trade.ema_slow,
                    trade.martingale_step,
                    "PENDING" if trade.platform_status == "PENDING" else "OPEN",
                    trade.platform_status,
                    trade.platform_error,
                ),
            )
            return int(cursor.lastrowid)

    def update_platform_status(
        self,
        trade_id: int,
        status: str,
        error: str = "",
    ) -> None:
        with self.lock, self._connect() as connection:
            connection.execute(
                "UPDATE trades SET platform_status=?, platform_error=? WHERE id=?",
                (status, error, trade_id),
            )

    def activate_platform_trade(self, trade_id: int) -> bool:
        with self.lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE trades SET result='OPEN' WHERE id=? AND result='PENDING'",
                (trade_id,),
            )
            return cursor.rowcount == 1

    def cancel_platform_trade(self, trade_id: int, error: str) -> bool:
        with self.lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE trades
                SET result='CANCELLED', exit_ts=?, pnl=0, platform_error=?
                WHERE id=? AND result='PENDING'
                """,
                (time.time(), error, trade_id),
            )
            return cursor.rowcount == 1

    def resolve_trade(
        self,
        trade_id: int,
        exit_price: float,
        exit_ts: float,
        result: str,
        pnl: float,
    ) -> None:
        with self.lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE trades
                SET exit_price=?, exit_ts=?, result=?, pnl=?
                WHERE id=? AND result='OPEN'
                """,
                (exit_price, exit_ts, result, pnl, trade_id),
            )

    def open_trades(self) -> list[dict]:
        with self.lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM trades WHERE result='OPEN' ORDER BY id"
            ).fetchall()
            return [dict(row) for row in rows]

    def recent_trades(self, limit: int = 100) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        with self.lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def trades_since(self, since: float) -> list[dict]:
        with self.lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM trades WHERE created_at>=? ORDER BY id",
                (float(since),),
            ).fetchall()
            return [dict(row) for row in rows]

    def reset(self) -> None:
        with self.lock, self._connect() as connection:
            connection.execute("DELETE FROM signals")
            connection.execute("DELETE FROM trades")

    def upsert_candles(self, candle_rows: list[dict]) -> None:
        if not candle_rows:
            return
        clean_rows = [
            (
                str(row["pair"]),
                int(row["bucket"]),
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                max(0, int(row.get("ticks", 0))),
                time.time(),
            )
            for row in candle_rows
        ]
        pairs = sorted({row[0] for row in clean_rows})
        with self.lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO market_candles
                    (pair, bucket, open, high, low, close, ticks, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pair, bucket) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    ticks=excluded.ticks,
                    updated_at=excluded.updated_at
                """,
                clean_rows,
            )
            for pair in pairs:
                connection.execute(
                    """
                    DELETE FROM market_candles
                    WHERE pair=? AND bucket NOT IN (
                        SELECT bucket FROM market_candles
                        WHERE pair=? ORDER BY bucket DESC LIMIT ?
                    )
                    """,
                    (pair, pair, MAX_CANDLES),
                )

    def load_candles(self) -> list[dict]:
        with self.lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT pair, bucket, open, high, low, close, ticks
                FROM market_candles ORDER BY pair, bucket
                """
            ).fetchall()
            return [dict(row) for row in rows]


database = DemoDatabase(DB_PATH)


@dataclass
class DemoTrade:
    pair: str
    direction: str
    amount: float
    entry_price: float
    entry_ts: float
    expiry_ts: float
    rsi: float
    ema_fast: float
    ema_slow: float
    martingale_step: int
    created_at: float
    platform_status: str = "SIMULATED"
    platform_error: str = ""
    id: int | None = None


platform_lock = threading.RLock()
platform_orders = deque()
platform_commands = deque()
platform_pending: dict[int, dict] = {}
platform_state = {
    "execution_enabled": PLATFORM_DEMO_DEFAULT,
    "demo_verified": False,
    "account_label": "",
    "balance_text": "",
    "balance_value": None,
    "session_start_balance": None,
    "platform_pnl": 0.0,
    "trade_amount": max(1, int(round(START_AMOUNT))),
    "visible_trade_amount": None,
    "safety_marker": False,
    "last_checked": None,
    "last_error": "",
    "last_order": None,
}
scanner_lock = threading.RLock()
scanner_state = {
    "enabled": SCAN_ROTATION_ENABLED,
    "interval_sec": SCAN_ROTATION_SEC,
    "last_rotation": 0.0,
    "target_pair": None,
    "rotation_index": 0,
    "status": "Hazır" if SCAN_ROTATION_ENABLED else "Söndürülüb",
    "last_error": "",
    "visited_pairs": [],
    "available_pairs": [],
    "unavailable_pairs": [],
}


class DemoTradingEngine:
    def __init__(self, db: DemoDatabase):
        self.db = db
        self.lock = threading.RLock()
        self.open_positions: dict[int, DemoTrade] = {}
        self.last_trade_times: dict[str, float] = {}
        self.last_signal_buckets: dict[str, int] = {}
        self.martingale_steps: dict[str, int] = {}
        self.current_amounts: dict[str, float] = {}
        self._load_open_positions()

    def _load_open_positions(self) -> None:
        for row in self.db.open_trades():
            trade = DemoTrade(
                id=row["id"],
                pair=row["pair"],
                direction=row["direction"],
                amount=row["amount"],
                entry_price=row["entry_price"],
                entry_ts=row["entry_ts"],
                expiry_ts=row["expiry_ts"],
                rsi=row["rsi"],
                ema_fast=row["ema_fast"],
                ema_slow=row["ema_slow"],
                martingale_step=row["martingale_step"],
                created_at=row["created_at"],
                platform_status=row.get("platform_status", "SIMULATED"),
                platform_error=row.get("platform_error", ""),
            )
            self.open_positions[int(trade.id)] = trade
            self.last_trade_times[trade.pair] = trade.entry_ts

    def _has_open_pair(self, pair: str) -> bool:
        return any(trade.pair == pair for trade in self.open_positions.values())

    def submit_signal(
        self,
        pair: str,
        direction: str,
        candle_bucket: int,
        rsi: float,
        ema_fast: float,
        ema_slow: float,
        entry_price: float,
        entry_ts: float,
    ) -> tuple[bool, str]:
        if direction not in {"AL", "SAT"}:
            return False, "Yanlış istiqamət"
        now = time.time()
        with self.lock:
            # Müddəti bitmiş Demo mövqeyi yeni siqnalları daimi bloklamasın.
            stale_cutoff = now - 45
            self.open_positions = {
                trade_id: position
                for trade_id, position in self.open_positions.items()
                if float(position.expiry_ts) >= stale_cutoff
            }

            if self.last_signal_buckets.get(pair) == candle_bucket:
                return False, "Eyni şam siqnalı"
            self.last_signal_buckets[pair] = candle_bucket

            reason = ""
            with platform_lock:
                platform_execution = bool(platform_state["execution_enabled"])
                platform_verified = bool(platform_state["demo_verified"])
                platform_balance = platform_state["balance_value"]
                configured_amount = float(platform_state["trade_amount"])
            if not platform_execution:
                reason = "OlympTrade Demo qoşulmayıb; daxili virtual əməliyyat yaradılmır"
            elif self.open_positions:
                reason = "OlympTrade Demo-da eyni anda yalnız bir əməliyyat açıla bilər"
            elif self._has_open_pair(pair):
                reason = "Aktiv üzrə açıq demo əməliyyatı var"
            elif now - self.last_trade_times.get(pair, 0.0) < COOLDOWN_SEC:
                reason = "Cooldown aktivdir"

            stats = self.statistics()
            amount = (
                configured_amount
                if platform_execution
                else self.current_amounts.get(pair, START_AMOUNT)
            )
            risk = self.risk_status()
            if not reason and risk["halted"]:
                reason = str(risk["reason"])
            elif (
                not reason
                and risk["limits_enabled"]
                and amount > float(risk["max_stake"])
            ):
                reason = (
                    f"Risk limiti: məbləğ {risk['max_stake']:.2f}-dən "
                    "çox ola bilməz"
                )
            elif platform_execution and not platform_verified:
                reason = "OlympTrade Deneme hesabı təsdiqlənməyib"
            elif (
                platform_execution
                and platform_balance is not None
                and amount > float(platform_balance)
            ):
                reason = "OlympTrade Deneme balansı kifayət etmir"
            elif not platform_execution and not reason and amount > stats["balance"]:
                reason = "Demo balansı kifayət etmir"

            accepted = not reason
            self.db.insert_signal(
                pair,
                direction,
                candle_bucket,
                rsi,
                ema_fast,
                ema_slow,
                accepted,
                reason,
            )
            if not accepted:
                _event("signal_rejected", pair=pair, direction=direction, reason=reason)
                return False, reason

            trade = DemoTrade(
                pair=pair,
                direction=direction,
                amount=round(amount, 2),
                entry_price=entry_price,
                entry_ts=entry_ts,
                expiry_ts=entry_ts + TRADE_DURATION_SEC,
                rsi=round(rsi, 4),
                ema_fast=round(ema_fast, 8),
                ema_slow=round(ema_slow, 8),
                martingale_step=0,
                created_at=now,
                platform_status=(
                    "PENDING"
                    if platform_execution
                    else "SIMULATED"
                ),
            )
            trade.id = self.db.insert_trade(trade)
            self.open_positions[int(trade.id)] = trade
            self.last_trade_times[pair] = entry_ts
            if platform_execution:
                with platform_lock:
                    platform_orders.append(
                        {
                            "trade_id": int(trade.id),
                            "pair": trade.pair,
                            "direction": trade.direction,
                            "amount": trade.amount,
                            "created_at": time.time(),
                        }
                    )

        log.info(
            "DEMO ƏMƏLİYYAT: #%s %s %s $%.2f @ %.8f",
            trade.id,
            pair,
            direction,
            trade.amount,
            entry_price,
        )
        if not platform_execution:
            _event("demo_trade_opened", **asdict(trade))
        return True, f"Demo əməliyyat #{trade.id} açıldı"

    def confirm_platform_open(self, trade_id: int) -> bool:
        with self.lock:
            trade = self.open_positions.get(int(trade_id))
            if trade is None or not self.db.activate_platform_trade(int(trade_id)):
                return False
            trade.platform_status = "CLICKED"
            trade.platform_error = ""
            payload = asdict(trade)
        _event("demo_trade_opened", **payload)
        return True

    def cancel_platform_open(self, trade_id: int, error: str) -> bool:
        with self.lock:
            trade = self.open_positions.get(int(trade_id))
            if trade is None:
                return False
            if not self.db.cancel_platform_trade(int(trade_id), error):
                return False
            self.open_positions.pop(int(trade_id), None)
            if self.last_trade_times.get(trade.pair) == trade.entry_ts:
                self.last_trade_times.pop(trade.pair, None)
        return True

    def on_tick(self, pair: str, price: float, timestamp: float) -> None:
        with platform_lock:
            platform_execution = bool(platform_state["execution_enabled"])
        if platform_execution:
            # Platform əməliyyatının nəticəsi qiymət simulyasiyasından deyil,
            # OlympTrade Deneme hesabının faktiki balans dəyişməsindən götürülür.
            return
        with self.lock:
            expiring = [
                trade
                for trade in self.open_positions.values()
                if trade.pair == pair and timestamp >= trade.expiry_ts
            ]
        for trade in expiring:
            self._resolve(trade, price, timestamp)

    def _resolve(self, trade: DemoTrade, exit_price: float, exit_ts: float) -> None:
        if math.isclose(exit_price, trade.entry_price, rel_tol=0.0, abs_tol=1e-12):
            result = "DRAW"
            pnl = 0.0
        else:
            won = (
                trade.direction == "AL" and exit_price > trade.entry_price
            ) or (
                trade.direction == "SAT" and exit_price < trade.entry_price
            )
            result = "WIN" if won else "LOSS"
            pnl = trade.amount * PAYOUT_RATE if won else -trade.amount
        pnl = round(pnl, 2)
        with self.lock:
            if trade.id not in self.open_positions:
                return
            self.db.resolve_trade(int(trade.id), exit_price, exit_ts, result, pnl)
            self.open_positions.pop(int(trade.id), None)
            self.martingale_steps[trade.pair] = 0
            self.current_amounts[trade.pair] = START_AMOUNT

        log.info(
            "DEMO NƏTİCƏ: #%s %s exit=%.8f pnl=%+.2f",
            trade.id,
            result,
            exit_price,
            pnl,
        )
        _event(
            "demo_trade_closed",
            trade_id=trade.id,
            pair=trade.pair,
            direction=trade.direction,
            result=result,
            pnl=pnl,
            entry_price=trade.entry_price,
            exit_price=exit_price,
        )

    def resolve_platform_balance(
        self,
        trade_id: int,
        balance_before: float,
        balance_after: float,
        exit_ts: float,
    ) -> bool:
        with self.lock:
            trade = self.open_positions.get(int(trade_id))
            if trade is None:
                return False
            pnl = round(float(balance_after) - float(balance_before), 2)
            tolerance = 0.005
            result = "WIN" if pnl > tolerance else "LOSS" if pnl < -tolerance else "DRAW"
            with candles_lock:
                exit_price = float(
                    live_prices.get(trade.pair, {}).get("price", trade.entry_price)
                )
            self.db.resolve_trade(int(trade.id), exit_price, exit_ts, result, pnl)
            self.db.update_platform_status(int(trade.id), "SETTLED", "")
            self.open_positions.pop(int(trade.id), None)
            self.martingale_steps[trade.pair] = 0
            self.current_amounts[trade.pair] = START_AMOUNT
        _event(
            "platform_demo_settled",
            trade_id=trade.id,
            pair=trade.pair,
            direction=trade.direction,
            result=result,
            pnl=pnl,
            balance_before=balance_before,
            balance_after=balance_after,
        )
        log.warning(
            "OLYMPTRADE DEMO NƏTİCƏ: #%s %s balans %.2f -> %.2f (P&L %+.2f)",
            trade.id,
            result,
            balance_before,
            balance_after,
            pnl,
        )
        return True

    def recent_trades(self, limit: int = 100) -> list[dict]:
        return self.db.recent_trades(limit)

    def risk_status(self) -> dict:
        day_start = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )
        today = self.db.trades_since(day_start)
        closed = [trade for trade in today if trade["result"] != "OPEN"]
        daily_pnl = round(sum(float(trade["pnl"]) for trade in closed), 2)
        consecutive_losses = 0
        for trade in reversed(closed):
            if trade["result"] != "LOSS":
                break
            consecutive_losses += 1

        with platform_lock:
            platform_balance = platform_state["balance_value"]
        reference_balance = (
            float(platform_balance)
            if platform_balance is not None
            else float(self.statistics()["balance"])
        )
        max_stake = round(
            max(1.0, reference_balance * MAX_STAKE_PERCENT / 100),
            2,
        )
        reason = ""
        if DEMO_RISK_LIMITS_ENABLED:
            if daily_pnl <= -MAX_DAILY_LOSS:
                reason = f"Günlük zərər limiti dolub ({daily_pnl:+.2f})"
            elif len(today) >= MAX_DAILY_TRADES:
                reason = f"Günlük əməliyyat limiti dolub ({len(today)})"
            elif consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                reason = (
                    "Ardıcıl zərər limiti dolub "
                    f"({consecutive_losses})"
                )
        return {
            "halted": bool(reason),
            "reason": reason,
            "limits_enabled": DEMO_RISK_LIMITS_ENABLED,
            "daily_pnl": daily_pnl,
            "daily_trades": len(today),
            "consecutive_losses": consecutive_losses,
            "max_stake": (
                max_stake if DEMO_RISK_LIMITS_ENABLED else reference_balance
            ),
            "martingale_enabled": False,
            "limits": {
                "max_daily_loss": (
                    MAX_DAILY_LOSS if DEMO_RISK_LIMITS_ENABLED else None
                ),
                "max_daily_trades": (
                    MAX_DAILY_TRADES if DEMO_RISK_LIMITS_ENABLED else None
                ),
                "max_consecutive_losses": (
                    MAX_CONSECUTIVE_LOSSES
                    if DEMO_RISK_LIMITS_ENABLED
                    else None
                ),
                "max_stake_percent": (
                    MAX_STAKE_PERCENT if DEMO_RISK_LIMITS_ENABLED else None
                ),
            },
            "day_start_utc": day_start,
        }

    def statistics(self) -> dict:
        trades = self.db.recent_trades(500)
        closed = [trade for trade in trades if trade["result"] != "OPEN"]
        wins = sum(trade["result"] == "WIN" for trade in closed)
        losses = sum(trade["result"] == "LOSS" for trade in closed)
        draws = sum(trade["result"] == "DRAW" for trade in closed)
        total_pnl = round(sum(float(trade["pnl"]) for trade in closed), 2)
        balance = round(START_BALANCE + total_pnl, 2)
        decided = wins + losses

        chronological = list(reversed(closed))
        equity = START_BALANCE
        peak = START_BALANCE
        max_drawdown = 0.0
        consecutive_losses = 0
        max_consecutive_losses = 0
        for trade in chronological:
            equity += float(trade["pnl"])
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak - equity)
            if trade["result"] == "LOSS":
                consecutive_losses += 1
                max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            elif trade["result"] == "WIN":
                consecutive_losses = 0

        return {
            "starting_balance": START_BALANCE,
            "balance": balance,
            "total_pnl": total_pnl,
            "open_trades": len(self.open_positions),
            "closed_trades": len(closed),
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "win_rate": round((wins / decided) * 100, 2) if decided else 0.0,
            "max_drawdown": round(max_drawdown, 2),
            "max_consecutive_losses": max_consecutive_losses,
            "payout_rate": PAYOUT_RATE,
        }

    def snapshot(self) -> dict:
        with self.lock:
            with platform_lock:
                platform = dict(platform_state)
            return {
                "live_trading": False,
                "demo_mode": True,
                "queued": 0,
                "pending_pairs": [],
                "awaiting_results": {
                    str(trade_id): asdict(trade)
                    for trade_id, trade in self.open_positions.items()
                },
                "martingale_steps": dict(self.martingale_steps),
                "current_amounts": dict(self.current_amounts),
                "statistics": self.statistics(),
                "risk": self.risk_status(),
                "platform_demo": platform,
            }

    def reset(self) -> None:
        with self.lock:
            self.db.reset()
            self.open_positions.clear()
            self.last_trade_times.clear()
            self.last_signal_buckets.clear()
            self.martingale_steps.clear()
            self.current_amounts.clear()
            with platform_lock:
                platform_orders.clear()
        _event("demo_account_reset", starting_balance=START_BALANCE)


trade_engine = DemoTradingEngine(database)

state_lock = threading.RLock()
state = {
    "status": "Demo başlayır...",
    "connected": False,
    "captured_count": 0,
    "active_pair": None,
    "history_candles_loaded": 0,
    "history_pairs": [],
    "ws_event_counts": {},
    "last_error": None,
}
candles_lock = threading.RLock()
candles: dict[str, deque] = {}
live_prices: dict[str, dict] = {}
price_ticks = deque(maxlen=MAX_TICKS)
_history_summary_logged = False
ai_lock = threading.RLock()
ai_pending_pairs: set[str] = set()
strategy_signal_lock = threading.RLock()
last_strategy_signal_buckets: dict[str, int] = {}
signal_latch_lock = threading.RLock()
signal_latches: dict[str, dict] = {}
ai_state = {
    "enabled": AI_CONFIRMATION_ENABLED,
    "configured": bool(os.environ.get("OPENAI_API_KEY")),
    "model": AI_MODEL,
    "min_confidence": AI_MIN_CONFIDENCE,
    "demo_fallback_enabled": AI_DEMO_FALLBACK_ENABLED,
    "status": (
        "Hazır"
        if AI_CONFIRMATION_ENABLED
        and bool(os.environ.get("OPENAI_API_KEY"))
        else "Söndürülüb"
        if not AI_CONFIRMATION_ENABLED
        else "OPENAI_API_KEY tapılmadı"
    ),
    "pending": [],
    "last_decision": None,
    "last_error": "",
    "requests": 0,
}


def ai_snapshot() -> dict:
    with ai_lock:
        return {
            **ai_state,
            "pending": sorted(ai_pending_pairs),
        }


def scanner_snapshot() -> dict:
    with scanner_lock:
        return {
            **scanner_state,
            "visited_pairs": list(scanner_state["visited_pairs"]),
            "available_pairs": list(scanner_state["available_pairs"]),
            "unavailable_pairs": list(scanner_state["unavailable_pairs"]),
        }


def set_scanner_enabled(enabled: bool) -> dict:
    with scanner_lock:
        scanner_state["enabled"] = bool(enabled)
        scanner_state["status"] = "Hazır" if enabled else "Söndürülüb"
        scanner_state["last_error"] = ""
        if enabled:
            scanner_state["last_rotation"] = 0.0
    _event("scanner_toggled", enabled=bool(enabled))
    return scanner_snapshot()


def _latch_display_signal(
    pair: str,
    candle_bucket: int,
    analysis: dict,
) -> dict | None:
    if not analysis.get("executable") or analysis.get("direction") not in {"AL", "SAT"}:
        return None
    now = time.time()
    valid_until = float(candle_bucket + CANDLE_INTERVAL_SEC * 2)
    if valid_until <= now:
        return None
    with signal_latch_lock:
        current = signal_latches.get(pair)
        if (
            current
            and int(current["candle_bucket"]) == int(candle_bucket)
            and float(current["valid_until"]) > now
        ):
            return dict(current)
        latched = {
            "pair": pair,
            "candle_bucket": int(candle_bucket),
            "direction": str(analysis["direction"]),
            "score": int(analysis["score"]),
            "quality": str(analysis["quality"]),
            "reasons": list(analysis["reasons"]),
            "trend_regime": str(analysis["trend_regime"]),
            "volatility": str(analysis["volatility"]),
            "created_at": now,
            "valid_until": valid_until,
        }
        signal_latches[pair] = latched
        return dict(latched)


def _active_display_signal(pair: str) -> dict | None:
    now = time.time()
    with signal_latch_lock:
        current = signal_latches.get(pair)
        if not current:
            return None
        if float(current["valid_until"]) <= now:
            signal_latches.pop(pair, None)
            return None
        return dict(current)


_cached_candles = database.load_candles()
for _cached in _cached_candles:
    _pair = str(_cached.pop("pair"))
    candles.setdefault(_pair, deque(maxlen=MAX_CANDLES)).append(_cached)
if _cached_candles:
    state["history_candles_loaded"] = len(_cached_candles)
    state["history_pairs"] = sorted(candles)


def _resolved_watch_assets() -> list[dict]:
    """Resolve each configured watch slot to one concrete OlympTrade pair."""
    required = _required_candles()
    resolved = []
    with candles_lock:
        for order, asset in enumerate(WATCH_ASSETS):
            candidates = []
            for preference, pair in enumerate(asset["pairs"]):
                queue = candles.get(pair, ())
                count = len(queue)
                latest = int(queue[-1]["bucket"]) if queue else 0
                candidates.append(
                    {
                        "pair": pair,
                        "count": count,
                        "latest": latest,
                        "preference": preference,
                    }
                )
            # Hazır axına üstünlük ver; bərabərlikdə OTC/ilk namizəd seçilir.
            selected = max(
                candidates,
                key=lambda item: (
                    item["count"] >= required,
                    item["count"],
                    item["latest"],
                    -item["preference"],
                ),
            )
            resolved.append(
                {
                    "name": asset["name"],
                    "pair": selected["pair"],
                    "candles": selected["count"],
                    "available": selected["count"] > 0,
                    "ready": selected["count"] >= required,
                    "order": order,
                }
            )
    return resolved


def _required_candles() -> int:
    return max(
        RSI_PERIOD + 1,
        EMA_SLOW + 1,
        TREND_EMA_SLOW + 1,
    )


def _resolved_watch_pairs() -> set[str]:
    return {
        item["pair"]
        for item in _resolved_watch_assets()
        if item["available"]
    }


def _calc_rsi(closes: list[float], period: int = RSI_PERIOD):
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for previous, current in zip(closes, closes[1:]):
        difference = current - previous
        gains.append(max(difference, 0.0))
        losses.append(max(-difference, 0.0))
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period
    for index in range(period, len(gains)):
        average_gain = (average_gain * (period - 1) + gains[index]) / period
        average_loss = (average_loss * (period - 1) + losses[index]) / period
    if average_loss == 0:
        return 100.0
    return 100 - (100 / (1 + average_gain / average_loss))


def _calc_ema(values: list[float], period: int):
    if len(values) < period:
        return None
    multiplier = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for value in values[period:]:
        ema = (value - ema) * multiplier + ema
    return ema


def _ema_series(values: list[float], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) < period:
        return output
    ema = sum(values[:period]) / period
    output[period - 1] = ema
    multiplier = 2.0 / (period + 1)
    for index in range(period, len(values)):
        ema = values[index] * multiplier + ema * (1.0 - multiplier)
        output[index] = ema
    return output


def _rsi_series(values: list[float], period: int = RSI_PERIOD) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return output
    gain = 0.0
    loss = 0.0
    for index in range(1, period + 1):
        difference = values[index] - values[index - 1]
        gain += max(difference, 0.0)
        loss += max(-difference, 0.0)
    gain /= period
    loss /= period
    output[period] = 100.0 if loss == 0 else 100 - (100 / (1 + gain / loss))
    for index in range(period + 1, len(values)):
        difference = values[index] - values[index - 1]
        gain = (gain * (period - 1) + max(difference, 0.0)) / period
        loss = (loss * (period - 1) + max(-difference, 0.0)) / period
        output[index] = (
            100.0 if loss == 0 else 100 - (100 / (1 + gain / loss))
        )
    return output


_backtest_lock = threading.RLock()
_backtest_cache: dict = {"created_at": 0.0, "data": None}


def _score_signal(
    closes: list[float],
    opens: list[float],
    highs: list[float],
    lows: list[float],
    index: int,
    rsi_value: float,
    fast_value: float,
    slow_value: float,
    previous_fast: float,
    trend_fast_value: float,
    trend_slow_value: float,
) -> dict:
    """Score a completed candle using trend, momentum, RSI and candle quality."""
    if index < 3:
        return {
            "direction": "GOZLE",
            "executable": False,
            "score": 0,
            "up_score": 0,
            "down_score": 0,
            "quality": "MƏLUMAT AZDIR",
            "reasons": ["Ən azı 4 tamamlanmış şam lazımdır"],
            "trend_regime": "MƏLUMAT AZDIR",
            "volatility": "MƏLUMAT AZDIR",
            "atr_percent": 0.0,
            "trend_gap_percent": 0.0,
        }
    recent_moves = [
        closes[position] - closes[position - 1]
        for position in range(index - 2, index + 1)
    ]
    upward_moves = sum(move > 0 for move in recent_moves)
    downward_moves = sum(move < 0 for move in recent_moves)
    up_score = 0
    down_score = 0
    up_reasons: list[str] = []
    down_reasons: list[str] = []

    if fast_value > slow_value:
        up_score += 22
        up_reasons.append(
            f"EMA {EMA_FAST}, EMA {EMA_SLOW}-dən yuxarıdır"
        )
    elif fast_value < slow_value:
        down_score += 22
        down_reasons.append(
            f"EMA {EMA_FAST}, EMA {EMA_SLOW}-dən aşağıdır"
        )

    if trend_fast_value > trend_slow_value:
        up_score += 20
        up_reasons.append(
            f"EMA {TREND_EMA_FAST}/{TREND_EMA_SLOW} böyük trendi yuxarıdır"
        )
    elif trend_fast_value < trend_slow_value:
        down_score += 20
        down_reasons.append(
            f"EMA {TREND_EMA_FAST}/{TREND_EMA_SLOW} böyük trendi aşağıdır"
        )

    if fast_value > previous_fast:
        up_score += 12
        up_reasons.append("Sürətli EMA yüksəlir")
    elif fast_value < previous_fast:
        down_score += 12
        down_reasons.append("Sürətli EMA enir")

    if ENTRY_RSI_MIN <= rsi_value <= ENTRY_RSI_MAX:
        up_score += 18
        up_reasons.append(f"RSI {rsi_value:.1f} yuxarı momentumu təsdiqləyir")
    elif 100 - ENTRY_RSI_MAX <= rsi_value <= 100 - ENTRY_RSI_MIN:
        down_score += 18
        down_reasons.append(f"RSI {rsi_value:.1f} aşağı momentumu təsdiqləyir")
    elif 46.0 < rsi_value < 54.0:
        up_score += 5
        down_score += 5

    momentum = closes[index] - closes[index - 1]
    if momentum > 0:
        up_score += 12
        up_reasons.append("Son 1 dəqiqəlik momentum müsbətdir")
    elif momentum < 0:
        down_score += 12
        down_reasons.append("Son 1 dəqiqəlik momentum mənfidir")

    if upward_moves >= 2:
        up_score += 8
        up_reasons.append("Son 3 hərəkətin çoxu yuxarıdır")
    if downward_moves >= 2:
        down_score += 8
        down_reasons.append("Son 3 hərəkətin çoxu aşağıdır")

    candle_range = max(highs[index] - lows[index], 1e-12)
    body_strength = abs(closes[index] - opens[index]) / candle_range
    body_points = 10 if body_strength >= MIN_CANDLE_BODY else 2
    if closes[index] > opens[index]:
        up_score += body_points
        up_reasons.append("Son şam alıcı üstünlüyü göstərir")
    elif closes[index] < opens[index]:
        down_score += body_points
        down_reasons.append("Son şam satıcı üstünlüyü göstərir")

    price_scale = max(abs(closes[index]), 1e-12)
    trend_gap_percent = abs(fast_value - slow_value) / price_scale * 100
    if trend_gap_percent >= 0.01:
        if fast_value > slow_value:
            up_score += 5
        elif fast_value < slow_value:
            down_score += 5

    true_ranges = []
    atr_start = max(1, index - RSI_PERIOD + 1)
    for position in range(atr_start, index + 1):
        true_ranges.append(
            max(
                highs[position] - lows[position],
                abs(highs[position] - closes[position - 1]),
                abs(lows[position] - closes[position - 1]),
            )
        )
    atr = sum(true_ranges) / len(true_ranges) if true_ranges else 0.0
    atr_percent = atr / price_scale * 100
    volatility = (
        "YÜKSƏK"
        if atr_percent > 1.5
        else "SAKİT"
        if atr_percent < 0.03
        else "NORMAL"
    )
    trend_regime = (
        "YUXARI TREND"
        if trend_fast_value > trend_slow_value
        else "AŞAĞI TREND"
        if trend_fast_value < trend_slow_value
        else "YAN BAZAR"
    )

    best_score = min(100, max(up_score, down_score))
    score_gap = abs(up_score - down_score)
    direction = (
        "AL"
        if up_score > down_score and best_score >= 55 and score_gap >= 12
        else "SAT"
        if down_score > up_score and best_score >= 55 and score_gap >= 12
        else "GOZLE"
    )
    up_entry = bool(
        fast_value > slow_value
        and trend_fast_value > trend_slow_value
        and fast_value > previous_fast
        and ENTRY_RSI_MIN <= rsi_value <= ENTRY_RSI_MAX
        and closes[index] > closes[index - 1]
        and body_strength >= MIN_CANDLE_BODY
    )
    down_entry = bool(
        fast_value < slow_value
        and trend_fast_value < trend_slow_value
        and fast_value < previous_fast
        and 100 - ENTRY_RSI_MAX <= rsi_value <= 100 - ENTRY_RSI_MIN
        and closes[index] < closes[index - 1]
        and body_strength >= MIN_CANDLE_BODY
    )
    executable = bool(
        (
            direction == "AL"
            and up_entry
            or direction == "SAT"
            and down_entry
        )
        and best_score >= SIGNAL_SCORE_THRESHOLD
        and volatility != "YÜKSƏK"
    )
    quality = (
        "GÜCLÜ"
        if executable and best_score >= 82
        else "TƏSDİQLƏNMİŞ"
        if executable
        else "İZLƏ"
        if direction in {"AL", "SAT"}
        else "GÖZLƏ"
    )
    reasons = (
        up_reasons
        if direction == "AL"
        else down_reasons
        if direction == "SAT"
        else ["Trend və momentum eyni istiqaməti təsdiqləmir"]
    )
    return {
        "direction": direction,
        "executable": executable,
        "score": int(best_score),
        "up_score": int(min(100, up_score)),
        "down_score": int(min(100, down_score)),
        "quality": quality,
        "reasons": reasons[:4],
        "trend_regime": trend_regime,
        "volatility": volatility,
        "atr_percent": round(atr_percent, 4),
        "trend_gap_percent": round(trend_gap_percent, 4),
        "body_strength": round(body_strength, 4),
    }


def _strategy_direction(
    closes: list[float],
    index: int,
    rsi_value: float,
    fast_value: float,
    slow_value: float,
    previous_fast: float,
) -> str | None:
    # Backward-compatible helper used by local diagnostics.
    synthetic_opens = [closes[max(0, position - 1)] for position in range(len(closes))]
    analysis = _score_signal(
        closes,
        synthetic_opens,
        list(closes),
        list(closes),
        index,
        rsi_value,
        fast_value,
        slow_value,
        previous_fast,
        fast_value,
        slow_value,
    )
    return (
        str(analysis["direction"])
        if analysis["executable"]
        else None
    )


def _backtest_pair(
    pair: str,
    candle_rows: list[dict],
    evaluation_start: int | None = None,
) -> dict:
    # Son şam hələ formalaşa bilər; backtest onu nəticəyə daxil etmir.
    completed = candle_rows[:-1]
    closes = [float(candle["close"]) for candle in completed]
    opens = [float(candle["open"]) for candle in completed]
    highs = [float(candle["high"]) for candle in completed]
    lows = [float(candle["low"]) for candle in completed]
    fast = _ema_series(closes, EMA_FAST)
    slow = _ema_series(closes, EMA_SLOW)
    trend_fast = _ema_series(closes, TREND_EMA_FAST)
    trend_slow = _ema_series(closes, TREND_EMA_SLOW)
    rsi = _rsi_series(closes, RSI_PERIOD)
    wins = losses = draws = 0
    upward_signals = downward_signals = 0
    equity = peak = max_drawdown = 0.0
    last_signal_index = -SIGNAL_COOLDOWN_CANDLES

    start = max(
        TREND_EMA_SLOW - 1,
        RSI_PERIOD + 1,
        int(evaluation_start or 0),
    )
    for index in range(start, len(closes) - 1):
        indicator_values = (
            rsi[index - 1],
            rsi[index],
            fast[index - 1],
            fast[index],
            slow[index],
            trend_fast[index],
            trend_slow[index],
        )
        if any(value is None for value in indicator_values):
            continue
        analysis = _score_signal(
            closes,
            opens,
            highs,
            lows,
            index,
            float(rsi[index]),
            float(fast[index]),
            float(slow[index]),
            float(fast[index - 1]),
            float(trend_fast[index]),
            float(trend_slow[index]),
        )
        if not analysis["executable"]:
            continue
        direction = str(analysis["direction"])
        if index - last_signal_index < SIGNAL_COOLDOWN_CANDLES:
            continue
        last_signal_index = index
        if direction == "AL":
            upward_signals += 1
        else:
            downward_signals += 1

        exit_price = closes[index + 1]
        if math.isclose(exit_price, closes[index], rel_tol=0.0, abs_tol=1e-12):
            draws += 1
            pnl = 0.0
        else:
            won = (
                direction == "AL" and exit_price > closes[index]
            ) or (
                direction == "SAT" and exit_price < closes[index]
            )
            if won:
                wins += 1
                pnl = PAYOUT_RATE
            else:
                losses += 1
                pnl = -1.0
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    decided = wins + losses
    trades = decided + draws
    pnl = wins * PAYOUT_RATE - losses
    profit_factor = (
        round((wins * PAYOUT_RATE) / losses, 3)
        if losses
        else None
    )
    return {
        "pair": pair,
        "candles": len(completed),
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "upward_signals": upward_signals,
        "downward_signals": downward_signals,
        "win_rate": round(wins / decided * 100, 2) if decided else 0.0,
        "pnl_per_unit": round(pnl, 3),
        "profit_factor": profit_factor,
        "expectancy": round(pnl / trades, 4) if trades else 0.0,
        "max_drawdown_per_unit": round(max_drawdown, 3),
        "profitable": bool(trades and pnl > 0),
        "evaluated_candles": max(0, len(closes) - start),
        "sample_quality": (
            "YETƏRLİ"
            if trades >= 30
            else "MƏHDUD"
            if trades >= 10
            else "ÇOX AZ"
        ),
    }


def backtest_snapshot(force: bool = False) -> dict:
    now = time.time()
    with _backtest_lock:
        cached = _backtest_cache["data"]
        if (
            not force
            and cached is not None
            and now - _backtest_cache["created_at"] < 30
        ):
            return cached

    resolved = _resolved_watch_assets()
    with candles_lock:
        histories = {
            item["pair"]: list(candles.get(item["pair"], ()))
            for item in resolved
        }
    pairs = []
    for item in resolved:
        history = histories[item["pair"]]
        full = _backtest_pair(item["pair"], history)
        holdout_start = max(0, int((len(history) - 1) * 0.70))
        holdout = _backtest_pair(
            item["pair"],
            history,
            evaluation_start=holdout_start,
        )
        full["display_name"] = item["name"]
        full["out_of_sample"] = {
            key: holdout[key]
            for key in (
                "evaluated_candles",
                "trades",
                "wins",
                "losses",
                "draws",
                "win_rate",
                "pnl_per_unit",
                "profit_factor",
                "expectancy",
                "max_drawdown_per_unit",
                "sample_quality",
            )
        }
        pairs.append(full)
    totals = {
        "candles": sum(item["candles"] for item in pairs),
        "trades": sum(item["trades"] for item in pairs),
        "wins": sum(item["wins"] for item in pairs),
        "losses": sum(item["losses"] for item in pairs),
        "draws": sum(item["draws"] for item in pairs),
        "upward_signals": sum(item["upward_signals"] for item in pairs),
        "downward_signals": sum(item["downward_signals"] for item in pairs),
        "pnl_per_unit": round(
            sum(item["pnl_per_unit"] for item in pairs),
            3,
        ),
    }
    decided = totals["wins"] + totals["losses"]
    totals["win_rate"] = (
        round(totals["wins"] / decided * 100, 2) if decided else 0.0
    )
    totals["profit_factor"] = (
        round((totals["wins"] * PAYOUT_RATE) / totals["losses"], 3)
        if totals["losses"]
        else None
    )
    totals["edge_vs_break_even"] = round(
        totals["win_rate"] - (100 / (1 + PAYOUT_RATE)),
        2,
    )
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": (
            "1m EMA 3/8 entry + EMA 15/50 trend + RSI 9, "
            "növbəti tamamlanmış şam"
        ),
        "ai_included": False,
        "payout_rate": PAYOUT_RATE,
        "break_even_win_rate": round(100 / (1 + PAYOUT_RATE), 2),
        "pairs": pairs,
        "totals": totals,
        "disclaimer": "Tarixi nəticə gələcək qazanca zəmanət vermir.",
    }
    with _backtest_lock:
        _backtest_cache["created_at"] = now
        _backtest_cache["data"] = result
    return result


def pair_validation_status(pair: str) -> dict:
    result = next(
        (
            item
            for item in backtest_snapshot()["pairs"]
            if item["pair"] == pair
        ),
        None,
    )
    if result is None:
        return {
            "eligible": False,
            "reason": "Aktiv üçün backtest yoxdur",
        }
    holdout = result.get("out_of_sample", {})
    full_pf = result.get("profit_factor")
    holdout_pf = holdout.get("profit_factor")
    eligible = bool(
        int(result["trades"]) >= 30
        and full_pf is not None
        and float(full_pf) >= 1.0
        and int(holdout.get("trades", 0)) >= 10
        and holdout_pf is not None
        and float(holdout_pf) >= 1.0
    )
    if eligible:
        reason = "Tarixi və son 30% nümunə minimum filtrləri keçir"
    elif int(result["trades"]) < 30:
        reason = f"Etibarlı qərar üçün siqnal nümunəsi azdır ({result['trades']}/30)"
    elif int(holdout.get("trades", 0)) < 10:
        reason = (
            "Son 30% yoxlama nümunəsi azdır "
            f"({holdout.get('trades', 0)}/10)"
        )
    elif full_pf is None or float(full_pf) < 1.0:
        reason = f"Ümumi profit factor zəifdir ({full_pf or 0:.2f})"
    else:
        reason = f"Son 30% profit factor zəifdir ({holdout_pf or 0:.2f})"
    return {
        "eligible": eligible,
        "reason": reason,
        "trades": int(result["trades"]),
        "win_rate": float(result["win_rate"]),
        "profit_factor": full_pf,
        "out_of_sample_trades": int(holdout.get("trades", 0)),
        "out_of_sample_win_rate": float(holdout.get("win_rate", 0)),
        "out_of_sample_profit_factor": holdout_pf,
    }


def demo_execution_validation(pair: str, analysis: dict) -> dict:
    """Apply strict backtest approval or a tightly limited Demo-only learning gate."""
    validation = pair_validation_status(pair)
    if validation["eligible"]:
        return {
            **validation,
            "backtest_eligible": True,
            "mode": "BACKTEST",
        }
    learning_eligible = bool(
        DEMO_LEARNING_MODE
        and analysis.get("executable")
        and int(analysis.get("score", 0)) >= DEMO_LEARNING_MIN_SCORE
    )
    if learning_eligible:
        return {
            **validation,
            "eligible": True,
            "backtest_eligible": False,
            "mode": "DEMO_LEARNING",
            "reason": (
                f"Demo sınaq rejimi: {analysis['score']}/100 güclü siqnal; "
                "real hesab icrası bağlıdır"
            ),
        }
    return {
        **validation,
        "backtest_eligible": False,
        "mode": "BLOCKED",
    }


def market_analysis_snapshot() -> dict:
    required = _required_candles()
    resolved = _resolved_watch_assets()
    output = {}
    with candles_lock:
        histories = {
            item["pair"]: list(candles.get(item["pair"], ()))
            for item in resolved
        }
        prices = dict(live_prices)
    for item in resolved:
        pair = item["pair"]
        history = histories[pair]
        completed = history[:-1]
        base = {
            "pair": pair,
            "display_name": item["name"],
            "candles": len(completed),
            "required_candles": required,
            "last_price": prices.get(pair, {}).get("price"),
            "direction": "GOZLE",
            "direction_label": "GÖZLƏ",
            "signal_state": "WAIT",
            "valid_for_sec": 0,
            "valid_until": None,
            "signal_started_at": None,
            "executable": False,
            "auto_eligible": False,
            "score": 0,
            "quality": "MƏLUMAT GÖZLƏNİLİR",
            "reasons": ["Tamamlanmış şamlar toplanır"],
            "trend_regime": "MƏLUMAT AZDIR",
            "volatility": "MƏLUMAT AZDIR",
            "rsi": None,
            "ema_fast": None,
            "ema_slow": None,
            "candle_bucket": (
                int(completed[-1]["bucket"])
                if completed
                else None
            ),
        }
        if len(completed) < required:
            output[pair] = base
            continue
        closes = [float(candle["close"]) for candle in completed]
        opens = [float(candle["open"]) for candle in completed]
        highs = [float(candle["high"]) for candle in completed]
        lows = [float(candle["low"]) for candle in completed]
        rsi = _calc_rsi(closes)
        fast = _calc_ema(closes, EMA_FAST)
        slow = _calc_ema(closes, EMA_SLOW)
        previous_fast = _calc_ema(closes[:-1], EMA_FAST)
        trend_fast = _calc_ema(closes, TREND_EMA_FAST)
        trend_slow = _calc_ema(closes, TREND_EMA_SLOW)
        if None in (rsi, fast, slow, previous_fast, trend_fast, trend_slow):
            output[pair] = base
            continue
        analysis = _score_signal(
            closes,
            opens,
            highs,
            lows,
            len(closes) - 1,
            float(rsi),
            float(fast),
            float(slow),
            float(previous_fast),
            float(trend_fast),
            float(trend_slow),
        )
        validation = demo_execution_validation(pair, analysis)
        active_signal = _active_display_signal(pair)
        if active_signal:
            display_analysis = {
                **analysis,
                "direction": active_signal["direction"],
                "score": active_signal["score"],
                "quality": active_signal["quality"],
                "reasons": active_signal["reasons"],
                "trend_regime": active_signal["trend_regime"],
                "volatility": active_signal["volatility"],
                "executable": True,
            }
            direction_label = (
                "YUXARI ↑"
                if active_signal["direction"] == "AL"
                else "AŞAĞI ↓"
            )
            signal_state = "ACTIVE"
            valid_until = float(active_signal["valid_until"])
            valid_for_sec = max(0, int(math.ceil(valid_until - time.time())))
            signal_started_at = datetime.fromtimestamp(
                float(active_signal["created_at"]),
                timezone.utc,
            ).isoformat()
        else:
            display_analysis = analysis
            direction_label = (
                "YUXARI NAMİZƏD"
                if analysis["direction"] == "AL"
                else "AŞAĞI NAMİZƏD"
                if analysis["direction"] == "SAT"
                else "GÖZLƏ"
            )
            signal_state = (
                "CANDIDATE"
                if analysis["direction"] in {"AL", "SAT"}
                else "WAIT"
            )
            valid_until = None
            valid_for_sec = 0
            signal_started_at = None
        output[pair] = {
            **base,
            **display_analysis,
            "auto_eligible": bool(
                active_signal and validation["eligible"]
            ),
            "validation": validation,
            "direction_label": direction_label,
            "signal_state": signal_state,
            "valid_until": valid_until,
            "valid_for_sec": valid_for_sec,
            "signal_started_at": signal_started_at,
            "rsi": round(float(rsi), 2),
            "ema_fast": round(float(fast), 8),
            "ema_slow": round(float(slow), 8),
            "trend_ema_fast": round(float(trend_fast), 8),
            "trend_ema_slow": round(float(trend_slow), 8),
        }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "ONE_MINUTE_TREND_V6",
        "execution_threshold": SIGNAL_SCORE_THRESHOLD,
        "assets": output,
        "executable_signals": sum(
            item["signal_state"] == "ACTIVE" for item in output.values()
        ),
        "active_signals": sum(
            item["signal_state"] == "ACTIVE" for item in output.values()
        ),
        "candidate_signals": sum(
            item["signal_state"] == "CANDIDATE" for item in output.values()
        ),
        "auto_eligible_signals": sum(
            bool(item["auto_eligible"]) for item in output.values()
        ),
    }


def _signal_entry_window_open(signal_data: dict) -> bool:
    valid_until = (
        int(signal_data["candle_bucket"])
        + CANDLE_INTERVAL_SEC * 2
    )
    return time.time() < valid_until


def _submit_confirmed_signal(signal_data: dict) -> None:
    pair = signal_data["pair"]
    if not _signal_entry_window_open(signal_data):
        _event(
            "signal_rejected",
            pair=pair,
            direction=signal_data["direction"],
            score=signal_data.get("score"),
            reason="1 dəqiqəlik siqnalın giriş vaxtı bitib",
        )
        return
    # Platform əmri yaradılmamışdan əvvəl aktivin OlympTrade-də həqiqətən açıq
    # olduğunu yoxla. Əks halda qısa müddətli PENDING mövqeyi başqa etibarlı
    # siqnalı "eyni anda bir əməliyyat" qaydası ilə səhvən bloklaya bilər.
    with state_lock:
        active_pair = state.get("active_pair")
    with scanner_lock:
        available_pairs = set(scanner_state.get("available_pairs", ()))
    if pair != active_pair and pair not in available_pairs:
        _event(
            "signal_rejected",
            pair=pair,
            direction=signal_data["direction"],
            score=signal_data.get("score"),
            reason=(
                f"{pair} OlympTrade-də açıq aktiv tabı deyil; "
                "Demo əmri yaradılmadı"
            ),
        )
        return
    with candles_lock:
        latest = live_prices.get(pair, {})
    entry_price = float(latest.get("price", signal_data["entry_price"]))
    entry_ts = float(latest.get("ts", time.time()))
    trade_engine.submit_signal(
        pair,
        signal_data["direction"],
        int(signal_data["candle_bucket"]),
        float(signal_data["rsi"]),
        float(signal_data["ema_fast"]),
        float(signal_data["ema_slow"]),
        entry_price,
        entry_ts,
    )


def _run_ai_signal_confirmation(signal_data: dict) -> None:
    pair = signal_data["pair"]
    try:
        request_body = {
            "model": AI_MODEL,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "You are a conservative secondary filter for an OlympTrade "
                        "DEMO-only signal. Never invent a new direction and never "
                        "promise profit. Approve only when the supplied RSI/EMA trend, "
                        "recent candles, and proposed direction are internally "
                        "consistent. Reject unclear, contradictory, stale, or "
                        "high-risk setups. Give a short reason in Azerbaijani."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "Confirm or reject this existing deterministic signal",
                            **signal_data,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "olympbot_signal_confirmation",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "approve": {"type": "boolean"},
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                            "risk_level": {
                                "type": "string",
                                "enum": ["LOW", "MEDIUM", "HIGH"],
                            },
                            "reason": {"type": "string"},
                        },
                        "required": [
                            "approve",
                            "confidence",
                            "risk_level",
                            "reason",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "max_output_tokens": 300,
        }
        api_request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                api_request,
                timeout=AI_TIMEOUT_SEC,
            ) as api_response:
                response_data = json.loads(api_response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                error_data = json.loads(exc.read().decode("utf-8"))
                api_message = str(
                    error_data.get("error", {}).get("message", "")
                ).strip()
            except Exception:
                api_message = ""
            raise RuntimeError(
                f"OpenAI API HTTP {exc.code}"
                + (f": {api_message[:300]}" if api_message else "")
            ) from exc

        output_texts = []
        for item in response_data.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    output_texts.append(str(content["text"]))
        if not output_texts:
            raise RuntimeError("AI strukturlaşdırılmış qərar qaytarmadı")
        parsed = json.loads("\n".join(output_texts))
        required_fields = {"approve", "confidence", "risk_level", "reason"}
        if not isinstance(parsed, dict) or not required_fields.issubset(parsed):
            raise RuntimeError("AI qərar formatı natamamdır")
        confidence = float(parsed["confidence"])
        if not 0 <= confidence <= 1:
            raise RuntimeError("AI etibar dəyəri düzgün deyil")
        risk_level = str(parsed["risk_level"])
        if risk_level not in {"LOW", "MEDIUM", "HIGH"}:
            raise RuntimeError("AI risk səviyyəsi düzgün deyil")
        approved = bool(
            parsed["approve"]
            and confidence >= AI_MIN_CONFIDENCE
            and risk_level != "HIGH"
        )
        decision = {
            "time": datetime.now(timezone.utc).isoformat(),
            "pair": pair,
            "direction": signal_data["direction"],
            "approved": approved,
            "model_approved": bool(parsed["approve"]),
            "confidence": round(confidence, 4),
            "risk_level": risk_level,
            "reason": str(parsed["reason"]).strip()[:320],
            "model": AI_MODEL,
        }
        with ai_lock:
            ai_state["last_decision"] = decision
            ai_state["last_error"] = ""
            ai_state["status"] = "Təsdiqləndi" if approved else "Rədd edildi"
        _event(
            "ai_signal_approved" if approved else "ai_signal_rejected",
            **decision,
        )
        if approved:
            _submit_confirmed_signal(signal_data)
    except Exception as exc:
        error = str(exc).strip()[:500] or type(exc).__name__
        fallback = bool(
            AI_DEMO_FALLBACK_ENABLED
            and _signal_entry_window_open(signal_data)
        )
        with ai_lock:
            ai_state["last_error"] = error
            ai_state["status"] = (
                "API xətası — yerli Demo strategiyası istifadə edildi"
                if fallback
                else "API xətası — siqnal vaxtı bitdi"
            )
        _event(
            "ai_signal_error",
            pair=pair,
            direction=signal_data["direction"],
            error=error,
            model=AI_MODEL,
        )
        if fallback:
            _event(
                "ai_signal_fallback",
                pair=pair,
                direction=signal_data["direction"],
                score=signal_data.get("score"),
                reason="OpenAI əlçatan deyil; təsdiqlənmiş yerli Demo strategiyası işlədildi",
            )
            log.warning(
                "AI təsdiqi alınmadı; yerli Demo strategiyası ilə davam edilir: %s",
                error,
            )
            _submit_confirmed_signal(signal_data)
        else:
            log.warning(
                "AI təsdiqi alınmadı və siqnal vaxtı bitdi; əməliyyat açılmadı: %s",
                error,
            )
    finally:
        with ai_lock:
            ai_pending_pairs.discard(pair)
            ai_state["pending"] = sorted(ai_pending_pairs)


def _queue_ai_signal_confirmation(signal_data: dict) -> None:
    pair = signal_data["pair"]
    with ai_lock:
        configured = bool(ai_state["configured"])
        if pair in ai_pending_pairs:
            _event(
                "ai_signal_skipped",
                pair=pair,
                direction=signal_data["direction"],
                reason="Aktiv üçün AI sorğusu artıq gözləyir",
            )
            return
        if not configured:
            fallback = bool(
                AI_DEMO_FALLBACK_ENABLED
                and _signal_entry_window_open(signal_data)
            )
            ai_state["status"] = (
                "AI hazır deyil — yerli Demo strategiyası istifadə edildi"
                if fallback
                else "AI hazır deyil — siqnal vaxtı bitdi"
            )
            ai_state["last_error"] = "OPENAI_API_KEY tapılmadı"
            _event(
                "ai_signal_error",
                pair=pair,
                direction=signal_data["direction"],
                error=ai_state["last_error"],
                model=AI_MODEL,
            )
            if fallback:
                _event(
                    "ai_signal_fallback",
                    pair=pair,
                    direction=signal_data["direction"],
                    score=signal_data.get("score"),
                    reason="OpenAI açarı yoxdur; təsdiqlənmiş yerli Demo strategiyası işlədildi",
                )
                _submit_confirmed_signal(signal_data)
            return
        ai_pending_pairs.add(pair)
        ai_state["pending"] = sorted(ai_pending_pairs)
        ai_state["status"] = "Siqnal yoxlanılır..."
        ai_state["requests"] = int(ai_state["requests"]) + 1
    threading.Thread(
        target=_run_ai_signal_confirmation,
        args=(signal_data,),
        name=f"ai-confirm-{pair}",
        daemon=True,
    ).start()


def process_signals_and_trade(pair: str, completed_bucket: int) -> None:
    with candles_lock:
        pair_candles = candles.get(pair)
        if not pair_candles:
            return
        completed = [
            candle for candle in pair_candles if candle["bucket"] <= completed_bucket
        ]
        closes = [float(candle["close"]) for candle in completed]
        opens = [float(candle["open"]) for candle in completed]
        highs = [float(candle["high"]) for candle in completed]
        lows = [float(candle["low"]) for candle in completed]
    required = _required_candles()
    if len(closes) < required:
        return

    rsi = _calc_rsi(closes)
    previous_rsi = _calc_rsi(closes[:-1])
    fast = _calc_ema(closes, EMA_FAST)
    slow = _calc_ema(closes, EMA_SLOW)
    previous_fast = _calc_ema(closes[:-1], EMA_FAST)
    trend_fast = _calc_ema(closes, TREND_EMA_FAST)
    trend_slow = _calc_ema(closes, TREND_EMA_SLOW)
    if None in (
        rsi,
        previous_rsi,
        fast,
        slow,
        previous_fast,
        trend_fast,
        trend_slow,
    ):
        return

    analysis = _score_signal(
        closes,
        opens,
        highs,
        lows,
        len(closes) - 1,
        float(rsi),
        float(fast),
        float(slow),
        float(previous_fast),
        float(trend_fast),
        float(trend_slow),
    )
    if not analysis["executable"]:
        return
    direction = str(analysis["direction"])
    with strategy_signal_lock:
        previous_bucket = last_strategy_signal_buckets.get(pair, 0)
        minimum_gap = SIGNAL_COOLDOWN_CANDLES * CANDLE_INTERVAL_SEC
        if int(completed_bucket) - int(previous_bucket) < minimum_gap:
            return
        last_strategy_signal_buckets[pair] = int(completed_bucket)
    latched_signal = _latch_display_signal(
        pair,
        int(completed_bucket),
        analysis,
    )
    if latched_signal is None:
        _event(
            "signal_rejected",
            pair=pair,
            direction=direction,
            score=analysis["score"],
            reason="Siqnal gecikib; 1 dəqiqəlik giriş pəncərəsi bitib",
        )
        return

    with candles_lock:
        latest = live_prices.get(pair, {})
        recent_candles = [
            {
                "bucket": int(candle["bucket"]),
                "open": round(float(candle["open"]), 8),
                "high": round(float(candle["high"]), 8),
                "low": round(float(candle["low"]), 8),
                "close": round(float(candle["close"]), 8),
            }
            for candle in completed[-25:]
        ]
    entry_price = float(latest.get("price", closes[-1]))
    validation = demo_execution_validation(pair, analysis)
    log.info(
        "DEMO SİQNAL: %s %s RSI=%.2f EMA%d=%.8f EMA%d=%.8f",
        pair,
        direction,
        rsi,
        EMA_FAST,
        fast,
        EMA_SLOW,
        slow,
    )
    _event(
        "demo_signal",
        pair=pair,
        direction=direction,
        rsi=rsi,
        previous_rsi=previous_rsi,
        ema_fast=fast,
        ema_slow=slow,
        trend_ema_fast=trend_fast,
        trend_ema_slow=trend_slow,
        score=analysis["score"],
        quality=analysis["quality"],
        trend_regime=analysis["trend_regime"],
        volatility=analysis["volatility"],
        reasons=analysis["reasons"],
        signal_started_at=datetime.fromtimestamp(
            float(latched_signal["created_at"]),
            timezone.utc,
        ).isoformat(),
        valid_until=datetime.fromtimestamp(
            float(latched_signal["valid_until"]),
            timezone.utc,
        ).isoformat(),
        auto_eligible=validation["eligible"],
        validation_reason=validation["reason"],
        strategy="ONE_MINUTE_TREND_V6",
        candle_bucket=completed_bucket,
    )
    if not validation["eligible"]:
        _event(
            "signal_rejected",
            pair=pair,
            direction=direction,
            score=analysis["score"],
            reason=f"Avtomatik Demo bloklandı: {validation['reason']}",
        )
        return
    signal_data = {
        "pair": pair,
        "direction": direction,
        "candle_bucket": int(completed_bucket),
        "rsi": round(float(rsi), 4),
        "previous_rsi": round(float(previous_rsi), 4),
        "ema_fast": round(float(fast), 8),
        "ema_slow": round(float(slow), 8),
        "trend_ema_fast": round(float(trend_fast), 8),
        "trend_ema_slow": round(float(trend_slow), 8),
        "entry_price": entry_price,
        "score": int(analysis["score"]),
        "quality": str(analysis["quality"]),
        "trend_regime": str(analysis["trend_regime"]),
        "volatility": str(analysis["volatility"]),
        "reasons": list(analysis["reasons"]),
        "validation": validation,
        "strategy": "ONE_MINUTE_TREND_V6",
        "timeframe_seconds": CANDLE_INTERVAL_SEC,
        "recent_candles": recent_candles,
    }
    if AI_CONFIRMATION_ENABLED:
        _queue_ai_signal_confirmation(signal_data)
    else:
        _submit_confirmed_signal(signal_data)


def _normalise_timestamp(raw_timestamp) -> float:
    timestamp = float(raw_timestamp)
    while timestamp > 10_000_000_000:
        timestamp /= 1000.0
    if timestamp <= 0:
        raise ValueError("Yanlış timestamp")
    return timestamp


def _extract_otp_ticks(parsed) -> list[dict]:
    ticks = []
    if not isinstance(parsed, list):
        return ticks
    for item in parsed:
        if not isinstance(item, dict) or item.get("e") != 1:
            continue
        data = item.get("d", [])
        if not isinstance(data, list):
            continue
        for raw in data:
            if not isinstance(raw, dict) or not {"p", "q", "t"} <= raw.keys():
                continue
            try:
                pair = str(raw["p"]).strip()
                price = float(raw["q"])
                timestamp = _normalise_timestamp(raw["t"])
            except (TypeError, ValueError):
                continue
            if pair and price > 0:
                ticks.append({"pair": pair, "price": price, "ts": timestamp})
    return ticks


PAIR_KEYS = ("p", "pair", "symbol", "asset", "instrument")
TIME_KEYS = ("t", "time", "timestamp", "ts", "bucket")
OHLC_ALIASES = {
    "open": ("o", "open"),
    "high": ("h", "high", "max"),
    "low": ("l", "low", "min"),
    "close": ("c", "close"),
}


def _looks_like_pair(value) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    return bool(
        2 <= len(text) <= 40
        and re.fullmatch(r"[A-Za-z0-9_./:-]+", text)
        and (
            "_OTC" in text.upper()
            or text.upper() == text
            or "/" in text
        )
    )


def _first_value(mapping: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _normalise_candle(
    pair,
    timestamp,
    open_price,
    high_price,
    low_price,
    close_price,
    ticks=0,
) -> dict | None:
    if not _looks_like_pair(pair):
        return None
    try:
        ts = _normalise_timestamp(timestamp)
        open_value = float(open_price)
        high_value = float(high_price)
        low_value = float(low_price)
        close_value = float(close_price)
        tick_count = max(0, int(ticks or 0))
    except (TypeError, ValueError, OverflowError):
        return None
    if (
        min(open_value, high_value, low_value, close_value) <= 0
        or high_value < max(open_value, close_value, low_value)
        or low_value > min(open_value, close_value, high_value)
    ):
        return None
    bucket = int(ts // CANDLE_INTERVAL_SEC) * CANDLE_INTERVAL_SEC
    return {
        "pair": str(pair).strip(),
        "bucket": bucket,
        "open": open_value,
        "high": high_value,
        "low": low_value,
        "close": close_value,
        "ticks": tick_count,
    }


def _extract_historical_market_data(parsed) -> tuple[list[dict], list[dict]]:
    historical_candles: list[dict] = []
    historical_ticks: list[dict] = []
    candle_seen = set()
    tick_seen = set()

    def visit(node, inherited_pair=None, event_code=None, depth=0):
        if depth > 12:
            return
        if isinstance(node, dict):
            pair = inherited_pair
            for key in PAIR_KEYS:
                candidate = node.get(key)
                if _looks_like_pair(candidate):
                    pair = str(candidate).strip()
                    break
            current_event = node.get("e", event_code)
            timestamp = _first_value(node, TIME_KEYS)
            values = {
                name: _first_value(node, aliases)
                for name, aliases in OHLC_ALIASES.items()
            }
            if pair and timestamp is not None and all(v is not None for v in values.values()):
                candle = _normalise_candle(
                    pair,
                    timestamp,
                    values["open"],
                    values["high"],
                    values["low"],
                    values["close"],
                    node.get("ticks", node.get("count", node.get("volume", 0))),
                )
                if candle is not None:
                    key = (candle["pair"], candle["bucket"])
                    if key not in candle_seen:
                        candle_seen.add(key)
                        historical_candles.append(candle)
            # e=1 canlı axınını mövcud parser emal edir. Digər event-lərdəki
            # p/q/t qeydləri tarixçi tick ola bilər.
            if (
                current_event != 1
                and pair
                and timestamp is not None
                and node.get("q") is not None
            ):
                try:
                    tick = {
                        "pair": pair,
                        "price": float(node["q"]),
                        "ts": _normalise_timestamp(timestamp),
                    }
                except (TypeError, ValueError, OverflowError):
                    tick = None
                if tick and tick["price"] > 0:
                    key = (tick["pair"], tick["ts"], tick["price"])
                    if key not in tick_seen:
                        tick_seen.add(key)
                        historical_ticks.append(tick)
            for value in node.values():
                if isinstance(value, (dict, list, tuple)):
                    visit(value, pair, current_event, depth + 1)
        elif isinstance(node, (list, tuple)):
            # Bir çox chart API-si şamı [timestamp, open, high, low, close]
            # kimi göndərir. Yalnız etibarlı pair konteksində qəbul edilir.
            if inherited_pair and 5 <= len(node) <= 8:
                candle = _normalise_candle(
                    inherited_pair,
                    node[0],
                    node[1],
                    node[2],
                    node[3],
                    node[4],
                    node[5] if len(node) > 5 else 0,
                )
                if candle is not None:
                    key = (candle["pair"], candle["bucket"])
                    if key not in candle_seen:
                        candle_seen.add(key)
                        historical_candles.append(candle)
            for value in node:
                if isinstance(value, (dict, list, tuple)):
                    visit(value, inherited_pair, event_code, depth + 1)

    visit(parsed)
    historical_candles.sort(key=lambda candle: (candle["pair"], candle["bucket"]))
    historical_ticks.sort(key=lambda tick: (tick["pair"], tick["ts"]))
    return historical_candles, historical_ticks


def _record_ws_shape(parsed) -> None:
    codes = []
    nodes = parsed if isinstance(parsed, list) else [parsed]
    for node in nodes[:50]:
        if isinstance(node, dict):
            code = node.get("e", "dict")
            keys = ",".join(sorted(str(key) for key in node.keys())[:12])
            codes.append(f"{code}:{keys}")
    if not codes:
        codes = [type(parsed).__name__]
    with state_lock:
        counts = state["ws_event_counts"]
        for signature in codes:
            counts[signature] = min(1_000_000, int(counts.get(signature, 0)) + 1)
        if len(counts) > 50:
            for key in sorted(counts, key=counts.get)[:-50]:
                counts.pop(key, None)


def _candles_from_ticks(ticks: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, int], dict] = {}
    for tick in ticks:
        bucket = int(tick["ts"] // CANDLE_INTERVAL_SEC) * CANDLE_INTERVAL_SEC
        key = (tick["pair"], bucket)
        candle = grouped.get(key)
        if candle is None:
            grouped[key] = {
                "pair": tick["pair"],
                "bucket": bucket,
                "open": tick["price"],
                "high": tick["price"],
                "low": tick["price"],
                "close": tick["price"],
                "ticks": 1,
                "_first_ts": tick["ts"],
                "_last_ts": tick["ts"],
            }
        else:
            candle["high"] = max(candle["high"], tick["price"])
            candle["low"] = min(candle["low"], tick["price"])
            candle["ticks"] += 1
            if tick["ts"] < candle["_first_ts"]:
                candle["_first_ts"] = tick["ts"]
                candle["open"] = tick["price"]
            if tick["ts"] > candle["_last_ts"]:
                candle["_last_ts"] = tick["ts"]
                candle["close"] = tick["price"]
    result = []
    for candle in grouped.values():
        candle.pop("_first_ts", None)
        candle.pop("_last_ts", None)
        result.append(candle)
    return sorted(result, key=lambda candle: (candle["pair"], candle["bucket"]))


def _merge_historical_candles(items: list[dict]) -> int:
    global _history_summary_logged
    if not items:
        return 0
    by_pair: dict[str, list[dict]] = {}
    for candle in items:
        by_pair.setdefault(candle["pair"], []).append(candle)
    loaded = 0
    persisted = []
    completed_candidates: list[tuple[str, int]] = []
    with candles_lock:
        for pair, incoming in by_pair.items():
            existing = list(candles.get(pair, ()))
            previous_latest = (
                int(existing[-1]["bucket"])
                if existing
                else None
            )
            merged = {int(candle["bucket"]): dict(candle) for candle in incoming}
            for candle in existing:
                bucket = int(candle["bucket"])
                if bucket in merged:
                    history = merged[bucket]
                    history["high"] = max(history["high"], candle["high"])
                    history["low"] = min(history["low"], candle["low"])
                    # Canlı şamın son qiyməti daha yenidir.
                    history["close"] = candle["close"]
                    history["ticks"] = max(history.get("ticks", 0), candle.get("ticks", 0))
                else:
                    merged[bucket] = dict(candle)
            ordered = [merged[bucket] for bucket in sorted(merged)][-MAX_CANDLES:]
            persisted.extend({"pair": pair, **candle} for candle in ordered)
            previous_buckets = {int(candle["bucket"]) for candle in existing}
            loaded += sum(int(candle["bucket"]) not in previous_buckets for candle in incoming)
            candles[pair] = deque(ordered, maxlen=MAX_CANDLES)
            incoming_latest = max(int(candle["bucket"]) for candle in incoming)
            if previous_latest is not None and incoming_latest > previous_latest:
                completed_candidates.append((pair, previous_latest))
    database.upsert_candles(persisted)
    if loaded:
        with state_lock:
            state["history_candles_loaded"] += loaded
            state["history_pairs"] = sorted(
                set(state["history_pairs"]) | set(by_pair)
            )
    # Bir yeni tamamlanmış şam adi bazar yenilənməsidir, siqnal deyil.
    # Jurnala yalnız başlanğıc/reconnect zamanı böyük tarixçə yükləməsini yaz.
    if loaded >= 10 and not _history_summary_logged:
        _event(
            "historical_candles_loaded",
            count=loaded,
            pairs=sorted(by_pair),
        )
        _history_summary_logged = True
    # OlympTrade bəzi aktivləri ayrıca tick deyil, dəqiqəlik tarixçə
    # yenilənməsi kimi göndərir. Yeni bucket gələndə əvvəlki şam tamamlanıb və
    # hər izlənən aktiv üçün strategiya ayrıca işlədilə bilər.
    selected_pairs = _resolved_watch_pairs()
    current_bucket = int(time.time() // CANDLE_INTERVAL_SEC) * CANDLE_INTERVAL_SEC
    for pair, completed_bucket in completed_candidates:
        if (
            pair in selected_pairs
            and 0 <= current_bucket - completed_bucket <= CANDLE_INTERVAL_SEC * 3
        ):
            process_signals_and_trade(pair, completed_bucket)
    return loaded


def _parse_payload(payload: str):
    try:
        return json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        starts = [
            index
            for index in (payload.find("["), payload.find("{"))
            if index >= 0
        ]
        if not starts:
            return None
        try:
            return json.loads(payload[min(starts) :])
        except json.JSONDecodeError:
            return None


def add_packet(direction: str, url: str, data=None) -> None:
    del url
    if data is None:
        return
    if isinstance(data, (bytes, bytearray)):
        try:
            payload = data.decode("utf-8")
        except UnicodeDecodeError:
            return
    else:
        payload = str(data)
    parsed = _parse_payload(payload)
    if parsed is None:
        return

    if direction == "RECV":
        _record_ws_shape(parsed)
        historical_candles, historical_ticks = _extract_historical_market_data(parsed)
        if historical_ticks:
            historical_candles.extend(_candles_from_ticks(historical_ticks))
        _merge_historical_candles(historical_candles)

    for tick in _extract_otp_ticks(parsed):
        pair = tick["pair"]
        completed_candle = None
        with candles_lock:
            live_prices[pair] = {"price": tick["price"], "ts": tick["ts"]}
            price_ticks.append(tick)
            bucket = int(tick["ts"] // CANDLE_INTERVAL_SEC) * CANDLE_INTERVAL_SEC
            pair_candles = candles.setdefault(pair, deque(maxlen=MAX_CANDLES))
            if pair_candles and pair_candles[-1]["bucket"] == bucket:
                candle = pair_candles[-1]
                candle["high"] = max(candle["high"], tick["price"])
                candle["low"] = min(candle["low"], tick["price"])
                candle["close"] = tick["price"]
                candle["ticks"] += 1
            elif not pair_candles or bucket > pair_candles[-1]["bucket"]:
                if pair_candles:
                    completed_candle = dict(pair_candles[-1])
                pair_candles.append(
                    {
                        "bucket": bucket,
                        "open": tick["price"],
                        "high": tick["price"],
                        "low": tick["price"],
                        "close": tick["price"],
                        "ticks": 1,
                    }
                )
            else:
                continue
        with state_lock:
            state["captured_count"] += 1
            state["active_pair"] = pair
        trade_engine.on_tick(pair, tick["price"], tick["ts"])
        if completed_candle is not None:
            database.upsert_candles([{"pair": pair, **completed_candle}])
            if pair in _resolved_watch_pairs():
                process_signals_and_trade(pair, completed_candle["bucket"])


def _first_visible(locator):
    try:
        for index in range(min(locator.count(), 20)):
            candidate = locator.nth(index)
            if candidate.is_visible():
                return candidate
    except Exception:
        return None
    return None


MONEY_TOKEN_RE = re.compile(
    r"(?:[₼Đ$€₺]\s*[\d][\d\s.,]*|(?:USD|AZN|EUR|TRY)\s*[\d][\d\s.,]*|"
    r"[\d][\d\s.,]*\s*(?:[₼Đ$€₺]|USD|AZN|EUR|TRY))",
    re.IGNORECASE,
)


def _parse_money(text: str) -> float | None:
    raw = re.sub(r"[^\d,.\-]", "", str(text or ""))
    if not raw or not re.search(r"\d", raw):
        return None
    negative = raw.startswith("-")
    raw = raw.lstrip("-")
    if "," in raw and "." in raw:
        decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        raw = raw.replace(thousands, "").replace(decimal, ".")
    elif "," in raw or "." in raw:
        separator = "," if "," in raw else "."
        parts = raw.split(separator)
        if len(parts) > 2 or (len(parts) == 2 and len(parts[-1]) == 3):
            raw = "".join(parts)
        else:
            raw = ".".join(parts)
    try:
        value = float(raw)
    except ValueError:
        return None
    return -value if negative else value


def _money_tokens(text: str) -> list[tuple[str, float]]:
    found = []
    for match in MONEY_TOKEN_RE.finditer(text or ""):
        token = re.sub(r"\s+", " ", match.group(0)).strip()
        value = _parse_money(token)
        if value is not None:
            found.append((token, value))
    return found


def _plain_number_tokens(text: str) -> list[tuple[str, float]]:
    found = []
    for match in re.finditer(r"\d[\d\s.,]*(?![\w%])", text or ""):
        token = re.sub(r"\s+", " ", match.group(0)).strip(" .,")
        value = _parse_money(token)
        if value is not None:
            found.append((token, value))
    return found


ACCOUNT_CONTEXT_DOM_SCRIPT = r"""
({labels}) => {
  const visible = el => {
    if (!el) return false;
    const style = getComputedStyle(el), rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const norm = value => String(value || '').replace(/\s+/g, ' ').trim();
  const wanted = labels.map(value => norm(value).toLocaleLowerCase());
  const elements = [...document.querySelectorAll('body *')];
  for (const element of elements) {
    if (!visible(element)) continue;
    const own = norm(element.innerText || element.textContent);
    if (!wanted.includes(own.toLocaleLowerCase())) continue;
    let box = element.parentElement;
    for (let depth = 0; box && depth < 7; depth++, box = box.parentElement) {
      const text = norm(box.innerText || box.textContent);
      const remainder = text.replace(own, ' ');
      if (/\d/.test(remainder)) return {label: own, context: text};
    }
    return {label: own, context: own};
  }
  return {label: '', context: ''};
}
"""


def _account_context(page) -> tuple[str, str]:
    try:
        result = page.evaluate(
            ACCOUNT_CONTEXT_DOM_SCRIPT,
            {
                "labels": [
                    "Deneme hesabı",
                    "Demo account",
                    "Practice account",
                ]
            },
        )
    except Exception:
        return "", ""
    if not isinstance(result, dict):
        return "", ""
    return str(result.get("label") or "").strip(), str(result.get("context") or "").strip()


def _inspect_platform_demo(page) -> None:
    account_label = ""
    balance_text = ""
    account_detected = False
    safety_detected = False

    # OlympTrade mətni daxili elementlərə bölə bildiyi üçün yalnız exact locator
    # yoxlamasına güvənmirik. innerText yalnız görünən UI mətnini qaytarır.
    try:
        body_text = page.locator("body").inner_text(timeout=2500)
    except Exception:
        body_text = ""
    compact = re.sub(r"\s+", " ", body_text).casefold()
    account_detected = any(
        phrase in compact
        for phrase in (
            "deneme hesab",
            "demo account",
            "practice account",
        )
    )
    safety_detected = any(
        phrase in compact
        for phrase in (
            "deneme hesabında gerçek işlemler yapılamaz",
            "gerçek işlemler yapılamaz",
            "real trades cannot be made",
        )
    )

    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        folded = line.casefold()
        if "deneme hesab" not in folded and "demo account" not in folded:
            continue
        account_label = line
        nearby = " ".join(lines[max(0, index - 2) : index + 2])
        candidates = _money_tokens(nearby)
        if candidates:
            # Hesab qalığı adətən hesab adının dərhal yanında və məbləğ
            # idarəsindən xeyli böyük olur.
            balance_text, _ = max(candidates, key=lambda item: item[1])
        break

    # DOM sırası vizual sıradan fərqli ola bilər. Hesab etiketinin ən yaxın
    # rəqəmli konteyneri balansı daha etibarlı verir.
    context_label, account_context = _account_context(page)
    if context_label:
        account_detected = True
        account_label = context_label
        context_money = _money_tokens(account_context)
        if context_money:
            balance_text, _ = max(context_money, key=lambda item: item[1])
        else:
            context_numbers = _plain_number_tokens(account_context)
            if context_numbers:
                balance_text, _ = max(context_numbers, key=lambda item: item[1])

    # Fallback: səhifə innerText/DOM evaluate vermirsə semantik locator istifadə edilir.
    account = _first_visible(
        page.get_by_text(
            re.compile(r"(Deneme hesabı|Demo account|Practice account)", re.IGNORECASE)
        )
    )
    if account is not None:
        account_detected = True
        if not account_label:
            account_label = account.inner_text().strip()
    if not safety_detected:
        marker = _first_visible(
            page.get_by_text(
                re.compile(
                    r"(gerçek işlemler yapılamaz|real trades cannot be made)",
                    re.IGNORECASE,
                )
            )
        )
        safety_detected = marker is not None

    if account is not None and not balance_text:
        ancestor = account
        for _ in range(6):
            try:
                ancestor = ancestor.locator("xpath=..")
                parent_text = ancestor.inner_text().strip()
            except Exception:
                break
            candidates = _money_tokens(parent_text)
            if candidates:
                balance_text, _ = max(candidates, key=lambda item: item[1])
                break
            numbers = _plain_number_tokens(
                re.sub(re.escape(account_label), " ", parent_text, flags=re.IGNORECASE)
            )
            if numbers:
                balance_text, _ = max(numbers, key=lambda item: item[1])
                break

    # Son ehtiyat: səhifədəki valyuta işarəli məbləğlərdən ən böyüyü adətən
    # hesab balansıdır. Bu yalnız hesab artıq Demo kimi təsdiqlənəndə işlədilir.
    if account_detected and not balance_text:
        all_money = _money_tokens(body_text)
        if all_money:
            balance_text, _ = max(all_money, key=lambda item: item[1])

    selected_label = re.sub(r"\s+", " ", account_label).strip().casefold()
    exact_demo_selected = selected_label in {
        "deneme hesabı",
        "demo account",
        "practice account",
    }
    real_account_visible = any(
        phrase in compact
        for phrase in (
            "real account",
            "live account",
            "gerçek hesap",
        )
    )
    # Bəzi platforma dillərində aşağıdakı təhlükəsizlik cümləsi göstərilmir.
    # Bu halda ekranda seçilmiş hesab etiketinin məhz Demo account olması kifayətdir.
    verified = (
        exact_demo_selected
        and not real_account_visible
        and (safety_detected or exact_demo_selected)
    )
    balance_value = _parse_money(balance_text)
    amount_control = _trade_amount_control(page)
    visible_trade_amount = (
        float(amount_control["value"])
        if amount_control.get("ok") and amount_control.get("value") is not None
        else None
    )
    with platform_lock:
        session_start = platform_state["session_start_balance"]
        if verified and balance_value is not None and session_start is None:
            session_start = balance_value
        configured_amount = platform_state["trade_amount"]
        platform_state.update(
            {
                "demo_verified": verified,
                "account_label": account_label,
                "balance_text": balance_text,
                "balance_value": balance_value,
                "session_start_balance": session_start,
                "platform_pnl": (
                    round(balance_value - session_start, 2)
                    if balance_value is not None and session_start is not None
                    else 0.0
                ),
                "trade_amount": configured_amount,
                "visible_trade_amount": visible_trade_amount,
                "safety_marker": safety_detected,
                "last_checked": time.time(),
                "last_error": (
                    ""
                    if verified
                    else "OlympTrade-də seçilmiş hesab Demo account kimi təsdiqlənmədi"
                ),
            }
        )


TRADE_AMOUNT_DOM_SCRIPT = r"""
({action}) => {
  const visible = el => {
    if (!el) return false;
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0;
  };
  const norm = value => String(value || '').replace(/\s+/g, ' ').trim();
  const parseMoney = value => {
    let raw = norm(value).replace(/[^\d,.\-]/g, '');
    if (!/\d/.test(raw)) return null;
    const negative = raw.startsWith('-'); raw = raw.replace(/^-/, '');
    if (raw.includes(',') && raw.includes('.')) {
      const decimal = raw.lastIndexOf(',') > raw.lastIndexOf('.') ? ',' : '.';
      const thousands = decimal === ',' ? '.' : ',';
      raw = raw.split(thousands).join('').replace(decimal, '.');
    } else if (raw.includes(',') || raw.includes('.')) {
      const sep = raw.includes(',') ? ',' : '.', parts = raw.split(sep);
      raw = parts.length > 2 || (parts.length === 2 && parts[1].length === 3)
        ? parts.join('') : parts.join('.');
    }
    const number = Number(raw);
    return Number.isFinite(number) ? (negative ? -number : number) : null;
  };
  const money = /^(?:[₼Đ$€₺]\s*\d[\d\s.,]*|(?:USD|AZN|EUR|TRY)\s*\d[\d\s.,]*|\d[\d\s.,]*\s*(?:[₼Đ$€₺]|USD|AZN|EUR|TRY))$/i;
  const plainNumber = /^\d[\d.,]*$/;
  const readText = el => norm(
    (el instanceof HTMLInputElement ? el.value : '') ||
    el.innerText || el.textContent || el.getAttribute('aria-valuenow')
  );
  const describe = el => norm(
    el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title')
  );
  const amountHeadings = [...document.querySelectorAll('body *')].filter(el => {
    if (!visible(el)) return false;
    const text = readText(el);
    return /^(?:tutar|amount|məbləğ)(?:\s*[,،:]|$)/i.test(text);
  });
  for (const heading of amountHeadings) {
    let box = heading;
    for (let depth = 0; box && depth < 6; depth++, box = box.parentElement) {
      const controls = [...box.querySelectorAll('button,[role="button"]')].filter(visible);
      if (controls.length < 2) continue;
      const candidates = [...box.querySelectorAll('input,[contenteditable="true"],body *')]
        .map(el => ({el, text: readText(el)}))
        .filter(item => visible(item.el) && (money.test(item.text) || plainNumber.test(item.text)));
      const selected = candidates.find(item => parseMoney(item.text) !== null);
      if (!selected) continue;
      const ordered = [...controls].sort(
        (a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left
      );
      const minus = controls.find(el => /^(?:-|−|–)$/.test(describe(el)) || /(minus|decrease|azalt)/i.test(describe(el))) || ordered[0];
      const plus = controls.find(el => /^\+$/.test(describe(el)) || /(plus|increase|artır)/i.test(describe(el))) || ordered[ordered.length - 1];
      if (!minus || !plus || minus === plus) continue;
      const value = parseMoney(selected.text);
      if (action === 'plus') plus.click();
      if (action === 'minus') minus.click();
      return {ok: true, text: selected.text, value};
    }
  }
  const labels = [...document.querySelectorAll('input,[contenteditable="true"],body *')]
    .filter(el => {
      const text = readText(el);
      return visible(el) && (money.test(text) || plainNumber.test(text));
    });
  for (const label of labels) {
    let box = label;
    for (let depth = 0; box && depth < 6; depth++, box = box.parentElement) {
      const controls = [...box.querySelectorAll('button,[role="button"]')].filter(visible);
      const minus = controls.find(el => /^(?:-|−|–)$/.test(describe(el)) || /(minus|decrease|azalt)/i.test(describe(el)));
      const plus = controls.find(el => /^\+$/.test(describe(el)) || /(plus|increase|artır)/i.test(describe(el)));
      if (!minus || !plus) continue;
      const text = readText(label), value = parseMoney(text);
      if (value === null) continue;
      if (action === 'plus') plus.click();
      if (action === 'minus') minus.click();
      return {ok: true, text, value};
    }
  }
  return {ok: false, text: '', value: null};
}
"""


def _trade_amount_control(page, action: str = "read") -> dict:
    try:
        result = page.evaluate(TRADE_AMOUNT_DOM_SCRIPT, {"action": action})
    except Exception as exc:
        return {"ok": False, "text": "", "value": None, "error": str(exc)}
    return result if isinstance(result, dict) else {"ok": False, "text": "", "value": None}


def _set_platform_trade_amount(page, target: int) -> tuple[bool, str]:
    target = int(target)
    for _ in range(501):
        current = _trade_amount_control(page)
        value = current.get("value")
        if not current.get("ok") or value is None:
            return False, "Platformdakı əməliyyat məbləği idarəsi tapılmadı"
        if math.isclose(float(value), float(target), abs_tol=0.001):
            with platform_lock:
                platform_state["visible_trade_amount"] = float(value)
            return True, ""
        action = "plus" if float(value) < target else "minus"
        clicked = _trade_amount_control(page, action)
        if not clicked.get("ok"):
            return False, "Platform məbləğinin +/- düyməsi işləmədi"
        page.wait_for_timeout(70)
    return False, "Məbləğ 500 addım daxilində qurula bilmədi"


def _find_platform_pair_tab(page, pair: str):
    """Return a visible open OlympTrade asset tab for ``pair``, if one exists."""
    labels = WATCH_PAIR_LABELS.get(pair, ())
    for label in labels:
        target = _first_visible(
            page.get_by_text(
                re.compile(rf"^{re.escape(label)}$", re.IGNORECASE)
            )
        )
        if target is not None:
            return target
    return None


def _select_platform_pair(page, pair: str) -> tuple[bool, str]:
    """Select the exact signal asset before any Demo trade button is clicked."""
    with state_lock:
        current_pair = state.get("active_pair")
    if current_pair == pair:
        return True, ""

    target = _find_platform_pair_tab(page, pair)
    if target is None:
        return (
            False,
            f"{pair} OlympTrade aktiv tablarında tapılmadı; yanlış aktivdə klik bloklandı",
        )
    try:
        target.click(timeout=3000)
    except Exception as exc:
        return False, f"{pair} aktivinə keçid alınmadı: {exc}"

    for _ in range(24):
        page.wait_for_timeout(250)
        with state_lock:
            current_pair = state.get("active_pair")
        if current_pair == pair:
            return True, ""
    return (
        False,
        f"Platform {pair} aktivinə keçidi canlı məlumatla təsdiqləmədi",
    )


def _rotate_market_scanner(page, now: float) -> None:
    with scanner_lock:
        if not scanner_state["enabled"]:
            return
        if now - float(scanner_state["last_rotation"]) < SCAN_ROTATION_SEC:
            return
    with platform_lock:
        platform_busy = bool(platform_orders or platform_pending)
    with trade_engine.lock:
        trade_busy = bool(trade_engine.open_positions)
    if platform_busy or trade_busy:
        with scanner_lock:
            scanner_state["status"] = "Demo əməliyyatı tamamlanır"
        return

    configured_pairs = [item["pair"] for item in _resolved_watch_assets()]
    if not configured_pairs:
        return
    with state_lock:
        current_pair = state.get("active_pair")
    available_pairs = []
    unavailable_pairs = []
    for pair in configured_pairs:
        if pair == current_pair or _find_platform_pair_tab(page, pair) is not None:
            available_pairs.append(pair)
        else:
            unavailable_pairs.append(pair)
    with scanner_lock:
        scanner_state["available_pairs"] = available_pairs
        scanner_state["unavailable_pairs"] = unavailable_pairs
    if not available_pairs:
        with scanner_lock:
            scanner_state["last_rotation"] = now
            scanner_state["target_pair"] = None
            scanner_state["status"] = "Açıq OlympTrade aktiv tabı tapılmadı"
            scanner_state["last_error"] = scanner_state["status"]
        return
    if len(available_pairs) == 1 and available_pairs[0] == current_pair:
        with scanner_lock:
            scanner_state["last_rotation"] = now
            scanner_state["target_pair"] = current_pair
            scanner_state["status"] = f"{current_pair} canlı axını aktivdir"
            scanner_state["last_error"] = ""
            if current_pair not in scanner_state["visited_pairs"]:
                scanner_state["visited_pairs"].append(current_pair)
        return
    pairs = available_pairs
    with scanner_lock:
        start = int(scanner_state["rotation_index"]) % len(pairs)
        target = pairs[start]
        for offset in range(len(pairs)):
            candidate = pairs[(start + offset) % len(pairs)]
            if candidate != current_pair:
                target = candidate
                scanner_state["rotation_index"] = (
                    start + offset + 1
                ) % len(pairs)
                break
        scanner_state["last_rotation"] = now
        scanner_state["target_pair"] = target
        scanner_state["status"] = f"{target} canlı axını yoxlanılır"

    ok, error = _select_platform_pair(page, target)
    with scanner_lock:
        scanner_state["last_error"] = error
        if ok:
            visited = list(scanner_state["visited_pairs"])
            if target not in visited:
                visited.append(target)
            scanner_state["visited_pairs"] = visited[-20:]
            scanner_state["status"] = f"{target} canlı axını aktivdir"
        else:
            scanner_state["status"] = f"{target} tabı tapılmadı"


def _mark_platform_order(order: dict, status: str, error: str = "") -> None:
    database.update_platform_status(order["trade_id"], status, error)
    if status == "CLICKED":
        if not trade_engine.confirm_platform_open(int(order["trade_id"])):
            error = "Platform kliki daxili əməliyyatla təsdiqlənmədi"
            status = "ERROR"
            database.update_platform_status(order["trade_id"], status, error)
            trade_engine.cancel_platform_open(int(order["trade_id"]), error)
    else:
        trade_engine.cancel_platform_open(int(order["trade_id"]), error)
    with platform_lock:
        platform_state["last_order"] = {
            **order,
            "status": status,
            "error": error,
            "updated_at": time.time(),
        }
        platform_state["last_error"] = error
    event_name = (
        "platform_demo_clicked"
        if status == "CLICKED"
        else "platform_demo_blocked"
    )
    _event(event_name, **order, status=status, error=error)


def _execute_platform_demo_order(page, order: dict) -> None:
    with platform_lock:
        enabled = bool(platform_state["execution_enabled"])
        verified = bool(platform_state["demo_verified"])
    if not enabled:
        _mark_platform_order(order, "CANCELLED", "Platform demo icrası söndürülüb")
        return
    pair_ok, pair_error = _select_platform_pair(page, str(order["pair"]))
    if not pair_ok:
        _mark_platform_order(order, "BLOCKED", pair_error)
        return
    # Hər klikdən dərhal əvvəl hesab yenidən yoxlanılır.
    _inspect_platform_demo(page)
    with platform_lock:
        verified = bool(platform_state["demo_verified"])
    if not verified:
        _mark_platform_order(
            order,
            "BLOCKED",
            "Real hesab qoruması: Deneme hesabı təsdiqlənmədi",
        )
        return
    with platform_lock:
        balance_before = platform_state["balance_value"]
    if balance_before is None:
        _mark_platform_order(
            order,
            "BLOCKED",
            "OlympTrade Deneme balansı oxunmadı; əməliyyat təhlükəsizlik üçün bloklandı",
        )
        return
    amount_ok, amount_error = _set_platform_trade_amount(
        page, int(round(float(order["amount"])))
    )
    if not amount_ok:
        _mark_platform_order(
            order,
            "BLOCKED",
            amount_error,
        )
        return

    duration_patterns = (
        r"(?:^|\W)1\s*(?:dk|dak(?:ika)?|dəq(?:iqə)?|deq(?:iqe)?)(?:\W|$)",
        r"(?:^|\W)1\s*(?:m|min(?:ute)?s?)(?:\W|$)",
        r"(?:^|\W)60\s*(?:s|sec(?:ond)?s?|san(?:iye)?)(?:\W|$)",
        r"(?:^|\W)00:01:00(?:\W|$)",
        r"(?:^|\W)0?1:00(?:\W|$)",
        r"(?:^|\W)00:01(?:\W|$)",
    )
    duration_found = False
    duration_locator = page.locator(
        'input,button,[role="button"],[role="spinbutton"],'
        '[aria-label],[title],[data-test],[data-testid]'
    )
    for index in range(min(duration_locator.count(), 1500)):
        candidate = duration_locator.nth(index)
        try:
            if not candidate.is_visible():
                continue
            candidate_text = " ".join(
                filter(
                    None,
                    (
                        candidate.get_attribute("value"),
                        candidate.get_attribute("aria-label"),
                        candidate.get_attribute("title"),
                        candidate.get_attribute("data-value"),
                        candidate.get_attribute("data-duration"),
                        candidate.inner_text(timeout=200),
                    ),
                )
            )
        except Exception:
            continue
        if any(
            re.search(pattern, candidate_text, re.IGNORECASE)
            for pattern in duration_patterns
        ):
            duration_found = True
            break
    if not duration_found:
        try:
            body_text = page.locator("body").inner_text(timeout=1000)
            duration_found = any(
                re.search(pattern, body_text, re.IGNORECASE)
                for pattern in duration_patterns
            )
        except Exception:
            duration_found = False
    if not duration_found:
        _mark_platform_order(
            order,
            "BLOCKED",
            "1 dəqiqəlik müddət UI-də tapılmadı",
        )
        return

    button_names = (
        ("Yukarı", "Yuxarı", "Up", "Higher", "Call", "Выше")
        if order["direction"] == "AL"
        else ("Aşağı", "Asagi", "Down", "Lower", "Put", "Ниже")
    )
    button = None
    button_name = button_names[0]

    # Prefer an exact accessible button name. OlympTrade sometimes appends the
    # payout percentage to that name, so the broader DOM scan below is only a
    # fallback.
    for candidate_name in button_names:
        candidate = _first_visible(
            page.get_by_role("button", name=candidate_name, exact=True)
        )
        if candidate is not None and candidate.is_enabled():
            button = candidate
            button_name = candidate_name
            break

    direction_pattern = re.compile(
        r"(?:^|\s)(?:"
        + "|".join(re.escape(name) for name in button_names)
        + r")(?:\s|$)",
        re.IGNORECASE,
    )
    candidates = page.locator('button,[role="button"]')
    fallback_indexes = range(min(candidates.count(), 1000)) if button is None else ()
    for index in fallback_indexes:
        candidate = candidates.nth(index)
        try:
            label = " ".join(
                filter(
                    None,
                    (
                        candidate.get_attribute("aria-label"),
                        candidate.get_attribute("title"),
                        candidate.inner_text(timeout=200),
                    ),
                )
            )
            label = re.sub(r"\s+", " ", label).strip()
            if (
                candidate.is_visible()
                and candidate.is_enabled()
                and direction_pattern.search(label)
            ):
                button = candidate
                button_name = label or button_names[0]
                break
        except Exception:
            continue

    if button is None:
        _mark_platform_order(
            order,
            "BLOCKED",
            "Demo istiqamət düyməsi tapılmadı: "
            + ", ".join(button_names),
        )
        return

    try:
        button.click(timeout=3000)
    except Exception as exc:
        _mark_platform_order(order, "ERROR", f"Demo klik xətası: {exc}")
        return
    with platform_lock:
        platform_pending[int(order["trade_id"])] = {
            **order,
            "balance_before": float(balance_before),
            "settle_after": time.time() + TRADE_DURATION_SEC + 8,
            "give_up_after": time.time() + TRADE_DURATION_SEC + 25,
        }
    _mark_platform_order(order, "CLICKED")
    log.warning(
        "OLYMPTRADE DEMO KLİK: #%s %s %s",
        order["trade_id"],
        order["pair"],
        button_name,
    )


def _process_platform_orders(page) -> None:
    for _ in range(5):
        with platform_lock:
            if not platform_orders:
                return
            order = platform_orders.popleft()
        _execute_platform_demo_order(page, order)


def _process_platform_commands(page) -> None:
    for _ in range(3):
        with platform_lock:
            if not platform_commands:
                return
            command = platform_commands.popleft()
        if command.get("type") == "set_amount":
            ok, error = _set_platform_trade_amount(page, int(command["amount"]))
            with platform_lock:
                platform_state["last_error"] = error
            _event(
                "platform_demo_amount_set",
                amount=command["amount"],
                ok=ok,
                error=error,
            )


def _settle_platform_orders() -> None:
    now = time.time()
    with platform_lock:
        balance_after = platform_state["balance_value"]
        pending = list(platform_pending.items())
    if balance_after is None:
        return
    for trade_id, item in pending:
        if now < float(item["settle_after"]):
            continue
        before = float(item["balance_before"])
        changed = not math.isclose(float(balance_after), before, abs_tol=0.005)
        if not changed and now < float(item["give_up_after"]):
            continue
        if trade_engine.resolve_platform_balance(
            trade_id, before, float(balance_after), now
        ):
            with platform_lock:
                platform_pending.pop(trade_id, None)
                platform_state["last_order"] = {
                    **item,
                    "status": "SETTLED",
                    "balance_after": float(balance_after),
                    "updated_at": now,
                }


def run_browser(stop_event: threading.Event) -> None:
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            no_viewport=True,
        )
        bound_pages: set[int] = set()

        def on_websocket(websocket):
            with state_lock:
                state["connected"] = True
            websocket.on(
                "framereceived",
                lambda frame: add_packet("RECV", websocket.url, frame),
            )
            websocket.on(
                "framesent",
                lambda frame: add_packet("SEND", websocket.url, frame),
            )

        def bind_page(candidate) -> None:
            if id(candidate) in bound_pages:
                return
            bound_pages.add(id(candidate))
            candidate.on("websocket", on_websocket)

        def find_or_open_platform_page():
            open_pages = [
                candidate
                for candidate in context.pages
                if not candidate.is_closed()
            ]
            for candidate in open_pages:
                if "olymptrade.com" in str(candidate.url).lower():
                    bind_page(candidate)
                    return candidate
            candidate = next(
                (
                    item
                    for item in open_pages
                    if str(item.url).lower() in {"", "about:blank"}
                ),
                None,
            )
            if candidate is None:
                candidate = context.new_page()
            bind_page(candidate)
            candidate.goto(
                "https://olymptrade.com/platform",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            return candidate

        context.on("page", bind_page)
        for existing_page in context.pages:
            bind_page(existing_page)
        page = find_or_open_platform_page()
        if "olymptrade.com" not in str(page.url).lower():
            page.goto(
                "https://olymptrade.com/platform",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
        # Bərpa edilmiş profildə qalan əlavə boş tabları göstərməyək.
        for extra_page in list(context.pages):
            if (
                extra_page is not page
                and not extra_page.is_closed()
                and str(extra_page.url).lower() in {"", "about:blank"}
            ):
                try:
                    extra_page.close()
                except Exception:
                    pass
        with state_lock:
            state["status"] = "Aktiv (DEMO)"
        log.info("OlympTrade açıldı. Təhlükəsiz DEMO mühərriki aktivdir")
        last_platform_check = 0.0
        try:
            while not stop_event.is_set():
                try:
                    if page.is_closed():
                        raise RuntimeError("OlympTrade səhifəsi bağlanıb")
                    page.wait_for_timeout(250)
                except Exception as exc:
                    if stop_event.is_set():
                        break
                    message = str(exc)
                    if not page.is_closed() and "Target page" not in message:
                        raise
                    with state_lock:
                        state["status"] = "OlympTrade səhifəsi bərpa edilir..."
                        state["connected"] = False
                    log.warning("OlympTrade səhifəsi bağlandı; yenidən açılır")
                    page = find_or_open_platform_page()
                    with state_lock:
                        state["status"] = "Aktiv (DEMO)"
                    continue
                now = time.time()
                if now - last_platform_check >= 1.0:
                    _inspect_platform_demo(page)
                    _settle_platform_orders()
                    last_platform_check = now
                _process_platform_commands(page)
                _process_platform_orders(page)
                _rotate_market_scanner(page, now)
        finally:
            try:
                context.close()
            except Exception as exc:
                log.warning("Brauzer artıq bağlanmışdı: %s", exc)


app = Flask(__name__)


@app.get("/")
def index():
    return "<h1>OlympBot Demo Engine</h1><p>Professional launcher istifadə edin.</p>"


@app.get("/api/status")
def api_status():
    with state_lock:
        general = dict(state)
    with candles_lock:
        market = {
            "pairs": len(candles),
            "live_prices": dict(live_prices),
            "recent_ticks": list(price_ticks)[-20:],
        }
    return jsonify(
        {
            "state": general,
            "market": market,
            "trading": trade_engine.snapshot(),
        }
    )


@app.get("/api/demo/trades")
def api_demo_trades():
    return jsonify({"trades": trade_engine.recent_trades(request.args.get("limit", 100))})


@app.get("/api/demo/stats")
def api_demo_stats():
    return jsonify(trade_engine.statistics())


@app.get("/api/platform-demo")
def api_platform_demo():
    with platform_lock:
        return jsonify(dict(platform_state))


@app.post("/api/platform-demo")
def api_platform_demo_control():
    payload = request.get_json(silent=True) or {}
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        return jsonify({"error": "enabled boolean olmalıdır"}), 400
    if enabled and payload.get("confirmation") != "DEMO":
        return jsonify({"error": "Platform Demo üçün DEMO təsdiqi tələb olunur"}), 400
    with platform_lock:
        if enabled and (
            not platform_state["demo_verified"]
        ):
            return jsonify(
                {
                    "error": (
                        "OlympTrade Deneme hesabı təsdiqlənməyib. "
                        "Sağ yuxarıda Deneme hesabı seçilməlidir."
                    )
                }
            ), 409
        platform_state["execution_enabled"] = enabled
        if not enabled:
            platform_orders.clear()
            platform_commands.clear()
    _event("platform_demo_mode_changed", enabled=enabled)
    return jsonify(
        {
            "ok": True,
            "execution_enabled": enabled,
            "message": (
                "OlympTrade Demo əməliyyatları aktivdir"
                if enabled
                else "OlympTrade Demo əməliyyatları söndürüldü"
            ),
        }
    )


@app.post("/api/platform-demo/amount")
def api_platform_demo_amount():
    payload = request.get_json(silent=True) or {}
    try:
        amount = int(payload.get("amount"))
    except (TypeError, ValueError):
        return jsonify({"error": "Məbləğ tam ədəd olmalıdır"}), 400
    if amount < 1 or amount > 10_000:
        return jsonify({"error": "Məbləğ 1–10.000 aralığında olmalıdır"}), 400
    with platform_lock:
        if not platform_state["demo_verified"]:
            return jsonify({"error": "Əvvəl OlympTrade Deneme hesabı təsdiqlənməlidir"}), 409
        platform_state["trade_amount"] = amount
        platform_commands.append({"type": "set_amount", "amount": amount})
    _event("platform_demo_amount_requested", amount=amount)
    return jsonify(
        {
            "ok": True,
            "amount": amount,
            "message": f"OlympTrade Demo əməliyyat məbləği {amount} olaraq seçildi",
        }
    )


@app.post("/api/demo/reset")
def api_demo_reset():
    payload = request.get_json(silent=True) or {}
    if payload.get("confirmation") != "RESET":
        return jsonify({"error": "Demo hesabını sıfırlamaq üçün RESET tələb olunur"}), 400
    trade_engine.reset()
    return jsonify({"ok": True, "message": "Demo hesabı sıfırlandı"})


def start_panel() -> None:
    app.run(
        host=PANEL_HOST,
        port=PANEL_PORT,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


def main() -> None:
    stop_event = threading.Event()

    def request_stop(signum=None, frame=None):
        del signum, frame
        stop_event.set()

    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(signal_name, request_stop)
        except (ValueError, OSError):
            pass

    threading.Thread(target=start_panel, name="demo-panel", daemon=True).start()
    try:
        run_browser(stop_event)
    except KeyboardInterrupt:
        request_stop()
    except Exception as exc:
        with state_lock:
            state["status"] = "Xəta"
            state["last_error"] = str(exc)
        log.exception("Demo bot dayandı: %s", exc)
        raise
    finally:
        log.info("Demo bot dayandırıldı")


if __name__ == "__main__":
    main()
