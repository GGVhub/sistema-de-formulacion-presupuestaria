"""Vista Admin: fecha límite, presupuestos, usuarios e historial. Solo para el rol admin."""
from __future__ import annotations

from datetime import datetime, time as hora_t, timedelta

import pandas as pd
import streamlit as st

import catalogos
import componentes as ui
import datos
import estado
import exportar
from nucleo import ZONA, ars, fecha_txt

NUEVO = "➕ Nuevo usuario"
HORAS = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]  # opciones para la hora límite
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# --------------------------------------------------------------------------
# Datos del panel: se piden una vez y se vuelven a pedir después de cada cambio
# --------------------------------------------------------------------------
def _leer(clave: str, funcion, *args) -> list[dict]:
    s = st.session_state
    if f"adm_{clave}" not in s:
        try:
            s[f"adm_{clave}"] = funcion(estado.token(), *args)
        except datos.ErrorAuth as e:
            estado.manejar_error(e)
            return []
    return s[f"adm_{clave}"]


def _refrescar(*claves: str) -> None:
    for c in claves or ("programas", "usuarios", "historial"):
        st.session_state.pop(f"adm_{c}", None)


def _ejecutar(funcion, *args, ok: str) -> bool:
    """Llama a la base; deja el aviso de éxito o de error. Devuelve True si salió bien."""
    try:
        funcion(estado.token(), *args)
    except datos.ErrorAuth as e:
        estado.manejar_error(e)
        return False
    estado.avisar(ok)
    return True


# ==========================================================================
# Fecha límite
# ==========================================================================
def _cb_guardar_fecha() -> None:
    s = st.session_state
    limite = datetime.combine(s.adm_fecha, hora_t.fromisoformat(s.adm_hora), tzinfo=ZONA)
    if _ejecutar(datos.admin_fecha_limite, limite.isoformat(),
                 ok=f"Fecha límite guardada: {limite:%d/%m/%Y %H:%M} hs."):
        estado.invalidar()


def _cb_quitar_fecha() -> None:
    if _ejecutar(datos.admin_fecha_limite, None, ok="Se quitó la fecha límite: la carga queda abierta."):
        estado.invalidar()


