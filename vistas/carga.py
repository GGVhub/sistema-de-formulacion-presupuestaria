"""Vista Carga: formulario para agregar registros."""
from __future__ import annotations

import streamlit as st

import catalogos
import componentes as ui
import datos
import estado
from nucleo import DEFAULTS_CARGA, PRIORIDADES, UNIDADES, ars, evaluar, fecha_txt, md


def cb_agregar() -> None:
    s = st.session_state
    faltan = [nombre for nombre, ok in (
        ("Programa", s.f_jur), ("Prioridad", s.f_prioridad), ("Partida", s.f_partida), ("Ítem", s.f_item),
        ("Cant. requerida", s.f_cant > 0), ("Cant. mínima", s.f_cant_min > 0), ("Unidad", s.f_unidad),
        ("Precio unitario", s.f_precio > 0), ("Justificación", s.f_just.strip()),
    ) if not ok]
    if faltan:
        s._aviso = ("error", "Todos los campos son obligatorios. Falta completar: " + ", ".join(faltan) + ".")
        return
    if s.f_cant_min > s.f_cant:
        s._aviso = ("error", "La cantidad mínima no puede superar a la cantidad requerida.")
        return

    registro = {  # partida, ítem y clasificador los completa la base a partir del código
        "nro_programa": s.f_jur,
        "codigo": int(s.f_item),
        "cantidad": int(s.f_cant),
        "cantidad_minima": int(s.f_cant_min),
        "unidad": s.f_unidad,
        "precio_unitario": float(s.f_precio),
        "prioridad": s.f_prioridad,
        "justificacion": s.f_just.strip(),
    }
    try:
        datos.agregar_registro(estado.token(), registro)
    except datos.ErrorAuth as e:
        estado.manejar_error(e)
        return
    nombre = catalogos.plan()["denom"].get(s.f_item, s.f_item)
    estado.recargar_registros()
    estado.avisar(f"Guardado: {nombre}")
    # Limpia ítem y cantidades pero conserva programa y partida (se cargan varios ítems seguidos)
    for k, v in DEFAULTS_CARGA.items():
        s[k] = v


def _aviso_presupuesto(ev: dict, f_prog: dict | None, preview: float) -> None:
    if preview and ev["estado"] == "requiere_baja":
        st.error(md(f"⛔ **Este ítem supera el presupuesto del programa** (saldo disponible {ars(ev['disp'], 0)}). "
                    f"Solo se puede cargar con prioridad **Baja**, hasta {ars(ev['disp_baja'], 0)} (margen del 10 %)."))
    elif preview and ev["estado"] == "excede":
        st.error(md(f"⛔ **Supera el margen del 10 %.** Para prioridad Baja quedan {ars(ev['disp_baja'], 0)}. "
                    "Reducí la cantidad o el precio."))
    elif preview and ev["estado"] == "baja_ok":
        st.warning(md("🟠 **Supera el presupuesto del programa.** Se permite por ser prioridad Baja: "
                      f"después de este ítem quedan {ars(ev['lim'] - ev['total'], 0)} del margen del 10 %."))
    elif not preview and evaluar(f_prog)["estado"] in ("excedido", "excede"):
        disp = evaluar(f_prog)["disp_baja"]
        if disp < 1:
            st.error("⛔ **Este programa llegó al límite** (presupuesto + 10 %). No se pueden cargar más ítems; "
                     "para liberar saldo, reducí o borrá registros existentes.")
        else:
            st.warning(md("🟠 **El presupuesto de este programa ya está agotado.** Solo se pueden cargar ítems "
                          f"de prioridad **Baja**, hasta {ars(disp, 0)}."))


def _aviso_duplicados(nro: str | None, item: int | None) -> None:
    """Avisa (sin bloquear) si el mismo ítem ya está cargado en el programa, por quien sea."""
    if not nro or item is None:
        return
    dups = estado.duplicados(nro, item)
    if not dups:
        return
    yo = estado.usuario()["usuario"]
    lineas = [
        f"- **{'vos' if d['cargado_por'] == yo else d['nombre_apellido']}** · {d['cantidad']} "
        f"{(d.get('unidad') or '').lower()} · {ars(float(d['monto']), 0)} · prioridad {d['prioridad']} "
        f"· {fecha_txt(d['creado_en'], con_hora=False)}"
        for d in dups[:5]
    ]
    if len(dups) > 5:
        lineas.append(f"- …y {len(dups) - 5} más")
    st.warning(md(f"⚠️ **Este ítem ya está cargado en el programa** ({len(dups)} registro"
                  f"{'s' if len(dups) > 1 else ''}). Revisá que no sea un duplicado; si corresponde, "
                  "podés cargarlo igual.\n" + "\n".join(lineas)))


