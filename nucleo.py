"""Constantes, formatos y la regla de presupuesto. No depende de la sesión ni de la base."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

ZONA = ZoneInfo("America/Argentina/Buenos_Aires")

PRIORIDADES = ["Alta", "Media", "Baja"]
UNIDADES = ["Unidad", "Mensual", "Kilos", "Litros", "Metros", "Horas", "Otro"]
# Rampa azul ordinal validada (Alta = más oscuro)
COLOR_PRIORIDAD = {"Alta": "#184f95", "Media": "#2a78d6", "Baja": "#86b6ef"}

AZUL, AZUL_CLARO = "#2a78d6", "#86b6ef"        # utilizado / este ítem (dentro del presupuesto)
NARANJA, NARANJA_CLARO = "#ec835a", "#f6c3ae"   # parte por encima del presupuesto
ESTADOS = {  # estado: (color del punto, texto) — el color nunca va solo, siempre con texto
    "ok":            ("#0ca30c", "Con saldo"),
    "alerta":        ("#fab219", "Por agotarse (≥ 90 %)"),
    "excedido":      ("#ec835a", "Excedido · solo prioridad Baja"),
    "baja_ok":       ("#ec835a", "Supera el presupuesto · permitido por ser Baja"),
    "requiere_baja": ("#d03b3b", "Supera el presupuesto · solo prioridad Baja"),
    "excede":        ("#d03b3b", "Supera el margen del 10 %"),
    "sin":           ("#9a9994", "Sin presupuesto cargado"),
}
ICONO_ESTADO = {"ok": "✅", "alerta": "⚠️", "excedido": "🟠", "excede": "⛔", "sin": "—"}

# Valores con los que se limpia el formulario de carga después de agregar
DEFAULTS_CARGA = {
    "f_item": None,
    "f_cant": 0,
    "f_cant_min": 1,
    "f_precio": 0.0,
    "f_unidad": "Unidad",
    "f_prioridad": "Alta",
    "f_just": "",
}

EDITABLES = {"cantidad", "cantidad_minima", "unidad", "precio_unitario", "prioridad", "justificacion"}


def md(txt: str) -> str:
    """Escapa $ para que Streamlit no lo tome como fórmula en st.error/st.warning."""
    return txt.replace("$", "\\$")


def ars(valor: float | None, dec: int = 2) -> str:
    """Formato moneda argentino: $ 1.234.567,89"""
    if valor is None or pd.isna(valor):
        return "—"
    txt = f"{valor:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"$ {txt}"


def a_fecha(valor) -> datetime | None:
    """Convierte lo que devuelve la base (texto ISO) a fecha y hora de Argentina."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    ts = pd.to_datetime(valor, utc=True, errors="coerce")
    return None if pd.isna(ts) else ts.tz_convert(ZONA).to_pydatetime()


def fecha_txt(valor, con_hora: bool = True) -> str:
    f = a_fecha(valor)
    return "—" if f is None else f.strftime("%d/%m/%Y %H:%M" if con_hora else "%d/%m/%Y")


def evaluar(f: dict | None, extra: float = 0.0, prioridad: str = "Alta", extra_min: float = 0.0) -> dict:
    """
    Misma regla que la base: hasta el presupuesto cualquier prioridad; por encima, solo Baja y hasta +10 %.
    f = fila de presupuesto_estado; extra / extra_min = monto y monto mínimo del ítem que se está cargando.
    """
    if not f or f.get("presupuesto") is None:
        return {"estado": "sin"}
    P, C = float(f["presupuesto"]), float(f["comprometido"])
    lim = P * (1 + float(f.get("margen") or 0.10))
    total = C + extra
    if total <= P:
        estado = "ok" if total < 0.9 * P else "alerta"
    elif total <= lim + 0.005:
        estado = "baja_ok" if prioridad == "Baja" else ("excedido" if extra == 0 else "requiere_baja")
    else:
        estado = "excede"
    minimo = float(f.get("minimo") or 0) + extra_min
    return {"estado": estado, "P": P, "C": C, "extra": extra, "total": total, "lim": lim,
            "saldo": P - total, "disp": max(P - C, 0), "disp_baja": max(lim - C, 0),
            "minimo": minimo, "saldo_min": P - minimo}
