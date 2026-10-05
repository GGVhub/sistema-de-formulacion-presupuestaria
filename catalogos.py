"""
Catálogos compartidos por todos los usuarios: plan de cuentas y programas.
Se arman una vez por hora (o cuando el admin cambia un programa) y se usan solo para leer.
"""
from __future__ import annotations

import streamlit as st

import datos


@st.cache_resource(ttl=3600, show_spinner="Cargando plan de cuentas…")
def plan() -> dict:
    """Plan de cuentas: Nivel 1 = Clasificador · Nivel 2 = Partida · Nivel 3 = Ítem."""
    df = datos.plan_cuentas()
    denom = dict(zip(df["codigo"], df["denominacion"]))
    superior = dict(zip(df["codigo"], df["codigo_superior"]))
    partidas = df[df["nivel"] == 2]["codigo"].tolist()
    n3 = df[df["nivel"] == 3]
    return {
        "denom": denom,
        "partidas": partidas,
        "etq_partida": {c: f"{c} · {denom[c]}" for c in partidas},
        "clasificador": {c: denom.get(superior[c], "—") for c in partidas},
        # Las partidas sin ítems de nivel 3 se cargan a nivel partida
        "items_de": {c: n3[n3["codigo_superior"] == c]["codigo"].tolist() or [c] for c in partidas},
        "etq_item": {c: f"{c} · {denom[c]}" for c in df["codigo"]},
    }


@st.cache_resource(ttl=3600, show_spinner=False)
def programas() -> dict:
    df = datos.programas()
    return {
        "lista": df["nro_programa"].tolist(),
        "nombre": dict(zip(df["nro_programa"], df["programa"])),
        "etiqueta": dict(zip(df["nro_programa"], df["etiqueta"])),                      # con el programa padre
        "corta": {n: f"{n} · {p}" for n, p in zip(df["nro_programa"], df["programa"])},  # "558-3 · ANP"
    }


def refrescar_programas() -> None:
    """Después de que el admin crea o renombra un programa."""
    datos.programas.clear()
    programas.clear()