def mostrar() -> None:
    s = st.session_state
    plan = catalogos.plan()
    progs = catalogos.programas()
    propios = estado.mis_programas()
    presu = estado.presupuesto()
    abierta = estado.carga()["abierta"]

    col_form, col_lado = st.columns([5, 2], gap="large")

    with col_form:
        # Fila 1: programa + prioridad
        a, b = st.columns([3, 1.3], gap="medium")
        a.selectbox("Programa", propios, key="f_jur", format_func=progs["etiqueta"].get,
                    index=None, placeholder="Elegí el programa…", disabled=len(propios) == 1,
                    help=None if len(propios) > 1 else "Es el único programa que tenés asignado.")
        b.segmented_control("Prioridad", PRIORIDADES, key="f_prioridad", width="stretch")

        # Fila 2: Partida (nivel 2) → Ítem (nivel 3) → Clasificador (nivel 1, automático)
        a, b, c = st.columns([1.6, 1.6, 1], gap="medium")
        a.selectbox("Partida", plan["partidas"], key="f_partida", format_func=plan["etq_partida"].get,
                    index=None, placeholder="Buscar partida (ej: combustibles, útiles…)")
        partida = s.f_partida
        opciones = plan["items_de"].get(partida, [])
        if s.f_item not in opciones:  # cambió la partida
            s.f_item = opciones[0] if len(opciones) == 1 else None
        b.selectbox(f"Ítem del catálogo{f' ({len(opciones)})' if len(opciones) > 1 else ''}", opciones,
                    key="f_item", format_func=plan["etq_item"].get, index=None,
                    placeholder="Elegí primero la partida" if not partida else "Elegí el ítem…",
                    disabled=not partida or len(opciones) == 1)
        c.text_input("Clasificador", value=plan["clasificador"].get(partida, ""), disabled=True,
                     placeholder="Según la partida")

        item = s.f_item
        if item:
            st.markdown(f"<div class='chips'><span class='chip'>Objeto del gasto <b>{item}</b></span></div>",
                        unsafe_allow_html=True)
        _aviso_duplicados(s.f_jur, item)

        # Fila 3: cantidades, unidad y precio
        a, b, c, d = st.columns([1, 1, 1, 1.4], gap="medium")
        a.number_input("Cant. requerida", min_value=0, step=1, key="f_cant")
        b.number_input("Cant. mínima", min_value=0, step=1, key="f_cant_min",
                       help="Lo mínimo indispensable si hay recorte presupuestario.")
        c.selectbox("Unidad", UNIDADES, key="f_unidad")
        d.number_input("Precio unitario ($)", min_value=0.0, step=100.0, format="%.2f", key="f_precio")

        st.text_area("Justificación", key="f_just", height=68, placeholder="¿Para qué se necesita?")

        # Totales + control de presupuesto + botón
        monto = s.f_cant * s.f_precio
        monto_min = s.f_cant_min * s.f_precio
        prioridad = s.f_prioridad or "Alta"
        f_prog = presu.get(s.f_jur)
        hay_item = item is not None and monto > 0
        preview, preview_min = (monto, monto_min) if hay_item else (0.0, 0.0)
        ev = evaluar(f_prog, preview, prioridad, preview_min)
        bloqueado = ev["estado"] in ("requiere_baja", "excede")
        if abierta:
            _aviso_presupuesto(ev, f_prog, preview)

        a, b = st.columns([3, 1.2], vertical_alignment="center")
        a.markdown(ui.totales(("Monto", ars(monto)), ("Monto mínimo", ars(monto_min))), unsafe_allow_html=True)
        b.button("➕ Agregar", type="primary", on_click=cb_agregar, width="stretch",
                 disabled=bloqueado or not abierta,
                 help="La carga está cerrada" if not abierta
                 else ("Supera el presupuesto disponible" if bloqueado else None))
        st.caption("Todos los campos son obligatorios.")

    # Panel lateral: presupuesto + lo cargado
    with col_lado:
        ui.titulo("Presupuesto")
        if s.f_jur:
            st.markdown(ui.medidor(s.f_jur, f_prog, preview, prioridad, preview_min), unsafe_allow_html=True)
        if len(propios) > 1:
            con = [n for n in propios if evaluar(presu.get(n))["estado"] != "sin"]
            sin = [n for n in propios if n not in con]
            with st.expander(f"Saldo de mis {len(propios)} programas", expanded=not s.f_jur):
                st.markdown("".join(ui.medidor_mini(n, presu.get(n)) for n in con), unsafe_allow_html=True)
                if sin:
                    st.caption("Sin presupuesto cargado: " + ", ".join(sin))

        df = estado.df_registros()
        ui.titulo("Registros cargados (todos)" if estado.es_admin() else "Mis registros")
        st.markdown(ui.totales(("Ítems", str(len(df))), ("Total", ars(df["monto"].sum(), 0))),
                    unsafe_allow_html=True)
        if df.empty:
            st.caption("Todavía no agregaste ítems. Los que cargues aparecen acá.")
        else:
            ult = df.head(8)[["prioridad", "item", "monto"]]
            ult["prioridad"] = ult["prioridad"].map({"Alta": "▲", "Media": "■", "Baja": "▼"})
            st.dataframe(
                ult, hide_index=True, width="stretch", height=min(35 * len(ult) + 38, 320),
                column_config={
                    "prioridad": st.column_config.TextColumn("", width=28, help="▲ Alta · ■ Media · ▼ Baja"),
                    "item": st.column_config.TextColumn("Ítem"),
                    "monto": st.column_config.NumberColumn("Monto", format="localized", width=110),
                },
            )
            if len(df) > 8:
                st.caption(f"…y {len(df) - 8} más en **Registros**.")
