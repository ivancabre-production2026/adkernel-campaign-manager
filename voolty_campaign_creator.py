"""
Voolty Campaign Creator
=======================
Automatiza la creación masiva de campañas en 3 sistemas:
  1. Binom (ilatintrack.biz)  → Crea el Offer + Campaign de tracking
  2. AdKernel (ilatin-media)  → Crea el Campaign + OfferNew con el link de Binom
  3. Galeonica (Voolty)       → Fuente de las offers/brands (URL de afiliado)

Flujo por cada brand:
  Visitante → AdKernel → Binom (tracking) → Galeonica/Voolty (afiliado)

Uso:
  python voolty_campaign_creator.py --csv brands.csv
  python voolty_campaign_creator.py --ejemplo        # genera CSV de ejemplo
  python voolty_campaign_creator.py --listar-stores  # lista stores de Galeonica
"""

import argparse
import csv
import json
import os
import sys
import time
from typing import Optional

import requests

# ------ Configuración ------------------------------------------------------------------------------------------------------------------------
# Podés setear las variables de entorno o editar los valores acá directamente.

# AdKernel
ADKERNEL_BASE    = "https://login.ilatin-media.com"
ADKERNEL_LOGIN   = os.getenv("ADKERNEL_LOGIN", "")
ADKERNEL_PASSWORD= os.getenv("ADKERNEL_PASSWORD", "")
ADKERNEL_TOKEN   = os.getenv("ADKERNEL_TOKEN", "")   # token estático (recomendado)
ADKERNEL_VERSION = 6

# Valores fijos de AdKernel (Voolty campaigns de Iván)
AK_ADVERTISER_ID     = 252364
AK_REMOTE_FEED       = 1214899   # Voolty - collectivepage
AK_PUB_FEED          = 717952    # SourceKnowledge - Main
AK_VOOLTY_CAMPAIGN_ID = 2513696  # Campaña existente "Voolty - collectivepage"

# Binom
BINOM_BASE       = "https://ilatintrack.biz"
BINOM_PANEL_BASE = "https://ilatintrack.biz/panel"
BINOM_KEY        = os.getenv("BINOM_API_KEY", "1f109c4331f132305a195943dff50e007f36333f95b3189c7def94d0e0c6bc8b")
BINOM_LOGIN      = os.getenv("BINOM_LOGIN", "")
BINOM_PASSWORD   = os.getenv("BINOM_PASSWORD", "")

# Postback S2S que Binom dispara hacia AdKernel al confirmar una conversion.
# El {id} tiene que ser el Goal ID real de la offer en AdKernel (ver ak_get_conversion_goal_id).
BINOM_S2S_POSTBACK_TEMPLATE = "https://xml.ilatin-media.com/conversion?id={goal_id}&c={{externalid}}&value={{payout}}"

# Valores fijos de Binom (grupo/dominio de campañas Adkernel de Iván)
BINOM_TS_ID         = 266                                    # Traffic Source: Adkernel
BINOM_CAMPAIGN_GROUP= "71d41d3f-6e75-4c5c-b3e8-21e8c36fa5bf"  # Grupo "Adkernel"
BINOM_DOMAIN_UUID   = "54f344d6-317c-461b-b9f3-5a67feb7e67d"  # Dominio de tracking
BINOM_AFF_NET_ID    = 363                                    # Voolty - Iván ILM
BINOM_OFFER_GROUP   = "48627415-2010-406c-b613-86b97bbe4345"   # Grupo de offers

# Galeonica
GALEONICA_PARTNER_KEY = "vp_t1eB2RG1N4b1sp45AfzcHK7Zm43QfTVw"
GALEONICA_API_BASE    = "https://api.galeonica.com/api/v1/partner"
GALEONICA_API_SECRET  = os.getenv("GALEONICA_API_SECRET", "18bf31c4c7d3cd7435e3ce430364ad1886f1aa581e056ab158bcac0ef73e070f")

# Binom tracking URL → se construye con el key del campaign
# Los tokens {subid}, {conversion}, etc. son de AdKernel/Binom
BINOM_URL_TEMPLATE = (
    "{base}/index.php?key={key}"
    "&cid={{conversion}}&bid={{price}}"
    "&url_referrer={{query}}&domain={{search_referrer}}"
    "&subid={{subid}}&keyword={{keyword}}"
    "&domain2={{search_referrer_domain}}"
)

# Galeonica tracking URL
VOOLTY_URL_TEMPLATE = (
    "https://go.voolty.com/api/v1/out"
    "?store={slug}&partner={partner}&subid={{clickid}}"
)


# ------ AdKernel Auth ------------------------------------------------------------------------------------------------------------------------

