"""Vista Resumen: presupuesto por programa (con escenario mínimo) y resumen de los registros propios."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

import catalogos
import componentes as ui
import estado
from nucleo import COLOR_PRIORIDAD, ESTADOS, ICONO_ESTADO, PRIORIDADES, ars, evaluar, md


def _barras(data: pd.DataFrame, y: str, color: str | None, alto: int):
    fig = px.bar(
        data, x="monto", y=y, color=color, orientation="h",
        color_discrete_map=COLOR_PRIORIDAD if color else None,
        color_discrete_sequence=None if color else ["#2a78d6"],
        category_orders={"prioridad": PRIORIDADES},
        custom_data=["monto_fmt"] + ([color] if color else []),
    )
    fig.update_traces(
        marker_line_width=2, marker_line_color="rgba(0,0,0,0)",
        hovertemplate="<b>%{y}</b><br>" + ("%{customdata[1]}: " if color else "") + "%{customdata[0]}<extra></extra>",
    )
    fig.update_layout(
        height=alto, margin=dict(l=0, r=10, t=10, b=0), bargap=0.35,
        xaxis_title=None, yaxis_title=None, legend_title_text=None,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        yaxis=dict(categoryorder="total ascending"),
        xaxis=dict(gridcolor="rgba(128,128,128,.15)", tickformat="~s", tickprefix="$ "),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(size=12),
    )
    return fig


def _tabla_presupuesto() -> pd.DataFrame:
    presu = estado.presupuesto()
    corta = catalogos.programas()["corta"]
    filas = []
    for nro in estado.mis_programas():
        f = presu.get(nro)
        ev = evaluar(f)
        P = ev.get("P")
        filas.append({
            "nro": nro, "Programa": corta.get(nro, nro), "Presupuesto": P,
            "Presupuesto utilizado": float(f["comprometido"]) if f else 0.0,
            "Saldo": ev.get("saldo"),
            "Escenario mínimo": ev.get("minimo", float(f.get("minimo") or 0) if f else 0.0),
            "Saldo con mínimo": ev.get("saldo_min"),
            "pct": (ev["total"] / P * 100) if P else None,
            "pct_min": (ev["minimo"] / P * 100) if P else None,
            "estado": ev["estado"],
        })
    return pd.DataFrame(filas)


def _grafico_presupuesto(g: pd.DataFrame):
    """% del presupuesto utilizado por programa; el rombo marca el escenario mínimo."""
    g = g.copy()
    g["texto"] = [f"{v:.0f} % · saldo {ars(sd, 0)}" for v, sd in zip(g["pct"], g["Saldo"])]
    fig = px.bar(g, x="pct", y="Programa", orientation="h", text="texto")
    fig.update_traces(
        marker_color=g["estado"].map(lambda e: ESTADOS[e][0]), marker_line_width=0,
        textposition="outside", cliponaxis=False, showlegend=False,
        customdata=list(zip(g["Presupuesto"].map(ars), g["Presupuesto utilizado"].map(ars),
                            g["Saldo"].map(ars), g["estado"].map(lambda e: ESTADOS[e][1]))),
        hovertemplate="<b>%{y}</b><br>Usado: %{x:.1f} %<br>Presupuesto: %{customdata[0]}"
                      "<br>Presupuesto utilizado: %{customdata[1]}<br>Saldo: %{customdata[2]}"
                      "<br>%{customdata[3]}<extra></extra>",
    )
    fig.add_scatter(
        x=g["pct_min"], y=g["Programa"], mode="markers", name="Escenario mínimo",
        marker=dict(symbol="diamond", size=11, color="#0b0b0b", line=dict(width=2, color="#fcfcfb")),
        customdata=list(zip(g["Escenario mínimo"].map(ars), g["Saldo con mínimo"].map(ars))),
        hovertemplate="<b>%{y}</b><br>Escenario mínimo: %{customdata[0]} (%{x:.1f} %)"
                      "<br>Saldo con mínimo: %{customdata[1]}<extra></extra>",
    )
    for x, dash in ((100, "solid"), (110, "dash")):
        fig.add_vline(x=x, line_width=1.5, line_dash=dash, line_color="#52514e" if x == 100 else "#d03b3b")
    fig.update_layout(
        height=90 + 30 * len(g), margin=dict(l=0, r=10, t=30, b=0), bargap=0.4,
        xaxis=dict(range=[0, max(150, float(g[["pct", "pct_min"]].max().max()) + 45)], ticksuffix=" %",
                   gridcolor="rgba(128,128,128,.15)", title=None),
        yaxis=dict(autorange="reversed", title=None),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, title=None),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(size=12),
    )
    return fig


def seccion_presupuesto() -> None:
    """Saldo de cada programa del usuario: indicadores, gráfico (% usado), escenario mínimo y tabla."""
    t = _tabla_presupuesto()
    ui.titulo("Presupuesto de mis programas", "incluye lo cargado por todos los usuarios de cada programa")
    con = t[t["Presupuesto"].notna()] if not t.empty else t
    if con.empty:
        st.info("Todavía no hay presupuesto cargado para tus programas, así que no hay control de saldo.")
        return

    P, C, M = con["Presupuesto"].sum(), con["Presupuesto utilizado"].sum(), con["Escenario mínimo"].sum()
    st.markdown(ui.kpis(
        ("Presupuesto", ars(P, 0)),
        ("Presupuesto utilizado", ars(C, 0), f"{C / P:.0%} del presupuesto" if P else ""),
        ("Saldo", f"<span class='{'neg' if P - C < 0 else ''}'>{ars(P - C, 0)}</span>"),
        ("Escenario mínimo", ars(M, 0),
         (f"quedarían {ars(P - M, 0)}" if P - M >= 0 else f"<span class='neg'>faltarían {ars(M - P, 0)}</span>")),
    ), unsafe_allow_html=True)

    st.divider()
    
    st.plotly_chart(_grafico_presupuesto(con), width="stretch", config={"displayModeBar": False})
    st.caption("│ línea gris: presupuesto (100 %) · ┆ línea roja punteada: límite +10 %, solo prioridad Baja · "
               "◆ escenario mínimo (suma de los montos mínimos) · 🟢 con saldo · 🟡 por agotarse · 🟠 excedido")

    st.divider()
    # Programas donde lo requerido no entra: ¿entra al menos el mínimo?
    pasados = con[con["Presupuesto utilizado"] > con["Presupuesto"]]
    for r in pasados.to_dict("records"):
        minimo, saldo_min = r["Escenario mínimo"], r["Saldo con mínimo"]
        if saldo_min >= 0:
            st.info(md(f"**{r['Programa']}**: lo requerido supera el presupuesto, pero el **escenario mínimo "
                       f"entra** ({ars(minimo, 0)}; quedarían {ars(saldo_min, 0)})."))
        else:
            st.warning(md(f"**{r['Programa']}**: ni el escenario mínimo entra en el presupuesto "
                          f"({ars(minimo, 0)}; faltarían {ars(-saldo_min, 0)})."))

    tabla = con.assign(Estado=con["estado"].map(lambda e: f"{ICONO_ESTADO.get(e, '')} {ESTADOS[e][1]}"))
    num = st.column_config.NumberColumn(format="localized")
    st.dataframe(
        tabla[["Programa", "Presupuesto", "Presupuesto utilizado", "Saldo", "pct",
               "Escenario mínimo", "Saldo con mínimo", "Estado"]].rename(columns={"pct": "% usado"}),
        hide_index=True, width="stretch", height=min(38 + 35 * len(tabla), 420),
        column_config={
            "Programa": st.column_config.TextColumn(width="medium"),
            "Presupuesto": num, "Presupuesto utilizado": num, "Saldo": num,
            "Escenario mínimo": num, "Saldo con mínimo": num,
            "% usado": st.column_config.ProgressColumn(min_value=0, max_value=110, format="%.0f %%"),
            "Estado": st.column_config.TextColumn(width="medium"),
        },
    )
    sin = t[t["Presupuesto"].isna()]["nro"].tolist()
    if sin:
        st.caption("Sin presupuesto cargado (sin control de saldo): " + ", ".join(sin))


def mostrar() -> None:
    seccion_presupuesto()
    st.divider()
    df = estado.df_registros()
    ui.titulo("Registros cargados (todos)" if estado.es_admin() else "Mis registros")
    if df.empty:
        st.info("Cargá algunos ítems para ver el resumen.")
        return

    total = df["monto"].sum()
    alta = df.loc[df["prioridad"] == "Alta", "monto"].sum()
    st.markdown(ui.kpis(
        ("Monto total", ars(total, 0)),
        ("Monto mínimo", ars(df["monto_minimo"].sum(), 0)),
        ("Prioridad alta", f"{alta / total:.0%}" if total else "—"),
        ("Ítems · programas", f"{len(df)} · {df['prog'].nunique()}"),
    ), unsafe_allow_html=True)

    st.write("")
    st.divider()
    izq, der = st.columns(2, gap="large")
    with izq:
        ui.titulo("Monto por programa y prioridad")
        g = df.groupby(["prog", "prioridad"], as_index=False)["monto"].sum()
        g["monto_fmt"] = g["monto"].map(ars)
        st.plotly_chart(_barras(g, "prog", "prioridad", 80 + 34 * g["prog"].nunique()),
                        width="stretch", config={"displayModeBar": False})
    with der:
        ui.titulo("Top 10 partidas por monto")
        g = (df.assign(partida=df["partida"].replace("", "Sin partida"))
               .groupby("partida", as_index=False)["monto"].sum().nlargest(10, "monto"))
        g["monto_fmt"] = g["monto"].map(ars)
        st.plotly_chart(_barras(g, "partida", None, 60 + 34 * len(g)),
                        width="stretch", config={"displayModeBar": False})

    with st.expander("Ver tabla por programa"):
        t = (df.pivot_table(index="prog", columns="prioridad", values="monto", aggfunc="sum", fill_value=0)
               .reindex(columns=PRIORIDADES, fill_value=0))
        t["Total"] = t.sum(axis=1)
        t["Monto mínimo"] = df.groupby("prog")["monto_minimo"].sum()
        st.dataframe(t.sort_values("Total", ascending=False), width="stretch",
                     column_config={c: st.column_config.NumberColumn(format="localized") for c in t.columns})
