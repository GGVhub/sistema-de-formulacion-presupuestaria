"""
Estado propio de cada sesión: usuario, registros, presupuesto y fecha límite.
Todo vive en st.session_state (cada usuario conectado tiene el suyo).
"""
from __future__ import annotations

import time
from datetime import datetime

import pandas as pd
import streamlit as st

import catalogos
import datos
from nucleo import DEFAULTS_CARGA, ZONA, a_fecha

REFRESCO = 30  # segundos que se reutiliza presupuesto y fecha límite antes de volver a pedirlos

COLS_REG = ["id", "nro_programa", "programa", "jurisdiccion", "partida_codigo", "partida",
            "codigo", "item", "objeto_gasto", "clasificador",
            "cantidad", "cantidad_minima", "unidad", "precio_unitario", "monto", "monto_minimo",
            "prioridad", "justificacion", "cargado_por", "creado_en"]


# --------------------------------------------------------------------------
# Usuario
# --------------------------------------------------------------------------
def usuario() -> dict:
    return st.session_state.usuario


def token() -> str:
    return st.session_state.usuario["token"]


def es_admin() -> bool:
    return st.session_state.usuario.get("rol") == "admin"


def mis_programas() -> list[str]:
    """Programas que puede usar este usuario: los asignados; admin o sin asignar = todos."""
    todos = catalogos.programas()["lista"]
    asignados = set(usuario().get("programas") or [])
    return todos if es_admin() or not asignados else [n for n in todos if n in asignados]


def manejar_error(e: Exception) -> None:
    """Si la sesión venció, vuelve al login; si no, deja el error para mostrar."""
    if datos.SESION_VENCIDA in str(e).lower():
        st.session_state.clear()
        st.session_state._aviso = ("error", "Tu sesión venció. Volvé a ingresar.")
    else:
        st.session_state._aviso = ("error", str(e))


def avisar(texto: str) -> None:
    st.session_state._aviso = ("ok", texto)


# --------------------------------------------------------------------------
# Registros
# --------------------------------------------------------------------------
def recargar_registros() -> None:
    try:
        st.session_state.registros = datos.listar_registros(token())
    except datos.ErrorAuth as e:
        st.session_state.setdefault("registros", [])
        manejar_error(e)
        if "usuario" not in st.session_state:  # sesión vencida: el próximo ciclo muestra el login
            return
    st.session_state.editor_v = st.session_state.get("editor_v", 0) + 1  # resetea la tabla editable
    invalidar()


def invalidar() -> None:
    """Fuerza a releer presupuesto, fecha límite y duplicados en el próximo ciclo."""
    st.session_state.presu_t = 0
    st.session_state.pop("dup_cache", None)
    for clave in ("adm_programas", "adm_usuarios", "adm_historial"):  # datos del panel de administración
        st.session_state.pop(clave, None)


def df_registros() -> pd.DataFrame:
    etiqueta = catalogos.programas()["etiqueta"]
    df = pd.DataFrame(st.session_state.registros, columns=COLS_REG)
    for c in ("justificacion", "partida", "clasificador"):
        df[c] = df[c].fillna("")
    # Etiqueta para mostrar: "558-3 · ANP"; los registros viejos conservan su jurisdicción
    df["prog"] = df["nro_programa"].map(etiqueta).fillna(df["programa"]).fillna(df["jurisdiccion"]).fillna("—")
    for c in ("precio_unitario", "monto", "monto_minimo"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["creado_en"] = (pd.to_datetime(df["creado_en"], utc=True, errors="coerce")
                         .dt.tz_convert(ZONA).dt.strftime("%d/%m/%Y %H:%M"))
    return df


# --------------------------------------------------------------------------
# Presupuesto y fecha límite (los calcula la base; acá solo se guardan unos segundos)
# --------------------------------------------------------------------------
def _refrescar_si_hace_falta() -> None:
    s = st.session_state
    if "presu_filas" in s and time.time() - s.get("presu_t", 0) <= REFRESCO:
        return
    try:
        s.presu_filas = datos.estado_presupuesto(token())
        s.carga_estado = datos.estado_carga(token())
    except datos.ErrorAuth as e:
        manejar_error(e)
        s.setdefault("presu_filas", [])
        s.setdefault("carga_estado", {"fecha_limite": None, "abierta": True})
    s.presu_t = time.time()


def presupuesto() -> dict:
    """{nro_programa: fila} con presupuesto, comprometido (todos los usuarios), mínimo y margen."""
    _refrescar_si_hace_falta()
    return {f["nro_programa"]: f for f in st.session_state.get("presu_filas", [])}


def carga() -> dict:
    """{'limite': datetime | None, 'abierta': bool} — abierta ya contempla que el admin no tiene cierre."""
    _refrescar_si_hace_falta()
    e = st.session_state.get("carga_estado") or {}
    limite = a_fecha(e.get("fecha_limite"))
    # Si la fecha pasó entre dos refrescos, se cierra igual en pantalla (la base lo valida siempre)
    vencida = limite is not None and datetime.now(ZONA) >= limite
    return {"limite": limite, "abierta": bool(e.get("abierta", True)) and (es_admin() or not vencida)}


def duplicados(nro: str, codigo: int) -> list[dict]:
    """Registros existentes del mismo ítem en el mismo programa (de cualquier usuario)."""
    cache = st.session_state.setdefault("dup_cache", {})
    clave = (nro, int(codigo))
    if clave not in cache:
        try:
            cache[clave] = datos.duplicados(token(), nro, codigo)
        except datos.ErrorAuth:
            cache[clave] = []
    return cache[clave]


# --------------------------------------------------------------------------
# Inicio de sesión de trabajo
# --------------------------------------------------------------------------
def init() -> None:
    s = st.session_state
    if "registros" not in s:
        recargar_registros()
        if "usuario" not in s:
            st.rerun()
    s.setdefault("editor_v", 0)
    s.setdefault("vista", "Carga")
    s.setdefault("f_jur", None)
    s.setdefault("f_partida", None)
    for k, v in DEFAULTS_CARGA.items():
        s.setdefault(k, v)
    propios = mis_programas()
    if s.get("f_jur") not in propios:  # valor viejo o de otro usuario
        s.f_jur = propios[0] if len(propios) == 1 else None