def ak_get_token() -> str:
    if ADKERNEL_TOKEN:
        return ADKERNEL_TOKEN
    if ADKERNEL_LOGIN and ADKERNEL_PASSWORD:
        r = requests.get(
            f"{ADKERNEL_BASE}/admin/auth",
            params={"login": ADKERNEL_LOGIN, "password": ADKERNEL_PASSWORD},
            timeout=30
        )
        r.raise_for_status()
        token = r.text.strip()
        if "incorrect" in token.lower():
            raise ValueError(f"AdKernel: credenciales incorrectas: {token}")
        return token
    # Pedir credenciales interactivamente
    import getpass
    print("AdKernel: ingresá tus credenciales (o seteá ADKERNEL_TOKEN como variable de entorno)")
    login = input("  Login: ").strip()
    password = getpass.getpass("  Password: ").strip()
    r = requests.get(
        f"{ADKERNEL_BASE}/admin/auth",
        params={"login": login, "password": password},
        timeout=30
    )
    r.raise_for_status()
    token = r.text.strip()
    if "incorrect" in token.lower():
        raise ValueError(f"AdKernel: credenciales incorrectas")
    print(f"  Token obtenido OK")
    return token


def ak_post(endpoint: str, token: str, body: dict) -> dict:
    url = f"{ADKERNEL_BASE}/admin/api/{endpoint}/"
    r = requests.post(
        url,
        params={"version": ADKERNEL_VERSION, "token": token},
        json=body,
        timeout=30
    )
    data = r.json()
    if data.get("status") != "OK":
        raise RuntimeError(f"AdKernel [{endpoint}]: {json.dumps(data, indent=2)}")
    return data


def ak_extract_id(response: dict) -> int:
    resp = response.get("response", {})
    # Formato creación: {"created": 12345}
    if "created" in resp:
        return int(resp["created"])
    # Formato edición: {"rows": {"12345": {...}}}
    rows = resp.get("rows", {})
    if rows:
        return int(next(iter(rows.keys())))
    raise RuntimeError(f"AdKernel: no ID en respuesta: {response}")


def ak_get_conversion_goal_id(token: str, offer_id: int) -> Optional[int]:
    """Lee el Goal ID de conversion real de una OfferNew ya creada en AdKernel."""
    r = requests.get(
        f"{ADKERNEL_BASE}/admin/api/OfferNew/{offer_id}",
        params={"version": ADKERNEL_VERSION, "token": token},
        timeout=30
    )
    rows = r.json().get("response", {}).get("rows", {})
    o = list(rows.values())[0] if rows else {}
    conv_vals = o.get("Conversions", {}).get("value", {})
    if not conv_vals:
        return None
    return next(iter(conv_vals.values())).get("id")


# ------ Binom API --------------------------------------------------------------------------------------------------------------------------------

def binom_headers() -> dict:
    return {"Api-Key": BINOM_KEY}


def binom_post(endpoint: str, body: dict) -> dict:
    r = requests.post(
        f"{BINOM_BASE}/public/api/v1/{endpoint}",
        headers=binom_headers(),
        json=body,
        timeout=30
    )
    if not r.ok:
        raise RuntimeError(f"Binom {endpoint} {r.status_code}: {r.text[:500]}")
    return r.json()


def binom_get(endpoint: str) -> dict:
    r = requests.get(
        f"{BINOM_BASE}/public/api/v1/{endpoint}",
        headers=binom_headers(),
        timeout=30
    )
    r.raise_for_status()
    return r.json()


# ------ Galeonica API ----------------------------------------------------------------------------------------------------------------------

def galeonica_headers() -> dict:
    return {"Authorization": f"Bearer {GALEONICA_PARTNER_KEY}:{GALEONICA_API_SECRET}"}


def galeonica_get(endpoint: str, params: dict = None) -> dict:
    r = requests.get(
        f"{GALEONICA_API_BASE}/{endpoint}",
        headers=galeonica_headers(),
        params=params or {},
        timeout=30
    )
    r.raise_for_status()
    return r.json()


def listar_stores(search: str = "", page: int = 1, per_page: int = 50) -> list:
    """Lista los stores de Galeonica con su slug y URL de afiliado."""
    try:
        data = galeonica_get("stores", {"search": search, "page": page, "per_page": per_page})
        stores = data.get("data") or data.get("stores") or data
        if isinstance(stores, list):
            return stores
    except Exception as e:
        print(f"[Galeonica] Error al listar stores via API: {e}")
        print("  → Usá la web: https://partner.galeonica.com/stores")
    return []


def build_galeonica_url(slug: str) -> str:
    """Construye la URL de Voolty para un store. Usa {clickid} = macro de Binom."""
    return (
        f"https://go.voolty.com/api/v1/out"
        f"?store={slug}&partner={GALEONICA_PARTNER_KEY}&subid={{clickid}}"
    )


# ------ Chequeo de duplicados en AdKernel ---------------------------------------------------------------------------------

_ak_existing_names: set | None = None  # cache para la sesión

