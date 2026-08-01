from __future__ import annotations

import csv
import io
import json
import os
import runpy
import signal
import socket
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from flask import Response, jsonify, request


APP_DIR = Path(__file__).resolve().parent
BOT_DIR = APP_DIR / "runtime"
CORE_FILE = APP_DIR / "olympbot_demo_core.py"
LEGACY_PROFILE = Path.home() / "Desktop" / "Olymptrade" / "olymp_user_data"


def _load_local_env(path: Path) -> None:
    """Load local settings without ever logging secret values."""
    if not path.is_file():
        return
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            name = name.strip()
            if name not in {
                "OPENAI_API_KEY",
                "OPENAI_MODEL",
                "AI_CONFIRMATION_ENABLED",
                "AI_MIN_CONFIDENCE",
            }:
                continue
            value = value.strip().strip("\"'")
            if value:
                os.environ.setdefault(name, value)
    except OSError:
        pass


_load_local_env(APP_DIR / ".env.local")

if sys.version_info < (3, 12):
    raise SystemExit(
        "OlympBot Professional Python 3.12 və ya daha yeni versiya tələb edir.\n"
        f"Cari versiya: {sys.version_info.major}.{sys.version_info.minor}"
    )

if not CORE_FILE.is_file():
    raise SystemExit(
        "Demo bot mühərriki tapılmadı:\n"
        f"{CORE_FILE}\n\n"
        "olympbot_demo_core.py faylının launcher ilə eyni qovluqda olduğunu yoxlayın."
    )

# Botu Desktop-dakı köhnə fayl və kilidlərdən tam ayırırıq. Jurnal, verilənlər
# bazası və brauzer profili launcher-in yanındakı runtime qovluğunda saxlanılır.
BOT_DIR.mkdir(parents=True, exist_ok=True)
os.chdir(APP_DIR)
os.environ.setdefault("PANEL_HOST", "127.0.0.1")
os.environ.setdefault("PANEL_PORT", "5000")
os.environ.setdefault("LIVE_TRADING", "false")
os.environ.setdefault("PLATFORM_DEMO_EXECUTION", "true")
os.environ.setdefault("BOT_DIR", str(BOT_DIR))
os.environ.setdefault("DEMO_DATA_DIR", str(BOT_DIR / "data"))
# Əvvəlki versiyada giriş edilmiş OlympTrade sessiyası varsa onu qoruyuruq.
# Beləliklə istifadəçi hesab məlumatlarını yenidən yazmağa məcbur olmur.
browser_profile = (
    LEGACY_PROFILE
    if (LEGACY_PROFILE / "Default").is_dir()
    else BOT_DIR / "browser-profile"
)
os.environ.setdefault("USER_DATA_DIR", str(browser_profile))

core = runpy.run_path(str(CORE_FILE), run_name="olympbot_professional_demo_core")
core_globals = core["run_browser"].__globals__
app = core["app"]
stop_event = threading.Event()
started_at = time.time()


