#!/usr/bin/env python3
"""
UnoRouter Register Bot - HTTP Only
Capsolver Turnstile + cloudscraper CF bypass
Flow: register → login → get API key → get free models → save
"""

import random
import time
import json
import sys
import cloudscraper
import requests

# ===================== CONFIG =====================
def _load_config(path="config.json"):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

_CFG = _load_config()
CAPSOLVER_KEY = _CFG.get("capsolver_key", "")
TURNSTILE_SITEKEY = _CFG.get("turnstile_sitekey", "0x4AAAAAACuPK5b5SmOxRGAW")
REGISTER_PAGE_URL = _CFG.get("register_url", "https://unorouter.com/en/register")
LOGIN_PAGE_URL = _CFG.get("login_url", "https://unorouter.com/en/login")
REGISTER_URL = "https://unorouter.com/api/auth/account/register"
LOGIN_URL = "https://unorouter.com/api/auth/account/login"
BEST_KEY_URL = "https://unorouter.com/api/billing/token/best-key"
MODELS_URL = "https://api.unorouter.com/v1/models"
PROXY_FILE = "proxy.txt"
RESULTS_FILE = "accounts.txt"

# ===================== HUMAN NAMES =====================
FIRST_NAMES = [
    "Andi", "Budi", "Citra", "Dewi", "Eko", "Fajar", "Gita", "Hendra",
    "Indah", "Joko", "Kartika", "Lina", "Maya", "Nanda", "Oscar", "Putri",
    "Rizki", "Sari", "Tono", "Utami", "Vina", "Wahyu", "Yuda", "Zahra",
    "Aditya", "Bella", "Cahya", "Dimas", "Erina", "Fahmi", "Galih", "Hana",
    "Ivan", "Kiki", "Laras", "Mira", "Nina", "Oki", "Prita", "Rama",
    "Sinta", "Tari", "Udin", "Vito", "Wulan", "Yoga", "Zaki", "Fitri",
    "Rudi", "Ani", "Bambang", "Cindy", "Dodi", "Eva", "Ferry", "Grace",
    "Heri", "Intan", "Jamal", "Karin", "Lutfi", "Monica", "Niko", "Olivia",
    "Pandu", "Rina", "Satrio", "Tiara", "Umar", "Vera", "Wawan", "Yanti",
]

LAST_NAMES = [
    "Santoso", "Wijaya", "Kusuma", "Pratama", "Hidayat", "Nugroho", "Saputra",
    "Mahendra", "Hermawan", "Gunawan", "Setiawan", "Hartono", "Lesmana", "Sudrajat",
    "Wibowo", "Susanto", "Permana", "Kurniawan", "Haryanto", "Ramadhan",
    "Purnomo", "Iskandar", "Hakim", "Nasution", "Siregar", "Lubis", "Harahap",
    "Putra", "Utomo", "Wahyudi", "Pangestu", "Cahyono", "Prasetyo", "Handoko",
    "Suryadi", "Raharjo", "Adinata", "Ardianto", "Firmansyah", "Julianto",
    "Kusnadi", "Laksmana", "Muljono", "Octavian", "Rachman", "Suharto", "Tanuwijaya",
]

# ===================== FUNCTIONS =====================

def load_proxies():
    with open(PROXY_FILE) as f:
        return [line.strip() for line in f if line.strip()]


def generate_human_name():
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    suffix = str(random.randint(1, 999))
    return f"{first}{last}{suffix}"


def generate_password(length=14):
    lower = "abcdefghijklmnopqrstuvwxyz"
    upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    digits = "0123456789"
    special = "!@#$%^&*"
    all_chars = lower + upper + digits + special
    pw = [
        random.choice(lower), random.choice(upper),
        random.choice(digits), random.choice(special),
    ]
    pw += [random.choice(all_chars) for _ in range(length - 4)]
    random.shuffle(pw)
    return "".join(pw)


def solve_turnstile(url):
    """Solve Cloudflare Turnstile via Capsolver (Proxyless)."""
    payload = {
        "clientKey": CAPSOLVER_KEY,
        "task": {
            "type": "AntiTurnstileTaskProxyLess",
            "websiteURL": url,
            "websiteKey": TURNSTILE_SITEKEY,
        },
    }
    try:
        resp = requests.post(
            "https://api.capsolver.com/createTask",
            json=payload, timeout=30,
        )
        data = resp.json()
    except Exception as e:
        print(f"  [capsolver] createTask error: {e}")
        return None

    if data.get("errorId") != 0:
        print(f"  [capsolver] error: {data.get('errorDescription', data)}")
        return None

    task_id = data.get("taskId")
    if not task_id:
        return None

    for _ in range(30):
        time.sleep(2)
        try:
            resp = requests.post(
                "https://api.capsolver.com/getTaskResult",
                json={"clientKey": CAPSOLVER_KEY, "taskId": task_id},
                timeout=15,
            )
            result = resp.json()
        except Exception:
            continue

        if result.get("status") == "ready":
            token = result.get("solution", {}).get("token", "")
            if token:
                return token
            return None

        if result.get("errorId") != 0:
            return None

    return None


