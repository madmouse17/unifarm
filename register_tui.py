#!/usr/bin/env python3
"""
UnoRouter Register Bot - TUI (Optimized)
curl_cffi TLS impersonation + parallel turnstile + header rotation
"""

import random
import time
import json
import sys
import threading
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from curl_cffi import requests as creq
import requests

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

CAPSOLVER_KEY = CFG.get("capsolver_key", "")
TURNSTILE_SITEKEY = CFG.get("turnstile_sitekey", "0x4AAAAAACuPK5b5SmOxRGAW")
REGISTER_PAGE_URL = CFG.get("register_url", "https://unorouter.com/en/register")
LOGIN_PAGE_URL = CFG.get("login_url", "https://unorouter.com/en/login")

REGISTER_URL = "https://unorouter.com/api/auth/account/register"
LOGIN_URL = "https://unorouter.com/api/auth/account/login"
BEST_KEY_URL = "https://unorouter.com/api/billing/token/best-key"
MODELS_URL = "https://api.unorouter.com/v1/models"

PROXY_FILE = CFG.get("proxy_file", "proxy.txt")
RESULTS_FILE = CFG.get("results_file", "accounts.txt")
RETRY = CFG.get("retry", 3)
COOLDOWN_MIN = CFG.get("cooldown_min", 2)
COOLDOWN_MAX = CFG.get("cooldown_max", 5)
BALANCE_WARN = CFG.get("balance_warn", 1.0)

# ===================== ANTI-DETECT =====================

# Random Chrome versions for header rotation
CHROME_VERSIONS = [
    "131.0.0.0", "130.0.0.0", "129.0.0.0", "128.0.0.0",
    "127.0.0.0", "126.0.0.0", "125.0.0.0", "124.0.0.0",
]

PLATFORMS = [
    ("Windows NT 10.0; Win64; x64", "Windows"),
    ("Macintosh; Intel Mac OS X 10_15_7", "macOS"),
    ("X11; Linux x86_64", "Linux"),
]

IMPERSONATE_TARGETS = ["chrome", "chrome124", "chrome131", "safari17_0"]


def random_headers():
    """Generate realistic randomized browser headers."""
    platform, _os = random.choice(PLATFORMS)
    chrome_ver = random.choice(CHROME_VERSIONS)
    ua = (
        f"Mozilla/5.0 ({platform}) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{chrome_ver.split('.')[0]}.0.0.0 Safari/537.36"
    )
    return {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin": "https://unorouter.com",
        "Referer": "https://unorouter.com/en/register",
        "Sec-Ch-Ua": f'"Chromium";v="{chrome_ver.split(".")[0]}", "Google Chrome";v="{chrome_ver.split(".")[0]}", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": f'"{_os}"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }


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
        self.balance = None
        self.avg_time = 0
        self.lock = threading.RLock()
        self.start_time = time.time()


state = None

# ===================== CORE =====================

def load_proxies():
    with open(PROXY_FILE) as f:
        return [line.strip() for line in f if line.strip()]


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


def get_balance():
    try:
        resp = requests.post("https://api.capsolver.com/getBalance", json={"clientKey": CAPSOLVER_KEY}, timeout=10)
        data = resp.json()
        if data.get("errorId") == 0:
            return data.get("balance", 0)
    except Exception:
        pass
    return None


def solve_turnstile(url, poll_interval=0.5):
    """Solve Turnstile via Capsolver with fast polling."""
    payload = {
        "clientKey": CAPSOLVER_KEY,
        "task": {
            "type": "AntiTurnstileTaskProxyLess",
            "websiteURL": url,
            "websiteKey": TURNSTILE_SITEKEY,
        },
    }
    try:
        resp = requests.post("https://api.capsolver.com/createTask", json=payload, timeout=30)
        data = resp.json()
    except Exception:
        return None

    if data.get("errorId") != 0:
        return None

    task_id = data.get("taskId")
    if not task_id:
        return None

    for _ in range(60):  # 60 * 0.5s = 30s max
        time.sleep(poll_interval)
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
            return result.get("solution", {}).get("token")
        if result.get("errorId") != 0:
            return None
    return None


