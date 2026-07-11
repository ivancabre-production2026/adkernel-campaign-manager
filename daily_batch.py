"""
daily_batch.py
==============
Corre todos los dias a las 10 AM:
  1. Obtiene los stores de Galeonica ordenados por comision
  2. Descarta los ya creados (registrados en created_brands.json)
  3. Elige los proximos 5
  4. Crea Binom offer + campaign + AdKernel offer + geo US
  5. Notificacion de Windows al inicio y al finalizar
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ---- Config -----------------------------------------------------------------
SCRIPT_DIR    = Path(__file__).parent
LOG_FILE      = SCRIPT_DIR / "daily_batch.log"
CREATED_FILE  = SCRIPT_DIR / "created_brands.json"
BATCH_SIZE    = 5
MIN_COMMISSION = 10.0   # % minimo
MAX_COMMISSION = 100.0  # % maximo (evita B2B/SaaS con comisiones >100%)

AK_LOGIN    = os.getenv("ADKERNEL_LOGIN",    "ilatinmedia")
AK_PASSWORD = os.getenv("ADKERNEL_PASSWORD", "5*&RcQXlKGG$Dz7j")
AK_TOKEN    = os.getenv("ADKERNEL_TOKEN",    "")

GALEONICA_KEY    = "vp_t1eB2RG1N4b1sp45AfzcHK7Zm43QfTVw"
GALEONICA_SECRET = "18bf31c4c7d3cd7435e3ce430364ad1886f1aa581e056ab158bcac0ef73e070f"

# SourceKnowledge (chequeo de trafico disponible por dominio antes de crear la offer)
SK_LOGIN       = os.getenv("SK_LOGIN", "")
SK_PASSWORD    = os.getenv("SK_PASSWORD", "")
MIN_SK_CLICKS  = 500   # trafico minimo disponible en SK para crear la offer

# -----------------------------------------------------------------------------

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def notify(title: str, msg: str):
    """Notificacion de Windows via PowerShell."""
    try:
        script = f"""
Add-Type -AssemblyName System.Windows.Forms
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.Visible = $true
$notify.ShowBalloonTip(8000, '{title}', '{msg}', [System.Windows.Forms.ToolTipIcon]::Info)
Start-Sleep -Seconds 9
$notify.Dispose()
"""
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", script],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
    except Exception as e:
        log(f"Notificacion fallida: {e}")


def load_created() -> set:
    if CREATED_FILE.exists():
        data = json.loads(CREATED_FILE.read_text(encoding="utf-8"))
        return set(data.get("slugs", []))
    return set()


def save_created(slugs: set):
    existing = load_created()
    merged = existing | slugs
    CREATED_FILE.write_text(
        json.dumps({"slugs": sorted(merged), "total": len(merged)}, indent=2),
        encoding="utf-8"
    )


def get_commission_max(store: dict) -> float:
    c = store.get("commission") or {}
    return float(c.get("commission_max") or c.get("percentage") or 0)


def get_domain(store: dict) -> str:
    return re.sub(r"https?://(www\.)?", "", store.get("url", "")).rstrip("/").split("/")[0]


def sk_login_playwright() -> dict:
    """Loguea en SourceKnowledge via Playwright y devuelve las cookies de sesion."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("[SK] Playwright no instalado, se omite el filtro de trafico SK.")
        return {}

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context()
            page = ctx.new_page()
            page.goto("https://app.sourceknowledge.com/ui/login")
            page.wait_for_timeout(2000)
            if page.query_selector('input[type="email"], input[name="email"], input[name="login"]'):
                page.fill('input[type="email"], input[name="email"], input[name="login"]', SK_LOGIN)
                page.fill('input[type="password"]', SK_PASSWORD)
                page.keyboard.press("Enter")
                page.wait_for_timeout(3000)
            cookies = {c["name"]: c["value"] for c in ctx.cookies()}
            browser.close()
        if not cookies:
            log("[SK] No se obtuvieron cookies de sesion.")
        return cookies
    except Exception as e:
        log(f"[SK] Login fallido: {e}")
        return {}


def calculate_bid(bid_cpc: float | None) -> str:
    """Calcula el bid optimo basado en el top bid de SK.
    - < $0.15  → $0.08 (piso)
    - $0.15–$0.50 → 55% del bidCpc
    - > $0.50  → $0.25 (techo)
    """
    if bid_cpc is None:
        return "0.10"  # fallback si SK no devuelve datos
    if bid_cpc < 0.15:
        return "0.08"
    if bid_cpc <= 0.50:
        return f"{bid_cpc * 0.55:.2f}"
    return "0.25"


