#!/usr/bin/env python3
"""
UnoRouter Register Bot - Camoufox Edition
Real browser for Turnstile solve + direct API calls for register/login
"""

import random
import time
import json
import re
import sys
import threading
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from camoufox.sync_api import Camoufox

from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.text import Text
from rich.align import Align
from rich import box

# ===================== CONFIG =====================

def load_config(path="config.json"):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


CFG = load_config()

PROXY_FILE = CFG.get("proxy_file", "proxy.txt")
RESULTS_FILE = CFG.get("results_file", "accounts.txt")
RETRY = CFG.get("retry", 3)
COOLDOWN_MIN = CFG.get("cooldown_min", 2)
COOLDOWN_MAX = CFG.get("cooldown_max", 5)

REGISTER_PAGE_URL = "https://unorouter.com/en/register"
LOGIN_PAGE_URL = "https://unorouter.com/en/login"
REGISTER_API_URL = "https://unorouter.com/api/auth/account/register"
LOGIN_API_URL = "https://unorouter.com/api/auth/account/login"
BEST_KEY_URL = "https://unorouter.com/api/billing/token/best-key"
MODELS_URL = "https://api.unorouter.com/v1/models"

TURNSTILE_TIMEOUT = 35  # max seconds to wait for Turnstile token

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

# ===================== STATE =====================

class State:
    def __init__(self, total):
        self.total = total
        self.success = 0
        self.failed = 0
        self.retried = 0
        self.current = 0
        self.status = "Initializing..."
        self.proxy = ""
        self.results = []
        self.lock = threading.RLock()
        self.start_time = time.time()
        self.avg_time = 0


state = None

# ===================== HELPERS =====================