DASHBOARD_HTML = r"""<!doctype html>
<html lang="az">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OlympBot Demo Terminal v6.3 — Server 24/7</title>
  <style>
    :root {
      --bg: #071018;
      --panel: rgba(16, 29, 42, .82);
      --panel-2: rgba(10, 21, 32, .9);
      --line: rgba(148, 180, 207, .14);
      --text: #eef6fb;
      --muted: #91a8b9;
      --cyan: #28d7d0;
      --green: #5ce1a2;
      --red: #ff6b7d;
      --amber: #ffc857;
      --blue: #62a8ff;
      --shadow: 0 18px 55px rgba(0, 0, 0, .28);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 12% 0%, rgba(40, 215, 208, .14), transparent 28rem),
        radial-gradient(circle at 92% 12%, rgba(98, 168, 255, .12), transparent 30rem),
        var(--bg);
    }
    button { font: inherit; }
    input {
      width: 92px; color: var(--text); background: rgba(255,255,255,.04);
      border: 1px solid var(--line); border-radius: 10px; padding: 9px 10px;
      font: inherit;
    }
    .shell { max-width: 1460px; margin: auto; padding: 26px; }
    header {
      display: flex; align-items: center; justify-content: space-between;
      gap: 20px; margin-bottom: 24px;
    }
    .brand { display: flex; align-items: center; gap: 13px; }
    .logo {
      width: 44px; height: 44px; display: grid; place-items: center;
      border-radius: 13px; font-weight: 900; letter-spacing: -.08em;
      background: linear-gradient(145deg, var(--cyan), #1682a8);
      box-shadow: 0 8px 28px rgba(40, 215, 208, .25);
    }
    h1 { margin: 0; font-size: 21px; letter-spacing: -.02em; }
    .subtitle { color: var(--muted); font-size: 12px; margin-top: 3px; }
    .actions { display: flex; gap: 9px; align-items: center; flex-wrap: wrap; }
    .btn {
      border: 1px solid var(--line); color: var(--text); background: rgba(255,255,255,.04);
      border-radius: 10px; padding: 9px 13px; cursor: pointer; transition: .18s ease;
      text-decoration: none; font: inherit;
    }
    .btn:hover { transform: translateY(-1px); border-color: rgba(40,215,208,.48); }
    .btn-live { background: rgba(255,107,125,.12); color: #ffabb5; }
    .btn-dry { background: rgba(40,215,208,.11); color: #7ce7e2; }
    .btn-stop { color: var(--muted); }
    .badge {
      display: inline-flex; align-items: center; gap: 7px; padding: 7px 10px;
      border-radius: 999px; font-size: 12px; font-weight: 700;
      border: 1px solid var(--line); background: rgba(255,255,255,.035);
    }
    .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--muted); }
    .dot.ok { background: var(--green); box-shadow: 0 0 0 5px rgba(92,225,162,.1); }
    .dot.warn { background: var(--amber); box-shadow: 0 0 0 5px rgba(255,200,87,.1); }
    .dot.bad { background: var(--red); box-shadow: 0 0 0 5px rgba(255,107,125,.1); }
    .grid { display: grid; gap: 15px; }
    .metrics { grid-template-columns: repeat(6, minmax(0, 1fr)); margin-bottom: 15px; }
    .main-grid { grid-template-columns: minmax(0, 1.65fr) minmax(320px, .85fr); }
    .lower-grid { grid-template-columns: 1.15fr .85fr; margin-top: 15px; }
    .card {
      border: 1px solid var(--line); border-radius: 16px; background: var(--panel);
      backdrop-filter: blur(16px); box-shadow: var(--shadow); overflow: hidden;
    }
    .metric { padding: 17px 18px; min-height: 103px; }
    .metric-label { color: var(--muted); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
    .metric-value { margin-top: 11px; font-size: 24px; font-weight: 750; letter-spacing: -.03em; }
    .metric-note { margin-top: 5px; font-size: 11px; color: var(--muted); }
    .signal-terminal { margin-bottom: 15px; }
    .signal-grid {
      display: grid; grid-template-columns: repeat(5, minmax(190px, 1fr));
      gap: 10px; padding: 14px;
    }
    .signal-card {
      position: relative; min-height: 185px; padding: 15px; overflow: hidden;
      border: 1px solid var(--line); border-radius: 14px;
      background: linear-gradient(145deg, rgba(255,255,255,.045), rgba(255,255,255,.012));
      cursor: pointer; transition: transform .18s ease, border-color .18s ease;
    }
    .signal-card:hover { transform: translateY(-2px); border-color: rgba(98,168,255,.42); }
    .signal-card.up { border-color: rgba(92,225,162,.34); background: linear-gradient(145deg, rgba(92,225,162,.11), rgba(255,255,255,.012)); }
    .signal-card.down { border-color: rgba(255,107,125,.34); background: linear-gradient(145deg, rgba(255,107,125,.11), rgba(255,255,255,.012)); }
    .signal-card.candidate { opacity: .72; border-style: dashed; }
    .signal-card.active-signal { box-shadow: 0 0 0 1px rgba(255,200,87,.14), 0 14px 35px rgba(0,0,0,.24); }
    .signal-card.ready::after {
      content: 'DEMO READY'; position: absolute; top: 10px; right: -27px;
      width: 105px; padding: 4px 0; transform: rotate(38deg);
      text-align: center; font-size: 8px; font-weight: 900; letter-spacing: .08em;
      color: #071018; background: var(--amber);
    }
    .signal-top { display: flex; justify-content: space-between; gap: 8px; align-items: flex-start; }
    .signal-name { font-size: 12px; font-weight: 800; }
    .signal-pair { color: var(--muted); font-size: 9px; margin-top: 2px; }
    .signal-score { font-size: 23px; line-height: 1; font-weight: 850; letter-spacing: -.05em; }
    .signal-score small { color: var(--muted); font-size: 9px; letter-spacing: 0; }
    .signal-direction { margin-top: 18px; font-size: 21px; font-weight: 900; letter-spacing: -.035em; }
    .signal-card.up .signal-direction { color: var(--green); }
    .signal-card.down .signal-direction { color: var(--red); }
    .signal-card.wait .signal-direction { color: var(--amber); }
    .signal-strength { height: 5px; margin-top: 10px; overflow: hidden; border-radius: 99px; background: rgba(255,255,255,.08); }
    .signal-strength span { display: block; height: 100%; border-radius: inherit; background: var(--amber); }
    .signal-card.up .signal-strength span { background: var(--green); }
    .signal-card.down .signal-strength span { background: var(--red); }
    .signal-meta { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 11px; }
    .signal-meta span { padding: 4px 6px; border-radius: 6px; color: var(--muted); background: rgba(255,255,255,.04); font-size: 9px; }
    .signal-reason { margin-top: 9px; color: var(--muted); font-size: 10px; line-height: 1.35; }
    .signal-history-head {
      display: flex; justify-content: space-between; align-items: center;
      padding: 13px 18px; border-top: 1px solid var(--line);
      border-bottom: 1px solid var(--line); background: rgba(0,0,0,.10);
    }
    .signal-history { max-height: 260px; overflow: auto; }
    .signal-history-row {
      display: grid; grid-template-columns: 90px minmax(150px,1fr) 120px 90px 125px 85px;
      gap: 12px; align-items: center; padding: 12px 18px;
      border-bottom: 1px solid var(--line); font-size: 11px;
    }
    .signal-history-row:last-child { border-bottom: 0; }
    .history-time { font-variant-numeric: tabular-nums; font-weight: 750; }
    .history-direction { font-weight: 850; }
    .history-direction.up { color: var(--green); }
    .history-direction.down { color: var(--red); }
    .history-status { text-align: right; font-weight: 800; color: var(--muted); }
    .history-status.active { color: var(--amber); }
    .card-head {
      padding: 16px 18px; display: flex; justify-content: space-between; align-items: center;
      border-bottom: 1px solid var(--line);
    }
    .card-title { font-size: 13px; font-weight: 750; }
    .card-note { color: var(--muted); font-size: 11px; }
    .chart-wrap { height: 390px; padding: 14px 14px 6px; position: relative; }
    .rsi-wrap { height: 125px; padding: 4px 14px 14px; position: relative; border-top: 1px solid var(--line); }
    .chart-tools { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .tool-btn {
      border: 1px solid var(--line); color: var(--muted); background: rgba(255,255,255,.025);
      border-radius: 8px; padding: 6px 9px; cursor: pointer; font-size: 11px;
    }
    .tool-btn.active { color: var(--cyan); border-color: rgba(40,215,208,.45); background: rgba(40,215,208,.1); }
    .legend { display: flex; gap: 10px; color: var(--muted); font-size: 10px; margin-top: 5px; }
    .legend span::before { content: ''; display:inline-block; width:9px; height:2px; margin-right:4px; vertical-align:middle; background:var(--legend); }
    .chart-hover {
      position: absolute; top: 12px; left: 14px; z-index: 3; pointer-events: none;
      color: var(--text); background: rgba(7,16,24,.84); border: 1px solid var(--line);
      border-radius: 8px; padding: 6px 8px; font-size: 10px; display: none;
    }
    canvas { width: 100%; height: 100%; display: block; }
    .empty {
      position: absolute; inset: 0; display: grid; place-items: center;
      color: var(--muted); font-size: 13px; pointer-events: none;
    }
    .asset-list { max-height: 330px; overflow: auto; }
    .asset-row {
      display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: center;
      padding: 13px 17px; border-bottom: 1px solid var(--line); cursor: pointer;
    }
    .asset-row:hover { background: rgba(255,255,255,.025); }
    .asset-row.active { background: rgba(40,215,208,.065); }
    .pair { font-weight: 720; font-size: 13px; }
    .small { color: var(--muted); font-size: 11px; margin-top: 3px; }
    .price { font-variant-numeric: tabular-nums; font-weight: 700; text-align: right; }
    .progress { height: 5px; background: rgba(255,255,255,.07); border-radius: 99px; margin-top: 7px; overflow: hidden; }
    .progress > span { height: 100%; display: block; background: linear-gradient(90deg, var(--blue), var(--cyan)); }
    .events { max-height: 330px; overflow: auto; }
    .event { display: grid; grid-template-columns: 10px 1fr auto; gap: 11px; padding: 13px 17px; border-bottom: 1px solid var(--line); }
    .event-mark { width: 7px; height: 7px; border-radius: 50%; margin-top: 5px; background: var(--blue); }
    .event.signal .event-mark { background: var(--amber); }
    .event.trade .event-mark { background: var(--green); }
    .event.reject .event-mark { background: var(--red); }
    .event-name { font-size: 12px; font-weight: 700; }
    .event-detail { color: var(--muted); font-size: 11px; margin-top: 3px; }
    .event-time { color: var(--muted); font-size: 10px; white-space: nowrap; }
    .risk { padding: 16px 18px; }
    .risk-row { display: flex; justify-content: space-between; gap: 14px; padding: 10px 0; border-bottom: 1px solid var(--line); font-size: 12px; }
    .risk-row:last-child { border: 0; }
    .risk-key { color: var(--muted); }
    .warning {
      margin-top: 14px; border: 1px solid rgba(255,200,87,.22); border-radius: 11px;
      padding: 11px 12px; color: #f5d891; background: rgba(255,200,87,.07);
      font-size: 11px; line-height: 1.5;
    }
    .system-error {
      display: none; margin: -9px 0 15px; border-color: rgba(255,107,125,.4);
      color: #ffbbc3; background: rgba(255,107,125,.08);
    }
    .toast {
      position: fixed; right: 24px; bottom: 24px; max-width: 390px;
      padding: 13px 15px; border: 1px solid var(--line); border-radius: 12px;
      background: #132231; box-shadow: var(--shadow); font-size: 12px;
      opacity: 0; transform: translateY(10px); pointer-events: none; transition: .2s ease;
    }
    .toast.show { opacity: 1; transform: translateY(0); }
    .toast.error { border-color: rgba(255,107,125,.4); color: #ffbbc3; }
    footer { text-align: center; color: #617789; font-size: 10px; padding: 22px 0 4px; }
    @media (max-width: 1050px) {
      .metrics { grid-template-columns: repeat(3, 1fr); }
      .signal-grid { grid-template-columns: repeat(3, 1fr); }
      .main-grid, .lower-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 650px) {
      .shell { padding: 16px; } header { align-items: flex-start; flex-direction: column; }
      .metrics { grid-template-columns: repeat(2, 1fr); }
      .signal-grid { grid-template-columns: 1fr; }
      .signal-history-row { grid-template-columns: 75px 1fr 90px 65px; }
      .signal-history-row .history-score, .signal-history-row .history-end { display:none; }
      .metric:last-child { grid-column: 1 / -1; }
      .chart-wrap { height: 300px; }
      .rsi-wrap { height: 110px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div class="brand">
        <div class="logo">OB</div>
        <div>
          <h1>OlympBot Demo Terminal <span style="color:var(--cyan)">v6.3 · SERVER 24/7</span></h1>
          <div class="subtitle">Çoxfaktorlu siqnal mərkəzi · risk nəzarəti · Demo icrası</div>
        </div>
      </div>
      <div class="actions">
        <span class="badge"><span id="connectionDot" class="dot"></span><span id="connectionText">Yoxlanılır</span></span>
        <span class="badge"><span id="platformDot" class="dot"></span><span id="platformText">Demo hesab yoxlanılır</span></span>
        <input id="tradeAmount" type="number" min="1" max="10000" step="1" value="1" title="OlympTrade Demo əməliyyat məbləği">
        <button class="btn btn-dry" onclick="saveTradeAmount()">Məbləği yaz</button>
        <a class="btn btn-dry" href="/api/export/trades.csv">Hesabat CSV</a>
        <button id="scannerButton" class="btn btn-dry" onclick="toggleScanner()">Skan: aktiv</button>
        <button id="platformButton" class="btn btn-live" onclick="togglePlatformDemo()">OlympTrade Demo qoş</button>
        <button class="btn btn-stop" onclick="stopBot()">Botu dayandır</button>
      </div>
    </header>
    <div id="systemError" class="warning system-error"></div>

    <section class="grid metrics">
      <div class="card metric"><div class="metric-label">Rejim</div><div id="mode" class="metric-value">DEMO</div><div id="modeNote" class="metric-note">Real kliklər söndürülüb</div></div>
      <div class="card metric"><div class="metric-label">OlympTrade balansı</div><div id="balance" class="metric-value">—</div><div class="metric-note">Deneme hesabından canlı oxunur</div></div>
      <div class="card metric"><div class="metric-label">Sessiya P&amp;L</div><div id="pnl" class="metric-value">—</div><div id="tradeCount" class="metric-note">Platform balans fərqi</div></div>
      <div class="card metric"><div class="metric-label">Win rate</div><div id="winRate" class="metric-value">0%</div><div id="winLoss" class="metric-note">0W / 0L</div></div>
      <div class="card metric"><div class="metric-label">Qəbul edilən tick</div><div id="tickCount" class="metric-value">0</div><div id="pairCount" class="metric-note">0 aktiv</div></div>
      <div class="card metric"><div class="metric-label">İş müddəti</div><div id="uptime" class="metric-value">00:00</div><div class="metric-note">Panel aktivdir</div></div>
    </section>

    <section class="card signal-terminal">
      <div class="card-head">
        <div>
          <div class="card-title">CANLI SİQNAL MƏRKƏZİ</div>
          <div class="card-note">EMA 3/8 giriş · EMA 15/50 əsas trend · RSI 9 · şam gücü</div>
        </div>
        <span id="liveSignalCount" class="badge">0 güclü siqnal</span>
      </div>
      <div id="signalCenter" class="signal-grid">
        <div class="empty" style="position:relative;height:150px;grid-column:1/-1">Bazar analizi hazırlanır…</div>
      </div>
      <div class="signal-history-head">
        <div>
          <div class="card-title">SİQNAL TARİXÇƏSİ</div>
          <div class="card-note">Təsdiqlənmiş siqnallar · ən yenisi yuxarıda</div>
        </div>
        <span id="signalHistoryCount" class="badge">0 siqnal</span>
      </div>
      <div id="signalHistory" class="signal-history">
        <div class="empty" style="position:relative;height:90px">Təsdiqlənmiş siqnal hələ yoxdur</div>
      </div>
    </section>

    <section class="grid main-grid">
      <div class="card">
        <div class="card-head">
          <div>
            <div id="chartTitle" class="card-title">Canlı şam qrafiki</div>
            <div id="chartSubtitle" class="card-note">Aktiv seçilməyib</div>
            <div class="legend"><span style="--legend:#ffd166">EMA 3</span><span style="--legend:#62a8ff">EMA 8</span><span style="--legend:#b084ff">RSI 9</span></div>
          </div>
          <div class="chart-tools">
            <button id="tf1" class="tool-btn active" onclick="setTimeframe(1)">1m</button>
            <button id="tf5" class="tool-btn" onclick="setTimeframe(5)">5m</button>
            <button id="tf15" class="tool-btn" onclick="setTimeframe(15)">15m</button>
            <button class="tool-btn" onclick="panChart(1)">←</button>
            <button class="tool-btn" onclick="panChart(-1)">→</button>
            <button class="tool-btn" onclick="zoomChart(10)">−</button>
            <button class="tool-btn" onclick="zoomChart(-10)">+</button>
            <span id="lastPrice" class="badge">—</span>
          </div>
        </div>
        <div class="chart-wrap">
          <canvas id="priceChart"></canvas>
          <div id="chartHover" class="chart-hover"></div>
          <div id="chartEmpty" class="empty">Şam məlumatı gözlənilir…</div>
        </div>
        <div class="rsi-wrap">
          <canvas id="rsiChart"></canvas>
          <div id="rsiEmpty" class="empty">RSI üçün ən azı 15 şam lazımdır</div>
        </div>
      </div>
      <div class="card">
        <div class="card-head"><div><div class="card-title">Aktivlər</div><div class="card-note">Şam hazırlığı və son qiymət</div></div><span id="warmupLabel" class="badge">0 / 22</span></div>
        <div id="assetList" class="asset-list"><div class="empty" style="position:relative;height:220px">Aktivlər gözlənilir…</div></div>
      </div>
    </section>

    <section class="grid lower-grid">
      <div class="card">
        <div class="card-head"><div><div class="card-title">Hadisələr və siqnallar</div><div class="card-note">Ən yeni hadisələr yuxarıda</div></div><span id="eventCount" class="badge">0 hadisə</span></div>
        <div id="events" class="events"><div class="empty" style="position:relative;height:220px">Siqnal hələ yaranmayıb</div></div>
      </div>
      <div class="card">
        <div class="card-head"><div><div class="card-title">Risk nəzarəti</div><div class="card-note">Cari ticarət mühərriki</div></div></div>
        <div class="risk">
          <div class="risk-row"><span class="risk-key">Açıq demo əməliyyatları</span><strong id="awaiting">0</strong></div>
          <div class="risk-row"><span class="risk-key">OlympTrade hesabı</span><strong id="platformAccount">Təsdiqlənməyib</strong></div>
          <div class="risk-row"><span class="risk-key">Platform balansı</span><strong id="platformBalance">—</strong></div>
          <div class="risk-row"><span class="risk-key">Seçilmiş əməliyyat məbləği</span><strong id="configuredAmount">—</strong></div>
          <div class="risk-row"><span class="risk-key">Platformda görünən məbləğ</span><strong id="visibleAmount">—</strong></div>
          <div class="risk-row"><span class="risk-key">Son platform əmri</span><strong id="platformOrder">—</strong></div>
          <div class="risk-row"><span class="risk-key">OpenAI təsdiqi</span><strong id="aiStatus">—</strong></div>
          <div class="risk-row"><span class="risk-key">AI modeli</span><strong id="aiModel">—</strong></div>
          <div class="risk-row"><span class="risk-key">Son AI qərarı</span><strong id="aiDecision">—</strong></div>
          <div class="risk-row"><span class="risk-key">Risk mühərriki</span><strong id="riskStatus">AKTİV</strong></div>
          <div class="risk-row"><span class="risk-key">Bugünkü P&amp;L</span><strong id="dailyPnl">+0.00</strong></div>
          <div class="risk-row"><span class="risk-key">Bugünkü əməliyyatlar</span><strong id="dailyTrades">0 / 20</strong></div>
          <div class="risk-row"><span class="risk-key">Ardıcıl zərərlər</span><strong id="consecutiveLosses">0 / 3</strong></div>
          <div class="risk-row"><span class="risk-key">Maksimum məbləğ</span><strong id="maxStake">—</strong></div>
          <div class="risk-row"><span class="risk-key">Martinqeyl</span><strong style="color:var(--green)">SÖNDÜRÜLÜB</strong></div>
          <div class="risk-row"><span class="risk-key">Strategiya</span><strong>1M Trend v6 · EMA 3/8 · RSI 9 · trend 15/50</strong></div>
          <div class="warning">Bot yalnız seçilmiş hesab “Deneme hesabı” və ya “Demo account” olduqda işləyir. Deterministik siqnal OpenAI tərəfindən əlavə yoxlanır; AI təsdiqi alınmasa əməliyyat bloklanır. Real hesab, oxunmayan balans, yanlış aktiv və ya təsdiqlənməyən məbləğ halında klik edilmir.</div>
        </div>
      </div>
    </section>
    <section class="card" style="margin-top:15px">
      <div class="card-head">
        <div>
          <div class="card-title">Tarixi backtest · 1 dəqiqə</div>
          <div class="card-note">Yalnız tamamlanmış şamlar · AI daxil deyil · gələcək məlumat istifadə olunmur</div>
        </div>
        <span id="backtestSummary" class="badge">Hesablanır…</span>
      </div>
      <div id="backtestList" class="asset-list">
        <div class="empty" style="position:relative;height:140px">Tarixi nəticələr hesablanır…</div>
      </div>
      <div class="warning" style="margin:14px 18px">Tarixi nəticə gələcək qazanca zəmanət vermir. OOS son 30% şam üzrə ayrıca yoxlamadır; az nümunəli nəticələr etibarlı sayılmamalıdır.</div>
    </section>
    <footer>OlympBot Demo Terminal v6.3 · 1 dəqiqə · Auto Demo · 24/7 server rejimi</footer>
  </div>
  <div id="toast" class="toast"></div>

  <script>
    let selectedPair = null;
    let snapshot = null;
    let timeframeMinutes = 1;
    let visibleCandles = 60;
    let candleOffset = 0;
    let chartGeometry = null;
    const $ = id => document.getElementById(id);
    const fmt = value => value == null || !Number.isFinite(Number(value))
      ? '—' : Number(value).toLocaleString('en-US', {maximumFractionDigits: 8});
    const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

    function toast(message, error=false) {
      const el = $('toast'); el.textContent = message; el.className = 'toast show' + (error ? ' error' : '');
      clearTimeout(window.toastTimer); window.toastTimer = setTimeout(() => el.className = 'toast', 3500);
    }

    function duration(seconds) {
      seconds = Math.max(0, Math.floor(seconds));
      const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
      return h > 0 ? `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}` : `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    }

    function render(data) {
      snapshot = data;
      const state = data.state, trading = data.trading, demo = data.demo || {}, platform = trading.platform_demo || {}, assets = data.assets || {}, ai = data.ai || {}, market = data.market_analysis || {}, scanner = data.scanner || {};
      const connected = !!state.connected;
      const startupError = String(state.last_error || '');
      $('connectionDot').className = 'dot ' + (connected ? 'ok' : startupError ? 'bad' : 'warn');
      $('connectionText').textContent = connected ? 'Bazar qoşulub' : startupError ? 'Başlanğıc xətası' : (state.status || 'Brauzer hazırlanır');
      $('systemError').style.display = startupError ? 'block' : 'none';
      $('systemError').textContent = startupError ? `Bot başlaya bilmədi: ${startupError}` : '';
      const demoArmed = !!platform.execution_enabled;
      const demoVerified = !!platform.demo_verified;
      const demoReady = demoArmed && demoVerified;
      $('mode').textContent = demoReady ? 'OLYMP DEMO' : demoArmed ? 'DEMO GÖZLƏYİR' : 'GÖZLƏMƏ';
      $('mode').style.color = demoReady ? 'var(--green)' : 'var(--cyan)';
      $('modeNote').textContent = demoReady
        ? 'Siqnal gələndə Deneme hesabına avtomatik əməliyyat göndərilir'
        : demoArmed
        ? 'Deneme hesabının təsdiqlənməsi gözlənilir'
        : 'Avtomatik əməliyyat söndürülüb';
      $('platformDot').className = 'dot ' + (platform.demo_verified ? 'ok' : 'warn');
      $('platformText').textContent = platform.demo_verified ? 'Deneme hesabı təsdiqləndi' : 'Deneme hesabı seçilməyib';
      $('platformButton').textContent = platform.execution_enabled ? 'Platform Demo ayır' : 'OlympTrade Demo qoş';
      $('platformButton').className = 'btn ' + (platform.execution_enabled ? 'btn-dry' : 'btn-live');
      const availablePairs = scanner.available_pairs || [];
      const unavailablePairs = scanner.unavailable_pairs || [];
      $('scannerButton').textContent = scanner.enabled
        ? `Skan: ${availablePairs.length || '…'} aktiv`
        : 'Skan: dayanıb';
      $('scannerButton').className = 'btn ' + (scanner.enabled ? 'btn-dry' : 'btn-stop');
      $('scannerButton').title = [
        scanner.status,
        availablePairs.length ? `Açıq tablar: ${availablePairs.join(', ')}` : '',
        unavailablePairs.length ? `Açıq deyil: ${unavailablePairs.join(', ')}` : '',
        scanner.last_error
      ].filter(Boolean).join(' · ');
      $('balance').textContent = platform.balance_text || '—';
      const pnl = Number(platform.platform_pnl || 0);
      const currency = String(platform.balance_text || '').match(/[₼Đ$€₺]/)?.[0] || '';
      $('pnl').textContent = platform.balance_value == null ? '—' : `${pnl >= 0 ? '+' : ''}${currency}${pnl.toFixed(2)}`;
      $('pnl').style.color = pnl > 0 ? 'var(--green)' : pnl < 0 ? 'var(--red)' : 'var(--text)';
      $('tradeCount').textContent = `${demo.closed_trades || 0} nəticə`;
      $('winRate').textContent = `${Number(demo.win_rate || 0).toFixed(1)}%`;
      $('winLoss').textContent = `${demo.wins || 0}W / ${demo.losses || 0}L / ${demo.draws || 0}D`;
      $('tickCount').textContent = Number(state.captured_count || 0).toLocaleString();
      const historyCount = Number(state.history_candles_loaded || 0);
      $('pairCount').textContent = `${Object.keys(assets).length} aktiv${historyCount ? ` · ${historyCount} tarixi şam` : ''}`;
      $('uptime').textContent = duration(data.uptime_sec);
      $('awaiting').textContent = Object.keys(trading.awaiting_results || {}).length;
      $('platformAccount').textContent = platform.account_label || 'Təsdiqlənməyib';
      $('platformBalance').textContent = platform.balance_text || '—';
      $('configuredAmount').textContent = platform.trade_amount ?? '—';
      $('visibleAmount').textContent = platform.visible_trade_amount ?? '—';
      if (document.activeElement !== $('tradeAmount')) $('tradeAmount').value = platform.trade_amount ?? 1;
      $('platformOrder').textContent = platform.last_order ? `${platform.last_order.status} #${platform.last_order.trade_id}` : '—';
      $('aiStatus').textContent = ai.status || (ai.enabled ? 'Hazırlanır' : 'Söndürülüb');
      $('aiStatus').style.color = ai.last_error ? 'var(--red)' : ai.enabled ? 'var(--green)' : 'var(--muted)';
      $('aiModel').textContent = ai.model || '—';
      const aiLast = ai.last_decision || {};
      $('aiDecision').textContent = aiLast.pair
        ? `${aiLast.approved ? 'TƏSDİQ' : 'RƏDD'} · ${aiLast.pair} · ${Math.round(Number(aiLast.confidence || 0) * 100)}%`
        : '—';
      const risk = trading.risk || {}, limits = risk.limits || {};
      $('riskStatus').textContent = risk.halted
        ? `DAYANDIRILIB · ${risk.reason}`
        : risk.limits_enabled === false ? 'LİMİTSİZ DEMO' : 'AKTİV';
      $('riskStatus').style.color = risk.halted ? 'var(--red)' : 'var(--green)';
      $('dailyPnl').textContent = `${Number(risk.daily_pnl || 0) >= 0 ? '+' : ''}${Number(risk.daily_pnl || 0).toFixed(2)}`;
      $('dailyPnl').style.color = Number(risk.daily_pnl || 0) < 0 ? 'var(--red)' : 'var(--green)';
      $('dailyTrades').textContent = `${risk.daily_trades || 0} / ${limits.max_daily_trades || '—'}`;
      $('consecutiveLosses').textContent = `${risk.consecutive_losses || 0} / ${limits.max_consecutive_losses || '—'}`;
      $('maxStake').textContent = `${fmt(risk.max_stake)} (${limits.max_stake_percent || '—'}%)`;

      const pairs = Object.entries(assets)
        .sort((a,b) => Number(a[1].order || 0) - Number(b[1].order || 0))
        .map(entry => entry[0]);
      if (!selectedPair || !assets[selectedPair]) selectedPair = pairs[0] || null;
      renderSignalCenter(market);
      renderSignalHistory(data.signal_history || []);
      renderAssets(assets, data.required_candles, market.assets || {});
      renderChart();
      renderEvents(data.events || [], data.trades || []);
      renderBacktest(data.backtest || {});
    }

    function renderBacktest(backtest) {
      const totals = backtest.totals || {}, pairs = backtest.pairs || [];
      $('backtestSummary').textContent = `${totals.trades || 0} əməliyyat · ${Number(totals.win_rate || 0).toFixed(1)}% · PF ${totals.profit_factor == null ? '—' : Number(totals.profit_factor).toFixed(2)} · ${Number(totals.pnl_per_unit || 0) >= 0 ? '+' : ''}${Number(totals.pnl_per_unit || 0).toFixed(2)} vahid`;
      if (!pairs.length) {
        $('backtestList').innerHTML = '<div class="empty" style="position:relative;height:140px">Tarixi şam yoxdur</div>';
        return;
      }
      $('backtestList').innerHTML = pairs.map(item => {
        const pnl = Number(item.pnl_per_unit || 0);
        const oos = item.out_of_sample || {};
        const state = !item.trades
          ? 'Siqnal tapılmayıb'
          : `${item.wins}W / ${item.losses}L / ${item.draws}D · PF ${item.profit_factor == null ? '—' : Number(item.profit_factor).toFixed(2)} · OOS ${oos.trades || 0} əm. / ${Number(oos.win_rate || 0).toFixed(1)}%`;
        return `<div class="asset-row">
          <div><div class="pair">${esc(item.display_name)} <span class="small">${esc(item.pair)}</span></div><div class="small">${item.candles} tamamlanmış şam · ↑ ${item.upward_signals || 0} / ↓ ${item.downward_signals || 0} · ${state}</div></div>
          <div style="text-align:right"><div class="price" style="color:${pnl > 0 ? 'var(--green)' : pnl < 0 ? 'var(--red)' : 'var(--text)'}">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</div><div class="small">${Number(item.win_rate || 0).toFixed(1)}% · DD ${Number(item.max_drawdown_per_unit || 0).toFixed(2)}</div></div>
        </div>`;
      }).join('');
    }

    function renderSignalCenter(market) {
      const rows = Object.values(market.assets || {});
      $('liveSignalCount').textContent = `${market.active_signals || 0} aktiv · ${market.candidate_signals || 0} namizəd · ${market.auto_eligible_signals || 0} Demo hazır`;
      $('liveSignalCount').style.color = Number(market.active_signals || 0) ? 'var(--amber)' : 'var(--muted)';
      if (!rows.length) {
        $('signalCenter').innerHTML = '<div class="empty" style="position:relative;height:150px;grid-column:1/-1">Bazar məlumatı gözlənilir…</div>';
        return;
      }
      $('signalCenter').innerHTML = rows.map(item => {
        const cls = item.direction === 'AL' ? 'up' : item.direction === 'SAT' ? 'down' : 'wait';
        const lifecycle = item.signal_state === 'ACTIVE' ? ' active-signal' : item.signal_state === 'CANDIDATE' ? ' candidate' : '';
        const reason = (item.reasons || []).slice(0, 2).join(' · ');
        const ready = item.auto_eligible ? ' ready' : '';
        const validation = item.validation || {};
        return `<div class="signal-card ${cls}${lifecycle}${ready}" onclick="selectPair('${esc(item.pair)}')">
          <div class="signal-top">
            <div><div class="signal-name">${esc(item.display_name)}</div><div class="signal-pair">${esc(item.pair)}</div></div>
            <div class="signal-score">${Number(item.score || 0)}<small>/100</small></div>
          </div>
          <div class="signal-direction">${esc(item.direction_label || 'GÖZLƏ')}</div>
          <div class="signal-strength"><span style="width:${Math.min(100, Number(item.score || 0))}%"></span></div>
          <div class="signal-meta">
            <span>${esc(item.quality || '—')}</span>
            <span>${item.signal_state === 'ACTIVE' ? `AKTİV ${item.valid_for_sec || 0}s` : item.signal_state === 'CANDIDATE' ? 'NAMİZƏD' : 'NEYTRAL'}</span>
            ${item.signal_state === 'ACTIVE' && item.signal_started_at ? `<span>Başladı ${new Date(item.signal_started_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'})}</span>` : ''}
            <span>RSI ${item.rsi == null ? '—' : Number(item.rsi).toFixed(1)}</span>
            <span>${esc(item.trend_regime || '—')}</span>
            <span>VOL ${esc(item.volatility || '—')}</span>
            <span>${validation.mode === 'DEMO_LEARNING' ? 'DEMO SINAQ' : validation.eligible ? 'BACKTEST OK' : 'YALNIZ SİQNAL'}</span>
          </div>
          <div class="signal-reason">${esc(reason || 'Tamamlanmış şamlar gözlənilir')}<br>${esc(validation.reason || '')}</div>
        </div>`;
      }).join('');
    }

    function renderSignalHistory(history) {
      $('signalHistoryCount').textContent = `${history.length} siqnal`;
      if (!history.length) {
        $('signalHistory').innerHTML = '<div class="empty" style="position:relative;height:90px">Təsdiqlənmiş siqnal hələ yoxdur</div>';
        return;
      }
      const now = Date.now();
      $('signalHistory').innerHTML = history.map(item => {
        const started = new Date(item.signal_started_at);
        const expires = new Date(item.valid_until);
        const active = Number.isFinite(expires.getTime()) && expires.getTime() > now;
        const remaining = active ? Math.max(0, Math.ceil((expires.getTime() - now) / 1000)) : 0;
        const age = Number.isFinite(started.getTime()) ? Math.max(0, Math.floor((now - started.getTime()) / 1000)) : 0;
        const direction = item.direction === 'AL' ? 'YUXARI ↑' : item.direction === 'SAT' ? 'AŞAĞI ↓' : item.direction;
        const cls = item.direction === 'AL' ? 'up' : 'down';
        const startedText = Number.isFinite(started.getTime()) ? started.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '—';
        const endText = Number.isFinite(expires.getTime()) ? expires.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '—';
        const reason = (item.reasons || []).join(' · ');
        return `<div class="signal-history-row" title="${esc(reason)}">
          <div><div class="history-time">${startedText}</div><div class="small">${age}s əvvəl</div></div>
          <div><div class="pair">${esc(item.pair || '—')}</div><div class="small">${esc(item.quality || 'TƏSDİQLƏNMİŞ')}</div></div>
          <div class="history-direction ${cls}">${esc(direction || '—')}</div>
          <div class="history-score">Güc <strong>${Number(item.score || 0)}/100</strong></div>
          <div class="history-end"><div>${endText}-dək</div><div class="small">${item.auto_eligible ? 'Demo uyğun' : 'Siqnal'}</div></div>
          <div class="history-status ${active ? 'active' : ''}">${active ? `AKTİV ${remaining}s` : 'BİTİB'}</div>
        </div>`;
      }).join('');
    }

    function renderAssets(assets, required, marketAssets={}) {
      const rows = Object.entries(assets)
        .sort((a,b) => Number(a[1].order || 0) - Number(b[1].order || 0));
      $('warmupLabel').textContent = selectedPair && assets[selectedPair]
        ? assets[selectedPair].candles >= required
          ? `${assets[selectedPair].candles} şam · HAZIR`
          : `${assets[selectedPair].candles} / ${required}`
        : `0 / ${required}`;
      if (!rows.length) {
        $('assetList').innerHTML = '<div class="empty" style="position:relative;height:220px">Aktivlər gözlənilir…</div>'; return;
      }
      $('assetList').innerHTML = rows.map(([pair, a]) => {
        const signal = marketAssets[pair] || {};
        const feedText = a.feed_mode === 'LIVE_TICKS'
          ? `${a.ticks_in_candle || 0} canlı tick`
          : a.feed_mode === 'RECENT_TICKS'
            ? `${a.ticks_in_candle || 0} son tick · rotasiya`
            : a.feed_mode === 'OHLC'
              ? 'OHLC axını · tick sayılmır'
              : 'Canlı axın yoxdur';
        const pct = Math.min(100, Math.round((a.candles / required) * 100));
        const status = !a.available
          ? 'Məlumat gözlənilir'
          : a.candles >= required
            ? `${signal.direction_label || 'GÖZLƏ'} · ${signal.score || 0}/100${a.platform_active ? ' · platformda seçilib' : ''}`
            : `${a.candles} şam · ${pct}% hazır`;
        return `<div class="asset-row ${pair === selectedPair ? 'active' : ''}" onclick="selectPair('${esc(pair)}')">
          <div><div class="pair">${esc(a.display_name || pair)} <span class="small">${esc(pair)}</span></div><div class="small">${status}</div><div class="progress"><span style="width:${pct}%"></span></div></div>
          <div><div class="price">${fmt(a.price)}</div><div class="small">${feedText}</div></div>
        </div>`;
      }).join('');
    }

    function selectPair(pair) { selectedPair = pair; candleOffset=0; if (snapshot) render(snapshot); }

    function aggregateCandles(raw, minutes) {
      const seconds = minutes * 60, grouped = [];
      for (const source of raw || []) {
        const bucket = Math.floor(Number(source.bucket) / seconds) * seconds;
        const candle = {
          bucket, open:Number(source.open), high:Number(source.high),
          low:Number(source.low), close:Number(source.close), ticks:Number(source.ticks || 0)
        };
        const last = grouped[grouped.length - 1];
        if (last && last.bucket === bucket) {
          last.high = Math.max(last.high, candle.high); last.low = Math.min(last.low, candle.low);
          last.close = candle.close; last.ticks += candle.ticks;
        } else grouped.push(candle);
      }
      return grouped;
    }

    function emaSeries(values, period) {
      const out = Array(values.length).fill(null);
      if (values.length < period) return out;
      let ema = values.slice(0,period).reduce((a,b)=>a+b,0) / period;
      out[period-1] = ema;
      const k = 2 / (period + 1);
      for (let i=period;i<values.length;i++) { ema = values[i]*k + ema*(1-k); out[i]=ema; }
      return out;
    }

    function rsiSeries(values, period=14) {
      const out = Array(values.length).fill(null);
      if (values.length <= period) return out;
      let gain=0, loss=0;
      for (let i=1;i<=period;i++) { const d=values[i]-values[i-1]; gain+=Math.max(d,0); loss+=Math.max(-d,0); }
      gain/=period; loss/=period;
      out[period] = loss === 0 ? 100 : 100-(100/(1+gain/loss));
      for (let i=period+1;i<values.length;i++) {
        const d=values[i]-values[i-1]; gain=(gain*(period-1)+Math.max(d,0))/period; loss=(loss*(period-1)+Math.max(-d,0))/period;
        out[i] = loss === 0 ? 100 : 100-(100/(1+gain/loss));
      }
      return out;
    }

    function prepareCanvas(id) {
      const canvas=$(id), rect=canvas.getBoundingClientRect(), dpr=window.devicePixelRatio||1;
      canvas.width=Math.max(1,Math.round(rect.width*dpr)); canvas.height=Math.max(1,Math.round(rect.height*dpr));
      const ctx=canvas.getContext('2d'); ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,rect.width,rect.height);
      return {canvas,ctx,w:rect.width,h:rect.height};
    }

    function drawLine(ctx, values, color, xFor, yFor) {
      ctx.beginPath(); let started=false;
      values.forEach((value,i) => {
        if (value == null || !Number.isFinite(value)) return;
        const x=xFor(i), y=yFor(value); started ? ctx.lineTo(x,y) : ctx.moveTo(x,y); started=true;
      });
      if (started) { ctx.strokeStyle=color; ctx.lineWidth=1.6; ctx.stroke(); }
    }

    function setTimeframe(minutes) {
      timeframeMinutes=minutes;
      candleOffset=0;
      [1,5,15].forEach(v => $('tf'+v).className='tool-btn'+(v===minutes?' active':''));
      renderChart();
    }

    function zoomChart(delta) {
      visibleCandles=Math.max(20,Math.min(300,visibleCandles+delta)); renderChart();
    }

    function panChart(direction) {
      if (!snapshot || !selectedPair) return;
      const total=aggregateCandles((snapshot.candles||{})[selectedPair]||[],timeframeMinutes).length;
      const jump=Math.max(5,Math.floor(visibleCandles*.6));
      candleOffset=Math.max(0,Math.min(Math.max(0,total-visibleCandles),candleOffset+direction*jump));
      renderChart();
    }

    function renderChart() {
      const raw = selectedPair && snapshot ? (snapshot.candles || {})[selectedPair] || [] : [];
      const all = aggregateCandles(raw,timeframeMinutes);
      const fullCloses=all.map(c=>c.close), fullEma3=emaSeries(fullCloses,3), fullEma8=emaSeries(fullCloses,8), fullRsi=rsiSeries(fullCloses,9);
      const end=Math.max(0,all.length-candleOffset);
      const start=Math.max(0,end-visibleCandles), candles=all.slice(start,end);
      const ema3=fullEma3.slice(start), ema8=fullEma8.slice(start), rsi=fullRsi.slice(start);
      const selectedAsset = snapshot && selectedPair ? (snapshot.assets || {})[selectedPair] : null;
      $('chartTitle').textContent = selectedAsset ? `${selectedAsset.display_name} · ${selectedPair}` : (selectedPair || 'Canlı şam qrafiki');
      $('chartSubtitle').textContent = candles.length ? `${timeframeMinutes} dəq. · ${start+1}–${end} / ${all.length} şam · EMA 3/8` : 'Şam məlumatı gözlənilir';
      $('lastPrice').textContent = candles.length ? fmt(candles[candles.length-1].close) : '—';
      $('chartEmpty').style.display = candles.length < 2 ? 'grid' : 'none';

      const {canvas,ctx,w,h}=prepareCanvas('priceChart'), left=38, right=70, top=16, bottom=28;
      ctx.font='10px system-ui'; ctx.textBaseline='middle';
      ctx.strokeStyle='rgba(148,180,207,.10)'; ctx.fillStyle='#7890a3';
      for(let i=0;i<=5;i++){const y=top+(h-top-bottom)*i/5;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();}
      if(candles.length<2){chartGeometry=null;renderRsi([],[]);return;}
      const priceValues=candles.flatMap(c=>[c.high,c.low]);
      ema3.forEach(v=>v!=null&&priceValues.push(v)); ema8.forEach(v=>v!=null&&priceValues.push(v));
      let min=Math.min(...priceValues), max=Math.max(...priceValues), extra=(max-min)*.08 || Math.abs(max)*.001 || 1; min-=extra; max+=extra;
      const span=max-min, plotW=w-left-right, plotH=h-top-bottom, step=plotW/candles.length;
      const xFor=i=>left+step*(i+.5), yFor=v=>top+(max-v)*plotH/span;
      for(let i=0;i<=5;i++){const value=max-span*i/5;ctx.fillText(fmt(value),w-right+8,top+plotH*i/5);}
      const bodyWidth=Math.max(2,Math.min(12,step*.62));
      candles.forEach((c,i)=>{
        const x=xFor(i), up=c.close>=c.open, color=up?'#28cf83':'#ff5b69';
        ctx.strokeStyle=color;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,yFor(c.high));ctx.lineTo(x,yFor(c.low));ctx.stroke();
        const y1=yFor(c.open),y2=yFor(c.close),bh=Math.max(1,Math.abs(y2-y1));ctx.fillStyle=color;ctx.fillRect(x-bodyWidth/2,Math.min(y1,y2),bodyWidth,bh);
      });
      drawLine(ctx,ema3,'#ffd166',xFor,yFor); drawLine(ctx,ema8,'#62a8ff',xFor,yFor);
      const labelEvery=Math.max(1,Math.ceil(candles.length/6));
      ctx.fillStyle='#7890a3';ctx.textAlign='center';
      candles.forEach((c,i)=>{if(i%labelEvery===0||i===candles.length-1)ctx.fillText(new Date(c.bucket*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}),xFor(i),h-10);});
      ctx.textAlign='left';

      const markers=[];
      (snapshot.events||[]).filter(e=>e.event==='demo_signal'&&e.pair===selectedPair).forEach(e=>markers.push({ts:Number(e.candle_bucket),direction:e.direction,type:'signal'}));
      (snapshot.trades||[]).filter(t=>t.pair===selectedPair).forEach(t=>markers.push({ts:Number(t.entry_ts),direction:t.direction,type:'trade'}));
      markers.forEach(m=>{
        let index=0,best=Infinity;candles.forEach((c,i)=>{const d=Math.abs(c.bucket-m.ts);if(d<best){best=d;index=i;}});
        if(best>timeframeMinutes*90)return;
        const c=candles[index], up=m.direction==='AL', x=xFor(index), y=up?yFor(c.low)+11:yFor(c.high)-11;
        ctx.fillStyle=m.type==='trade'?'#fff':'#ffc857';ctx.beginPath();
        if(up){ctx.moveTo(x,y-7);ctx.lineTo(x-5,y+2);ctx.lineTo(x+5,y+2);}else{ctx.moveTo(x,y+7);ctx.lineTo(x-5,y-2);ctx.lineTo(x+5,y-2);}
        ctx.closePath();ctx.fill();
      });
      chartGeometry={candles,xFor,left,right,w,step};
      renderRsi(candles,rsi);
    }

    function renderRsi(candles,rsi) {
      const {ctx,w,h}=prepareCanvas('rsiChart'), left=38,right=70,top=10,bottom=22,plotH=h-top-bottom;
      $('rsiEmpty').style.display=rsi.some(v=>v!=null)?'none':'grid';
      const yFor=v=>top+(100-v)*plotH/100, step=(w-left-right)/Math.max(1,candles.length), xFor=i=>left+step*(i+.5);
      ctx.fillStyle='rgba(255,91,105,.05)';ctx.fillRect(left,top,w-left-right,yFor(72)-top);
      ctx.fillStyle='rgba(40,207,131,.05)';ctx.fillRect(left,yFor(28),w-left-right,top+plotH-yFor(28));
      ctx.setLineDash([4,4]);ctx.strokeStyle='rgba(255,200,87,.4)';
      [72,54,46,28].forEach(v=>{ctx.beginPath();ctx.moveTo(left,yFor(v));ctx.lineTo(w-right,yFor(v));ctx.stroke();});
      ctx.setLineDash([]);ctx.fillStyle='#7890a3';ctx.font='10px system-ui';[72,54,46,28].forEach(v=>ctx.fillText(String(v),w-right+8,yFor(v)+3));
      drawLine(ctx,rsi,'#b084ff',xFor,yFor);
    }

    function renderEvents(events, trades) {
      const persistentTrades = (trades || [])
        .filter(t => ['OPEN', 'WIN', 'LOSS', 'DRAW'].includes(String(t.result || '')))
        .map(t => ({
        time: new Date(Number(t.exit_ts || t.entry_ts || t.created_at) * 1000).toISOString(),
        event: `demo_trade_${String(t.result || 'OPEN').toLowerCase()}`,
        pair: t.pair,
        direction: t.direction,
        amount: t.amount,
        result: t.result,
        pnl: t.pnl,
        trade_id: t.id
      }));
      const visibleEventTypes = new Set([
        'demo_signal',
        'signal_rejected',
        'ai_signal_approved',
        'ai_signal_rejected',
        'ai_signal_error',
        'ai_signal_fallback',
        'ai_signal_skipped',
        'platform_demo_clicked',
        'platform_demo_blocked'
      ]);
      const signalEvents = (events || []).filter(e => visibleEventTypes.has(String(e.event || '')));
      const combined = [...signalEvents, ...persistentTrades].sort((a,b) => new Date(a.time) - new Date(b.time));
      $('eventCount').textContent = `${combined.length} hadisə`;
      if (!combined.length) {
        $('events').innerHTML = '<div class="empty" style="position:relative;height:220px">Siqnal hələ yaranmayıb</div>'; return;
      }
      $('events').innerHTML = [...combined].reverse().map(e => {
        const type = String(e.event || 'event');
        const cls = type.includes('signal') ? 'signal' : (type.includes('reject') || type.includes('loss')) ? 'reject' : type.includes('trade') ? 'trade' : '';
        const pnl = Number(e.pnl || 0);
        const names = {
          demo_signal: 'Yeni strategiya siqnalı',
          signal_rejected: 'Siqnal qəbul edilmədi',
          ai_signal_approved: 'OpenAI siqnalı təsdiqlədi',
          ai_signal_rejected: 'OpenAI siqnalı rədd etdi',
          ai_signal_error: 'OpenAI yoxlaması alınmadı',
          ai_signal_fallback: 'Yerli Demo strategiyası ilə davam edildi',
          ai_signal_skipped: 'OpenAI yoxlaması ötürüldü',
          platform_demo_clicked: 'Demo əməliyyatı platformaya göndərildi',
          platform_demo_blocked: 'Demo əməliyyatı bloklandı',
          demo_trade_open: 'Demo əməliyyatı açıqdır',
          demo_trade_win: 'Demo nəticəsi: QAZANC',
          demo_trade_loss: 'Demo nəticəsi: ZƏRƏR',
          demo_trade_draw: 'Demo nəticəsi: BƏRABƏR'
        };
        const direction = e.direction === 'AL' ? 'YUXARI ↑' : e.direction === 'SAT' ? 'AŞAĞI ↓' : e.direction;
        const result = e.result === 'WIN' ? 'QAZANC' : e.result === 'LOSS' ? 'ZƏRƏR' : e.result === 'DRAW' ? 'BƏRABƏR' : e.result;
        const rsi = Number.isFinite(Number(e.rsi)) ? `RSI ${Number(e.rsi).toFixed(1)}` : '';
        const score = e.score !== undefined ? `Güc ${Number(e.score)}/100` : '';
        const confidence = e.confidence !== undefined ? `Etibar ${Math.round(Number(e.confidence) * 100)}%` : '';
        const reasons = Array.isArray(e.reasons) ? e.reasons.slice(0,2).join(', ') : '';
        const detail = [e.pair, direction, score, e.quality, rsi, e.trend_regime, e.volatility, confidence, e.risk_level, e.amount ? `$${e.amount}` : '', result, e.pnl !== undefined ? `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}` : '', reasons, e.reason, e.error].filter(Boolean).join(' · ');
        const tm = e.time ? new Date(e.time).toLocaleTimeString() : '';
        return `<div class="event ${cls}"><span class="event-mark"></span><div><div class="event-name">${esc(names[type] || type)}</div><div class="event-detail">${esc(detail || 'Demo məlumatı')}</div></div><span class="event-time">${esc(tm)}</span></div>`;
      }).join('');
    }

    async function toggleScanner() {
      const current = !!(snapshot && snapshot.scanner && snapshot.scanner.enabled);
      try {
        const res = await fetch('/api/scanner', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({enabled:!current})
        });
        const body = await res.json();
        if (!res.ok) throw new Error(body.error || 'Skan rejimi dəyişmədi');
        toast(body.message);
        await refresh();
      } catch (e) { toast(e.message, true); }
    }

    async function saveTradeAmount() {
      const amount = Number($('tradeAmount').value);
      if (!Number.isInteger(amount) || amount < 1 || amount > 10000) {
        toast('Məbləğ 1–10.000 aralığında tam ədəd olmalıdır', true); return;
      }
      try {
        const res = await fetch('/api/platform-demo/amount', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({amount})});
        const body = await res.json(); if (!res.ok) throw new Error(body.error || 'Məbləğ yazılmadı');
        toast(body.message); await refresh();
      } catch (e) { toast(e.message, true); }
    }

    async function togglePlatformDemo() {
      const current = !!(snapshot && snapshot.trading && snapshot.trading.platform_demo && snapshot.trading.platform_demo.execution_enabled);
      let confirmation = '';
      if (!current) {
        confirmation = prompt('Yalnız OlympTrade Deneme hesabına demo əmrləri göndəriləcək. Qoşmaq üçün DEMO yazın:') || '';
        if (confirmation !== 'DEMO') { toast('Platform Demo qoşulmadı'); return; }
      }
      try {
        const res = await fetch('/api/platform-demo', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled:!current, confirmation})});
        const body = await res.json(); if (!res.ok) throw new Error(body.error || 'Platform Demo dəyişmədi');
        toast(body.message); await refresh();
      } catch (e) { toast(e.message, true); }
    }

    async function stopBot() {
      if (!confirm('Botu və idarə etdiyi brauzeri dayandırmaq istəyirsiniz?')) return;
      try {
        const res = await fetch('/api/control/stop', {method:'POST'});
        const body = await res.json(); toast(body.message);
      } catch (e) { toast('Bot dayandırılır…'); }
    }

    async function refresh() {
      try {
        const res = await fetch('/api/dashboard', {cache:'no-store'});
        if (!res.ok) throw new Error('Status alınmadı');
        render(await res.json());
      } catch (e) {
        $('connectionDot').className='dot bad'; $('connectionText').textContent='Panel əlaqəsi kəsildi';
      }
    }
    $('priceChart').addEventListener('mousemove', event => {
      if (!chartGeometry) return;
      const rect=$('priceChart').getBoundingClientRect(), x=event.clientX-rect.left;
      const index=Math.floor((x-chartGeometry.left)/chartGeometry.step);
      const candle=chartGeometry.candles[index], hover=$('chartHover');
      if (!candle) { hover.style.display='none'; return; }
      hover.innerHTML=`${new Date(candle.bucket*1000).toLocaleString()} · O ${fmt(candle.open)} · H ${fmt(candle.high)} · L ${fmt(candle.low)} · C ${fmt(candle.close)} · ${candle.ticks} tick`;
      hover.style.display='block';
    });
    $('priceChart').addEventListener('mouseleave', () => $('chartHover').style.display='none');
    window.addEventListener('resize', () => snapshot && renderChart());
    refresh(); setInterval(refresh, 1200);
  </script>
</body>
</html>"""