def sk_check_traffic(domains: list, cookies: dict) -> dict:
    """Devuelve {domain: {"clicks": N, "bidCpc": X}} consultando SourceKnowledge en tandas de 50."""
    result = {}
    for i in range(0, len(domains), 50):
        chunk = domains[i:i + 50]
        try:
            r = requests.post(
                "https://app.sourceknowledge.com/ui-api/affiliate/top-domains?_format=json",
                json={"domains": chunk},
                cookies=cookies,
                timeout=30
            )
            for item in r.json():
                result[item["domain"]] = {
                    "clicks": item.get("availableClicks"),
                    "bidCpc": item.get("bidCpc"),
                }
        except Exception as e:
            log(f"[SK] Error chequeando trafico: {e}")
    return result


def fetch_all_stores() -> list:
    headers = {"Authorization": f"Bearer {GALEONICA_KEY}:{GALEONICA_SECRET}"}
    stores = []
    page = 1
    while True:
        r = requests.get(
            "https://api.galeonica.com/api/v1/partner/stores",
            headers=headers,
            params={"page": page, "per_page": 100},
            timeout=30
        )
        batch = r.json().get("data") or []
        if not batch:
            break
        stores.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return stores


def pick_next_batch(stores: list, already_created: set, n: int, sk_cookies: dict = None) -> list:
    """Elige los proximos N stores US por comision que no fueron creados aun.

    Si sk_cookies esta disponible, descarta los dominios con menos de
    MIN_SK_CLICKS de trafico disponible en SourceKnowledge.
    """
    candidates = [
        s for s in stores
        if s.get("country") == "US"
        and MIN_COMMISSION <= get_commission_max(s) <= MAX_COMMISSION
        and (s.get("slug") or "") not in already_created
        and (s.get("slug") or "").strip() != ""
    ]
    candidates.sort(key=get_commission_max, reverse=True)

    if not sk_cookies:
        return candidates[:n]

    picked = []
    idx = 0
    while len(picked) < n and idx < len(candidates):
        chunk = candidates[idx: idx + n * 3]
        idx += len(chunk)
        domains = [get_domain(s) for s in chunk]
        traffic = sk_check_traffic(domains, sk_cookies)
        for s, d in zip(chunk, domains):
            info = traffic.get(d) or {}
            clicks = info.get("clicks")
            if clicks is not None and clicks >= MIN_SK_CLICKS:
                s["_sk_bidCpc"] = info.get("bidCpc")
                picked.append(s)
                if len(picked) >= n:
                    break
            else:
                log(f"  Descartado por bajo trafico SK: {s.get('name')} ({d}) -> {clicks} clicks")
    return picked


def get_ak_token() -> str:
    if AK_TOKEN:
        # Validar que el token guardado siga activo antes de usarlo
        try:
            r = requests.get(
                "https://login.ilatin-media.com/admin/api/OfferNew/",
                params={"version": 6, "token": AK_TOKEN, "limit": 1},
                timeout=10,
            )
            if r.json().get("status") == "OK":
                return AK_TOKEN
            log("Token guardado expirado, obteniendo uno nuevo...")
        except Exception:
            pass

    if not AK_PASSWORD:
        raise RuntimeError(
            "AdKernel: falta ADKERNEL_PASSWORD. "
            "Seteala con: [System.Environment]::SetEnvironmentVariable('ADKERNEL_PASSWORD','tu_pass','User')"
        )
    r = requests.get(
        "https://login.ilatin-media.com/admin/auth",
        params={"login": AK_LOGIN, "password": AK_PASSWORD},
        timeout=15,
    )
    if r.status_code != 200 or "<" in r.text:
        raise RuntimeError(f"AdKernel auth fallida ({r.status_code}): {r.text[:120]}")
    token = r.text.strip()
    if "incorrect" in token.lower():
        raise RuntimeError("AdKernel: credenciales incorrectas")
    # Persistir el nuevo token para la próxima ejecución
    import subprocess as _sp
    _sp.run(
        ["powershell", "-Command",
         f"[System.Environment]::SetEnvironmentVariable('ADKERNEL_TOKEN', '{token}', 'User')"],
        capture_output=True,
    )
    log(f"Token renovado y guardado (primeros 25 chars): {token[:25]}")
    return token


def build_csv_row(store: dict) -> dict:
    name = store.get("name", "").strip()
    slug = (store.get("slug") or "").strip()
    domain = get_domain(store)
    bid_cpc = store.get("_sk_bidCpc")
    bid = calculate_bid(bid_cpc)
    log(f"  [{name}] SK bidCpc={bid_cpc} -> bid={bid}")
    return {
        "brand_name":  name,
        "store_slug":  slug,
        "country":     "US",
        "bid":         bid,
        "sk_bid_cpc":  bid_cpc if bid_cpc is not None else "",
        "ad_title":    f"{name} - Official Site",
        "ad_desc":     f"Shop {name} online. Free shipping on qualifying orders.",
        "ad_display":  domain or f"{slug}.com",
        "ad_cta":      "Shop Now",
        "is_active":   "false",
    }


