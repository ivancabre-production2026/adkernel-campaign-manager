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
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

  /* App background */
  .stApp { background: #f9fafb; }
  .main .block-container {
    padding-top: 1.75rem;
    padding-bottom: 3rem;
    max-width: 1280px;
  }

  /* Sidebar */
  [data-testid="stSidebar"] {
    background: #111827;
    border-right: none;
  }
  [data-testid="stSidebar"] * { color: #d1d5db !important; }
  [data-testid="stSidebar"] .stRadio label {
    padding: 9px 14px;
    border-radius: 8px;
    transition: background 0.12s;
    display: block;
    font-size: 0.85rem;
    font-weight: 500;
  }
  [data-testid="stSidebar"] .stRadio label:hover { background: #1f2937; }
  [data-testid="stSidebar"] [data-testid="stRadio"] input:checked + label {
    background: #1f2937;
    color: #fff !important;
  }

  /* Page title */
  h1 {
    font-size: 1.6rem !important;
    font-weight: 700 !important;
    color: #111827 !important;
    letter-spacing: -0.03em !important;
    margin-bottom: 0 !important;
    line-height: 1.2 !important;
  }

  /* Section labels */
  .section-label {
    font-size: 0.7rem;
    font-weight: 700;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 12px;
    margin-top: 4px;
  }

  /* Log output */
  .log-box {
    background: #0d1117;
    color: #7ee787;
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 0.76rem;
    padding: 16px 20px;
    border-radius: 10px;
    max-height: 340px;
    overflow-y: auto;
    line-height: 1.7;
    border: 1px solid #21262d;
  }

  /* Dividers */
  hr { border: none; border-top: 1px solid #e5e7eb; margin: 1.25rem 0; }

  /* Buttons */
  .stButton > button {
    border-radius: 8px;
    font-weight: 500;
    font-size: 0.85rem;
    letter-spacing: 0.01em;
    transition: all 0.12s;
    border: 1px solid #e5e7eb;
    background: #fff;
    color: #374151;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
  }
  .stButton > button:hover { background: #f9fafb; border-color: #d1d5db; }
  .stButton > button[kind="primary"] {
    background: #111827;
    border-color: #111827;
    color: #fff;
    box-shadow: 0 1px 3px rgba(0,0,0,0.15);
  }
  .stButton > button[kind="primary"]:hover { background: #1f2937; border-color: #1f2937; }

  /* Inputs */
  .stTextInput > div > div > input,
  .stNumberInput > div > div > input {
    border-radius: 8px !important;
    border-color: #e5e7eb !important;
    font-size: 0.875rem !important;
    background: #fff !important;
  }
  .stSelectbox > div > div { border-radius: 8px !important; border-color: #e5e7eb !important; }

  /* Dataframe */
  [data-testid="stDataFrame"] {
    border: 1px solid #e5e7eb !important;
    border-radius: 12px !important;
    overflow: hidden;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
  }

  /* Form */
  [data-testid="stForm"] {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  }

  /* Expanders */
  [data-testid="stExpander"] {
    border: 1px solid #e5e7eb !important;
    border-radius: 10px !important;
    background: #fff !important;
  }

  /* Tabs */
  .stTabs [data-baseweb="tab-list"] {
    background: #f3f4f6;
    border-radius: 10px;
    padding: 4px;
    gap: 2px;
  }
  .stTabs [data-baseweb="tab"] {
    border-radius: 7px;
    font-size: 0.85rem;
    font-weight: 500;
    padding: 7px 16px;
  }
  .stTabs [aria-selected="true"] {
    background: #fff !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }

  /* Chat */
  [data-testid="stChatMessageContent"] { font-size: 0.9rem; }

  /* Hide branding */
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


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding: 8px 0 24px 0;">
      <div style="font-size: 1rem; font-weight: 700; color: #fff; letter-spacing: -0.01em;">
        Campaign Manager
      </div>
      <div style="font-size: 0.75rem; color: #6b7280; margin-top: 2px;">
        Voolty · AdKernel · Binom
      </div>
    </div>
    """, unsafe_allow_html=True)

    page = st.radio("Navegación", [
        "Dashboard",
        "Crear Campaign",
        "Monitoreo Offers",
        "Asistente IA",
    ], label_visibility="collapsed")


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


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "Dashboard":
    import datetime

    # ── Header ─────────────────────────────────────────────────────────────
    hcol1, hcol2 = st.columns([5, 1])
    with hcol1:
        st.markdown("<h1>Dashboard</h1>", unsafe_allow_html=True)
    with hcol2:
        st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
        if st.button("↺ Actualizar", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # Period selector
    p_col1, p_col2, p_col3, _ = st.columns([1, 1, 1, 4])
    with p_col1:
        p_hoy = st.button("Hoy", use_container_width=True,
                           type="primary" if st.session_state.get("period") == "today" else "secondary")
    with p_col2:
        p_7d  = st.button("7 días", use_container_width=True,
                           type="primary" if st.session_state.get("period") == "7d" else "secondary")
    with p_col3:
        p_30d = st.button("30 días", use_container_width=True,
                           type="primary" if st.session_state.get("period", "30d") == "30d" else "secondary")

    if p_hoy: st.session_state["period"] = "today"
    elif p_7d: st.session_state["period"] = "7d"
    elif p_30d: st.session_state["period"] = "30d"
    period = st.session_state.get("period", "30d")

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
    st.markdown(
        f'<p style="color:#9ca3af;font-size:0.8rem;margin:-4px 0 20px 0;">'
        f'{period_label} · <b style="color:#6b7280">{len(active)}</b> offers activas · '
        f'<b style="color:#6b7280">{len(offers)}</b> total</p>',
        unsafe_allow_html=True
    )

    # ── KPI cards ────────────────────────────────────────────────────────────
    def kpi(label, value, sub="", color="#111827", bg="#fff", border="#e5e7eb"):
        return f"""<div style="background:{bg};border:1px solid {border};border-radius:12px;
            padding:18px 20px;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
          <div style="font-size:0.68rem;font-weight:600;color:#9ca3af;text-transform:uppercase;
              letter-spacing:0.08em;margin-bottom:10px">{label}</div>
          <div style="font-size:1.75rem;font-weight:700;color:{color};line-height:1;
              letter-spacing:-0.02em">{value}</div>
          {f'<div style="font-size:0.72rem;color:#9ca3af;margin-top:6px">{sub}</div>' if sub else ''}
        </div>"""

    roi_color  = "#059669" if total_roi >= 0 else "#dc2626"
    roi_bg     = "#f0fdf4" if total_roi >= 0 else "#fef2f2"
    prof_color = "#059669" if total_profit >= 0 else "#dc2626"

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.markdown(kpi("Gasto", f"${total_cost:,.2f}", f"CPC: ${total_cpc:.3f}"), unsafe_allow_html=True)
    k2.markdown(kpi("Revenue", f"${total_revenue:,.2f}", f"{total_convs} conversiones"), unsafe_allow_html=True)
    k3.markdown(kpi("Profit", f"${total_profit:+,.2f}", f"CPA: ${total_cpa:.2f}" if total_cpa else "sin conv.", color=prof_color), unsafe_allow_html=True)
    k4.markdown(kpi("ROI", f"{total_roi:+.1f}%", f"{period_label}", color=roi_color, bg=roi_bg, border=roi_bg), unsafe_allow_html=True)
    k5.markdown(kpi("Conversiones", str(total_convs), f"CPA: ${total_cpa:.2f}" if total_cpa else "—"), unsafe_allow_html=True)
    k6.markdown(kpi("Clicks", f"{total_clicks:,}", f"EPC: ${(total_revenue/total_clicks):.3f}" if total_clicks else "—"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Alertas ──────────────────────────────────────────────────────────────
    alerts = []
    for oid_key, s in offer_stats.items():
        cost  = float(s.get("adv_cost", 0))
        convs = int(s.get("adv_conversions", 0))
        roi   = float(s.get("adv_roi") or -100)
        name  = s.get("offer", "").replace("US - ", "").replace(" - Voolty", "")
        bid_avg = float(s.get("adv_bids_avg") or 0)
        if cost >= SPEND_ALERT and convs == 0:
            alerts.append(("danger", f"{name} — ${cost:.0f} gastados, 0 conversiones. Pausar o bajar bid."))
        elif roi < -70 and cost > 10:
            alerts.append(("warning", f"{name} — ROI {roi:+.0f}% con ${cost:.0f} invertidos. Revisar bid (actual ${bid_avg:.2f})."))
        elif roi > 100 and cost > 15:
            alerts.append(("success", f"{name} — ROI {roi:+.0f}%! Podés subir el bid para escalar."))

    if alerts:
        alert_styles = {
            "danger":  ("border-left:4px solid #ef4444;background:#fef2f2;", "#991b1b"),
            "warning": ("border-left:4px solid #f59e0b;background:#fffbeb;", "#92400e"),
            "success": ("border-left:4px solid #10b981;background:#f0fdf4;", "#065f46"),
        }
        st.markdown('<div style="font-size:0.75rem;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px">Alertas</div>', unsafe_allow_html=True)
        for kind, msg in alerts:
            style, color = alert_styles[kind]
            st.markdown(
                f'<div style="{style}border-radius:8px;padding:10px 16px;margin-bottom:8px;'
                f'font-size:0.85rem;color:{color}">{msg}</div>',
                unsafe_allow_html=True
            )
        st.markdown("<br>", unsafe_allow_html=True)

    # ── Tabla de offers ──────────────────────────────────────────────────────
    st.markdown('<div style="font-size:0.75rem;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px">Detalle por Offer</div>', unsafe_allow_html=True)

    # Build offer_id → AK offer object map
    offer_id_map = {int(o["id"]): o for o in offers}

    rows = []
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

        # ROI semaphore
        if not is_active:
            flag = "⬜"
        elif convs == 0 and cost > 5:
            flag = "🔴"
        elif roi > 50:
            flag = "🟢"
        elif roi > 0:
            flag = "🟡"
        elif roi > -50:
            flag = "🟠"
        else:
            flag = "🔴"

        rows.append({
            "":         flag,
            "Offer":    name,
            "Clicks":   clicks,
            "Conv.":    convs,
            "Gasto":    f"${cost:.2f}",
            "Revenue":  f"${rev:.2f}",
            "Profit":   f"${profit:+.2f}",
            "ROI":      f"{roi:+.1f}%",
            "CPC":      f"${cpc:.3f}",
            "CPA":      f"${cpa:.2f}" if cpa else "—",
            "EPC":      f"${epc:.3f}" if epc else "—",
            "Bid":      f"${bid:.2f}",
            "Max Bid":  f"${max_b:.2f}" if max_b else "—",
        })

    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("Sin datos para el período seleccionado.")

    # ── Offers sin activar ───────────────────────────────────────────────────
    if inactive:
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander(f"Offers inactivas ({len(inactive)})"):
            irows = [{
                "Offer":  o["name"].replace("US - ","").replace(" - Voolty",""),
                "ID":     o["id"],
                "Bid":    f"${float(o.get('bid',0)):.2f}",
                "Max":    f"${float(o.get('max_bid',0)):.2f}" if o.get("max_bid") else "—",
            } for o in inactive]
            st.dataframe(irows, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# CREAR CAMPAIGN
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Crear Campaign":
    import subprocess, sys as _sys

    st.markdown("<h1>Crear Campaign</h1>", unsafe_allow_html=True)
    st.markdown('<p style="color:#6b7280;font-size:0.875rem;margin-bottom:1.5rem;">Creación automática desde Voolty + SK, o manual para un store específico.</p>', unsafe_allow_html=True)

    tab_auto, tab_manual = st.tabs(["⚡  Automático", "✏️  Manual"])

    # ─── TAB AUTOMÁTICO ────────────────────────────────────────────────────────
    with tab_auto:
        st.markdown("""
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:20px 24px;margin-bottom:20px;">
          <div style="font-size:0.95rem;font-weight:600;color:#0f1117;margin-bottom:6px;">¿Cómo funciona?</div>
          <ol style="color:#4b5563;font-size:0.875rem;margin:0;padding-left:18px;line-height:1.9;">
            <li>Descarga el catálogo completo de Voolty/Galeonica</li>
            <li>Consulta SourceKnowledge y filtra por tráfico real disponible</li>
            <li>Calcula el bid óptimo por dominio (fórmula SK bidCpc)</li>
            <li>Crea Binom offer + campaign + AdKernel offer con keywords y geo US</li>
          </ol>
        </div>
        """, unsafe_allow_html=True)

        ca1, ca2, ca3 = st.columns([1, 1, 2])
        with ca1:
            auto_n = st.number_input("Offers a crear", min_value=1, max_value=20, value=5,
                                     help="El sistema selecciona los mejores N stores disponibles")
        with ca2:
            auto_dry = st.toggle("Dry run (sin crear)", value=True,
                                 help="Muestra los stores seleccionados sin crear nada")
        with ca3:
            st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)

        st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)

        if auto_dry:
            btn_label = f"🔍  Previsualizar {auto_n} offers"
            btn_help  = "Muestra qué stores seleccionaría el sistema sin tocar AdKernel/Binom"
        else:
            btn_label = f"⚡  Crear {auto_n} offers automáticamente"
            btn_help  = "Crea las offers reales en Binom y AdKernel"

        run_auto = st.button(btn_label, type="primary", help=btn_help)

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
                        st.info("Dry run completado. Desactivá el toggle para crear las campañas reales.")
                    else:
                        st.success(f"Batch completado. Revisá el log arriba para ver el detalle.")
                        st.cache_data.clear()
                else:
                    st.error(f"El script terminó con código {proc.returncode}.")
            except Exception as e:
                import traceback
                st.error(f"Error al ejecutar batch: {e}")
                st.code(traceback.format_exc())

    # ─── TAB MANUAL ───────────────────────────────────────────────────────────
    with tab_manual:
        with st.form("crear_campaign"):
            st.markdown('<div class="section-header">Datos del store</div>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            with c1:
                brand_name = st.text_input("Brand name *", placeholder="Bombas")
            with c2:
                store_slug = st.text_input("Slug *", placeholder="bombas")
            with c3:
                ad_display = st.text_input("Dominio", placeholder="bombas.com")

            st.markdown('<div class="section-header" style="margin-top:16px;">Puja</div>', unsafe_allow_html=True)
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

            st.markdown('<div class="section-header" style="margin-top:16px;">Anuncio</div>', unsafe_allow_html=True)
            c7, c8, c9 = st.columns(3)
            with c7:
                ad_title = st.text_input("Título", placeholder="Bombas — Official Site")
            with c8:
                ad_desc  = st.text_input("Descripción", placeholder="Premium socks. Free shipping.")
            with c9:
                ad_cta   = st.text_input("CTA", value="Shop Now")

            st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
            is_active = st.checkbox("Activar inmediatamente", value=False,
                                     help="Por defecto se crea inactiva para revisión manual.")

            st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)
            submitted = st.form_submit_button("Crear Campaign →", type="primary", width='stretch')

        if submitted:
            if not brand_name or not store_slug:
                st.error("Brand name y slug son obligatorios.")
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

                    st.markdown("<hr>", unsafe_allow_html=True)
                    status = result.get("status", "OK")

                    if "SKIP" in str(status) or "ERROR" in str(status):
                        st.warning(f"**Resultado:** {status}")
                    else:
                        st.success("Campaign creada correctamente.")
                        r1, r2, r3 = st.columns(3)
                        r1.metric("Binom Offer",    result.get("binom_offer", "—"))
                        r2.metric("Binom Campaign", result.get("binom_campaign", "—"))
                        r3.metric("AdKernel Offer", result.get("ak_offer", "—"))
                        if result.get("postback_url"):
                            st.markdown('<div class="section-header" style="margin-top:16px;">Postback S2S</div>', unsafe_allow_html=True)
                            st.code(result["postback_url"])
                except Exception as e:
                    import traceback
                    st.error(f"Error inesperado: {e}")
                    st.code(traceback.format_exc())




# ══════════════════════════════════════════════════════════════════════════════
# MONITOREO OFFERS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Monitoreo Offers":
    st.markdown("<h1>Monitoreo de Offers</h1>", unsafe_allow_html=True)
    st.markdown('<p style="color:#6b7280;font-size:0.875rem;margin-bottom:1.5rem;">Estado y configuración de bids en tiempo real.</p>', unsafe_allow_html=True)

    c_ref, c_filt, _ = st.columns([1, 1, 3])
    with c_ref:
        if st.button("↺  Actualizar"):
            st.cache_data.clear()
            st.rerun()
    with c_filt:
        solo_activas = st.toggle("Solo activas", value=False)

    with st.spinner(""):
        try:
            offers = ak_get_offers(ak_get_token())
        except Exception as e:
            st.error(f"Error AdKernel: {e}")
            st.stop()

    if solo_activas:
        offers = [o for o in offers if o.get("is_active")]

    st.markdown('<div class="section-header">Offers</div>', unsafe_allow_html=True)

    rows = [{
        "Nombre":   o["name"].replace("US - ", "").replace(" - Voolty", ""),
        "ID":       o["id"],
        "Estado":   "Activa" if o.get("is_active") else "Inactiva",
        "CPC":      f"${o['bid']:.2f}",
        "Max Bid":  f"${o['max_bid']:.2f}" if o.get("max_bid") else "—",
        "Optimiz.": "Sí" if o.get("optimize_bids_new") else "No",
    } for o in offers]

    st.dataframe(rows, width='stretch', hide_index=True)

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown('<div class="section-header">Editar bid</div>', unsafe_allow_html=True)

    offer_map = {f"{o['name'].replace('US - ','').replace(' - Voolty','')}  (ID {o['id']})": o for o in offers}
    selected  = st.selectbox("Offer", list(offer_map.keys()), label_visibility="collapsed")
    offer     = offer_map[selected]

    c1, c2, c3, c4 = st.columns(4)
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
        st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
        if st.button("Guardar →", type="primary", width='stretch'):
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
                    st.success(f"Offer {offer['id']} actualizada.")
                    st.cache_data.clear()
                    time.sleep(0.8)
                    st.rerun()
                else:
                    st.error(r.text)
            except Exception as e:
                st.error(f"Error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ASISTENTE IA
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Asistente IA":
    import os, subprocess, json as _json, sys as _sys

    st.markdown("<h1>Asistente IA</h1>", unsafe_allow_html=True)
    st.markdown('<p style="color:#6b7280;font-size:0.875rem;margin-bottom:1rem;">Pedile lo que necesitás en lenguaje natural.</p>', unsafe_allow_html=True)

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
        st.error("Instalá el SDK: `pip install anthropic`")
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
        if st.button("Limpiar conversación", type="secondary"):
            st.session_state["chat_messages"] = []
            st.rerun()
