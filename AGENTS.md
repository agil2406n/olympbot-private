# OlympBot development rules

## Scope

- Maintain the professional OlympBot dashboard and its one-minute Demo strategy.
- Primary source files are `outputs/olympbot_demo_core.py` and
  `outputs/OlympBot_Professional.py`.
- The 24/7 service definitions are under `deploy/`.

## Non-negotiable safety

- Keep real-account trading hard-disabled. Never remove or bypass the
  OlympTrade `Deneme/Demo` account verification before a click.
- Automatic execution is authorized only for the Demo account.
- Keep martingale disabled.
- Do not store API keys, passwords, browser profiles, cookies, runtime databases,
  session logs, or SSH private keys in source packages or version control.
- Do not make profitability guarantees. Historical and Demo results are only
  validation evidence.

## Current server behavior

- Strategy timeframe and trade duration are 60 seconds.
- Server Demo learning mode requires a fully executable signal with score 90+
  while strict backtest validation continues to be calculated.
- OlympTrade Demo execution has no daily trade, daily loss, consecutive-loss,
  or stake-percentage halt. Available Demo balance and one-open-trade-at-a-time
  checks still apply.
- The scanner must rotate only through asset tabs that are actually open in
  OlympTrade. Gold must not be added.
- Phone access uses private Tailscale Serve; do not enable a public Funnel.

## Verification before deployment

1. Compile both Python source files with `python -m py_compile`.
2. Verify the dashboard API returns HTTP 200 repeatedly without increasing the
   process file-descriptor count.
3. Verify the platform reports `demo_verified=true`, `execution_enabled=true`,
   a positive visible amount, and one-minute duration before claiming readiness.
4. A signal card is not proof of execution. Use the event chain
   `demo_signal` -> `demo_trade_opened` -> `platform_demo_clicked` or
   `platform_demo_blocked`, followed by settlement.
5. Preserve the existing OlympTrade browser profile and runtime database during
   server updates.

## Packaging

- Keep `outputs/OlympBot_Server_24x7_v6.3.zip` free of `.env`, runtime data,
  browser profiles, credentials, and logs.