def _read_events(limit: int = 100) -> list[dict]:
    path = core_globals.get("SESSION_LOG")
    if not path or not Path(path).is_file():
        return []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()[-limit:]
        events = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events
    except OSError:
        return []


def _event_timestamp(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return None
    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).timestamp()
    except (TypeError, ValueError):
        return None


def _read_signal_history(limit: int = 100) -> list[dict]:
    log_dir = Path(core_globals["LOG_DIR"])
    if not log_dir.is_dir():
        return []
    records = []
    try:
        files = sorted(
            log_dir.glob("session-*.jsonl"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:30]
        for path in files:
            for line in reversed(path.read_text(encoding="utf-8").splitlines()):
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("event") != "demo_signal":
                    continue
                started_at = event.get("signal_started_at") or event.get("time")
                started_ts = _event_timestamp(started_at)
                if started_ts is None:
                    continue
                valid_until = event.get("valid_until")
                valid_ts = _event_timestamp(valid_until)
                if valid_ts is None:
                    valid_ts = started_ts + 60
                    valid_until = datetime.fromtimestamp(
                        valid_ts,
                        timezone.utc,
                    ).isoformat()
                records.append(
                    {
                        "pair": event.get("pair"),
                        "direction": event.get("direction"),
                        "score": event.get("score"),
                        "quality": event.get("quality"),
                        "rsi": event.get("rsi"),
                        "trend_regime": event.get("trend_regime"),
                        "volatility": event.get("volatility"),
                        "reasons": event.get("reasons") or [],
                        "auto_eligible": bool(event.get("auto_eligible")),
                        "signal_started_at": started_at,
                        "valid_until": valid_until,
                        "started_ts": started_ts,
                        "valid_until_ts": valid_ts,
                        "session": path.stem,
                    }
                )
                if len(records) >= limit:
                    break
            if len(records) >= limit:
                break
    except OSError:
        return []
    records.sort(key=lambda item: item["started_ts"], reverse=True)
    now = time.time()
    for record in records:
        record["status"] = (
            "ACTIVE"
            if float(record["valid_until_ts"]) > now
            else "EXPIRED"
        )
        record["remaining_sec"] = max(
            0,
            int(float(record["valid_until_ts"]) - now),
        )
    return records[:limit]


def dashboard():
    return DASHBOARD_HTML


def dashboard_api():
    with core_globals["state_lock"]:
        state = dict(core_globals["state"])
    with core_globals["candles_lock"]:
        assets = {}
        candle_history = {}
        watch_assets = core_globals["_resolved_watch_assets"]()
        visible_pairs = []
        for watch in watch_assets:
            pair = watch["pair"]
            candle_queue = core_globals["candles"].get(pair, ())
            latest = candle_queue[-1] if candle_queue else {}
            live = core_globals["live_prices"].get(pair, {})
            live_age = (
                max(0.0, time.time() - float(live["ts"]))
                if live.get("ts") is not None
                else None
            )
            is_platform_active = state.get("active_pair") == pair
            feed_mode = (
                "LIVE_TICKS"
                if is_platform_active and live_age is not None and live_age <= 15
                else "RECENT_TICKS"
                if live_age is not None and live_age <= 120
                else "OHLC"
                if candle_queue
                else "NO_DATA"
            )
            visible_pairs.append(pair)
            assets[pair] = {
                "price": live.get("price", latest.get("close")),
                "timestamp": live.get("ts", latest.get("bucket")),
                "candles": max(0, len(candle_queue) - 1),
                "ticks_in_candle": latest.get("ticks", 0),
                "feed_mode": feed_mode,
                "live_age_sec": live_age,
                "display_name": watch["name"],
                "available": watch["available"],
                "ready": watch["ready"],
                "platform_active": is_platform_active,
                "order": watch["order"],
            }
            candle_history[pair] = list(candle_queue)[-500:]
        ticks = list(core_globals["price_ticks"])
        state["history_candles_loaded"] = sum(
            len(core_globals["candles"].get(pair, ())) for pair in visible_pairs
        )
        state["history_pairs"] = visible_pairs
    required = int(core_globals["_required_candles"]())
    return jsonify(
        {
            "server_time": datetime.now(timezone.utc).isoformat(),
            "uptime_sec": time.time() - started_at,
            "required_candles": required,
            "state": state,
            "trading": core_globals["trade_engine"].snapshot(),
            "demo": core_globals["trade_engine"].statistics(),
            "market_analysis": core_globals["market_analysis_snapshot"](),
            "scanner": core_globals["scanner_snapshot"](),
            "backtest": core_globals["backtest_snapshot"](),
            "ai": core_globals["ai_snapshot"](),
            "trades": core_globals["trade_engine"].recent_trades(100),
            "assets": assets,
            "candles": candle_history,
            "ticks": ticks,
            "events": _read_events(),
            "signal_history": _read_signal_history(),
        }
    )


def export_trades_csv():
    fields = [
        "id",
        "created_at",
        "pair",
        "direction",
        "amount",
        "entry_price",
        "entry_ts",
        "expiry_ts",
        "exit_price",
        "exit_ts",
        "result",
        "pnl",
        "rsi",
        "ema_fast",
        "ema_slow",
        "platform_status",
        "platform_error",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in reversed(core_globals["trade_engine"].recent_trades(500)):
        writer.writerow(row)
    filename = datetime.now(timezone.utc).strftime(
        "olympbot_demo_trades_%Y%m%d_%H%M%S.csv"
    )
    return Response(
        "\ufeff" + output.getvalue(),
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def signals_api():
    return jsonify(
        {
            "server_time": datetime.now(timezone.utc).isoformat(),
            "demo_only": True,
            "analysis": core_globals["market_analysis_snapshot"](),
            "history": _read_signal_history(),
        }
    )


def scanner_control():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload.get("enabled"), bool):
        return jsonify({"error": "enabled true/false olmalıdır"}), 400
    scanner = core_globals["set_scanner_enabled"](payload["enabled"])
    return jsonify(
        {
            "ok": True,
            "scanner": scanner,
            "message": (
                "Canlı aktiv rotasiyası qoşuldu"
                if scanner["enabled"]
                else "Canlı aktiv rotasiyası dayandırıldı"
            ),
        }
    )


def reset_demo():
    payload = request.get_json(silent=True) or {}
    if payload.get("confirmation") != "RESET":
        return jsonify({"error": "Demo hesabını sıfırlamaq üçün RESET tələb olunur"}), 400
    core_globals["trade_engine"].reset()
    return jsonify({"ok": True, "message": "Demo hesabı və statistika sıfırlandı"})


def stop_bot():
    core_globals["_event"]("stop_requested", source="dashboard")
    stop_event.set()
    return jsonify({"ok": True, "message": "Bot dayandırılır…"})


# Mövcud sadə ana səhifəni peşəkar panel ilə əvəz edir.
app.view_functions["index"] = dashboard
app.add_url_rule("/api/dashboard", "professional_dashboard_api", dashboard_api, methods=["GET"])
app.add_url_rule("/api/signals", "professional_signals_api", signals_api, methods=["GET"])
app.add_url_rule("/api/scanner", "professional_scanner_control", scanner_control, methods=["POST"])
app.add_url_rule("/api/export/trades.csv", "professional_export_csv", export_trades_csv, methods=["GET"])
app.add_url_rule("/api/control/reset-demo", "professional_reset_demo", reset_demo, methods=["POST"])
app.add_url_rule("/api/control/stop", "professional_stop_bot", stop_bot, methods=["POST"])


def _request_stop(signum=None, frame=None):
    del signum, frame
    stop_event.set()


def main() -> None:
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(signal_name, _request_stop)
        except (ValueError, OSError):
            pass

    preferred_port = int(core_globals["PANEL_PORT"])
    panel_port = preferred_port
    for candidate in range(preferred_port, preferred_port + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.3)
            if probe.connect_ex(("127.0.0.1", candidate)) != 0:
                panel_port = candidate
                break
    else:
        raise SystemExit("5000–5009 panel portlarının hamısı istifadə olunur")
    core_globals["PANEL_PORT"] = panel_port
    if panel_port != preferred_port:
        core_globals["log"].warning(
            "%s portu köhnə proses tərəfindən tutulub; yeni panel %s portunda açılır",
            preferred_port,
            panel_port,
        )

    panel_url = f"http://127.0.0.1:{panel_port}/"
    panel_thread = threading.Thread(
        target=core_globals["start_panel"],
        name="professional-panel",
        daemon=True,
    )
    panel_thread.start()
    auto_open_panel = os.environ.get("AUTO_OPEN_PANEL", "true").strip().lower()
    if auto_open_panel in {"1", "true", "yes", "on"}:
        threading.Timer(2.0, lambda: webbrowser.open(panel_url)).start()

    core_globals["log"].info("OlympBot Professional paneli: %s", panel_url)
    with core_globals["state_lock"]:
        core_globals["state"]["status"] = "OlympTrade brauzeri hazırlanır..."
        core_globals["state"]["last_error"] = None

    try:
        # Playwright sync mühərriki əsas thread-də işləməlidir. Ayrı thread-də
        # işlədilməsi Windows-da Flask panelinin sorğularını dondura bilir.
        core_globals["run_browser"](stop_event)
    except Exception as exc:
        if not stop_event.is_set():
            with core_globals["state_lock"]:
                core_globals["state"]["status"] = "Brauzer xətası"
                core_globals["state"]["last_error"] = str(exc)
                core_globals["state"]["connected"] = False
            core_globals["log"].exception(
                "OlympTrade brauzeri başlaya bilmədi: %s", exc
            )
            # Panel açıq qalır və konkret xətanı göstərir; sonsuz yüklənmə yoxdur.
            while not stop_event.wait(0.5):
                pass
    except KeyboardInterrupt:
        _request_stop()
    finally:
        core_globals["log"].info("OlympBot Professional dayandırıldı")


if __name__ == "__main__":
    main()
