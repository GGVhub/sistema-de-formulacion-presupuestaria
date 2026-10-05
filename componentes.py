"""Piezas visuales reutilizables: tarjeta de presupuesto, barras e indicadores."""
from __future__ import annotations

import streamlit as st

import catalogos
from nucleo import AZUL, AZUL_CLARO, ESTADOS, NARANJA, NARANJA_CLARO, ars, evaluar


def titulo(texto: str, aclaracion: str = "") -> None:
    extra = f" <span>· {aclaracion}</span>" if aclaracion else ""
    st.markdown(f"<p class='panel-titulo'>{texto}{extra}</p>", unsafe_allow_html=True)


def totales(*pares: tuple[str, str]) -> str:
    """Caja gris con pares (etiqueta, valor)."""
    return "<div class='totales'>" + "".join(
        f"<div><small>{k}</small><strong>{v}</strong></div>" for k, v in pares) + "</div>"


def kpis(*items: tuple) -> str:
    """Fila de indicadores. Cada item: (etiqueta, valor) o (etiqueta, valor, subtexto)."""
    html = ""
    for it in items:
        sub = f"<span class='sub'>{it[2]}</span>" if len(it) > 2 and it[2] else ""
        html += f"<div class='kpi'><small>{it[0]}</small><div>{it[1]}{sub}</div></div>"
    return f"<div class='kpis'>{html}</div>"


def estado_html(estado: str) -> str:
    color, texto = ESTADOS[estado]
    return f"<span class='presu-est'><span class='dot' style='background:{color}'></span>{texto}</span>"


def barra_html(ev: dict, chico: bool = False) -> str:
    """Barra: utilizado + ítem en carga, con marcas de presupuesto, límite +10 % y escenario mínimo."""
    P, C, M, lim = ev["P"], ev["C"], ev["extra"], ev["lim"]
    esc = max(lim, C + M, ev["minimo"], 1) * 1.02
    segs = [(min(C, P), AZUL), (min(C + M, P) - min(C, P), AZUL_CLARO),
            (max(C - P, 0), NARANJA), (max(C + M, P) - max(C, P), NARANJA_CLARO)]
    html = "".join(f"<b style='width:{100 * v / esc:.3f}%;background:{c}'></b>" for v, c in segs if v > 0)
    html += f"<i style='left:{100 * P / esc:.3f}%' title='Presupuesto'></i>"
    html += f"<i class='dash' style='left:{100 * lim / esc:.3f}%' title='Límite +10 % (solo Baja)'></i>"
    if not chico and ev["minimo"] > 0:
        html += f"<u style='left:{100 * ev['minimo'] / esc:.3f}%' title='Escenario mínimo'></u>"
    return f"<div class='meter{' chico' if chico else ''}'>{html}</div>"


def medidor(nro: str, f: dict | None, extra: float = 0.0, prioridad: str = "Alta",
            extra_min: float = 0.0) -> str:
    """Tarjeta con saldo + barra. extra / extra_min = ítem que se está cargando (vista previa)."""
    ev = evaluar(f, extra, prioridad, extra_min)
    nombre = f"<span class='presu-prog'>{catalogos.programas()['etiqueta'].get(nro, nro)}</span>"
    if ev["estado"] == "sin":
        return (f"<div class='presu'><div class='presu-top'>{nombre}</div>{estado_html('sin')}"
                "<div class='presu-ley'>Todavía no se cargó el presupuesto de este programa: "
                "no hay control de saldo.</div></div>")
    saldo = ev["saldo"]
    ley = [f"<span><span class='sq' style='background:{AZUL}'></span>Utilizado {ars(ev['C'], 0)} "
           f"({ev['C'] / ev['P']:.0%})</span>" if ev["P"] else ""]
    if extra > 0:
        ley.append(f"<span><span class='sq' style='background:{AZUL_CLARO}'></span>Este ítem {ars(extra, 0)}</span>")
    ley.append("<span>│ presupuesto</span><span style='color:#d03b3b'>┆ +10 % solo Baja</span>")
    minimo = ""
    if ev["minimo"] > 0:
        entra = ev["saldo_min"] >= 0
        minimo = (f"<div class='presu-min'>▲ <b>Escenario mínimo</b> {ars(ev['minimo'], 0)} · "
                  + (f"quedarían {ars(ev['saldo_min'], 0)}" if entra
                     else f"<span class='neg'>faltarían {ars(-ev['saldo_min'], 0)}</span>") + "</div>")
    return (
        f"<div class='presu'><div class='presu-top'>{nombre}{estado_html(ev['estado'])}</div>"
        f"<div class='presu-saldo'><small>Saldo{' con este ítem' if extra > 0 else ''}</small>"
        f"<div><strong class='{'neg' if saldo < 0 else ''}'>{ars(saldo, 0)}</strong>"
        f"<span>de {ars(ev['P'], 0)}</span></div></div>"
        f"{barra_html(ev)}<div class='presu-ley'>{''.join(ley)}</div>{minimo}</div>"
    )


def medidor_mini(nro: str, f: dict | None) -> str:
    ev = evaluar(f)
    return (f"<div class='presu-mini'><span>{catalogos.programas()['corta'].get(nro, nro)}</span>"
            f"<strong class='{'neg' if ev['saldo'] < 0 else ''}'>{ars(ev['saldo'], 0)}</strong>"
            f"{barra_html(ev, chico=True)}</div>")