def main(dry_run: bool = False):
    log("=" * 60)
    log(f"Iniciando batch diario de creacion de offers{' [DRY RUN]' if dry_run else ''}")
    notify("Voolty Campaign Creator", f"Iniciando creacion de {BATCH_SIZE} offers nuevas...")

    # 1. Cargar historial
    already_created = load_created()
    log(f"Brands ya creados: {len(already_created)}")

    # 2. Obtener stores de Galeonica
    log("Obteniendo stores de Galeonica...")
    stores = fetch_all_stores()
    log(f"Total stores disponibles: {len(stores)}")

    # 3. Elegir proximos 5 (filtrando por trafico disponible en SourceKnowledge)
    sk_cookies = {}
    if SK_LOGIN and SK_PASSWORD:
        log("Logueando en SourceKnowledge...")
        sk_cookies = sk_login_playwright()
        if not sk_cookies:
            log("No se pudo loguear en SourceKnowledge, se omite el filtro de trafico.")
    else:
        log("SK_LOGIN/SK_PASSWORD no configurados, se omite el filtro de trafico SK.")

    # Pedimos 6x el batch para tener margen frente a stores pausados
    CANDIDATE_POOL = BATCH_SIZE * 6
    batch = pick_next_batch(stores, already_created, CANDIDATE_POOL, sk_cookies)
    if not batch:
        log("No hay mas stores disponibles para crear. Fin.")
        notify("Voolty Campaign Creator", "No hay mas stores disponibles.")
        return

    log(f"Pool de candidatos: {len(batch)} brands (se crean hasta {BATCH_SIZE} activos)")
    for s in batch:
        log(f"  - {s['name']} ({get_commission_max(s):.1f}%)  slug={s.get('slug')}")

    # 4. Escribir CSV temporal
    import csv
    import tempfile
    tmp_csv = SCRIPT_DIR / f"_daily_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    fieldnames = ["brand_name","store_slug","country","bid","sk_bid_cpc","ad_title","ad_desc","ad_display","ad_cta","is_active"]
    with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for s in batch:
            w.writerow(build_csv_row(s))

    # 5. Correr el creador principal con --set-geo
    if dry_run:
        log("DRY RUN: se omite la creacion real. Stores seleccionados:")
        for s in batch:
            row = build_csv_row(s)
            log(f"  [{row['brand_name']}]  bid={row['bid']}  sk_bid={row['sk_bid_cpc']}  dominio={row['ad_display']}")
        log("Batch diario finalizado (dry run).")
        return

    log("Corriendo voolty_campaign_creator.py --set-geo ...")
    env = os.environ.copy()
    env["ADKERNEL_TOKEN"]   = get_ak_token()
    env["ADKERNEL_LOGIN"]   = AK_LOGIN
    env["ADKERNEL_PASSWORD"] = AK_PASSWORD
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "voolty_campaign_creator.py"),
         "--csv", str(tmp_csv), "--set-geo", "--max-ok", str(BATCH_SIZE)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(SCRIPT_DIR)
    )

    log(result.stdout)
    if result.stderr:
        log(f"STDERR: {result.stderr}")

    # 6. Registrar solo los brands que fueron OK (no los SKIP — se reintentan el siguiente dia)
    stdout = result.stdout or ""
    skipped_names = set()
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("SKIP store pausado") or "SKIPPED" in line:
            # La linea anterior del output es "[BrandName] ----"
            # Buscamos el slug en el batch por nombre
            pass  # se hace abajo via parseo del bloque
    # Parseo: cada bloque "[BrandName] ---" seguido de "SKIP" → skip
    import re as _re
    skip_brands = set(_re.findall(r'\[([^\]]+)\] -{10,}\n\s+SKIP', stdout))
    ok_slugs = {
        s.get("slug", "") for s in batch
        if s.get("name", "").strip() not in skip_brands
    }
    save_created(ok_slugs)
    skipped_count = len(batch) - len(ok_slugs)
    log(f"Brands registrados en historial: {ok_slugs}")
    if skipped_count:
        log(f"Brands omitidos (SKIP, se reintentan manana): {skip_brands}")

    # 7. Limpiar CSV temporal
    try:
        tmp_csv.unlink()
    except Exception:
        pass

    # 8. Notificacion final
    ok_count = result.stdout.count("OK Listo")
    skip_count = result.stdout.count("SKIP store pausado")
    msg = f"{ok_count} offers creadas"
    if skip_count:
        msg += f", {skip_count} stores pausados (saltados)"
    msg += "."
    log(msg)
    log("Batch diario finalizado.")
    notify("Voolty Campaign Creator", msg)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-ok",  type=int, default=BATCH_SIZE,
                        help="Cantidad de offers a crear (default: 5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simular sin crear nada en AdKernel/Binom")
    args = parser.parse_args()
    BATCH_SIZE = args.max_ok
    main(dry_run=args.dry_run)
