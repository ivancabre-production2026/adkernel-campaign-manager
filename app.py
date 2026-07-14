"""
app.py — Voolty Campaign Manager
"""

import json
import os
import sys
import time
import io
import contextlib
from pathlib import Path
import pandas as pd
import requests
import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Campaign Manager",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
# Colores, fuentes, radios y bordes viven en .streamlit/config.toml (theming nativo).
# Lo que sigue es solo lo que el theming nativo no cubre: el look de navegación
# tipo "sidebar app" del radio y la consola de logs estilo terminal.
st.markdown("""
<style>
  [data-testid="stSidebar"] .stRadio [role="radiogroup"] label {
    padding: 9px 14px;
    border-radius: 8px;
    transition: background 0.12s;
    margin-bottom: 2px;
  }
  [data-testid="stSidebar"] .stRadio [role="radiogroup"] label:hover { background: #1f2937; }
  [data-testid="stSidebar"] .stRadio [role="radiogroup"] label[data-checked="true"] { background: #1f2937; }

  .log-box {
    background: #0d1117;
    color: #7ee787;
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 0.8rem;
    padding: 16px 20px;
    border-radius: 10px;
    max-height: 340px;
    overflow-y: auto;
    line-height: 1.7;
    border: 1px solid #21262d;
  }

  #MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ── Constants ──────────────────────────────────────────────────────────────────
AK_BASE        = "https://login.ilatin-media.com"
AK_LOGIN       = os.environ.get("ADKERNEL_LOGIN",    "ilatinmedia")
AK_PASS        = os.environ.get("ADKERNEL_PASSWORD", "5*&RcQXlKGG$Dz7j")
AK_VERSION     = 6
AK_CAMPAIGN_ID = int(os.environ.get("ADKERNEL_CAMPAIGN_ID", "2513696"))
BINOM_KEY      = os.environ.get("BINOM_KEY", "1f109c4331f132305a195943dff50e007f36333f95b3189c7def94d0e0c6bc8b")
CREATED_FILE   = ROOT / "created_brands.json"
BINOM_DATA_FILE = ROOT / "binom_data.json"


def load_binom_manual() -> dict:
    """Carga datos Binom ingresados manualmente. Clave = nombre corto de offer."""
    if BINOM_DATA_FILE.exists():
        try:
            return json.loads(BINOM_DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_binom_manual(data: dict):
    BINOM_DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Helpers ────────────────────────────────────────────────────────────────────
def ak_get_token() -> str:
    if "ak_token" not in st.session_state:
        r = requests.get(f"{AK_BASE}/admin/auth",
            params={"login": AK_LOGIN, "password": AK_PASS, "version": AK_VERSION}, timeout=15)
        st.session_state["ak_token"] = r.text.strip().split("&")[0]
    return st.session_state["ak_token"]


@st.cache_data(ttl=120, show_spinner=False)
def ak_get_offers(_tok: str) -> list[dict]:
    r = requests.get(f"{AK_BASE}/admin/api/OfferNew/",
        params={"version": AK_VERSION, "token": _tok,
                "ad_campaign_id": AK_CAMPAIGN_ID, "limit": 200}, timeout=30)
    rows = r.json().get("response", {}).get("rows", {})
    return list(rows.values())


def load_created() -> dict:
    if CREATED_FILE.exists():
        return json.loads(CREATED_FILE.read_text(encoding="utf-8"))
    return {}


# ── Semaforo de performance (colores tipo Binom) ────────────────────────────────
ROI_TIER_COLORS = {
    "excellent": "#bbf7d0",
    "good":      "#dcfce7",
    "regular":   "#fef9c3",
    "bad":       "#fecaca",
    "paused":    "#f1f5f9",
}


def roi_tier(roi: float, active: bool = True, spent: bool = False, converted: bool = False) -> str:
    if not active:
        return "paused"
    if spent and not converted:
        return "bad"
    if roi > 100:
        return "excellent"
    if roi > 0:
        return "good"
    if roi > -50:
        return "regular"
    return "bad"


def style_by_tier(tiers: list):
    def _style(row):
        color = ROI_TIER_COLORS.get(tiers[row.name], "")
        return [f"background-color: {color}"] * len(row) if color else [""] * len(row)
    return _style


# ── Sidebar ────────────────────────────────────────────────────────────────────
PAGES = {
    "Dashboard":          ":material/dashboard:",
    "Crear campaign":     ":material/add_circle:",
    "Monitoreo offers":   ":material/monitoring:",
    "Asistente IA":       ":material/smart_toy:",
}

with st.sidebar:
    st.markdown("""
    <div style="padding: 8px 0 20px 0;">
      <div style="font-size: 1rem; font-weight: 700; color: #fff; letter-spacing: -0.01em;">
        ⚡ Campaign Manager
      </div>
      <div style="font-size: 0.75rem; color: #6b7280; margin-top: 2px;">
        Voolty · AdKernel · Binom
      </div>
    </div>
    """, unsafe_allow_html=True)

    page = st.radio(
        "Navegación",
        list(PAGES.keys()),
        format_func=lambda p: f"{PAGES[p]}  {p}",
        label_visibility="collapsed",
    )

    st.caption("v1.0 · Railway")


# ── AdKernel Offer Stats ───────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def ak_get_offer_stats(_tok: str, date_param: str) -> dict:
    """Devuelve {offer_id: row} desde AdvertiserReports/offer. Incluye cost, revenue, profit, ROI, conversions."""
    try:
        r = requests.get(f"{AK_BASE}/admin/api/AdvertiserReports/offer",
            params={"version": AK_VERSION, "token": _tok,
                    "ad_campaign_id": AK_CAMPAIGN_ID,
                    "date": date_param, "limit": 200},
            timeout=30)
        data = r.json()
        if data.get("status") != "OK":
            return {}
        rows = data["response"]["list"]["rows"]
        total = data["response"].get("total", {})
        result = {}
        for row in rows.values():
            oid = row.get("offer_id")
            if oid:
                result[int(oid)] = row
        result["__total__"] = total
        return result
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def ak_get_keyword_stats(_tok: str, date_param: str) -> dict:
    """Devuelve {offer_id: [rows]} desde AdvertiserReports/offer,keyword2 (desglose por keyword/dominio dentro de cada offer)."""
    try:
        r = requests.get(f"{AK_BASE}/admin/api/AdvertiserReports/offer,keyword2",
            params={"version": AK_VERSION, "token": _tok,
                    "ad_campaign_id": AK_CAMPAIGN_ID,
                    "date": date_param, "limit": 2000},
            timeout=30)
        data = r.json()
        if data.get("status") != "OK":
            return {}
        rows = data["response"]["list"]["rows"]
        result = {}
        for row in rows.values():
            oid = row.get("offer_id")
            if oid:
                result.setdefault(int(oid), []).append(row)
        return result
    except Exception:
        return {}


@st.cache_data(ttl=60, show_spinner=False)
def ak_get_offer_keywords(_tok: str, offer_id: int) -> list[dict]:
    """Lee las keywords (kwd + match_type + bid_adjustment) configuradas para una offer."""
    r = requests.get(f"{AK_BASE}/admin/api/OfferNew/Keyword/{offer_id}",
        params={"version": AK_VERSION, "token": _tok}, timeout=30)
    data = r.json()
    if data.get("status") != "OK":
        return []
    rows = data.get("response", {}).get("rows", {}).get(str(offer_id), {})
    return list(rows.values())


def ak_update_keyword_bids(tok: str, offer_id: int, edits: list[dict]) -> dict:
    """Actualiza bid_adjustment (y/o enabled) de keywords puntuales. edits: [{kwd, match_type, bid_adjustment}, ...]."""
    r = requests.put(f"{AK_BASE}/admin/api/OfferNew/Keyword/{offer_id}",
        params={"version": AK_VERSION, "token": tok},
        json={"mode": "UPDATE", "edit": edits}, timeout=30)
    return r.json()


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "Dashboard":
    import datetime

    # ── Header ─────────────────────────────────────────────────────────────
    with st.container(horizontal=True, vertical_alignment="center"):
        st.title("Dashboard")
        with st.container(horizontal_alignment="right"):
            if st.button("Actualizar", icon=":material/refresh:"):
                st.cache_data.clear()
                st.rerun()

    period_map = {"Hoy": "today", "7 días": "7d", "30 días": "30d"}
    period_label_selected = st.segmented_control(
        "Período", list(period_map.keys()), default="30 días", label_visibility="collapsed"
    ) or "30 días"
    period = period_map[period_label_selected]

    today = datetime.date.today()
    if period == "today":
        date_param   = f"{today}_{today}"
        period_label = "Hoy"
    elif period == "7d":
        date_param   = f"{today - datetime.timedelta(days=6)}_{today}"
        period_label = "Últimos 7 días"
    else:
        date_param   = f"{today - datetime.timedelta(days=29)}_{today}"
        period_label = "Últimos 30 días"

    SPEND_ALERT = 20.0

    # ── Load data ───────────────────────────────────────────────────────────
    with st.spinner(""):
        try:
            tok    = ak_get_token()
            offers = ak_get_offers(tok)
        except Exception as e:
            st.error(f"No se pudo conectar a AdKernel: {e}")
            st.stop()

    offer_stats = ak_get_offer_stats(tok, date_param)
    total_row   = offer_stats.pop("__total__", {})

    active   = [o for o in offers if o.get("is_active")]
    inactive = [o for o in offers if not o.get("is_active")]

    # ── KPI totals from AK ───────────────────────────────────────────────────
    total_clicks  = int(total_row.get("adv_clicks", 0))
    total_cost    = float(total_row.get("adv_cost", 0))
    total_revenue = float(total_row.get("adv_value", 0))
    total_profit  = float(total_row.get("adv_profit", 0))
    total_roi     = float(total_row.get("adv_roi", 0))
    total_convs   = int(total_row.get("adv_conversions", 0))
    total_cpa     = float(total_row.get("adv_cpa") or 0)
    total_cpc     = float(total_row.get("adv_cpc") or 0)

    # ── Subtitle ─────────────────────────────────────────────────────────────
    st.caption(f"{period_label} · {len(active)} offers activas · {len(offers)} total")

    # ── KPI cards ────────────────────────────────────────────────────────────
    epc = (total_revenue / total_clicks) if total_clicks else 0

    with st.container(horizontal=True):
        st.metric("Revenue", f"${total_revenue:,.2f}",
                   f"{total_convs} conversiones", delta_color="off", border=True)
        st.metric("Gasto", f"${total_cost:,.2f}",
                   f"CPC ${total_cpc:.3f}", delta_color="off", border=True)
        st.metric("Profit", f"${total_profit:+,.2f}",
                   f"{total_roi:+.1f}% ROI", border=True)
        st.metric("ROI", f"{total_roi:+.1f}%",
                   f"${total_profit:+,.2f} profit", border=True)
        st.metric("Conversiones", str(total_convs),
                   f"CPA ${total_cpa:.2f}" if total_cpa else None, delta_color="off", border=True)
        st.metric("Clicks", f"{total_clicks:,}",
                   f"EPC ${epc:.3f}" if total_clicks else None, delta_color="off", border=True)

    # ── Tabla de offers ──────────────────────────────────────────────────────
    st.caption("Detalle por offer")

    # Build offer_id → AK offer object map
    offer_id_map = {int(o["id"]): o for o in offers}

    rows = []
    tiers = []
    row_oids = []
    offer_options = {}
    for oid_key, s in sorted(offer_stats.items(), key=lambda x: float(x[1].get("adv_cost", 0)), reverse=True):
        oid    = int(oid_key)
        cost   = float(s.get("adv_cost", 0))
        rev    = float(s.get("adv_value", 0))
        profit = float(s.get("adv_profit", 0))
        roi    = float(s.get("adv_roi") or -100 if s.get("adv_conversions", 0) > 0 or cost > 0 else 0)
        convs  = int(s.get("adv_conversions", 0))
        clicks = int(s.get("adv_clicks", 0))
        cpc    = float(s.get("adv_cpc") or 0)
        cpa    = float(s.get("adv_cpa") or 0)
        epc    = float(s.get("adv_epc") or 0)
        name   = s.get("offer", "").replace("US - ", "").replace(" - Voolty", "")

        # Get bid from offer config
        ak_offer = offer_id_map.get(oid, {})
        bid   = float(ak_offer.get("bid", 0))
        max_b = float(ak_offer.get("max_bid") or 0)
        is_active = ak_offer.get("is_active", True)

        rows.append({
            "Offer":    name,
            "Clicks":   clicks,
            "Conv.":    convs,
            "Revenue":  rev,
            "Gasto":    cost,
            "Profit":   profit,
            "ROI":      roi / 100,
            "CPC":      cpc,
            "CPA":      cpa or None,
            "EPC":      epc or None,
            "Bid":      bid,
            "Max Bid":  max_b or None,
            "Acción":   [":material/pause_circle: Pausar"] if is_active else [":material/play_circle: Activar"],
        })
        tiers.append(roi_tier(roi, active=is_active, spent=cost > 5, converted=convs > 0))
        row_oids.append(oid)
        offer_options[f"{name}  (ID {oid})"] = oid

    def _handle_offer_action():
        click = st.session_state.get("offer_row_action")
        if not click:
            return
        target_oid = row_oids[click["row"]]
        new_state = "Activar" in click["label"]
        try:
            r = requests.put(
                f"{AK_BASE}/admin/api/OfferNew/{target_oid}",
                params={"version": AK_VERSION, "token": tok},
                json={"is_active": new_state}, timeout=20
            )
            if r.json().get("status") == "OK":
                st.cache_data.clear()
                st.toast(f"Offer {target_oid} {'activada' if new_state else 'pausada'}.", icon=":material/check_circle:")
            else:
                st.toast(f"Error: {r.text[:200]}", icon=":material/error:")
        except Exception as e:
            st.toast(f"Error: {e}", icon=":material/error:")

    if rows:
        df = pd.DataFrame(rows)
        styled = df.style.apply(style_by_tier(tiers), axis=1)
        st.dataframe(
            styled,
            width="stretch", hide_index=True,
            column_config={
                "Revenue": st.column_config.NumberColumn(format="$%.2f"),
                "Gasto":   st.column_config.NumberColumn(format="$%.2f"),
                "Profit":  st.column_config.NumberColumn(format="$%.2f"),
                "ROI":     st.column_config.NumberColumn(format="percent"),
                "CPC":     st.column_config.NumberColumn(format="$%.3f"),
                "CPA":     st.column_config.NumberColumn(format="$%.2f"),
                "EPC":     st.column_config.NumberColumn(format="$%.3f"),
                "Bid":     st.column_config.NumberColumn(format="$%.2f"),
                "Max Bid": st.column_config.NumberColumn(format="$%.2f"),
                "Acción":  st.column_config.ButtonColumn(
                    "Acción", on_click=_handle_offer_action, key="offer_row_action", width="small"
                ),
            },
        )
    else:
        st.info("Sin datos para el período seleccionado.", icon=":material/info:")

    # ── Detalle por keyword + acciones rápidas ────────────────────────────────
    st.caption("Detalle por keyword")

    if offer_options:
        sel_label = st.selectbox("Offer", list(offer_options.keys()), label_visibility="collapsed")
        sel_oid   = offer_options[sel_label]
        sel_offer = offer_id_map.get(sel_oid, {})

        with st.container(horizontal=True, vertical_alignment="bottom"):
            kw_bid = st.number_input("Default CPC ($)", min_value=0.01, max_value=5.0,
                value=float(sel_offer.get("bid", 0.10)), step=0.01, format="%.2f", key="dash_bid")
            kw_state = st.selectbox("Estado", ["Activa", "Inactiva"],
                index=0 if sel_offer.get("is_active") else 1, key="dash_state")
            if st.button("Guardar", icon=":material/save:", type="primary", key="dash_save"):
                try:
                    r = requests.put(
                        f"{AK_BASE}/admin/api/OfferNew/{sel_oid}",
                        params={"version": AK_VERSION, "token": tok},
                        json={"bid": kw_bid, "is_active": kw_state == "Activa"},
                        timeout=20
                    )
                    if r.json().get("status") == "OK":
                        st.success(f"Offer {sel_oid} actualizada.", icon=":material/check_circle:")
                        st.cache_data.clear()
                        time.sleep(0.8)
                        st.rerun()
                    else:
                        st.error(r.text, icon=":material/error:")
                except Exception as e:
                    st.error(f"Error: {e}", icon=":material/error:")

        keyword_stats = ak_get_keyword_stats(tok, date_param)
        kw_perf = {k.get("keyword2", ""): k for k in keyword_stats.get(sel_oid, [])}
        kw_list = ak_get_offer_keywords(tok, sel_oid)

        kw_list_sorted = sorted(
            kw_list,
            key=lambda k: float(kw_perf.get(k.get("kwd", ""), {}).get("adv_cost", 0)),
            reverse=True,
        )

        kw_rows = []
        kw_keys = []
        for kw in kw_list_sorted:
            perf    = kw_perf.get(kw.get("kwd", ""), {})
            k_cost  = float(perf.get("adv_cost", 0))
            k_convs = int(perf.get("adv_conversions", 0))
            k_roi   = float(perf.get("adv_roi") if perf.get("adv_roi") is not None else (0 if k_cost == 0 else -100))
            kw_rows.append({
                "Keyword":      kw.get("kwd", "—"),
                "Match":        kw.get("match_type", "").upper(),
                "Activa":       bool(kw.get("enabled", True)),
                "Bid Adj. (%)": round(float(kw.get("bid_adjustment", 1.0)) * 100, 1),
                "Clicks":       int(perf.get("adv_clicks", 0)),
                "Gasto":        k_cost,
                "Revenue":      float(perf.get("adv_value", 0)),
                "Profit":       float(perf.get("adv_profit", 0)),
                "ROI":          k_roi / 100,
            })
            kw_keys.append((kw.get("kwd", ""), kw.get("match_type", "")))

        if kw_rows:
            kw_df = pd.DataFrame(kw_rows)
            st.data_editor(
                kw_df, key="kw_editor", hide_index=True, width="stretch",
                disabled=["Keyword", "Match", "Clicks", "Gasto", "Revenue", "Profit", "ROI"],
                column_config={
                    "Bid Adj. (%)": st.column_config.NumberColumn(min_value=10, max_value=500, step=5, format="%.1f%%"),
                    "Gasto":        st.column_config.NumberColumn(format="$%.2f"),
                    "Revenue":      st.column_config.NumberColumn(format="$%.2f"),
                    "Profit":       st.column_config.NumberColumn(format="$%.2f"),
                    "ROI":          st.column_config.NumberColumn(format="percent"),
                },
            )
            edited_rows = st.session_state.get("kw_editor", {}).get("edited_rows", {})
            if edited_rows:
                if st.button(f"Guardar {len(edited_rows)} cambio(s) de keyword", icon=":material/save:", type="primary", key="kw_save"):
                    edits = []
                    for row_idx, changes in edited_rows.items():
                        kwd, match_type = kw_keys[int(row_idx)]
                        edit_body = {"kwd": kwd, "match_type": match_type}
                        if "Bid Adj. (%)" in changes:
                            edit_body["bid_adjustment"] = round(changes["Bid Adj. (%)"] / 100, 4)
                        if "Activa" in changes:
                            edit_body["enabled"] = changes["Activa"]
                        edits.append(edit_body)
                    try:
                        result = ak_update_keyword_bids(tok, sel_oid, edits)
                        if result.get("status") == "OK":
                            st.success(f"{len(edits)} keyword(s) actualizadas.", icon=":material/check_circle:")
                            st.cache_data.clear()
                            time.sleep(0.8)
                            st.rerun()
                        else:
                            st.error(str(result)[:300], icon=":material/error:")
                    except Exception as e:
                        st.error(f"Error: {e}", icon=":material/error:")
        else:
            st.caption("Esta offer no tiene keywords configuradas.")
    else:
        st.caption("No hay offers con datos en este período.")

    # ── Alertas ──────────────────────────────────────────────────────────────
    alerts = []
    for oid_key, s in offer_stats.items():
        cost  = float(s.get("adv_cost", 0))
        convs = int(s.get("adv_conversions", 0))
        roi   = float(s.get("adv_roi") or -100)
        name  = s.get("offer", "").replace("US - ", "").replace(" - Voolty", "")
        bid_avg = float(s.get("adv_bids_avg") or 0)
        if cost >= SPEND_ALERT and convs == 0:
            alerts.append(("danger", f"**{name}** — \\${cost:.0f} gastados, 0 conversiones. Pausar o bajar bid."))
        elif roi < -70 and cost > 10:
            alerts.append(("warning", f"**{name}** — ROI {roi:+.0f}% con \\${cost:.0f} invertidos. Revisar bid (actual \\${bid_avg:.2f})."))
        elif roi > 100 and cost > 15:
            alerts.append(("success", f"**{name}** — ROI {roi:+.0f}%! Podés subir el bid para escalar."))

    if alerts:
        callout = {"danger": st.error, "warning": st.warning, "success": st.success}
        icon = {"danger": ":material/error:", "warning": ":material/priority_high:", "success": ":material/trending_up:"}
        with st.expander(f"Alertas ({len(alerts)})", icon=":material/notifications:"):
            for kind, msg in alerts:
                callout[kind](msg, icon=icon[kind])

    # ── Offers sin activar ───────────────────────────────────────────────────
    if inactive:
        with st.expander(f"Offers inactivas ({len(inactive)})", icon=":material/visibility_off:"):
            irows = [{
                "Offer":  o["name"].replace("US - ","").replace(" - Voolty",""),
                "ID":     o["id"],
                "Bid":    f"${float(o.get('bid',0)):.2f}",
                "Max":    f"${float(o.get('max_bid',0)):.2f}" if o.get("max_bid") else "—",
            } for o in inactive]
            st.dataframe(irows, width="stretch", hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# CREAR CAMPAIGN
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Crear campaign":
    import subprocess, sys as _sys

    st.title("Crear campaign")
    st.caption("Creación automática desde Voolty + SK, o manual para un store específico.")

    tab_auto, tab_manual = st.tabs([":material/bolt: Automático", ":material/edit: Manual"])

    # ─── TAB AUTOMÁTICO ────────────────────────────────────────────────────────
    with tab_auto:
        with st.container(border=True):
            st.markdown("**¿Cómo funciona?**")
            st.markdown(
                "1. Descarga el catálogo completo de Voolty/Galeonica\n"
                "2. Consulta SourceKnowledge y filtra por tráfico real disponible\n"
                "3. Calcula el bid óptimo por dominio (fórmula SK bidCpc)\n"
                "4. Crea Binom offer + campaign + AdKernel offer con keywords y geo US"
            )

        st.space("small")

        ca1, ca2, ca3 = st.columns([1, 1, 2], vertical_alignment="bottom")
        with ca1:
            auto_n = st.number_input("Offers a crear", min_value=1, max_value=20, value=5,
                                     help="El sistema selecciona los mejores N stores disponibles")
        with ca2:
            auto_dry = st.toggle("Dry run (sin crear)", value=True,
                                 help="Muestra los stores seleccionados sin crear nada")

        if auto_dry:
            btn_label = f"Previsualizar {auto_n} offers"
            btn_icon  = ":material/search:"
            btn_help  = "Muestra qué stores seleccionaría el sistema sin tocar AdKernel/Binom"
        else:
            btn_label = f"Crear {auto_n} offers automáticamente"
            btn_icon  = ":material/bolt:"
            btn_help  = "Crea las offers reales en Binom y AdKernel"

        run_auto = st.button(btn_label, icon=btn_icon, type="primary", help=btn_help)

        if run_auto:
            log_placeholder = st.empty()
            log_lines = []

            def log_auto(msg):
                msg = msg.strip()
                if not msg:
                    return
                log_lines.append(msg)
                log_placeholder.markdown(
                    '<div class="log-box">' + "<br>".join(log_lines[-40:]) + '</div>',
                    unsafe_allow_html=True
                )

            cmd = [_sys.executable, str(ROOT / "daily_batch.py"), "--max-ok", str(auto_n)]
            if auto_dry:
                cmd.append("--dry-run")

            log_auto(f"▶  {'[DRY RUN] ' if auto_dry else ''}Iniciando batch de {auto_n} offers...")
            log_auto(f"   Comando: {' '.join(cmd[2:])}")

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", errors="replace",
                    cwd=str(ROOT)
                )
                for line in proc.stdout:
                    log_auto(line)
                stderr_out = proc.stderr.read()
                proc.wait()

                if stderr_out.strip():
                    log_auto("── STDERR ──")
                    for line in stderr_out.splitlines():
                        log_auto(line)

                if proc.returncode == 0:
                    if auto_dry:
                        st.info("Dry run completado. Desactivá el toggle para crear las campañas reales.", icon=":material/info:")
                    else:
                        st.success("Batch completado. Revisá el log arriba para ver el detalle.", icon=":material/check_circle:")
                        st.cache_data.clear()
                else:
                    st.error(f"El script terminó con código {proc.returncode}.", icon=":material/error:")
            except Exception as e:
                import traceback
                st.error(f"Error al ejecutar batch: {e}")
                st.code(traceback.format_exc())

    # ─── TAB MANUAL ───────────────────────────────────────────────────────────
    with tab_manual:
        with st.form("crear_campaign"):
            st.caption("Datos del store")
            c1, c2, c3 = st.columns(3)
            with c1:
                brand_name = st.text_input("Brand name *", placeholder="Bombas")
            with c2:
                store_slug = st.text_input("Slug *", placeholder="bombas")
            with c3:
                ad_display = st.text_input("Dominio", placeholder="bombas.com")

            st.caption("Puja")
            c4, c5, c6 = st.columns(3)
            with c4:
                sk_bid_cpc = st.number_input("bidCpc SK", min_value=0.0, max_value=10.0,
                                              value=0.0, step=0.01, format="%.4f",
                                              help="Dejá en 0 para usar fallback 200%")
            with c5:
                bid = st.number_input("Default CPC ($)", min_value=0.01, max_value=5.0,
                                       value=0.10, step=0.01, format="%.2f")
            with c6:
                country = st.selectbox("País", ["US", "CA", "UK", "AU"])

            st.caption("Anuncio")
            c7, c8, c9 = st.columns(3)
            with c7:
                ad_title = st.text_input("Título", placeholder="Bombas — Official Site")
            with c8:
                ad_desc  = st.text_input("Descripción", placeholder="Premium socks. Free shipping.")
            with c9:
                ad_cta   = st.text_input("CTA", value="Shop Now")

            is_active = st.checkbox("Activar inmediatamente", value=False,
                                     help="Por defecto se crea inactiva para revisión manual.")

            submitted = st.form_submit_button("Crear campaign", icon=":material/arrow_forward:", type="primary", width="stretch")

        if submitted:
            if not brand_name or not store_slug:
                st.error("Brand name y slug son obligatorios.", icon=":material/error:")
            else:
                cfg = {
                    "brand_name":  brand_name.strip(),
                    "store_slug":  store_slug.strip(),
                    "country":     country,
                    "bid":         bid,
                    "sk_bid_cpc":  sk_bid_cpc if sk_bid_cpc > 0 else None,
                    "ad_title":    ad_title or f"{brand_name} — Official Site",
                    "ad_desc":     ad_desc  or f"Shop {brand_name} online.",
                    "ad_display":  ad_display or f"{store_slug}.com",
                    "ad_cta":      ad_cta or "Shop Now",
                    "is_active":   "true" if is_active else "false",
                }

                log_placeholder = st.empty()
                log_lines = []

                def log(msg):
                    log_lines.append(msg)
                    log_placeholder.markdown(
                        f'<div class="log-box">' + "<br>".join(log_lines[-30:]) + '</div>',
                        unsafe_allow_html=True
                    )

                log(f"▶  Iniciando: {brand_name} / {store_slug}")

                try:
                    from voolty_campaign_creator import ak_get_token as get_tok, crear_brand
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        tok    = get_tok()
                        result = crear_brand(cfg, tok)
                    for line in buf.getvalue().splitlines():
                        log(line)

                    status = result.get("status", "OK")

                    if "SKIP" in str(status) or "ERROR" in str(status):
                        st.warning(f"**Resultado:** {status}", icon=":material/warning:")
                    else:
                        st.success("Campaign creada correctamente.", icon=":material/check_circle:")
                        with st.container(horizontal=True):
                            st.metric("Binom offer",    result.get("binom_offer", "—"), border=True)
                            st.metric("Binom campaign", result.get("binom_campaign", "—"), border=True)
                            st.metric("AdKernel offer",  result.get("ak_offer", "—"), border=True)
                        if result.get("postback_url"):
                            st.caption("Postback S2S")
                            st.code(result["postback_url"])
                except Exception as e:
                    import traceback
                    st.error(f"Error inesperado: {e}", icon=":material/error:")
                    st.code(traceback.format_exc())


# ══════════════════════════════════════════════════════════════════════════════
# MONITOREO OFFERS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Monitoreo offers":
    st.title("Monitoreo de offers")
    st.caption("Estado y configuración de bids en tiempo real.")

    c_ref, c_filt, _ = st.columns([1, 1, 3])
    with c_ref:
        if st.button("Actualizar", icon=":material/refresh:"):
            st.cache_data.clear()
            st.rerun()
    with c_filt:
        solo_activas = st.toggle("Solo activas", value=False)

    with st.spinner(""):
        try:
            offers = ak_get_offers(ak_get_token())
        except Exception as e:
            st.error(f"Error AdKernel: {e}", icon=":material/error:")
            st.stop()

    if solo_activas:
        offers = [o for o in offers if o.get("is_active")]

    st.caption("Offers")

    rows = [{
        "Nombre":   o["name"].replace("US - ", "").replace(" - Voolty", ""),
        "ID":       o["id"],
        "Estado":   "Activa" if o.get("is_active") else "Inactiva",
        "CPC":      f"${o['bid']:.2f}",
        "Max Bid":  f"${o['max_bid']:.2f}" if o.get("max_bid") else "—",
        "Optimiz.": "Sí" if o.get("optimize_bids_new") else "No",
    } for o in offers]

    st.dataframe(rows, width="stretch", hide_index=True)

    st.caption("Editar bid")

    offer_map = {f"{o['name'].replace('US - ','').replace(' - Voolty','')}  (ID {o['id']})": o for o in offers}
    selected  = st.selectbox("Offer", list(offer_map.keys()), label_visibility="collapsed")
    offer     = offer_map[selected]

    c1, c2, c3, c4 = st.columns(4, vertical_alignment="bottom")
    with c1:
        new_cpc = st.number_input("Default CPC ($)",
            min_value=0.01, max_value=5.0,
            value=float(offer.get("bid", 0.10)),
            step=0.01, format="%.2f")
    with c2:
        new_max = st.number_input("Max Bid ($)",
            min_value=0.0, max_value=5.0,
            value=float(offer.get("max_bid") or 0.0),
            step=0.01, format="%.2f",
            help="Techo duro para el optimizador. 0 = sin techo.")
    with c3:
        new_state = st.selectbox("Estado", ["Activa", "Inactiva"],
            index=0 if offer.get("is_active") else 1)
    with c4:
        if st.button("Guardar", icon=":material/save:", type="primary", width="stretch"):
            try:
                tok  = ak_get_token()
                body = {
                    "bid":       new_cpc,
                    "is_active": new_state == "Activa",
                    "max_bid":   new_max if new_max > 0 else None,
                }
                r = requests.put(
                    f"{AK_BASE}/admin/api/OfferNew/{offer['id']}",
                    params={"version": AK_VERSION, "token": tok},
                    json=body, timeout=20
                )
                if r.json().get("status") == "OK":
                    st.success(f"Offer {offer['id']} actualizada.", icon=":material/check_circle:")
                    st.cache_data.clear()
                    time.sleep(0.8)
                    st.rerun()
                else:
                    st.error(r.text, icon=":material/error:")
            except Exception as e:
                st.error(f"Error: {e}", icon=":material/error:")


# ══════════════════════════════════════════════════════════════════════════════
# ASISTENTE IA
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Asistente IA":
    import os, subprocess, json as _json, sys as _sys

    st.title("Asistente IA")
    st.caption("Pedile lo que necesitás en lenguaje natural.")

    # ── API key: env var o input manual ───────────────────────────────────
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        api_key = st.session_state.get("anthropic_api_key", "")
    if not api_key:
        entered = st.text_input("API Key de Anthropic", type="password",
                                placeholder="sk-ant-api03-...",
                                help="Obtenela en console.anthropic.com → API Keys")
        if entered:
            st.session_state["anthropic_api_key"] = entered
            st.rerun()
        st.stop()

    try:
        import anthropic as _anthropic
    except ImportError:
        st.error("Instalá el SDK: `pip install anthropic`", icon=":material/error:")
        st.stop()

    # ── Herramientas disponibles para el asistente ─────────────────────────
    TOOLS = [
        {
            "name": "crear_offers_automatico",
            "description": "Crea N offers automáticamente: baja el catálogo de Voolty, filtra por tráfico en SourceKnowledge, calcula el bid óptimo y crea todo en Binom y AdKernel.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "cantidad": {"type": "integer", "description": "Cuántas offers crear (1-20)", "default": 5},
                    "dry_run":  {"type": "boolean", "description": "Si true, solo muestra los stores sin crear nada", "default": False},
                },
                "required": [],
            },
        },
        {
            "name": "listar_offers",
            "description": "Lista las offers actuales en AdKernel con su estado, CPC y max bid.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "modificar_bid",
            "description": "Modifica el CPC y/o max_bid de una offer en AdKernel por su ID o nombre.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "offer_id":  {"type": "integer", "description": "ID de la offer en AdKernel"},
                    "nombre":    {"type": "string",  "description": "Nombre parcial de la offer (si no se conoce el ID)"},
                    "nuevo_cpc": {"type": "number",  "description": "Nuevo CPC en dólares"},
                    "nuevo_max": {"type": "number",  "description": "Nuevo max_bid en dólares (0 = sin techo)"},
                    "activar":   {"type": "boolean", "description": "True para activar, False para desactivar"},
                },
                "required": [],
            },
        },
        {
            "name": "ver_historial",
            "description": "Muestra cuántas y qué brands ya fueron creadas en el historial local.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
    ]

    # ── Ejecutores de herramientas ─────────────────────────────────────────
    def _run_tool(name: str, inp: dict) -> str:
        if name == "crear_offers_automatico":
            cantidad = inp.get("cantidad", 5)
            dry_run  = inp.get("dry_run", False)
            cmd = [_sys.executable, str(ROOT / "daily_batch.py"), "--max-ok", str(cantidad)]
            if dry_run:
                cmd.append("--dry-run")
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT))
            return (proc.stdout + proc.stderr)[-3000:]  # últimos 3000 chars del log

        if name == "listar_offers":
            try:
                tok = ak_get_token()
                offers = ak_get_offers(tok)
                rows = [{"nombre": o["name"].replace("US - ","").replace(" - Voolty",""),
                         "id": o["id"], "cpc": o["bid"],
                         "activa": o.get("is_active", False)} for o in offers]
                return _json.dumps(rows, ensure_ascii=False)
            except Exception as e:
                return f"Error: {e}"

        if name == "modificar_bid":
            try:
                tok = ak_get_token()
                offers = ak_get_offers(tok)
                target = None
                if inp.get("offer_id"):
                    target = next((o for o in offers if o["id"] == inp["offer_id"]), None)
                elif inp.get("nombre"):
                    q = inp["nombre"].lower()
                    target = next((o for o in offers if q in o["name"].lower()), None)
                if not target:
                    return "No encontré la offer. Indicá el ID o un nombre más preciso."
                body = {}
                if inp.get("nuevo_cpc") is not None:
                    body["bid"] = inp["nuevo_cpc"]
                if inp.get("nuevo_max") is not None:
                    body["max_bid"] = inp["nuevo_max"] if inp["nuevo_max"] > 0 else None
                if inp.get("activar") is not None:
                    body["is_active"] = inp["activar"]
                r = requests.put(
                    f"{AK_BASE}/admin/api/OfferNew/{target['id']}",
                    params={"version": AK_VERSION, "token": tok},
                    json=body, timeout=20
                )
                if r.json().get("status") == "OK":
                    st.cache_data.clear()
                    return f"OK — Offer '{target['name']}' (ID {target['id']}) actualizada: {body}"
                return f"Error API: {r.text[:300]}"
            except Exception as e:
                return f"Error: {e}"

        if name == "ver_historial":
            data = load_created()
            slugs = data.get("slugs", [])
            return f"Total en historial: {len(slugs)}\nÚltimos 20: {', '.join(slugs[-20:])}"

        return f"Herramienta '{name}' no implementada."

    # ── Estado del chat ────────────────────────────────────────────────────
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    # Mostrar historial
    for msg in st.session_state["chat_messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input del usuario
    if prompt := st.chat_input("Ej: creame 3 offers, bajá el bid de Bombas a $0.12, mostrá las activas..."):
        st.session_state["chat_messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            status_ph = st.empty()
            reply_ph  = st.empty()

            client = _anthropic.Anthropic(api_key=api_key)
            messages = [{"role": m["role"], "content": m["content"]}
                        for m in st.session_state["chat_messages"]]

            # Agentic loop: Claude puede llamar múltiples herramientas en secuencia
            full_reply = ""
            while True:
                status_ph.markdown("*Pensando…*")
                resp = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1024,
                    system=(
                        "Sos el asistente del Campaign Manager de Iván. "
                        "Gestionás campañas de afiliados en AdKernel/Binom/Voolty. "
                        "Respondé siempre en español, de forma concisa. "
                        "Cuando ejecutés herramientas, resumí el resultado sin repetir el log completo. "
                        "Si hay errores importantes en el log, mencionálos."
                    ),
                    tools=TOOLS,
                    messages=messages,
                )

                # Procesar respuesta
                tool_calls = [b for b in resp.content if b.type == "tool_use"]
                text_blocks = [b for b in resp.content if b.type == "text"]

                if text_blocks:
                    full_reply = text_blocks[0].text
                    reply_ph.markdown(full_reply)

                if not tool_calls or resp.stop_reason == "end_turn":
                    break

                # Ejecutar herramientas
                tool_results = []
                for tc in tool_calls:
                    status_ph.markdown(f"*Ejecutando `{tc.name}`…*")
                    output = _run_tool(tc.name, tc.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": output,
                    })

                # Agregar al hilo para la siguiente vuelta
                messages.append({"role": "assistant", "content": resp.content})
                messages.append({"role": "user",      "content": tool_results})

            status_ph.empty()
            if not full_reply:
                full_reply = "Listo."
                reply_ph.markdown(full_reply)

            st.session_state["chat_messages"].append({"role": "assistant", "content": full_reply})

    # Botón limpiar
    if st.session_state["chat_messages"]:
        if st.button("Limpiar conversación", icon=":material/delete_sweep:", type="secondary"):
            st.session_state["chat_messages"] = []
            st.rerun()
