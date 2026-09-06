# UnoRouter Register Bot

Automated account registration for UnoRouter (unorouter.com) using HTTP-only approach — no browser automation, no Playwright.

**Repo:** https://github.com/hirotomasato/unifarm

**Features:**
- Cloudflare bypass via TLS impersonation (curl_cffi)
- Turnstile CAPTCHA solving via Capsolver (Proxyless)
- Automatic API key extraction + free model enumeration
- Retry logic with dead proxy auto-swap
- Concurrent workers support
- Rich TUI dashboard with live stats
- Anti-detection: randomized TLS fingerprints, headers, Chrome versions

## Prerequisites

```bash
pip install curl_cffi rich requests cloudscraper
```

Or use the included venv:

```bash
python3 -m venv venv
./venv/bin/pip install curl_cffi rich requests cloudscraper
```

## Quick Start

```bash
# 1. Edit config.json with your Capsolver key
# 2. Add proxies to proxy.txt (one per line: http://IP:PORT)
# 3. Run

./venv/bin/python register_tui.py 5        # register 5 accounts
./venv/bin/python register_tui.py 10 -w 3  # 10 accounts, 3 concurrent workers
```

## Files

```
unifarm/
├── config.json        # API keys, sitekey, retry, cooldown settings
├── proxy.txt          # HTTP proxies (one per line)
├── register_tui.py    # Main script — TUI dashboard (recommended)
├── register_bot.py    # CLI version — plain text output
├── accounts.txt       # Output: username|password|api_key|model_count
├── free_models.txt    # Output: list of free models
└── venv/              # Python virtualenv
```

## Configuration (config.json)

Copy `config.example.json` to `config.json` and fill in your key:

```bash
cp config.example.json config.json
# edit config.json with your Capsolver key
```

```json
{
    "capsolver_key": "CAP-...",
    "turnstile_sitekey": "0x4AAAAAACuPK5b5SmOxRGAW",
    "retry": 3,
    "cooldown_min": 2,
    "cooldown_max": 5,
    "concurrent": 1,
    "balance_warn": 1.0
}
```

| Key | Description |
|-----|-------------|
| `capsolver_key` | Capsolver API key (starts with `CAP-`) |
| `turnstile_sitekey` | UnoRouter's Turnstile site key |
| `retry` | Max retries per account (proxy swap on failure) |
| `cooldown_min` | Min cooldown between accounts (seconds) |
| `cooldown_max` | Max cooldown between accounts (seconds) |
| `concurrent` | Default worker count (override with `-w`) |
| `balance_warn` | Show warning when Capsolver balance drops below this |

## Flow

Each account goes through:

1. **Solve Turnstile** (register page) — Capsolver Proxyless
2. **Register** — POST /api/auth/account/register
3. **Solve Turnstile** (login page) — parallel with step 2
4. **Login** — POST /api/auth/account/login
5. **Get API Key** — GET /api/billing/token/best-key
6. **Verify Key** — real call to /v1/models
7. **Save** — username, password, api_key, free model count

## Anti-Detection

- **TLS Fingerprint**: curl_cffi impersonates Chrome/Safari (randomized per session)
- **Headers**: rotating Chrome versions (124-131), random platforms, sec-ch-ua headers
- **Sessions**: cookies maintained across requests within each account flow
- **Proxies**: each account uses a random proxy from proxy.txt

## Notes

- Turnstile tokens are **single-use** — cannot reuse between register and login
- Proxies must be accessible from the machine running the script (IP-whitelisted proxies won't work with NopeCHA)
- Capsolver Proxyless solves Turnstile from Capsolver's servers — no proxy needed for solving
- Average speed: ~12 seconds per account
- Capsolver cost: ~$0.002 per solve, ~$0.004 per account

## License

masantoid