def make_session(proxy_url):
    """Create curl_cffi session with Chrome impersonation + proxy."""
    impersonate = random.choice(IMPERSONATE_TARGETS)
    s = creq.Session(impersonate=impersonate)
    if proxy_url:
        s.proxies = {"http": proxy_url, "https": proxy_url}
    return s


def register_account(session, username, password, turnstile_token):
    payload = {
        "username": username,
        "password": password,
        "email": "",
        "aff_code": "",
        "turnstile": turnstile_token,
    }
    try:
        resp = session.post(
            REGISTER_URL, json=payload,
            headers=random_headers(), timeout=20,
        )
        if resp.status_code != 200:
            return False, resp.text
        data = resp.json()
        return data.get("success", False), resp.text
    except Exception as e:
        return False, str(e)


def login_account(session, username, password, turnstile_token):
    payload = {"username": username, "password": password, "turnstile": turnstile_token}
    try:
        resp = session.post(
            LOGIN_URL, json=payload,
            headers=random_headers(), timeout=20,
        )
        if resp.status_code != 200:
            return None
        return resp.json().get("data", {})
    except Exception:
        return None


def get_api_key(session, access_token):
    try:
        resp = session.get(
            BEST_KEY_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        key = resp.json().get("key", "")
        return f"sk-{key}" if key else None
    except Exception:
        return None


def verify_and_get_models(session, api_key):
    """Verify key + get free models in one call."""
    try:
        resp = session.get(
            MODELS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        if resp.status_code != 200:
            return False, []
        models = resp.json().get("data", [])
        free = [m["id"] for m in models if ":free" in m.get("id", "")]
        return True, free
    except Exception:
        return False, []


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


# ===================== SINGLE REGISTRATION (optimized) =====================

def run_single_optimized(proxies):
    """One registration with retry + parallel turnstile."""
    username = generate_human_name()
    password = generate_password()

    for attempt in range(1, RETRY + 1):
        proxy = random.choice(proxies)
        t_start = time.time()

        with state.lock:
            state.proxy = proxy.replace("http://", "")
            if attempt > 1:
                state.retried += 1

        update_status(f"A{attempt} solving turnstile [{username}]")
        ts_reg = solve_turnstile(REGISTER_PAGE_URL)
        if not ts_reg:
            continue

        session = make_session(proxy)

        update_status(f"A{attempt} register [{username}]")
        # Start login turnstile solve IN PARALLEL with register request
        login_token_future = {"token": None}
        def solve_login():
            login_token_future["token"] = solve_turnstile(LOGIN_PAGE_URL)
        t = threading.Thread(target=solve_login)
        t.start()

        success, resp = register_account(session, username, password, ts_reg)
        if not success:
            t.join()
            continue
        try:
            if not json.loads(resp).get("success"):
                t.join()
                continue
        except json.JSONDecodeError:
            t.join()
            continue

        # Wait for login turnstile (already solved in parallel)
        t.join()
        ts_login = login_token_future["token"]
        if not ts_login:
            continue

        update_status(f"A{attempt} login [{username}]")
        login_data = login_account(session, username, password, ts_login)
        if not login_data or not login_data.get("access_token"):
            continue
        access_token = login_data["access_token"]

        update_status(f"A{attempt} key [{username}]")
        api_key = get_api_key(session, access_token)
        if not api_key:
            continue

        update_status(f"A{attempt} verify [{username}]")
        ok, free_models = verify_and_get_models(session, api_key)
        if not ok:
            continue
        model_count = len(free_models)

        save_account(username, password, api_key, model_count)
        save_free_models(free_models)

        elapsed = time.time() - t_start
        short_key = f"{api_key[:15]}...{api_key[-8:]}"
        with state.lock:
            state.success += 1
            state.results.append((username, short_key, model_count))
            if state.avg_time == 0:
                state.avg_time = elapsed
            else:
                state.avg_time = state.avg_time * 0.7 + elapsed * 0.3
        update_status(f"OK {username} ({elapsed:.1f}s)")
        return True

    with state.lock:
        state.failed += 1
    update_status(f"FAIL {username}")
    return False


# ===================== TUI =====================

def make_banner():
    b = Text(justify="center")
    b.append("UNOROUTER REGISTER BOT", style="bold white")
    b.append("\n")
    b.append("curl_cffi antidetect + Capsolver Turnstile", style="dim cyan")
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


def make_balance_box():
    with state.lock:
        balance = state.balance
    if balance is None:
        text = Text("Checking...", style="dim")
    elif balance < BALANCE_WARN:
        text = Text(f"${balance:.2f} LOW!", style="bold red")
    else:
        text = Text(f"${balance:.2f}", style="bold green")
    return Panel(Align.center(text, vertical="middle"), title="[bold cyan]Balance[/]", border_style="cyan", box=box.ROUNDED)


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
        return Panel(Align.center(Text("No accounts yet...", style="dim italic")), title="[bold cyan]Results[/]", border_style="cyan", box=box.ROUNDED)
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
        Layout(name="balance", ratio=1),
    )
    layout["bottom"].split_row(
        Layout(name="progress", ratio=1),
        Layout(name="results", ratio=2),
    )
    layout["banner"].update(make_banner())
    layout["status"].update(make_status_box())
    layout["stats"].update(make_stats_box())
    layout["balance"].update(make_balance_box())
    layout["progress"].update(make_progress_box())
    layout["results"].update(make_results_box())
    layout["footer"].update(Align.center(Text(" CTRL+C to quit ", style="dim")))
    return layout


def main():
    global state

    parser = argparse.ArgumentParser(description="UnoRouter Register Bot (Optimized)")
    parser.add_argument("count", nargs="?", type=int, default=1)
    parser.add_argument("-w", "--workers", type=int, default=CFG.get("concurrent", 1))
    args = parser.parse_args()

    count = args.count
    workers = args.workers
    proxies = load_proxies()
    state = State(count)

    update_status("Checking balance...")
    state.balance = get_balance()
    if state.balance is not None:
        print(f"[info] Capsolver balance: ${state.balance:.2f}")
    else:
        print("[!] Could not check balance")

    is_tty = sys.stdout.isatty()
    if is_tty:
        print("\033[?25l")

    try:
        if is_tty:
            with Live(make_layout(), refresh_per_second=10, screen=True) as live:
                if workers <= 1:
                    for i in range(count):
                        with state.lock:
                            state.current = i + 1
                        run_single_optimized(proxies)
                        if i < count - 1:
                            delay = random.uniform(COOLDOWN_MIN, COOLDOWN_MAX)
                            update_status(f"Cooldown {delay:.1f}s...")
                            end = time.time() + delay
                            while time.time() < end:
                                time.sleep(0.1)
                                live.update(make_layout())
                        live.update(make_layout())
                else:
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        futures = [pool.submit(run_single_optimized, proxies) for _ in range(count)]
                        done = 0
                        for future in as_completed(futures):
                            future.result()
                            done += 1
                            with state.lock:
                                state.current = done
                            live.update(make_layout())
                update_status("Done!")
                live.update(make_layout())
                time.sleep(1)
        else:
            if workers <= 1:
                for i in range(count):
                    with state.lock:
                        state.current = i + 1
                    print(f"[{i+1}/{count}] ...", flush=True)
                    run_single_optimized(proxies)
                    with state.lock:
                        print(f"  -> success={state.success} failed={state.failed}")
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [pool.submit(run_single_optimized, proxies) for _ in range(count)]
                    for future in as_completed(futures):
                        future.result()
                        with state.lock:
                            print(f"  done: success={state.success} failed={state.failed}")
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