def load_proxies():
    proxies = []
    with open(PROXY_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            proxies.append(parse_proxy(line))
    return proxies


def parse_proxy(line):
    # Format: http://user:pass@host:port
    if line.startswith("http") and "@" in line:
        from urllib.parse import urlparse
        parsed = urlparse(line)
        return {
            "server": f"http://{parsed.hostname}:{parsed.port}",
            "username": parsed.username or "",
            "password": parsed.password or "",
        }
    # Format: host:port:user:pass
    parts = line.split(":")
    if len(parts) == 4:
        return {
            "server": f"http://{parts[0]}:{parts[1]}",
            "username": parts[2],
            "password": parts[3],
        }
    if len(parts) == 2:
        return {"server": f"http://{parts[0]}:{parts[1]}"}
    return {"server": f"http://{line}"}


def generate_human_name():
    return f"{random.choice(FIRST_NAMES)}{random.choice(LAST_NAMES)}{random.randint(1, 999)}"


def generate_password(length=14):
    lower = "abcdefghijklmnopqrstuvwxyz"
    upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    digits = "0123456789"
    special = "!@#$%^&*"
    all_chars = lower + upper + digits + special
    pw = [random.choice(lower), random.choice(upper), random.choice(digits), random.choice(special)]
    pw += [random.choice(all_chars) for _ in range(length - 4)]
    random.shuffle(pw)
    return "".join(pw)


def update_status(msg):
    with state.lock:
        state.status = msg


def save_account(username, password, api_key, model_count):
    with open(RESULTS_FILE, "a") as f:
        f.write(f"{username}|{password}|{api_key}|{model_count} free models\n")


def save_free_models(free_models):
    with open("free_models.txt", "w") as f:
        for m in sorted(free_models):
            f.write(f"{m}\n")


# ===================== CORE: CAMOUFOX REGISTRATION =====================

def wait_turnstile_token(page, timeout=TURNSTILE_TIMEOUT):
    """Wait for Cloudflare Turnstile to auto-solve and populate the hidden input."""
    for i in range(timeout):
        time.sleep(1)
        token_len = page.evaluate('''
            () => {
                const el = document.querySelector('[name="cf-turnstile-response"]');
                return el ? el.value.length : 0;
            }
        ''')
        if token_len > 10:
            token = page.evaluate('''
                () => document.querySelector('[name="cf-turnstile-response"]').value
            ''')
            return token
    return None


def api_register(page, username, password, turnstile_token):
    """Call register API directly from browser context."""
    result = page.evaluate('''
        async (args) => {
            const [username, password, token] = args;
            try {
                const resp = await fetch('/api/auth/account/register', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        username: username,
                        password: password,
                        email: '',
                        aff_code: '',
                        turnstile: token
                    })
                });
                const data = await resp.json();
                return {status: resp.status, data: data};
            } catch(e) {
                return {error: e.message};
            }
        }
    ''', [username, password, turnstile_token])
    return result


def api_login(page, username, password, turnstile_token):
    """Call login API directly from browser context."""
    result = page.evaluate('''
        async (args) => {
            const [username, password, token] = args;
            try {
                const resp = await fetch('/api/auth/account/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        username: username,
                        password: password,
                        turnstile: token
                    })
                });
                const data = await resp.json();
                return {status: resp.status, data: data};
            } catch(e) {
                return {error: e.message};
            }
        }
    ''', [username, password, turnstile_token])
    return result


def api_get_best_key(page, access_token):
    """Get best API key using access token."""
    result = page.evaluate('''
        async (token) => {
            try {
                const resp = await fetch('/api/billing/token/best-key', {
                    headers: {'Authorization': 'Bearer ' + token}
                });
                const data = await resp.json();
                return {status: resp.status, data: data};
            } catch(e) {
                return {error: e.message};
            }
        }
    ''', access_token)
    return result


def api_verify_models(page, api_key):
    """Verify API key and get list of models."""
    result = page.evaluate('''
        async (key) => {
            try {
                const resp = await fetch('https://api.unorouter.com/v1/models', {
                    headers: {'Authorization': 'Bearer ' + key}
                });
                if (resp.status !== 200) return {status: resp.status, error: 'non-200'};
                const data = await resp.json();
                return {status: resp.status, data: data};
            } catch(e) {
                return {error: e.message};
            }
        }
    ''', api_key)
    return result


def run_single(proxies, index):
    """One full registration flow using Camoufox."""
    username = generate_human_name()
    password = generate_password()
    proxy_data = random.choice(proxies)

    with state.lock:
        state.proxy = proxy_data.get("server", "direct")

    for attempt in range(1, RETRY + 1):
        if attempt > 1:
            with state.lock:
                state.retried += 1
            proxy_data = random.choice(proxies)

        try:
            with Camoufox(headless=True, proxy=proxy_data) as browser:
                page = browser.new_page()
                print(f"  [debug] Browser opened, navigating...", flush=True)

                # ===== STEP 1: Get Turnstile token from register page =====
                update_status(f"A{attempt} turnstile (register) [{username}]")
                page.goto(REGISTER_PAGE_URL, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)

                reg_token = wait_turnstile_token(page, TURNSTILE_TIMEOUT)
                if not reg_token:
                    update_status(f"A{attempt} no register token [{username}]")
                    print(f"  [debug] No register turnstile token after {TURNSTILE_TIMEOUT}s", flush=True)
                    continue

                # ===== STEP 2: Register via API =====
                update_status(f"A{attempt} registering [{username}]")
                print(f"  [debug] Registering {username}...", flush=True)
                reg_result = api_register(page, username, password, reg_token)

                if reg_result.get("error"):
                    continue
                reg_data = reg_result.get("data", {})
                if not reg_data.get("success"):
                    msg = reg_data.get("message", "unknown")
                    update_status(f"A{attempt} reg failed: {msg} [{username}]")
                    continue

                # ===== STEP 3: Get Turnstile token from login page =====
                update_status(f"A{attempt} turnstile (login) [{username}]")
                page.goto(LOGIN_PAGE_URL, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)

                login_token = wait_turnstile_token(page, TURNSTILE_TIMEOUT)
                if not login_token:
                    update_status(f"A{attempt} no login token [{username}]")
                    print(f"  [debug] No login turnstile token", flush=True)
                    continue

                # ===== STEP 4: Login via API =====
                update_status(f"A{attempt} logging in [{username}]")
                print(f"  [debug] Logging in {username}...", flush=True)
                login_result = api_login(page, username, password, login_token)

                if login_result.get("error"):
                    continue
                login_data = login_result.get("data", {})
                access_token = login_data.get("data", {}).get("access_token")
                if not access_token:
                    msg = login_data.get("message", "no access_token")
                    update_status(f"A{attempt} login failed: {msg} [{username}]")
                    continue

                # ===== STEP 5: Get API key =====
                update_status(f"A{attempt} getting API key [{username}]")
                key_result = api_get_best_key(page, access_token)
                if key_result.get("error"):
                    continue
                key_data = key_result.get("data", {})
                raw_key = key_data.get("key", "")
                if not raw_key:
                    update_status(f"A{attempt} no API key [{username}]")
                    continue
                api_key = f"sk-{raw_key}" if not raw_key.startswith("sk-") else raw_key

                # ===== STEP 6: Verify key + get models =====
                update_status(f"A{attempt} verifying [{username}]")
                verify_result = api_verify_models(page, api_key)
                free_models = []
                if not verify_result.get("error"):
                    models = verify_result.get("data", {}).get("data", [])
                    free_models = [m["id"] for m in models if ":free" in m.get("id", "")]

                model_count = len(free_models)
                save_account(username, password, api_key, model_count)
                if free_models:
                    save_free_models(free_models)

                elapsed = time.time() - state.start_time
                short_key = f"{api_key[:15]}...{api_key[-8:]}" if len(api_key) > 23 else api_key
                with state.lock:
                    state.success += 1
                    state.results.append((username, short_key, model_count))
                    if state.avg_time == 0:
                        state.avg_time = elapsed
                    else:
                        state.avg_time = state.avg_time * 0.7 + elapsed * 0.3
                update_status(f"OK {username} ({model_count} models)")
                return True

        except Exception as e:
            update_status(f"A{attempt} error: {str(e)[:50]} [{username}]")
            time.sleep(2)
            continue

    with state.lock:
        state.failed += 1
    update_status(f"FAIL {username}")
    return False


# ===================== TUI =====================

def make_banner():
    b = Text(justify="center")
    b.append("UNOROUTER REGISTER BOT", style="bold white")
    b.append("\n")
    b.append("Camoufox + Auto Turnstile + Direct API", style="dim cyan")
    return Panel(Align.center(b, vertical="middle"), border_style="bold cyan", box=box.HEAVY)


def make_status_box():
    with state.lock:
        status_text = state.status
        current = state.current
        total = state.total
        proxy = state.proxy
        retried = state.retried
        elapsed = time.time() - state.start_time
        avg = state.avg_time

    spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int(time.time() * 10) % 10]

    inner = Table.grid(padding=(0, 2))
    inner.add_column(style="bold cyan", width=10)
    inner.add_column(style="white")
    inner.add_row("Status", f"{spinner} {status_text}")
    inner.add_row("Proxy", proxy or "N/A")
    inner.add_row("Current", f"{current}/{total}")
    inner.add_row("Retried", str(retried))
    inner.add_row("Avg", f"{avg:.1f}s" if avg else "-")
    inner.add_row("Elapsed", f"{elapsed:.0f}s")
    return Panel(inner, title="[bold cyan]Status[/]", border_style="cyan", box=box.ROUNDED)


