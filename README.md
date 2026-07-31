# OlympBot Professional

OlympBot is a guarded one-minute signal dashboard and automated OlympTrade Demo
execution service. It runs continuously on a Linux server and exposes its panel
privately through Tailscale.

## Safety model

- Real-account execution is hard-disabled.
- Every platform click requires a visible OlympTrade Deneme/Demo account check.
- Martingale is disabled.
- The server uses stake `1`, a maximum of 5 Demo trades per UTC day, a maximum
  daily loss of 5, and stops after 3 consecutive losses.
- Historical and Demo results are not guarantees of future performance.

## Main files

- `outputs/olympbot_demo_core.py` — market feed, one-minute strategy, risk and
  guarded Demo execution.
- `outputs/OlympBot_Professional.py` — professional dashboard and API.
- `deploy/` — systemd units for the 24/7 Linux deployment.
- `AGENTS.md` — mandatory development and verification rules for coding agents.

## Local validation

```powershell
python -m py_compile outputs\olympbot_demo_core.py outputs\OlympBot_Professional.py
```

See `outputs/OlympBot_Professional_README.md` for setup and operating details.
Never commit browser profiles, runtime databases, logs, `.env` files, API keys,
SSH keys, or account credentials.
