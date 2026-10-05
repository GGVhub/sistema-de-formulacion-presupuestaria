"""
Pantallas de ingreso y cambio de contraseña.

Uso en app.py:
    usuario = auth.requerir_login()   # corta la ejecución si no hay sesión válida
    auth.menu_usuario()               # botón con nombre, cambiar contraseña y salir
"""
from __future__ import annotations

import streamlit as st

import datos


def _encabezado(titulo: str, sub: str) -> None:
    st.markdown(
        f"<div style='margin:6vh 0 1rem'><div style='font-size:1.45rem;font-weight:700'>{titulo}</div>"
        f"<div style='font-size:.85rem;opacity:.75'>{sub}</div></div>",
        unsafe_allow_html=True,
    )


def _salir() -> None:
    token = (st.session_state.get("usuario") or {}).get("token")
    if token:
        datos.logout(token)
    st.session_state.clear()


# --------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------
def _pantalla_login() -> None:
    _, centro, _ = st.columns([1, 1.1, 1])
    with centro:
        _encabezado("Formulación Presupuestaria", "Ministerio de Ambiente y Economía Circular")
        aviso = st.session_state.pop("_aviso", None)
        if aviso and aviso[0] == "error":
            st.warning(aviso[1])
        with st.form("login", border=True):
            usuario = st.text_input("Usuario", placeholder="nombre.apellido", autocomplete="username")
            password = st.text_input("Contraseña", type="password", autocomplete="current-password")
            enviar = st.form_submit_button("Ingresar", type="primary", width="stretch")
        if enviar:
            if not usuario or not password:
                st.error("Completá usuario y contraseña.")
                return
            try:
                u = datos.login(usuario, password)
            except datos.ErrorAuth as e:
                st.error(str(e))
                return
            if u is None:
                st.error("Usuario o contraseña incorrectos.")
                return
            st.session_state.usuario = u
            st.rerun()
        st.caption("¿Olvidaste tu contraseña? Pedile al administrador que la restablezca.")


# --------------------------------------------------------------------------
# Cambio de contraseña (obligatorio en el primer ingreso, o desde el menú)
# --------------------------------------------------------------------------
def _form_cambio(obligatorio: bool) -> None:
    u = st.session_state.usuario
    with st.form("cambio_password", border=not obligatorio):
        actual = st.text_input("Contraseña actual" + (" (cambiar123)" if obligatorio else ""),
                               type="password", autocomplete="current-password")
        nueva = st.text_input("Nueva contraseña", type="password", autocomplete="new-password",
                              help="Mínimo 4 caracteres.")
        repetir = st.text_input("Repetir nueva contraseña", type="password", autocomplete="new-password")
        ok = st.form_submit_button("Guardar contraseña", type="primary", width="stretch")
    if ok:
        if nueva != repetir:
            st.error("Las contraseñas nuevas no coinciden.")
            return
        try:
            datos.cambiar_password(u["usuario"], actual, nueva)
        except datos.ErrorAuth as e:
            st.error(str(e))
            return
        u["debe_cambiar_password"] = False
        st.session_state._aviso = ("ok", "Contraseña actualizada.")
        st.rerun()


def _pantalla_cambio_obligatorio() -> None:
    u = st.session_state.usuario
    _, centro, _ = st.columns([1, 1.1, 1])
    with centro:
        _encabezado(f"Hola, {u['nombre_apellido'].split()[0]}",
                    "Es tu primer ingreso: elegí una contraseña nueva para continuar.")
        with st.container(border=True):
            _form_cambio(obligatorio=True)
        st.button("Salir", on_click=_salir, type="tertiary")


@st.dialog("Cambiar contraseña")
def _dialogo_cambio() -> None:
    _form_cambio(obligatorio=False)


# --------------------------------------------------------------------------
# API pública
# --------------------------------------------------------------------------
def requerir_login() -> dict:
    """Devuelve el usuario logueado; si no hay sesión (o debe cambiar la clave) muestra la pantalla y corta."""
    u = st.session_state.get("usuario")
    if u is not None and not u.get("token"):  # sesión iniciada con una versión anterior de la app
        st.session_state.clear()
        u = None
    if u is None:
        _pantalla_login()
        st.stop()
    if u.get("debe_cambiar_password"):
        _pantalla_cambio_obligatorio()
        st.stop()
    return u


def menu_usuario() -> None:
    u = st.session_state.usuario
    with st.popover(f"👤 {u['nombre_apellido'].split()[0]}", width="stretch"):
        st.markdown(f"**{u['nombre_apellido']}**  \n`{u['usuario']}`")
        if u.get("secretaria"):
            st.caption(u["secretaria"].title())
        if u.get("rol") == "admin":
            st.caption("Rol: administrador")
        if st.button("🔑 Cambiar contraseña", width="stretch"):
            _dialogo_cambio()
        st.button("↪ Cerrar sesión", on_click=_salir, width="stretch")