def make_stats_box():
    with state.lock:
        success = state.success
        failed = state.failed
        retried = state.retried
    done = success + failed
    pct = f"{success/done*100:.0f}%" if done > 0 else "0%"
    inner = Table.grid(padding=(0, 2))
    inner.add_column(justify="center")
    inner.add_column(justify="center")
    inner.add_row(Text(f"{success}", style="bold green"), Text(f"{failed}", style="bold red"))
    inner.add_row(Text("OK", style="green"), Text("FAIL", style="red"))
    inner.add_row(Text(""), Text(""))
    inner.add_row(Text(pct, style="bold yellow"), Text(f"R:{retried}", style="dim"))
    return Panel(inner, title="[bold cyan]Stats[/]", border_style="cyan", box=box.ROUNDED)


def make_progress_box():
    with state.lock:
        total = state.total
        done = state.success + state.failed
    bar_width = 40
    filled = int(done / total * bar_width) if total > 0 else 0
    bar = Text()
    bar.append("▰" * filled, style="bold green")
    bar.append("▱" * (bar_width - filled), style="dim")
    inner = Table.grid(padding=(0, 1))
    inner.add_column()
    inner.add_row(bar)
    inner.add_row(Align.center(Text(f" {done}/{total} ", style="bold white")))
    return Panel(inner, title="[bold cyan]Progress[/]", border_style="cyan", box=box.ROUNDED)