def ak_get_existing_offer_names(token: str, campaign_id: int) -> set:
    """
    Retorna el set de nombres (en minúsculas) de las OfferNew ya existentes
    en la campaña de AdKernel. Hace la llamada una sola vez por sesión (cache).
    """
    global _ak_existing_names
    if _ak_existing_names is not None:
        return _ak_existing_names

    try:
        r = requests.get(
            f"{ADKERNEL_BASE}/admin/api/OfferNew/",
            params={
                "version": ADKERNEL_VERSION,
                "token": token,
                "ad_campaign_id": campaign_id,
                "limit": 1000,
            },
            timeout=30,
        )
        rows = r.json().get("response", {}).get("rows", {})
        _ak_existing_names = {v.get("name", "").lower() for v in rows.values()}
    except Exception as e:
        print(f"  [AK duplicados] No se pudo obtener lista de offers existentes: {e}")
        _ak_existing_names = set()

    return _ak_existing_names


def ak_offer_already_exists(token: str, brand_name: str, campaign_id: int) -> bool:
    """Devuelve True si ya existe una offer con el nombre de ese brand en la campaña."""
    existing = ak_get_existing_offer_names(token, campaign_id)
    # Nuestro formato: "US - {brand} - Voolty"
    expected_name = f"us - {brand_name.lower()} - voolty"
    return expected_name in existing


# ------ Verificación de URL Voolty -----------------------------------------------------------------------------------------

# Dominios que indican que una offer está pausada o el slug no existe.
_VOOLTY_BAD_DOMAINS = {
    "voolty.com", "go.voolty.com", "galeonica.com",
    "partner.galeonica.com", "api.galeonica.com",
}