def register_account(session, username, password, turnstile_token):
    """Register a new account."""
    payload = {
        "username": username,
        "password": password,
        "email": "",
        "aff_code": "",
        "turnstile": turnstile_token,
    }
    try:
        resp = session.post(
            REGISTER_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        return resp.status_code == 200, resp.text
    except Exception as e:
        return False, str(e)


def login_account(session, username, password, turnstile_token):
    """Login and get access token + API key."""
    payload = {
        "username": username,
        "password": password,
        "turnstile": turnstile_token,
    }
    try:
        resp = session.post(
            LOGIN_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code != 200:
            return None, resp.text
        data = resp.json()
        return data.get("data", {}), None
    except Exception as e:
        return None, str(e)


def get_api_key(session, access_token):
    """Get the best/default API key."""
    try:
        resp = session.get(
            BEST_KEY_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        key = data.get("key", "")
        return f"sk-{key}" if key else None
    except Exception:
        return None


def get_free_models(session, api_key):
    """Get list of free models via OpenAI-compatible endpoint."""
    try:
        resp = session.get(
            MODELS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        models = resp.json().get("data", [])
        return [m["id"] for m in models if ":free" in m.get("id", "")]
    except Exception:
        return []


def save_account(username, password, api_key, free_models):
    """Save account to results file."""
    free_count = len(free_models)
    with open(RESULTS_FILE, "a") as f:
        f.write(f"{username}|{password}|{api_key}|{free_count} free models\n")
    print(f"  [save] written to {RESULTS_FILE}")

    # Also save free models list to a separate file
    with open("free_models.txt", "w") as f:
        for m in sorted(free_models):
            f.write(f"{m}\n")


def test_single(proxy_url=None):
    """Test a single registration + login + key extraction."""
    print(f"\n{'='*60}")
    print(f"Prox: {proxy_url}")
    print(f"{'='*60}")

    # Create cloudscraper session with proxy
    s = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "desktop": True}
    )
    if proxy_url:
        s.proxies = {"http": proxy_url, "https": proxy_url}

    # Generate fake identity
    username = generate_human_name()
    password = generate_password()
    print(f"  [gen] username={username}, password={password}")

    # Step 1: Solve Turnstile for register
    print("  [1/5] Solving Turnstile for register...")
    ts = solve_turnstile(REGISTER_PAGE_URL)
    if not ts:
        print("  [FAIL] Turnstile solve failed")
        return False

    # Step 2: Register
    print("  [2/5] Registering...")
    success, resp = register_account(s, username, password, ts)
    if not success:
        print(f"  [FAIL] Register failed: {resp[:200]}")
        return False
    try:
        rj = json.loads(resp)
        if not rj.get("success"):
            print(f"  [FAIL] Register rejected: {resp[:200]}")
            return False
    except json.JSONDecodeError:
        print(f"  [FAIL] Invalid response: {resp[:200]}")
        return False
    print("  [OK] Registered")

    # Step 3: Solve Turnstile for login
    print("  [3/5] Solving Turnstile for login...")
    ts2 = solve_turnstile(LOGIN_PAGE_URL)
    if not ts2:
        print("  [FAIL] Login Turnstile solve failed")
        return False

    # Step 4: Login
    print("  [4/5] Logging in...")
    login_data, err = login_account(s, username, password, ts2)
    if not login_data:
        print(f"  [FAIL] Login failed: {err}")
        return False
    access_token = login_data.get("access_token", "")
    print(f"  [OK] Logged in (user ID: {login_data.get('user', {}).get('id')})")

    # Step 5: Get API key
    print("  [5/5] Getting API key...")
    api_key = get_api_key(s, access_token)
    if not api_key:
        print("  [FAIL] Could not get API key")
        return False
    print(f"  [OK] API Key: {api_key[:20]}...{api_key[-8:]}")

    # Step 6: Get free models
    free_models = get_free_models(s, api_key)
    print(f"  [OK] Free models: {len(free_models)}")

    # Save
    save_account(username, password, api_key, free_models)

    print(f"  [SUCCESS] {username} | {api_key}")
    return True


def main():
    print("=" * 60)
    print("UnoRouter Register Bot")
    print("Capsolver Turnstile + cloudscraper CF bypass")
    print("=" * 60)

    proxies = load_proxies()
    print(f"Loaded {len(proxies)} proxies")

    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(f"Target: {count} account(s)")

    success_count = 0
    fail_count = 0

    for i in range(count):
        proxy = random.choice(proxies)
        print(f"\n--- Attempt {i+1}/{count} ---")

        if test_single(proxy):
            success_count += 1
        else:
            fail_count += 1

        if i < count - 1:
            delay = random.uniform(3, 6)
            print(f"  [delay] {delay:.1f}s...")
            time.sleep(delay)

    print(f"\n{'='*60}")
    print(f"SUMMARY: {success_count} success, {fail_count} failed")
    print(f"Results saved to: {RESULTS_FILE}")
    print(f"Free models saved to: free_models.txt")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()