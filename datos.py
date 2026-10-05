"""
Capa de acceso a datos.

La app nunca lee Excel ni Supabase directamente: pide DataFrames a estas
funciones. El origen se elige solo:

  - Si existe [supabase] en .streamlit/secrets.toml  -> lee de Supabase.
  - Si no                                           -> lee los .xlsx de ./data

Así podés migrar tabla por tabla sin tocar la interfaz.
Todas las funciones devuelven columnas con los MISMOS nombres en ambos modos.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent / "data"

# Nombres de tablas en Supabase (ver supabase/programas.sql y plan_cuentas.sql)
T_PLAN = "plan_cuentas"
T_PROGRAMAS = "programas"


# --------------------------------------------------------------------------
# Origen de datos
# --------------------------------------------------------------------------
def _supabase_config() -> dict | None:
    try:
        cfg = st.secrets.get("supabase")
    except Exception:  # no existe secrets.toml
        return None
    return dict(cfg) if cfg and cfg.get("url") and cfg.get("key") else None


def origen() -> str:
    return "Supabase" if _supabase_config() else "Excel local"


@st.cache_resource
def _cliente():
    from supabase import create_client

    cfg = _supabase_config()
    return create_client(cfg["url"], cfg["key"])


def _leer_tabla(tabla: str, columnas: str = "*", lote: int = 1000) -> pd.DataFrame:
    """Lee una tabla completa de Supabase paginando (la API devuelve máx. 1000 filas)."""
    filas, desde = [], 0
    while True:
        res = _cliente().table(tabla).select(columnas).range(desde, desde + lote - 1).execute()
        filas.extend(res.data)
        if len(res.data) < lote:
            break
        desde += lote
    return pd.DataFrame(filas)


# --------------------------------------------------------------------------
# Catálogos
# --------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner="Cargando plan de cuentas…")
def plan_cuentas() -> pd.DataFrame:
    """Columnas: codigo, denominacion, nivel (1 clasificador · 2 partida · 3 ítem), codigo_superior."""
    if _supabase_config():
        df = _leer_tabla(T_PLAN, "codigo,denominacion,nivel,codigo_superior")
    else:
        df = pd.read_excel(DATA_DIR / "Plan_de_cuentas_objeto_del_gasto.xlsx").rename(columns={
            "Código": "codigo", "Denominación": "denominacion", "Nivel": "nivel",
            "Código superior": "codigo_superior"})[["codigo", "denominacion", "nivel", "codigo_superior"]]
    df["codigo"] = df["codigo"].astype(int)
    df["codigo_superior"] = pd.to_numeric(df["codigo_superior"], errors="coerce").astype("Int64")
    df["denominacion"] = df["denominacion"].astype(str).str.strip()
    return df.sort_values("codigo").reset_index(drop=True)


@st.cache_data(ttl=3600)
def programas() -> pd.DataFrame:
    """Columnas: nro_programa, programa, programa_padre, etiqueta (sin presupuesto)."""
    if _supabase_config():
        df = _leer_tabla(T_PROGRAMAS, "nro_programa,programa,programa_padre,orden")
    else:
        df = pd.read_excel(DATA_DIR / "programas.xlsx").rename(
            columns={"NRO_PROGRAMA": "nro_programa", "PROGRAMA": "programa"})
        df["nro_programa"] = df["nro_programa"].astype(str).str.strip()
        df["programa"] = df["programa"].astype(str).str.strip()
        df["programa_padre"] = df["nro_programa"].str.split("-").str[0]
        df["orden"] = range(1, len(df) + 1)
    df = df.sort_values("orden").reset_index(drop=True)
    nombre = dict(zip(df["nro_programa"], df["programa"]))
    # Subprogramas muestran también el programa al que pertenecen: "558-3 · ANP (Biodiversidad Y …)"
    df["etiqueta"] = [
        f"{n} · {p} ({nombre[padre]})" if n != padre and padre in nombre else f"{n} · {p}"
        for n, p, padre in zip(df["nro_programa"], df["programa"], df["programa_padre"])
    ]
    return df[["nro_programa", "programa", "programa_padre", "etiqueta"]]


# --------------------------------------------------------------------------
# Autenticación (funciones SQL en supabase/usuarios.sql — el hash lo hace Postgres)
# --------------------------------------------------------------------------
class ErrorAuth(Exception):
    """Error con mensaje listo para mostrar al usuario."""


def _rpc(funcion: str, params: dict):
    if not _supabase_config():
        raise ErrorAuth("El ingreso requiere Supabase configurado en .streamlit/secrets.toml.")
    try:
        return _cliente().rpc(funcion, params).execute().data
    except Exception as e:  # APIError de PostgREST trae el mensaje del RAISE en .message
        msg = getattr(e, "message", None)
        if msg:
            raise ErrorAuth(msg) from e
        raise ErrorAuth("No se pudo conectar con el servidor. Probá de nuevo en unos minutos.") from e


def login(usuario: str, password: str) -> dict | None:
    """Devuelve los datos del usuario (sin hash) o None si las credenciales no son válidas."""
    filas = _rpc("login", {"p_usuario": usuario, "p_password": password})
    return filas[0] if filas else None


def cambiar_password(usuario: str, actual: str, nueva: str) -> None:
    _rpc("cambiar_password", {"p_usuario": usuario, "p_actual": actual, "p_nueva": nueva})


def resetear_password(admin: str, admin_password: str, usuario: str, temporal: str) -> None:
    _rpc("resetear_password", {"p_admin": admin, "p_admin_password": admin_password,
                               "p_usuario": usuario, "p_temporal": temporal})


def logout(token: str) -> None:
    try:
        _rpc("logout", {"p_token": token})
    except ErrorAuth:
        pass  # si la sesión ya no existe, no importa


# --------------------------------------------------------------------------
# Registros de la formulación (supabase/formulacion.sql) — todo pasa por el token de sesión
# --------------------------------------------------------------------------
SESION_VENCIDA = "sesión venció"


def listar_registros(token: str) -> list[dict]:
    return _rpc("formulacion_listar", {"p_token": token}) or []


def agregar_registro(token: str, registro: dict) -> int:
    return _rpc("formulacion_agregar", {"p_token": token, "p_datos": registro})


def actualizar_registro(token: str, id_: int, cambios: dict) -> None:
    _rpc("formulacion_actualizar", {"p_token": token, "p_id": int(id_), "p_cambios": cambios})


def borrar_registro(token: str, id_: int) -> None:
    _rpc("formulacion_borrar", {"p_token": token, "p_id": int(id_)})


def estado_presupuesto(token: str) -> list[dict]:
    """Presupuesto, comprometido (todos los usuarios) y margen de los programas del usuario."""
    return _rpc("presupuesto_estado", {"p_token": token}) or []


def estado_carga(token: str) -> dict:
    """Fecha límite de carga y si sigue abierta para este usuario."""
    filas = _rpc("carga_estado", {"p_token": token})
    return filas[0] if filas else {"fecha_limite": None, "abierta": True}


def duplicados(token: str, nro_programa: str, codigo: int) -> list[dict]:
    """Registros ya cargados (por cualquier usuario) del mismo ítem en el mismo programa."""
    return _rpc("formulacion_duplicados", {"p_token": token, "p_nro": nro_programa, "p_codigo": int(codigo)}) or []


# --------------------------------------------------------------------------
# Administración (supabase/admin.sql) — la base exige rol admin en cada llamada
# --------------------------------------------------------------------------
def admin_fecha_limite(token: str, fecha_iso: str | None) -> None:
    _rpc("admin_fecha_limite_guardar", {"p_token": token, "p_fecha": fecha_iso})


def admin_programas(token: str) -> list[dict]:
    return _rpc("admin_programas_listar", {"p_token": token}) or []


def admin_programa_guardar(token: str, nro: str, programa: str, presupuesto: float | None) -> None:
    _rpc("admin_programa_guardar", {"p_token": token, "p_nro": nro, "p_programa": programa,
                                    "p_presupuesto": presupuesto})


def admin_usuarios(token: str) -> list[dict]:
    return _rpc("admin_usuarios_listar", {"p_token": token}) or []


def admin_usuario_guardar(token: str, datos_usuario: dict) -> None:
    _rpc("admin_usuario_guardar", {"p_token": token, "p_datos": datos_usuario})


def admin_usuario_resetear(token: str, usuario: str) -> None:
    _rpc("admin_usuario_resetear", {"p_token": token, "p_usuario": usuario})


def admin_historial(token: str, limite: int = 500) -> list[dict]:
    return _rpc("admin_historial", {"p_token": token, "p_limite": int(limite)}) or []