def verificar_url_voolty(slug: str) -> tuple[bool, str]:
    """
    Verifica que el store esté activo en Voolty.

    Voolty responde con un HTML que contiene un meta-refresh hacia el tracker del merchant.
    Si ese meta-refresh existe y apunta a un dominio externo → store activo.
    Si el body está vacío o no hay meta-refresh → store pausado o slug inválido.

    Retorna (True, destino) o (False, motivo).
    """
    import re as _re
    from urllib.parse import urlparse as _urlparse

    url = build_galeonica_url(slug).replace("{clickid}", "check")
    try:
        r = requests.get(
            url,
            allow_redirects=False,   # Voolty usa meta-refresh, no HTTP redirect
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        body = r.text.strip()

        if not body:
            return False, "respuesta vacía (slug inválido o store eliminado)"

        # Buscar la URL en el meta-refresh: content="1;url=https://..."
        m = _re.search(r'content="[^"]*?url=([^"]+)"', body, _re.IGNORECASE)
        if not m:
            return False, "no hay meta-refresh en la respuesta (store pausado)"

        meta_url = m.group(1).replace("&amp;", "&").strip()
        dest_domain = _urlparse(meta_url).netloc.lower().lstrip("www.")

        # Si el meta-refresh apunta a voolty/galeonica → pausado
        if dest_domain in _VOOLTY_BAD_DOMAINS:
            return False, f"meta-refresh apunta a {dest_domain} (store pausado)"

        return True, dest_domain

    except requests.exceptions.Timeout:
        return False, "timeout al verificar la URL"
    except requests.exceptions.RequestException as e:
        return False, f"error de red: {e}"


# ------ Step 1: Crear Offer en Binom ----------------------------------------------------------------------------------------

def crear_binom_offer(brand_name: str, dest_url: str, country_code: str = "US") -> int:
    """Crea el offer en Binom apuntando a Voolty. Retorna el offer ID."""
    body = {
        "name": f"{country_code} - {brand_name} - Voolty",
        "url": dest_url,
        "countryCode": country_code,
        "currency": "USD",
        "amount": 0,
        "isAuto": True,
        "isUpsell": False,
        "groupUuid": BINOM_OFFER_GROUP,
        "affiliateNetworkId": BINOM_AFF_NET_ID,
    }
    data = binom_post("offer", {"offer": body})
    offer_id = data.get("id") or data.get("offer", {}).get("id")
    if not offer_id:
        raise RuntimeError(f"Binom offer no devolvió ID: {data}")
    print(f"  [Binom Offer] ID={offer_id}  '{body['name']}'")
    return int(offer_id)


# ------ Step 2: Crear Campaign en Binom ----------------------------------------------------------------------------------

def crear_binom_campaign(brand_name: str, offer_id: int, country_code: str = "US") -> tuple[int, str]:
    """Crea la campaña en Binom con la offer en el path. Retorna (campaign_id, tracking_url)."""
    body = {
        "name": f"{country_code} - {brand_name} - Voolty - Adkernel",
        "groupUuid": BINOM_CAMPAIGN_GROUP,
        "domainUuid": BINOM_DOMAIN_UUID,
        "trafficSourceId": BINOM_TS_ID,
        "costModel": "CPC",
        "currency": "USD",
        "cost": 0,
        "isAutoCost": True,
        "hideReferrerType": "NONE",
        "distributionType": "NORMAL",
        "campaignSettings": {
            "s2sPostback": "",
            "postbackPercent": 100,
            "payoutPercent": 100,
            "trafficLossPercent": 0,
            "appendToCampaignUrl": "",
            "appendToOfferUrl": "",
            "appendToLandingUrl": "",
        },
        "customRotation": {
            "defaultPaths": [{
                "name": "Path 1",
                "enabled": True,
                "weight": 100,
                "landings": [{"id": 0, "weight": 100, "enabled": True, "name": "DIRECT", "languageCode": ""}],
                "offers": [{"offerId": offer_id, "campaignId": 0, "weight": 100, "enabled": True, "directUrl": ""}],
            }],
            "rules": [],
        },
    }
    data = binom_post("campaign", body)
    camp_id = data.get("id")
    if not camp_id:
        raise RuntimeError(f"Binom campaign no devolvió ID: {data}")

    # Key comes from GET (not in POST response)
    camp_data = binom_get(f"campaign/{camp_id}")
    camp_key = camp_data.get("key")
    tracking_url = camp_data.get("link") or (
        f"{BINOM_BASE}/index.php?key={camp_key}"
        "&cid={conversion}&bid={bid}&subid={subid}&keyword={keyword}"
        "&url_referrer={query}&domain={search_referrer}&domain2={search_referrer_domain}"
    ) if camp_key else ""

    print(f"  [Binom Campaign] ID={camp_id}  '{body['name']}'")
    return int(camp_id), tracking_url


# ------ Step 3: Crear Campaign en AdKernel ----------------------------------------------------------------------------

def crear_ak_campaign(token: str, brand_name: str, cfg: dict) -> int:
    """
    Crea la campaña en AdKernel.
    Retorna el campaign ID.
    """
    body = {
        "advertiser_id": AK_ADVERTISER_ID,
        "remotefeed_id": AK_REMOTE_FEED,
        "name": f"US - {brand_name}",
        "pricing_model": "CPC",
        "type": "CPC",
        "is_active": _bool(cfg.get("is_active", False)),  # default inactivo
        "budget_limiter_type": cfg.get("budget_limiter_type", "EVENLY"),
        "clicks_per_ip": int(cfg.get("clicks_per_ip", 1)),
        "pub_feeds": [AK_PUB_FEED],
    }
    if cfg.get("budget_daily") not in (None, ""):
        body["budget_daily"] = float(cfg["budget_daily"])
    if cfg.get("budget_total") not in (None, ""):
        body["budget_total"] = float(cfg["budget_total"])

    data = ak_post("Campaign", token, body)
    camp_id = ak_extract_id(data)
    print(f"  [AdKernel Campaign] ID={camp_id}  '{body['name']}'")
    return camp_id


# ------ Step 4: Crear OfferNew en AdKernel ----------------------------------------------------------------------------

def _calc_domain_bid_adj(bid_cpc: float | None) -> float:
    """
    Convierte el bidCpc de SK al bid_adjustment para el keyword de dominio.
    Usa la misma logica que calculate_bid() en daily_batch.py pero devuelve
    el ratio respecto al Default CPC ($0.10).

    bidCpc < $0.15  -> target $0.08 -> adj 0.80
    bidCpc $0.15-$0.50 -> target 55% del bidCpc -> adj = target / 0.10
    bidCpc > $0.50  -> target $0.25 -> adj 2.50
    bidCpc None     -> adj 2.0 (fallback conservador)
    """
    if bid_cpc is None:
        return 2.0
    if bid_cpc < 0.15:
        target = 0.08
    elif bid_cpc <= 0.50:
        target = bid_cpc * 0.55
    else:
        target = 0.25
    return round(target / 0.10, 4)


def _build_keywords(domain: str, brand_kw: str, domain_bid_adj: float = 2.0) -> list:
    """
    Genera el set de keywords estandar para una brand:
    - RON (*): fallback, bid 100%
    - dominio (Broad/Phrase/Exact): habilitado, bid segun SK bidCpc
    - keyword de marca (Broad/Phrase/Exact): deshabilitado, bid 50%
    """
    kws = []
    kws.append({"kwd": "*", "match_type": "ron", "bid_adjustment": 1.0, "enabled": True, "is_negative": False})
    for mt in ["broad", "phrase", "exact"]:
        kws.append({"kwd": domain,    "match_type": mt, "bid_adjustment": domain_bid_adj, "enabled": True,  "is_negative": False})
    for mt in ["broad", "phrase", "exact"]:
        kws.append({"kwd": brand_kw,  "match_type": mt, "bid_adjustment": 0.5,           "enabled": False, "is_negative": False})
    return kws


def crear_ak_offer(token: str, brand_name: str, ak_campaign_id: int,
                   dest_url: str, cfg: dict) -> int:
    """
    Crea el OfferNew en AdKernel con keywords y goal de conversión.
    Retorna el offer ID.
    """
    domain   = cfg.get("ad_display", "").strip() or f"{brand_name.lower().replace(' ','-')}.com"
    brand_kw = brand_name.lower()
    sk_bid_cpc = cfg.get("sk_bid_cpc")
    if sk_bid_cpc not in (None, ""):
        try:
            sk_bid_cpc = float(sk_bid_cpc)
        except (ValueError, TypeError):
            sk_bid_cpc = None
    domain_bid_adj = _calc_domain_bid_adj(sk_bid_cpc)

    ad = {
        "type": "TEXT",
        "title": cfg.get("ad_title", brand_name),
        "desc": cfg.get("ad_desc", ""),
        "display": domain,
        "dest_url": dest_url,
        "cta": cfg.get("ad_cta", "Shop Now"),
        "enabled": True,
    }

    body = {
        "ad_campaign_id": ak_campaign_id,
        "name": f"{cfg.get('country', 'US').strip().upper() or 'US'} - {brand_name} - Voolty",
        "is_active": _bool(cfg.get("is_active", False)),  # default inactivo — activar manualmente
        "bid": float(cfg.get("bid", 0.1)),
        "optimize_bids_new": True,
        "optimize_xml_source_type": "SUBID",
        "optimize_subid_test_clicks": int(cfg.get("optimize_test_clicks", 50)),
        "optimize_subid_test_cost": float(cfg.get("optimize_test_cost", 3)),
        "optimize_subid_test_conversions": int(cfg.get("optimize_test_conversions", 1)),
        "optimize_subid_block_clicks": int(cfg.get("optimize_block_clicks", 60)),
        "optimize_source_block_cost": float(cfg.get("optimize_block_cost", 3)),
        "ad_rotation": cfg.get("ad_rotation", "CTR"),
        "language": cfg.get("language", "en"),
        "Ad": {"mode": "REPLACE", "create": [ad]},
        "Keyword": {"mode": "REPLACE", "create": _build_keywords(domain, brand_kw, domain_bid_adj)},
        "Conversions": {"mode": "REPLACE", "create": [{"name": f"{brand_name} Conversion", "cost_per_value": 1}]},
        "PublisherFeed": {
            "mode": "REPLACE",
            "edit": [{"feed": AK_PUB_FEED, "enabled": True, "bid_adjustment": 1}]
        },
    }

    data = ak_post("OfferNew", token, body)
    offer_id = ak_extract_id(data)
    print(f"  [AdKernel OfferNew] ID={offer_id}  '{body['name']}'")
    return offer_id


# ------ Step 4: Geo US via Playwright ----------------------------------------------------------------------------------------------------

def set_us_geo_playwright(offer_ids: list[int], ak_login: str, ak_password: str):
    """
    Abre el browser, navega a cada offer en AdKernel y aplica geo US vía Import Locations.
    Requiere: pip install playwright && python -m playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [Geo US] Playwright no instalado. Corré: pip install playwright && python -m playwright install chromium")
        return

    CSV_US = "country,bid_adjustment\nus,1"

    def inject_and_import(page, offer_id: int):
        page.goto(f"{ADKERNEL_BASE}/admin#form/OfferNew/edit?id={offer_id}")
        page.wait_for_load_state("networkidle", timeout=15000)
        page.wait_for_timeout(3000)

        # Click tab Locations
        page.evaluate("""() => {
            const el = Array.from(document.querySelectorAll('td, a')).find(
                e => e.textContent.trim() === 'Locations' && e.offsetParent !== null);
            if (el) el.click();
        }""")
        page.wait_for_timeout(2000)

        # Click Import Locations
        page.evaluate("""() => {
            const btn = Array.from(document.querySelectorAll('button')).find(
                b => b.textContent.includes('Import Locations'));
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(1500)

        # Inyectar CSV en el file input
        page.evaluate(f"""(csv) => {{
            const fi = document.querySelector('input[type="file"]');
            if (!fi) return;
            const file = new File([csv], 'us.csv', {{type:'text/csv'}});
            const dt = new DataTransfer();
            dt.items.add(file);
            fi.files = dt.files;
            fi.dispatchEvent(new Event('change', {{bubbles: true}}));
        }}""", CSV_US)
        page.wait_for_timeout(800)

        # Submit del dialog (último botón con 'Submit')
        page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button'))
                .filter(b => b.textContent.includes('Submit'));
            if (btns.length) btns[btns.length - 1].click();
        }""")
        page.wait_for_timeout(3000)

        # Submit del form principal
        page.evaluate("""() => {
            const btn = Array.from(document.querySelectorAll('button')).find(
                b => b.textContent.includes('Submit'));
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(4000)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()

        # Login
        print("  [Geo US] Abriendo browser para login en AdKernel...")
        page.goto(f"{ADKERNEL_BASE}/admin")
        page.wait_for_timeout(3000)

        # Si hay form de login, rellenarlo
        if page.query_selector('input[name="login"], input[type="text"]'):
            page.fill('input[name="login"], input[type="text"]', ak_login)
            page.fill('input[name="password"], input[type="password"]', ak_password)
            page.keyboard.press("Enter")
            page.wait_for_timeout(4000)

        for offer_id in offer_ids:
            print(f"  [Geo US] Offer {offer_id}...")
            try:
                inject_and_import(page, offer_id)
                print(f"  [Geo US] OK {offer_id} geo US seteada")
            except Exception as e:
                print(f"  [Geo US] ERROR {offer_id}: {e}")

        browser.close()
    print("  [Geo US] Listo.")


# ------ S2S Postback en Binom (via Playwright) ----------------------------------------------------------------------------------------------

def set_binom_s2s_postback_playwright(postback_pairs: list[tuple[int, str]], binom_login: str, binom_password: str):
    """
    Abre el browser, loguea en el panel de Binom y completa el campo "S2S Postback"
    de cada campana con el conversion goal id real de su offer en AdKernel.
    postback_pairs: lista de (binom_campaign_id, postback_url).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [Binom S2S] Playwright no instalado. Corré: pip install playwright && python -m playwright install chromium")
        return

    def fill_postback(page, camp_id: int, url: str):
        page.goto(f"{BINOM_PANEL_BASE}/campaigns/edit/{camp_id}")
        page.wait_for_load_state("networkidle", timeout=15000)
        page.wait_for_timeout(2000)

        # Expandir "Advanced Settings" si esta colapsado
        page.evaluate("""() => {
            const el = Array.from(document.querySelectorAll('span, div')).find(
                e => e.textContent.trim() === 'Advanced Settings' && e.offsetParent !== null);
            if (el) el.click();
        }""")
        page.wait_for_timeout(1000)

        # Ubicar el input de "S2S Postback" por su label y completarlo
        filled = page.evaluate("""(url) => {
            function ownText(el) {
                let t = '';
                for (const node of el.childNodes) {
                    if (node.nodeType === Node.TEXT_NODE) t += node.textContent;
                }
                return t.trim();
            }
            const span = Array.from(document.querySelectorAll('span')).find(e => ownText(e) === 'S2S Postback');
            if (!span) return false;
            let p = span, input = null;
            for (let i = 0; i < 6 && p && !input; i++) {
                input = p.querySelector ? p.querySelector('input, textarea') : null;
                if (!input) p = p.parentElement;
            }
            if (!input) return false;
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(input, url);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }""", url)

        if not filled:
            raise RuntimeError("campo S2S Postback no encontrado")

        page.wait_for_timeout(500)

        # Guardar
        page.evaluate("""() => {
            const btn = Array.from(document.querySelectorAll('button')).find(
                b => b.textContent.trim() === 'Save' && b.offsetParent !== null);
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(2500)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()

        print("  [Binom S2S] Abriendo browser para login en Binom...")
        page.goto(f"{BINOM_PANEL_BASE}/login")
        page.wait_for_timeout(3000)

        if page.query_selector('input[name="login"], input[type="text"], input[type="email"]'):
            page.fill('input[name="login"], input[type="text"], input[type="email"]', binom_login)
            page.fill('input[name="password"], input[type="password"]', binom_password)
            page.keyboard.press("Enter")
            page.wait_for_timeout(4000)

        for camp_id, url in postback_pairs:
            print(f"  [Binom S2S] Campana {camp_id}...")
            try:
                fill_postback(page, camp_id, url)
                print(f"  [Binom S2S] OK {camp_id} postback seteado")
            except Exception as e:
                print(f"  [Binom S2S] ERROR {camp_id}: {e}")

        browser.close()
    print("  [Binom S2S] Listo.")


# ------ Función principal ----------------------------------------------------------------------------------------------------------------

def crear_brand(cfg: dict, ak_token: str) -> dict:
    """
    Flujo completo: Binom offer → Binom campaign → AdKernel OfferNew.
    """
    brand   = cfg["brand_name"].strip()
    slug    = cfg["store_slug"].strip()
    country = cfg.get("country", "US").strip().upper() or "US"

    print(f"\n[{brand}] ----------------------------------------------------------")

    # 0. Verificar que el store esté activo en Voolty antes de crear nada
    ok, detail = verificar_url_voolty(slug)
    if not ok:
        print(f"  SKIP store pausado o inactivo: {detail}")
        return {
            "brand":  brand,
            "slug":   slug,
            "status": f"SKIPPED: {detail}",
        }

    print(f"  [Voolty OK] redirige a {detail}")

    # 0b. Verificar que no exista ya en AdKernel (evita duplicados de corridas anteriores)
    if ak_offer_already_exists(ak_token, brand, AK_VOOLTY_CAMPAIGN_ID):
        print(f"  SKIP ya existe en AdKernel: 'US - {brand} - Voolty'")
        return {
            "brand":  brand,
            "slug":   slug,
            "status": "SKIPPED: ya existe en AdKernel",
        }

    voolty_url = build_galeonica_url(slug)

    # 1. Binom offer → apunta a Voolty
    binom_offer_id = crear_binom_offer(brand, voolty_url, country)
    time.sleep(0.3)

    # 2. Binom campaign → apunta a la offer
    binom_camp_id, binom_url = crear_binom_campaign(brand, binom_offer_id, country)
    time.sleep(0.3)

    # 3. AdKernel OfferNew → dest_url apunta al tracker (Binom)
    ak_offer_id = crear_ak_offer(ak_token, brand, AK_VOOLTY_CAMPAIGN_ID, binom_url, cfg)

    # 4. Goal ID real de conversion en AdKernel -> postback que Binom le va a disparar
    goal_id = ak_get_conversion_goal_id(ak_token, ak_offer_id)
    postback_url = BINOM_S2S_POSTBACK_TEMPLATE.format(goal_id=goal_id) if goal_id else ""
    if not goal_id:
        print(f"  [Binom S2S] No se pudo leer el goal id de la offer {ak_offer_id}, postback queda pendiente")

    result = {
        "brand":           brand,
        "slug":            slug,
        "voolty_url":      voolty_url,
        "binom_offer":     binom_offer_id,
        "binom_campaign":  binom_camp_id,
        "binom_url":       binom_url,
        "ak_offer":        ak_offer_id,
        "ak_campaign":     AK_VOOLTY_CAMPAIGN_ID,
        "postback_url":    postback_url,
        "status":          "OK",
    }
    print(f"  OK Listo")
    return result


def run_csv(path: str, set_geo: bool = False, ak_login: str = "", ak_password: str = "", max_ok: int = 0):
    ak_token = ak_get_token()
    results = []

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"\nProcesando {len(rows)} brand(s)...\n")

    ok_count = 0
    for i, row in enumerate(rows, 1):
        if max_ok and ok_count >= max_ok:
            print(f"\n[Límite --max-ok {max_ok} alcanzado, deteniendo]")
            break
        row = {k.strip(): v.strip() for k, v in row.items()}
        print(f"[{i}/{len(rows)}]", end=" ")
        try:
            result = crear_brand(row, ak_token)
            results.append(result)
            if result.get("status") == "OK":
                ok_count += 1
        except Exception as e:
            brand = row.get("brand_name", f"row {i}")
            print(f"\n  [ERROR] {e}")
            results.append({"brand": brand, "status": f"ERROR: {e}"})

        if i < len(rows):
            time.sleep(1)

    # Resumen
    print("\n------ Resumen " + "--" * 50)
    for r in results:
        st = r.get("status", "")
        if st == "OK":
            print(f"  OK      {r['brand']}")
            print(f"          AdKernel: campaign={r['ak_campaign']}  offer={r['ak_offer']}")
        elif st.startswith("SKIPPED"):
            print(f"  SKIP    {r.get('brand')} → {st}")
        else:
            print(f"  ERROR   {r.get('brand')} → {st}")

    # Guardar CSV de resultados
    out_path = path.replace(".csv", "_resultados.csv")
    fieldnames = ["brand", "slug", "binom_offer", "binom_campaign", "binom_url",
                  "ak_campaign", "ak_offer", "postback_url", "status"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)
    print(f"\nResultados guardados en: {out_path}")

    # Setear el S2S Postback en Binom (necesario para que las conversiones lleguen a AdKernel)
    postback_pairs = [
        (r["binom_campaign"], r["postback_url"])
        for r in results
        if r.get("status") == "OK" and r.get("postback_url")
    ]
    if postback_pairs:
        if BINOM_LOGIN and BINOM_PASSWORD:
            print(f"\n[Binom S2S] Seteando postback en {len(postback_pairs)} campana(s) via browser...")
            set_binom_s2s_postback_playwright(postback_pairs, BINOM_LOGIN, BINOM_PASSWORD)
        else:
            print("\n[Binom S2S] BINOM_LOGIN/BINOM_PASSWORD no configurados. Postbacks pendientes de setear a mano:")
            for camp_id, url in postback_pairs:
                print(f"    campana {camp_id}: {url}")

    # Paso opcional: setear geo US en AdKernel via browser
    if set_geo:
        ok_offers = [r["ak_offer"] for r in results if r.get("status") == "OK"]
        if ok_offers:
            print(f"\n[Geo US] Seteando geo US en {len(ok_offers)} offers via browser...")
            login = ak_login or os.getenv("ADKERNEL_LOGIN", "")
            pwd   = ak_password or os.getenv("ADKERNEL_PASSWORD", "")
            if not login or not pwd:
                import getpass
                if not login:
                    login = input("AdKernel login: ").strip()
                if not pwd:
                    pwd = getpass.getpass("AdKernel password: ")
            set_us_geo_playwright(ok_offers, login, pwd)


# ------ CSV de ejemplo ----------------------------------------------------------------------------------------------------------------------

EJEMPLO_CSV = """\
brand_name,store_slug,budget_daily,budget_total,budget_limiter_type,is_active,clicks_per_ip,bid,ad_title,ad_desc,ad_display,ad_cta,ad_rotation,language,optimize_test_clicks,optimize_test_cost,optimize_test_conversions,optimize_block_clicks,optimize_block_cost
Bombas Socks,bombas,10,,EVENLY,true,1,0.1,Bombas Socks - Premium Comfort,"Discover the most comfortable socks. Free shipping on every order.",bombas.com,Shop Now,CTR,en,50,3,1,60,3
Etsy,etsy,12,,ASAP,true,1,0.08,Etsy - Handcrafted & Unique,"Find handcrafted items from top creators around the world.",etsy.com,Shop Now,CTR,en,50,3,1,60,3
1-800 Contacts,1800contacts,8,,EVENLY,false,1,0.12,1-800 Contacts - Easy Reorders,"Order contacts online. Fast delivery. Best price guarantee.",1800contacts.com,Order Now,CTR,en,50,3,1,60,3
"""


def write_ejemplo_csv(path: str = "brands_ejemplo.csv"):
    with open(path, "w", encoding="utf-8") as f:
        f.write(EJEMPLO_CSV)
    print(f"CSV de ejemplo creado: {path}")
    print()
    print("Columnas del CSV:")
    print("  brand_name              Nombre del brand (ej. 'Bombas Socks')")
    print("  store_slug              Slug del store en Galeonica (ej. 'bombas')")
    print("                          → Verifica en: https://partner.galeonica.com/stores")
    print("  budget_daily            Presupuesto diario en AdKernel (USD)")
    print("  budget_total            Presupuesto total (vacío = sin límite)")
    print("  budget_limiter_type     EVENLY | ASAP")
    print("  is_active               true | false")
    print("  clicks_per_ip           Clicks por IP (default: 1)")
    print("  bid                     CPC bid en AdKernel (default: 0.1)")
    print("  ad_title                Título del anuncio")
    print("  ad_desc                 Descripción del anuncio")
    print("  ad_display              Dominio visible (ej. 'bombas.com')")
    print("  ad_cta                  Call to action (default: 'Shop Now')")
    print("  ad_rotation             CTR | RANDOM | CR | EPC (default: CTR)")
    print("  language                Idioma (default: en)")
    print("  optimize_test_clicks    Clicks mínimos para optimización (default: 50)")
    print("  optimize_test_cost      Gasto mínimo para optimización (default: 3)")
    print("  optimize_test_conversions  Conversiones mínimas (default: 1)")
    print("  optimize_block_clicks   Clicks para bloquear subID (default: 60)")
    print("  optimize_block_cost     Costo para bloquear fuente (default: 3)")


# ------ Listar stores de Galeonica --------------------------------------------------------------------------------------------

def cmd_listar_stores(search: str = ""):
    if not GALEONICA_API_SECRET:
        print("Para usar la API de Galeonica, configurá: GALEONICA_API_SECRET=tu_secreto")
        print("Podés ver el secreto en: https://partner.galeonica.com/developer/api-credentials")
        print()
        print("Alternativamente, visitá: https://partner.galeonica.com/stores")
        return

    stores = listar_stores(search=search)
    if not stores:
        print("No se encontraron stores.")
        return

    print(f"\n{'Store':<40} {'Slug':<30} {'Comisión':<12} {'País'}")
    print("--" * 100)
    for s in stores:
        name = s.get("name", "")[:38]
        slug = (s.get("slug") or s.get("id") or "")[:28]
        commission = s.get("commission", s.get("max_commission", ""))
        country = s.get("country", s.get("countryCode", ""))
        print(f"  {name:<40} {slug:<30} {commission!s:<12} {country}")


# ------ Utilidades ----------------------------------------------------------------------------------------------------------------------------

def _bool(val) -> bool:
    if isinstance(val, bool):
        return val
    return str(val).lower() in ("true", "1", "yes", "si", "sí")


# ------ CLI --------------------------------------------------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Crea campañas Voolty en Binom + AdKernel desde Galeonica"
    )
    parser.add_argument("--csv",           metavar="ARCHIVO.csv", help="CSV con los brands a crear")
    parser.add_argument("--set-geo",       action="store_true",   help="Setea geo US en AdKernel via browser (requiere Playwright)")
    parser.add_argument("--max-ok",        type=int, default=0,   help="Parar tras N creaciones exitosas (0 = sin límite)")
    parser.add_argument("--ejemplo",       action="store_true",   help="Genera un CSV de ejemplo")
    parser.add_argument("--listar-stores", action="store_true",   help="Lista stores de Galeonica")
    parser.add_argument("--search",        default="",            help="Filtro de búsqueda para --listar-stores")
    args = parser.parse_args()

    if args.ejemplo:
        write_ejemplo_csv()

    elif args.listar_stores:
        cmd_listar_stores(search=args.search)

    elif args.csv:
        if not os.path.exists(args.csv):
            print(f"Archivo no encontrado: {args.csv}")
            sys.exit(1)
        run_csv(args.csv, set_geo=args.set_geo, max_ok=args.max_ok)

    else:
        parser.print_help()
        print()
        print("Ejemplos:")
        print("  # Configurar credenciales (solo una vez):")
        print("  set ADKERNEL_TOKEN=tu_token_estatico")
        print("  set GALEONICA_API_SECRET=tu_secreto")
        print()
        print("  # El BINOM_API_KEY ya está hardcodeado en el script")
        print()
        print("  # Ver stores disponibles en Galeonica:")
        print("  python voolty_campaign_creator.py --listar-stores")
        print("  python voolty_campaign_creator.py --listar-stores --search bombas")
        print()
        print("  # Generar CSV de ejemplo:")
        print("  python voolty_campaign_creator.py --ejemplo")
        print()
        print("  # Crear campañas desde CSV:")
        print("  python voolty_campaign_creator.py --csv brands_ejemplo.csv")
