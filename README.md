# UnoRouter Register Bot — Camoufox Edition

Automated account registration for UnoRouter (unorouter.com) using **Camoufox browser** — no captcha solver needed, Turnstile auto-solves via browser fingerprint.

**Original repo:** https://github.com/hirotomasato/unifarm  
**Camoufox fork:** https://github.com/madmouse17/unifarm

## What Changed (Camoufox Edition)

| Before (original) | After (Camoufox) |
|---|---|
| Capsolver API ($0.002/solve) | Camoufox browser — **FREE** |
| curl_cffi HTTP requests | Real browser automation |
| Manual Turnstile solving | **Auto Turnstile** via fingerprint |
| Requires proxy for API calls | Browser bypasses Cloudflare natively |

## Features

- 🆓 **Free** — No captcha solver API needed
- 🦊 **Camoufox** — Real Firefox-based anti-detect browser
- 🔐 **Auto Turnstile** — Cloudflare Turnstile solves automatically
- 🌐 **Cloudflare bypass** — Native browser fingerprint beats CF
- 🔄 **Proxy support** — Rotating residential proxy support
- 📊 **TUI dashboard** — Rich terminal UI with live stats
- ⚡ **Direct API** — Register/login via API for speed
- 🎭 **Anti-detection** — Browser fingerprint spoofing built-in

## Prerequisites

```bash
pip install camoufox rich
```

Or use the included venv:

```bash
python -m venv venv
./venv/Scripts/pip install camoufox rich
```

Camoufox will auto-download its browser binary on first run (~490MB).

## Quick Start

```bash
# 1. Add proxies to proxy.txt (one per line)
# 2. Run

./venv/Scripts/python register_camoufox.py 1        # register 1 account
./venv/Scripts/python register_camoufox.py 5        # register 5 accounts
./venv/Scripts/python register_camoufox.py 10 -w 3  # 10 accounts, 3 workers
```

## Files

```
unifarm/
├── config.json             # Settings (retry, cooldown, etc.)
├── proxy.txt               # HTTP proxies (one per line)
├── register_camoufox.py    # Main script — Camoufox browser (NEW)
├── register_tui.py         # Original script — Capsolver + curl_cffi
├── register_bot.py         # Original CLI version
├── accounts.txt            # Output: username|password|api_key|model_count
├── free_models.txt         # Output: list of free models
└── venv/                   # Python virtualenv
```

## Configuration (config.json)

```json
{
    "proxy_file": "proxy.txt",
    "results_file": "accounts.txt",
    "retry": 3,
    "cooldown_min": 2,
    "cooldown_max": 5,
    "concurrent": 1
}
```

| Key | Description |
|-----|-------------|
| `proxy_file` | Path to proxy list |
| `results_file` | Where to save accounts |
| `retry` | Max retries per account |
| `cooldown_min` | Min cooldown between accounts (seconds) |
| `cooldown_max` | Max cooldown between accounts (seconds) |

## Proxy Format

```
# Format 1: http://user:pass@host:port
http://user:pass@103.1.2.3:8080

# Format 2: host:port:user:pass
103.1.2.3:8080:user:pass

# Format 3: host:port (no auth)
103.1.2.3:8080
```

## Flow

Each account goes through:

1. **Launch Camoufox** — Anti-detect browser with proxy
2. **Open Register Page** — Navigate to unorouter.com/en/register
3. **Solve Turnstile** — Auto-solves via browser fingerprint (~8-15s)
4. **Register** — POST /api/auth/account/register with Turnstile token
5. **Open Login Page** — Navigate to unorouter.com/en/login
6. **Solve Turnstile** — Auto-solves on login page (~7-10s)
7. **Login** — POST /api/auth/account/login → access_token
8. **Get API Key** — GET /api/billing/token/best-key
9. **Verify Key** — Real call to /v1/models
10. **Save** — username, password, api_key, free model count

## Performance

- Average speed: ~40-50 seconds per account
- Turnstile solve: ~8-15 seconds (auto, no API needed)
- Proxy: rotating residential recommended
- Cost: **$0** (no captcha solver fees)

## How Turnstile Auto-Solves

Camoufox is a modified Firefox with anti-fingerprinting. Cloudflare Turnstile
uses browser fingerprinting to detect bots. Camoufox spoofs:

- Canvas fingerprint
- WebGL fingerprint  
- Audio fingerprint
- Navigator properties
- Screen resolution
- Font enumeration

This makes Turnstile think it's a real browser → auto-solves without clicking.

## License

masantoid