def make_results_box():
    with state.lock:
        results = list(state.results)
    if not results:
        return Panel(Align.center(Text("No accounts yet...", style="dim italic")),
                     title="[bold cyan]Results[/]", border_style="cyan", box=box.ROUNDED)
    table = Table(box=box.SIMPLE, header_style="bold cyan", border_style="dim cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("Username", style="green")
    table.add_column("API Key", style="yellow")
    table.add_column("Models", justify="right", style="magenta")
    for i, (u, k, m) in enumerate(results[-12:], 1):
        table.add_row(str(i), u, k, str(m))
    return Panel(table, title="[bold cyan]Results[/]", border_style="cyan", box=box.ROUNDED)


def make_layout():
    layout = Layout()
    layout.split(Layout(name="banner", size=3), Layout(name="main"), Layout(name="footer", size=1))
    layout["main"].split(Layout(name="top"), Layout(name="bottom"))
    layout["top"].split_row(
        Layout(name="status", ratio=2),
        Layout(name="stats", ratio=1),
    )
    layout["bottom"].split_row(
        Layout(name="progress", ratio=1),
        Layout(name="results", ratio=2),
    )
    return layout


def update_layout():
    layout = make_layout()
    layout["banner"].update(make_banner())
    layout["status"].update(make_status_box())
    layout["stats"].update(make_stats_box())
    layout["progress"].update(make_progress_box())
    layout["results"].update(make_results_box())
    return layout


# ===================== MAIN =====================

def main():
    global state

    parser = argparse.ArgumentParser(description="UnoRouter Register Bot (Camoufox)")
    parser.add_argument("count", nargs="?", type=int, default=1)
    parser.add_argument("-w", "--workers", type=int, default=1)
    args = parser.parse_args()

    count = args.count
    workers = args.workers
    proxies = load_proxies()

    if not proxies:
        print("[ERROR] No proxies found in proxy.txt!")
        sys.exit(1)

    state = State(count)
    print(f"[info] Loaded {len(proxies)} proxies")
    print(f"[info] Registering {count} account(s) with {workers} worker(s)")

    is_tty = sys.stdout.isatty()
    if is_tty:
        print("\033[?25l")

    try:
        if is_tty:
            with Live(update_layout(), refresh_per_second=4, screen=True) as live:
                if workers <= 1:
                    for i in range(count):
                        with state.lock:
                            state.current = i + 1
                        run_single(proxies, i)
                        if i < count - 1:
                            delay = random.uniform(COOLDOWN_MIN, COOLDOWN_MAX)
                            update_status(f"Cooldown {delay:.1f}s...")
                            end = time.time() + delay
                            while time.time() < end:
                                time.sleep(0.1)
                                live.update(update_layout())
                        live.update(update_layout())
                else:
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        futures = [pool.submit(run_single, proxies, i) for i in range(count)]
                        done = 0
                        for future in as_completed(futures):
                            future.result()
                            done += 1
                            with state.lock:
                                state.current = done
                            live.update(update_layout())
                update_status("Done!")
                live.update(update_layout())
                time.sleep(1)
        else:
            for i in range(count):
                with state.lock:
                    state.current = i + 1
                print(f"[{i+1}/{count}] ...", flush=True)
                run_single(proxies, i)
                with state.lock:
                    print(f"  -> success={state.success} failed={state.failed}")
    except KeyboardInterrupt:
        pass
    finally:
        if is_tty:
            print("\033[?25h")

    with state.lock:
        success = state.success
        failed = state.failed
        retried = state.retried
        elapsed = time.time() - state.start_time
        avg = state.avg_time

    print(f"\n{'='*60}")
    print(f"SUMMARY: {success} success, {failed} failed, {retried} retries, {elapsed:.0f}s")
    if avg:
        print(f"Avg time/account: {avg:.1f}s")
    print(f"Results saved to: {RESULTS_FILE}")
    print(f"Free models saved to: free_models.txt")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
