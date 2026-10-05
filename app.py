"""
Formulación Presupuestaria — Ministerio de Ambiente y Economía Circular

Punto de entrada: login, encabezado, navegación y aviso de fecha límite.
Cada vista vive en su propio archivo dentro de vistas/.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st

import auth
import catalogos
import datos
import estado
import estilos
from nucleo import ZONA, md
from vistas import admin, carga, registros, resumen

st.set_page_config(page_title="Formulación Presupuestaria", page_icon="🌿", layout="wide",
                   initial_sidebar_state="collapsed")
estilos.aplicar()

VISTAS = {"Carga": carga.mostrar, "Registros": registros.mostrar, "Resumen": resumen.mostrar,
          "Admin": admin.mostrar}


def _falta(limite: datetime) -> str:
    seg = int((limite - datetime.now(ZONA)).total_seconds())
    if seg >= 2 * 86400:
        return f"faltan {seg // 86400} días"
    if seg >= 3600:
        horas = seg // 3600
        return f"falta{'n' if horas != 1 else ''} {horas} hora{'s' if horas != 1 else ''}"
    minutos = max(seg // 60, 1)
    return f"falta{'n' if minutos != 1 else ''} {minutos} minuto{'s' if minutos != 1 else ''}"


def aviso_fecha_limite() -> None:
    """Línea discreta mientras falta tiempo; aviso fuerte en las últimas 48 h o cuando ya cerró."""
    c = estado.carga()
    limite = c["limite"]
    if limite is None:
        return
    cuando = f"{limite:%d/%m/%Y} a las {limite:%H:%M} hs"
    cerro = datetime.now(ZONA) >= limite
    if estado.es_admin():
        st.caption(f"📅 Fecha límite de carga: {cuando} — "
                   + ("**cerrada para los usuarios**" if cerro else _falta(limite))
                   + ". Como administrador podés seguir editando.")
    elif not c["abierta"]:
        st.error(f"🔒 **La carga cerró el {cuando}.** Podés consultar y exportar tus registros, "
                 "pero ya no agregar, editar ni borrar.")
    elif (limite - datetime.now(ZONA)).total_seconds() < 48 * 3600:
        st.warning(f"⏳ **La carga cierra el {cuando}** ({_falta(limite)}). Después no se van a poder "
                   "agregar ni modificar registros.")
    else:
        st.caption(f"📅 La carga cierra el {cuando} ({_falta(limite)}).")


# --------------------------------------------------------------------------
# Ingreso y datos base
# --------------------------------------------------------------------------
auth.requerir_login()  # pantalla de ingreso / cambio de clave; corta si no hay sesión
try:
    catalogos.plan()
    catalogos.programas()
except FileNotFoundError as e:
    st.error(f"No encuentro los archivos de datos: {e}. Copiá los .xlsx en la carpeta `data/` "
             "o configurá Supabase en `.streamlit/secrets.toml`.")
    st.stop()
estado.init()

# --------------------------------------------------------------------------
# Encabezado + navegación (una sola fila)
# --------------------------------------------------------------------------
logo = Path(__file__).parent / "ambiente.png"
if logo.exists():
    st.logo(str(logo), size="large")

opciones = ["Carga", "Registros", "Resumen"] + (["Admin"] if estado.es_admin() else [])
if st.session_state.get("vista") not in opciones:
    st.session_state.vista = "Carga"

c_tit, c_nav, c_usr = st.columns([3, 2.4, 0.8], vertical_alignment="center")
with c_usr:
    auth.menu_usuario()
with c_tit:
    st.markdown(
        "<div class='app-title'><div class='t'>Formulación Presupuestaria</div>"
        f"<span>Ministerio de Ambiente y Economía Circular · datos: {datos.origen()}</span></div>",
        unsafe_allow_html=True,
    )
with c_nav:
    n = len(st.session_state.registros)
    etiquetas = {"Carga": "📝 Carga", "Registros": f"📋 Registros ({n})", "Resumen": "📊 Resumen",
                 "Admin": "⚙️ Admin"}
    vista = st.segmented_control("Vista", opciones, key="vista", format_func=etiquetas.get,
                                 label_visibility="collapsed", width="stretch") or "Carga"

aviso = st.session_state.pop("_aviso", None)
if aviso:
    (st.toast if aviso[0] == "ok" else st.error)(md(aviso[1]), **({"icon": "✅"} if aviso[0] == "ok" else {}))

aviso_fecha_limite()
VISTAS[vista]()
