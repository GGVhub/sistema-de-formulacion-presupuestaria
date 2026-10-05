"""Vista Registros: tabla editable con lo cargado."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

import componentes as ui
import datos
import estado
import exportar
from nucleo import EDITABLES, PRIORIDADES, UNIDADES, ZONA, ars


def cb_editar() -> None:
    """Guarda en Supabase los cambios hechos en la tabla editable."""
    s = st.session_state
    cambios = s[f"editor_{s.editor_v}"]
    ids = [r["id"] for r in s.registros]
    token = estado.token()
    try:
        for i, campos in cambios["edited_rows"].items():
            datos.actualizar_registro(token, ids[int(i)], {k: v for k, v in campos.items() if k in EDITABLES})
        for i in cambios["deleted_rows"]:
            datos.borrar_registro(token, ids[int(i)])
        n = len(cambios["deleted_rows"])
        if n:
            estado.avisar(f"{'Borrados' if n > 1 else 'Borrado'} {n} registro{'s' if n > 1 else ''}.")
    except datos.ErrorAuth as e:
        estado.manejar_error(e)
    estado.recargar_registros()


def mostrar() -> None:
    df = estado.df_registros()
    if df.empty:
        st.info("No hay registros cargados todavía.")
        return
    abierta = estado.carga()["abierta"]

    a, b, c = st.columns([4, 1.2, 1], vertical_alignment="center")
    if abierta:
        a.caption("Los cambios se guardan al instante. Podés editar cantidades, precio, unidad, prioridad y "
                  "justificación en la tabla. Para borrar: seleccioná la fila a la izquierda y apretá 🗑.")
    else:
        a.caption("🔒 La carga está cerrada: los registros se pueden consultar y exportar, pero no modificar.")
    b.download_button("⬇️ Exportar Excel", exportar.registros(df),
                      file_name=f"formulacion_{datetime.now(ZONA):%Y%m%d_%H%M}.xlsx",
                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                      width="stretch")
    c.button("🔄 Actualizar", on_click=estado.recargar_registros, width="stretch",
             help="Vuelve a leer los registros desde la base")

    cc = st.column_config
    fijas = ["prog", "partida", "item", "clasificador", "objeto_gasto", "monto", "monto_minimo",
             "creado_en", "cargado_por"]
    st.data_editor(
        df, key=f"editor_{st.session_state.editor_v}", on_change=cb_editar, hide_index=True,
        num_rows="delete" if abierta else "fixed",
        disabled=fijas if abierta else True,
        width="stretch", height=min(35 * len(df) + 40, 560),
        column_order=["prog", "partida", "item", "clasificador", "objeto_gasto", "cantidad", "cantidad_minima",
                      "unidad", "precio_unitario", "monto", "monto_minimo", "prioridad",
                      "justificacion", "creado_en"] + (["cargado_por"] if estado.es_admin() else []),
        column_config={
            "prog": cc.TextColumn("Programa", width="small"),
            "partida": cc.TextColumn("Partida", width="medium"),
            "item": cc.TextColumn("Ítem", width="medium"),
            "clasificador": cc.TextColumn("Clasificador", width="medium"),
            "objeto_gasto": cc.NumberColumn("Obj. gasto", format="%d"),
            "cantidad": cc.NumberColumn("Cant.", min_value=1, step=1, required=True),
            "cantidad_minima": cc.NumberColumn("Cant. mín.", min_value=1, step=1, required=True),
            "unidad": cc.SelectboxColumn("Unidad", options=UNIDADES, required=True),
            "precio_unitario": cc.NumberColumn("Precio unit.", min_value=0, format="localized", required=True),
            "monto": cc.NumberColumn("Monto", format="localized"),
            "monto_minimo": cc.NumberColumn("Monto mín.", format="localized"),
            "prioridad": cc.SelectboxColumn("Prioridad", options=PRIORIDADES, required=True),
            "justificacion": cc.TextColumn("Justificación", width="small", required=True),
            "creado_en": cc.TextColumn("Cargado", width="small"),
            "cargado_por": cc.TextColumn("Usuario", width="small"),
        },
    )
    st.markdown(ui.totales(("Registros", str(len(df))), ("Monto total", ars(df["monto"].sum())),
                           ("Monto mínimo total", ars(df["monto_minimo"].sum()))), unsafe_allow_html=True)