def _tab_fecha() -> None:
    limite = estado.carga()["limite"]
    ahora = datetime.now(ZONA)
    if limite is None:
        st.info("No hay fecha límite: los usuarios pueden cargar sin restricción de tiempo.")
    elif ahora >= limite:
        st.error(f"🔒 La carga **cerró** el {limite:%d/%m/%Y} a las {limite:%H:%M} hs. Los usuarios pueden "
                 "consultar y exportar, pero no agregar, editar ni borrar. Vos, como administrador, sí.")
    else:
        st.success(f"🟢 La carga está **abierta** hasta el {limite:%d/%m/%Y} a las {limite:%H:%M} hs.")

    base = limite or (ahora + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    a, b, _ = st.columns([1, 1, 2])
    fecha = a.date_input("Fecha límite", value=base.date(), format="DD/MM/YYYY", key="adm_fecha")
    actual = f"{base:%H}:{'30' if base.minute >= 30 else '00'}"
    hora = hora_t.fromisoformat(b.selectbox("Hora", HORAS, index=HORAS.index(actual), key="adm_hora"))
    nuevo = datetime.combine(fecha, hora, tzinfo=ZONA)
    if hora == hora_t(0, 0):
        st.caption(f"Con las 00:00 del {nuevo:%d/%m}, el último día completo para cargar es el "
                   f"{nuevo - timedelta(days=1):%d/%m/%Y}.")
    if nuevo <= ahora:
        st.warning("Esa fecha ya pasó: si la guardás, la carga queda cerrada para los usuarios.")
    a, b, _ = st.columns([1, 1, 2])
    a.button("Guardar fecha límite", type="primary", on_click=_cb_guardar_fecha, width="stretch", key="adm_b_fecha")
    b.button("Quitar fecha límite", on_click=_cb_quitar_fecha, width="stretch", disabled=limite is None,
             key="adm_b_quitar_fecha")


# ==========================================================================
# Presupuestos
# ==========================================================================
def _cb_guardar_presupuestos() -> None:
    s = st.session_state
    filas = s.get("adm_programas", [])
    cambios = s.get(f"adm_prog_editor_{s.get('adm_prog_v', 0)}", {}).get("edited_rows", {})
    if not cambios:
        s._aviso = ("error", "No hay cambios para guardar.")
        return
    guardados = 0
    try:
        for i, campos in cambios.items():
            f = filas[int(i)]
            datos.admin_programa_guardar(
                estado.token(), f["nro_programa"],
                campos.get("programa", f["programa"]),
                campos["presupuesto"] if "presupuesto" in campos else f["presupuesto"])
            guardados += 1
    except datos.ErrorAuth as e:
        estado.manejar_error(e)
    else:
        estado.avisar(f"Se guardaron {guardados} programa{'s' if guardados != 1 else ''}.")
    _despues_de_programas()


def _cb_agregar_programa() -> None:
    s = st.session_state
    if _ejecutar(datos.admin_programa_guardar, s.adm_np_nro, s.adm_np_nombre, s.adm_np_presu,
                 ok=f"Programa {s.adm_np_nro.strip()} creado."):
        s.adm_np_nro, s.adm_np_nombre, s.adm_np_presu = "", "", None
    _despues_de_programas()


def _despues_de_programas() -> None:
    _refrescar("programas")
    catalogos.refrescar_programas()
    estado.invalidar()
    st.session_state.adm_prog_v = st.session_state.get("adm_prog_v", 0) + 1


def _tab_presupuestos() -> None:
    filas = _leer("programas", datos.admin_programas)
    if not filas:
        st.info("No hay programas cargados.")
    else:
        df = pd.DataFrame(filas)
        for c in ("presupuesto", "utilizado", "minimo"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["saldo"] = df["presupuesto"] - df["utilizado"]
        con = df[df["presupuesto"].notna()]
        st.markdown(ui.kpis(
            ("Programas con presupuesto", f"{len(con)} de {len(df)}"),
            ("Presupuesto total", ars(con["presupuesto"].sum(), 0)),
            ("Utilizado", ars(con["utilizado"].sum(), 0)),
            ("Saldo", ars(con["saldo"].sum(), 0)),
        ), unsafe_allow_html=True)
        st.caption("Editá **Programa** y **Presupuesto** en la tabla y apretá Guardar. "
                   "Presupuesto vacío = sin control de saldo para ese programa.")
        cc = st.column_config
        st.data_editor(
            df, key=f"adm_prog_editor_{st.session_state.get('adm_prog_v', 0)}", hide_index=True,
            width="stretch", height=min(40 + 35 * len(df), 560),
            column_order=["nro_programa", "programa", "presupuesto", "utilizado", "saldo", "minimo", "registros"],
            disabled=["nro_programa", "utilizado", "saldo", "minimo", "registros"],
            column_config={
                "nro_programa": cc.TextColumn("N°", width="small"),
                "programa": cc.TextColumn("Programa", width="large", required=True),
                "presupuesto": cc.NumberColumn("Presupuesto ✏️", min_value=0, format="localized"),
                "utilizado": cc.NumberColumn("Utilizado", format="localized"),
                "saldo": cc.NumberColumn("Saldo", format="localized"),
                "minimo": cc.NumberColumn("Escenario mínimo", format="localized"),
                "registros": cc.NumberColumn("Registros", width="small"),
            },
        )
        a, _ = st.columns([1, 3])
        a.button("Guardar cambios", type="primary", on_click=_cb_guardar_presupuestos, width="stretch",
                 key="adm_b_presu")
        pasados = con[con["utilizado"] > con["presupuesto"]]
        if not pasados.empty:
            st.warning("Programas con más utilizado que presupuesto: " + ", ".join(pasados["nro_programa"]) +
                       ". Los usuarios solo van a poder cargar ítems de prioridad Baja (hasta +10 %).")

    with st.expander("➕ Agregar un programa"):
        a, b, c = st.columns([1, 3, 1.5])
        a.text_input("N° de programa", key="adm_np_nro", placeholder="ej: 562 o 558-4")
        b.text_input("Nombre", key="adm_np_nombre")
        c.number_input("Presupuesto (opcional)", min_value=0.0, step=100000.0, value=None, format="%.2f",
                       key="adm_np_presu")
        st.button("Crear programa", on_click=_cb_agregar_programa, key="adm_b_programa")


# ==========================================================================
# Usuarios
# ==========================================================================
def _cb_guardar_usuario(sel: str) -> None:
    s = st.session_state
    k = f"adm_u_{sel}_"
    usuario = (s[k + "usuario"] if sel == NUEVO else sel).strip().lower()
    datos_usuario = {
        "usuario": usuario,
        "nombre_apellido": s[k + "nombre"],
        "secretaria": s[k + "secretaria"],
        "sub_secretaria": s[k + "sub"],
        "programas": list(s[k + "programas"]),
        "rol": s[k + "rol"],
        "activo": bool(s[k + "activo"]),
    }
    if _ejecutar(datos.admin_usuario_guardar, datos_usuario,
                 ok=f"Usuario {usuario} {'creado con la contraseña cambiar123' if sel == NUEVO else 'guardado'}."):
        _refrescar("usuarios")
        if sel == NUEVO:
            s.adm_u_sel_pendiente = usuario  # queda seleccionado el recién creado


def _cb_resetear(usuario: str) -> None:
    if _ejecutar(datos.admin_usuario_resetear, usuario,
                 ok=f"Contraseña de {usuario} restablecida a cambiar123."):
        _refrescar("usuarios")


def _tab_usuarios() -> None:
    s = st.session_state
    filas = _leer("usuarios", datos.admin_usuarios)
    por_usuario = {f["usuario"]: f for f in filas}
    progs = catalogos.programas()

    df = pd.DataFrame(filas)
    if not df.empty:
        df["programas_txt"] = df["programas"].map(lambda p: ", ".join(p) if p else "Todos")
        df["estado"] = [("Inactivo" if not a else "Bloqueado" if b else "Debe cambiar clave" if d else "Activo")
                        for a, b, d in zip(df["activo"], df["bloqueado"], df["debe_cambiar_password"])]
        df["ultimo"] = df["ultimo_login"].map(fecha_txt)
        df["secretaria"] = df["secretaria"].fillna("")
        cc = st.column_config
        st.dataframe(
            df[["usuario", "nombre_apellido", "secretaria", "programas_txt", "rol", "estado", "ultimo", "registros"]],
            hide_index=True, width="stretch", height=min(40 + 35 * len(df), 330),
            column_config={
                "usuario": cc.TextColumn("Usuario"), "nombre_apellido": cc.TextColumn("Nombre y apellido"),
                "secretaria": cc.TextColumn("Secretaría", width="medium"),
                "programas_txt": cc.TextColumn("Programas", width="medium"), "rol": cc.TextColumn("Rol", width="small"),
                "estado": cc.TextColumn("Estado"), "ultimo": cc.TextColumn("Último ingreso"),
                "registros": cc.NumberColumn("Registros", width="small"),
            },
        )

    opciones = [NUEVO] + sorted(por_usuario)
    if s.get("adm_u_sel_pendiente") in opciones:   # recién creado: seleccionarlo
        s.adm_u_sel = s.pop("adm_u_sel_pendiente")
    if s.get("adm_u_sel") not in opciones:
        s.adm_u_sel = NUEVO
    sel = st.selectbox("Usuario a editar", opciones, key="adm_u_sel",
                       format_func=lambda u: u if u == NUEVO else f"{por_usuario[u]['nombre_apellido']} ({u})")
    u = por_usuario.get(sel, {})
    k = f"adm_u_{sel}_"
    es_yo = sel == estado.usuario()["usuario"]

    with st.container(border=True):
        a, b = st.columns(2)
        if sel == NUEVO:
            a.text_input("Usuario", key=k + "usuario", placeholder="nombre.apellido",
                         help="Sin espacios ni acentos. Es lo que la persona escribe para ingresar.")
        else:
            a.text_input("Usuario", value=sel, disabled=True, key=k + "usuario_fijo")
        b.text_input("Nombre y apellido", value=u.get("nombre_apellido", ""), key=k + "nombre")
        a, b = st.columns(2)
        a.text_input("Secretaría", value=u.get("secretaria") or "", key=k + "secretaria")
        b.text_input("Subsecretaría / dirección", value=u.get("sub_secretaria") or "", key=k + "sub")
        st.multiselect("Programas asignados", progs["lista"], key=k + "programas",
                       default=[p for p in (u.get("programas") or []) if p in progs["lista"]],
                       format_func=progs["corta"].get, placeholder="Sin asignar = ve todos los programas",
                       help="El usuario solo puede cargar en estos programas. Si no tiene ninguno, ve todos.")
        a, b, _ = st.columns([1, 1, 2])
        a.selectbox("Rol", ["usuario", "admin"], index=["usuario", "admin"].index(u.get("rol", "usuario")),
                    key=k + "rol", disabled=es_yo,
                    help="No podés cambiar tu propio rol." if es_yo else "El admin ve todo y accede a este panel.")
        b.toggle("Activo", value=u.get("activo", True), key=k + "activo", disabled=es_yo,
                 help="No podés desactivar tu propio usuario." if es_yo
                 else "Un usuario inactivo no puede ingresar; sus registros se conservan.")

        a, b, _ = st.columns([1, 1.3, 1.7])
        a.button("Crear usuario" if sel == NUEVO else "Guardar cambios", type="primary",
                 on_click=_cb_guardar_usuario, args=(sel,), width="stretch", key=k + "guardar")
        if sel != NUEVO:
            with b.popover("🔑 Restablecer contraseña", width="stretch"):
                st.write(f"La contraseña de **{sel}** vuelve a `cambiar123`, se desbloquea la cuenta y se le "
                         "pide cambiarla en el próximo ingreso.")
                st.button("Sí, restablecer", on_click=_cb_resetear, args=(sel,), type="primary", key=k + "reset")
        else:
            st.caption("El usuario nuevo queda con la contraseña `cambiar123` y debe cambiarla al ingresar.")


# ==========================================================================
# Historial
# ==========================================================================
def _tab_historial() -> None:
    a, b, c, d = st.columns([1, 1.5, 1.5, 1], vertical_alignment="bottom")
    limite = a.selectbox("Mostrar", [200, 500, 2000], index=1, format_func=lambda n: f"últimos {n}",
                         key="adm_h_limite", on_change=_refrescar, args=("historial",))
    filas = _leer("historial", datos.admin_historial, limite)
    df = pd.DataFrame(filas, columns=["id", "fecha", "usuario", "accion", "registro_id", "nro_programa",
                                      "item", "detalle"])
    usuarios = b.multiselect("Usuario", sorted(df["usuario"].dropna().unique()), key="adm_h_usuarios",
                             placeholder="Todos")
    acciones = c.multiselect("Acción", ["alta", "edición", "baja"], key="adm_h_acciones", placeholder="Todas")
    d.button("🔄 Actualizar", on_click=_refrescar, args=("historial",), width="stretch", key="adm_b_hist")
    if df.empty:
        st.info("Todavía no hay movimientos registrados.")
        return
    if usuarios:
        df = df[df["usuario"].isin(usuarios)]
    if acciones:
        df = df[df["accion"].isin(acciones)]
    df = df.assign(fecha=df["fecha"].map(fecha_txt))
    cc = st.column_config
    st.dataframe(
        df[["fecha", "usuario", "accion", "nro_programa", "item", "detalle", "registro_id"]],
        hide_index=True, width="stretch", height=min(40 + 35 * len(df), 520),
        column_config={
            "fecha": cc.TextColumn("Fecha"), "usuario": cc.TextColumn("Usuario"),
            "accion": cc.TextColumn("Acción", width="small"), "nro_programa": cc.TextColumn("Programa", width="small"),
            "item": cc.TextColumn("Ítem", width="medium"), "detalle": cc.TextColumn("Detalle", width="large"),
            "registro_id": cc.NumberColumn("N° registro", width="small"),
        },
    )
    a, b = st.columns([1, 3], vertical_alignment="center")
    a.download_button("⬇️ Exportar historial", exportar.tabla(df.drop(columns=["id"]), "Historial"),
                      file_name=f"historial_{datetime.now(ZONA):%Y%m%d_%H%M}.xlsx", mime=MIME_XLSX, width="stretch",
                      key="adm_b_hist_xlsx")
    b.caption(f"{len(df)} movimiento{'s' if len(df) != 1 else ''}. El usuario “sql” indica cambios hechos a mano "
              "desde el SQL Editor de Supabase. Los registros borrados se pueden recuperar desde la base.")


# ==========================================================================
def mostrar() -> None:
    if not estado.es_admin():
        st.error("Esta sección es solo para administradores.")
        return
    t_fecha, t_presu, t_usuarios, t_hist = st.tabs(
        ["📅 Fecha límite", "💰 Programas y presupuestos", "👥 Usuarios", "🕓 Historial de cambios"])
    with t_fecha:
        _tab_fecha()
    with t_presu:
        _tab_presupuestos()
    with t_usuarios:
        _tab_usuarios()
    with t_hist:
        _tab_historial()
