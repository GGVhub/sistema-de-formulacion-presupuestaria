"""
Refresca en Supabase las tablas que salen de Excel: plan_cuentas y programas.

No hace falta para instalar: plan_cuentas.sql y programas.sql ya traen los datos.
Sirve solo si cambia alguno de los Excel de ./data y querés volver a subirlo.
(Los presupuestos y los programas también se pueden editar desde el panel Admin de la app.)

Uso (desde la carpeta del proyecto):
    python supabase/cargar_excel.py                # las dos tablas
    python supabase/cargar_excel.py plan_cuentas   # solo una

La URL se toma de .streamlit/secrets.toml. La clave SECRET (service_role) se pide por
consola sin mostrarse — no la guardes en archivos. También se pueden usar las variables
de entorno SUPABASE_URL y SUPABASE_SERVICE_KEY.

Actualiza por clave (código / número de programa): no duplica filas.
Ojo: al subir "programas" se pisa el presupuesto con el del Excel si la columna trae valor.
"""
import getpass
import os
import sys
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd
from supabase import create_client

DATA = Path(__file__).resolve().parent.parent / "data"


def programas() -> pd.DataFrame:
    df = pd.read_excel(DATA / "programas.xlsx")
    df = df.rename(columns={"NRO_PROGRAMA": "nro_programa", "PROGRAMA": "programa",
                            "PRESUPUESTO": "presupuesto"})
    df["nro_programa"] = df["nro_programa"].astype(str).str.strip()
    df["programa"] = df["programa"].astype(str).str.strip()
    df["orden"] = range(1, len(df) + 1)
    return df[["nro_programa", "programa", "presupuesto", "orden"]]


def plan_cuentas() -> pd.DataFrame:
    df = pd.read_excel(DATA / "Plan_de_cuentas_objeto_del_gasto.xlsx").rename(columns={
        "Código": "codigo", "Denominación": "denominacion", "Nivel": "nivel",
        "Código superior": "codigo_superior", "Agrupación principal": "agrupacion",
        "Página fuente": "pagina_fuente", "Observaciones": "observaciones"})
    df["codigo_superior"] = df["codigo_superior"].astype("Int64")
    df["denominacion"] = df["denominacion"].astype(str).str.strip()
    return df.sort_values("nivel")  # padres antes que hijos


TABLAS = {"plan_cuentas": plan_cuentas, "programas": programas}
CLAVE_UPSERT = {"programas": "nro_programa", "plan_cuentas": "codigo"}  # se actualiza en lugar de duplicar


def subir(cliente, tabla: str, df: pd.DataFrame, lote: int = 500) -> None:
    df = df.astype(object).replace({np.nan: None, pd.NA: None, pd.NaT: None})
    filas = df.to_dict("records")
    for i in range(0, len(filas), lote):
        q = cliente.table(tabla)
        q = q.upsert(filas[i:i + lote], on_conflict=CLAVE_UPSERT[tabla]) if tabla in CLAVE_UPSERT \
            else q.insert(filas[i:i + lote])
        q.execute()
        print(f"  {tabla}: {min(i + lote, len(filas)):,}/{len(filas):,}", end="\r")
    print(f"  {tabla}: {len(filas):,} filas OK          ")


def credenciales() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL")
    if not url:
        secrets = DATA.parent / ".streamlit" / "secrets.toml"
        try:
            url = tomllib.loads(secrets.read_text(encoding="utf-8"))["supabase"]["url"]
        except (FileNotFoundError, KeyError):
            url = input("URL del proyecto (https://xxxx.supabase.co): ").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY") or getpass.getpass(
        "Clave SECRET / service_role (no se muestra al escribir): ").strip()
    if key.startswith("sb_publishable") or '"role":"anon"' in key:
        sys.exit("Esa es la clave pública (publishable/anon): solo puede leer. "
                 "Usá la SECRET / service_role de Project Settings > API Keys.")
    return url, key


if __name__ == "__main__":
    url, key = credenciales()
    print(f"Conectando a {url} …")
    cliente = create_client(url, key)
    for nombre in sys.argv[1:] or TABLAS:
        subir(cliente, nombre, TABLAS[nombre]())
