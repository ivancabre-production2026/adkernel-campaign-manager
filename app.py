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
  /* Global */
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

  html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
  }

  /* Sidebar */
  [data-testid="stSidebar"] {
    background: #0f1117;
    border-right: 1px solid #1e2130;
  }
  [data-testid="stSidebar"] * {
    color: #c9d1d9 !important;
  }
  [data-testid="stSidebar"] .stRadio label {
    padding: 8px 12px;
    border-radius: 6px;
    transition: background 0.15s;
    display: block;
    font-size: 0.875rem;
    font-weight: 500;
    letter-spacing: 0.01em;
  }
  [data-testid="stSidebar"] .stRadio label:hover {
    background: #1e2130;
  }

  /* Main background */
  .main .block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
    max-width: 1200px;
  }

  /* Page title */
  h1 {
    font-size: 1.5rem !important;
    font-weight: 600 !important;
    color: #0f1117 !important;
    letter-spacing: -0.02em !important;
    margin-bottom: 0.25rem !important;
  }

  /* Metric cards */
  .metric-card {
    background: #ffffff;
    border: 1px solid #e8ecf0;
    border-radius: 10px;
    padding: 20px 24px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }
  .metric-label {
    font-size: 0.75rem;
    font-weight: 500;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 8px;
  }
  .metric-value {
    font-size: 2rem;
    font-weight: 700;
    color: #0f1117;
    line-height: 1;
  }
  .metric-value.green { color: #059669; }
  .metric-value.amber { color: #d97706; }
  .metric-value.red   { color: #dc2626; }

  /* Status badges */
  .badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
  }
  .badge-green  { background: #d1fae5; color: #065f46; }
  .badge-gray   { background: #f3f4f6; color: #374151; }
  .badge-amber  { background: #fef3c7; color: #92400e; }

  /* Section header */
  .section-header {
    font-size: 0.8rem;
    font-weight: 600;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 12px;
    margin-top: 8px;
  }

  /* Log output */
  .log-box {
    background: #0f1117;
    color: #a8ff78;
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 0.78rem;
    padding: 16px;
    border-radius: 8px;
    max-height: 320px;
    overflow-y: auto;
    line-height: 1.6;
  }

  /* Divider */
  hr {
    border: none;
    border-top: 1px solid #e8ecf0;
    margin: 1.5rem 0;
  }

  /* Buttons */
  .stButton > button {
    border-radius: 7px;
    font-weight: 500;
    font-size: 0.875rem;
    letter-spacing: 0.01em;
    transition: all 0.15s;
    border: 1px solid #d1d5db;
  }
  .stButton > button[kind="primary"] {
    background: #0f1117;
    border-color: #0f1117;
    color: white;
  }
  .stButton > button[kind="primary"]:hover {
    background: #1e2130;
    border-color: #1e2130;
  }

  /* Form inputs */
  .stTextInput > div > div > input,
  .stNumberInput > div > div > input,
  .stSelectbox > div > div {
    border-radius: 7px !important;
    border-color: #d1d5db !important;
    font-size: 0.875rem !important;
  }

  /* Dataframe */
  [data-testid="stDataFrame"] {
    border: 1px solid #e8ecf0;
    border-radius: 10px;
    overflow: hidden;
  }

  /* Form container */
  [data-testid="stForm"] {
    background: #ffffff;
    border: 1px solid #e8ecf0;
    border-radius: 10px;
    padding: 24px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }

  /* Hide Streamlit branding */
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


def metric_card(label: str, value, color: str = "") -> str:
    cls = f"metric-value {color}".strip()
    return f"""
    <div class="metric-card">
      <div class="metric-label">{label}</div>
      <div class="{cls}">{value}</div>
    </div>"""


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


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "Dashboard":
    import datetime

    # ── Fetch data ─────────────────────────────────────────────────────────
    col_ref, col_range, _ = st.columns([1, 2, 4])
    with col_ref:
        if st.button("↺  Actualizar"):
            st.cache_data.clear()
            st.rerun()
    with col_range:
        date_range = st.selectbox("Período", ["Hoy", "Últimos 7 días", "Últimos 30 días"],
                                   index=2, label_visibility="collapsed")

    SPEND_ALERT = 30.0   # alerta si una offer gasta más de este $ sin conversiones

    with st.spinner("Cargando datos..."):
        try:
            tok    = ak_get_token()
            offers = ak_get_offers(tok)
        except Exception as e:
            st.error(f"No se pudo conectar a AdKernel: {e}")
            st.stop()

    # ── Fetch AdKernel stats (clicks/cost per offer via API) ────────────────
    @st.cache_data(ttl=180, show_spinner=False)
    def ak_get_stats(_tok: str) -> dict:
        """Devuelve {offer_id: {clicks, cost, impressions}} desde AdKernel."""
        try:
            now   = datetime.date.today()
            start = now - datetime.timedelta(days=29)
            r = requests.get(f"{AK_BASE}/admin/api/Stat/",
                params={"version": AK_VERSION, "token": _tok,
                        "ad_campaign_id": AK_CAMPAIGN_ID,
                        "date_from": str(start), "date_to": str(now),
                        "group_by": "offer", "limit": 500},
                timeout=30)
            rows = r.json().get("response", {}).get("rows", {})
            return {int(k): v for k, v in rows.items()}
        except Exception:
            return {}

    @st.cache_data(ttl=300, show_spinner=False)
    def binom_get_stats(_key: str) -> list:
        """Devuelve stats de campañas desde Binom."""
        try:
            r = requests.post("https://ilatintrack.biz/public/api/v1/click.stat",
                headers={"Api-Key": _key},
                json={"group1": "campaign_name", "date": "last_30_days"},
                timeout=45)
            if r.ok:
                return r.json() if r.text else []
        except Exception:
            pass
        return []

    stats    = ak_get_stats(tok)
    binom_st = binom_get_stats(BINOM_KEY)
    binom_map = {}
    for row in binom_st:
        name = row.get("name", "")
        binom_map[name] = row

    active   = [o for o in offers if o.get("is_active")]
    inactive = [o for o in offers if not o.get("is_active")]

    # ── Aggregate totals ────────────────────────────────────────────────────
    total_clicks = sum(s.get("clicks", 0) for s in stats.values())
    total_cost   = sum(float(s.get("cost", 0)) for s in stats.values())
    total_revenue = sum(float(r.get("revenue", 0)) for r in binom_map.values())
    total_profit  = total_revenue - total_cost
    total_roi     = (total_profit / total_cost * 100) if total_cost > 0 else 0
    total_leads   = sum(int(r.get("leads", 0)) for r in binom_map.values())

    roi_color = "green" if total_roi > 0 else "red"

    # ── KPI Row ─────────────────────────────────────────────────────────────
    st.markdown("<h1>Dashboard</h1>", unsafe_allow_html=True)
    st.markdown(f'<p style="color:#6b7280;font-size:0.875rem;margin-bottom:1.5rem;">{date_range} · {len(active)} offers activas · {len(offers)} total</p>', unsafe_allow_html=True)

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.markdown(metric_card("Gasto Total",    f"${total_cost:,.2f}",   "red" if total_cost > 0 else ""), unsafe_allow_html=True)
    k2.markdown(metric_card("Revenue",        f"${total_revenue:,.2f}", "green" if total_revenue > 0 else ""), unsafe_allow_html=True)
    k3.markdown(metric_card("Profit",         f"${total_profit:,.2f}", "green" if total_profit >= 0 else "red"), unsafe_allow_html=True)
    k4.markdown(metric_card("ROI",            f"{total_roi:+.1f}%",    roi_color), unsafe_allow_html=True)
    k5.markdown(metric_card("Leads / Conv.",  total_leads,             "green" if total_leads > 0 else ""), unsafe_allow_html=True)
    k6.markdown(metric_card("Clicks",         f"{total_clicks:,}",     ""), unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Alertas ─────────────────────────────────────────────────────────────
    alerts = []
    for o in active:
        oid  = int(o["id"])
        s    = stats.get(oid, {})
        cost = float(s.get("cost", 0))
        name = o["name"].replace("US - ", "").replace(" - Voolty", "")

        bkey = next((k for k in binom_map if name.lower().split()[0] in k.lower()), None)
        leads = int(binom_map[bkey].get("leads", 0)) if bkey else 0
        roi   = float(binom_map[bkey].get("roi", 0)) if bkey else None

        if cost >= SPEND_ALERT and leads == 0:
            alerts.append(("🔴", f"**{name}** gastó ${cost:.2f} sin conversiones — considerá pausar o bajar bid"))
        elif roi is not None and roi < -60 and cost > 5:
            alerts.append(("🟠", f"**{name}** ROI {roi:+.1f}% con ${cost:.2f} gastados — bajá el bid"))
        elif roi is not None and roi > 80 and cost > 5:
            alerts.append(("🟢", f"**{name}** ROI {roi:+.1f}% — podés subir el bid para escalar"))

    if alerts:
        st.markdown('<div class="section-header">Alertas</div>', unsafe_allow_html=True)
        for icon, msg in alerts:
            st.markdown(f"{icon} {msg}")
        st.markdown("<hr>", unsafe_allow_html=True)

    # ── Tabla de offers ─────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Offers activas — detalle</div>', unsafe_allow_html=True)

    rows = []
    for o in sorted(active, key=lambda x: float(stats.get(int(x["id"]), {}).get("cost", 0)), reverse=True):
        oid   = int(o["id"])
        s     = stats.get(oid, {})
        cost  = float(s.get("cost", 0))
        clicks = int(s.get("clicks", 0))
        name  = o["name"].replace("US - ", "").replace(" - Voolty", "")
        bid   = float(o.get("bid", 0))
        max_b = float(o.get("max_bid") or 0)

        bkey = next((k for k in binom_map if name.lower().split()[0] in k.lower()), None)
        rev   = float(binom_map[bkey].get("revenue", 0)) if bkey else 0
        leads = int(binom_map[bkey].get("leads", 0)) if bkey else 0
        roi   = float(binom_map[bkey].get("roi", 0)) if bkey else None
        epc   = float(binom_map[bkey].get("epc", 0)) if bkey else 0
        profit = rev - cost

        # Semáforo
        if roi is None:
            flag = "⚪"
        elif roi > 30:
            flag = "🟢"
        elif roi > -20:
            flag = "🟡"
        else:
            flag = "🔴"

        rows.append({
            " ":        flag,
            "Offer":    name,
            "Clicks":   clicks,
            "Gasto":    f"${cost:.2f}" if cost > 0 else "—",
            "Revenue":  f"${rev:.2f}"  if rev  > 0 else "—",
            "Profit":   f"${profit:+.2f}" if rev > 0 else "—",
            "ROI":      f"{roi:+.1f}%" if roi is not None else "—",
            "Leads":    leads if leads > 0 else "—",
            "EPC":      f"${epc:.4f}" if epc > 0 else "—",
            "Bid":      f"${bid:.2f}",
            "Max Bid":  f"${max_b:.2f}" if max_b > 0 else "—",
        })

    if rows:
        st.dataframe(rows, width='stretch', hide_index=True)
    else:
        st.info("No hay offers activas.")

    # ── Offers sin activar ───────────────────────────────────────────────────
    if inactive:
        st.markdown("<hr>", unsafe_allow_html=True)
        with st.expander(f"Offers inactivas ({len(inactive)}) — pendientes de revisión"):
            irows = [{
                "Offer":   o["name"].replace("US - ","").replace(" - Voolty",""),
                "ID":      o["id"],
                "Bid":     f"${float(o.get('bid',0)):.2f}",
            } for o in inactive]
            st.dataframe(irows, width='stretch', hide_index=True)


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
