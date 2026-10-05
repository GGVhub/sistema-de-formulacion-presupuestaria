# Formulación Presupuestaria — Ministerio de Ambiente y Economía Circular

App en Streamlit + Supabase para cargar la formulación presupuestaria por programa.

## Estructura

```
app.py                 entrada: login, encabezado, navegación, aviso de fecha límite
auth.py                pantallas de ingreso y cambio de contraseña
datos.py               única puerta a Supabase (lecturas y llamadas a funciones)
estilos.py             CSS
nucleo.py              constantes, formato de moneda/fechas y la regla de presupuesto
catalogos.py           plan de cuentas y programas (compartidos entre usuarios)
estado.py              lo propio de cada sesión: usuario, registros, presupuesto, fecha límite
componentes.py         tarjetas, medidores e indicadores
exportar.py            Excel con formato
vistas/carga.py        formulario de carga
vistas/registros.py    tabla editable
vistas/resumen.py      presupuesto por programa y resumen
vistas/admin.py        panel de administración (solo rol admin)

supabase/usuarios.sql      usuarios, sesiones, login (bcrypt en Postgres)
supabase/programas.sql     programas presupuestarios (con datos)
supabase/plan_cuentas.sql  plan de cuentas del objeto del gasto (con datos)
supabase/formulacion.sql   registros, reglas de presupuesto, fecha límite, duplicados
supabase/admin.sql         historial de cambios + funciones del panel de administración
supabase/limpieza.sql      borra las tablas que ya no se usan (una sola vez)
supabase/cargar_excel.py   opcional: refresca plan de cuentas / programas desde Excel
```

## Instalación

**Supabase › SQL Editor**, en este orden (todos se pueden volver a ejecutar sin perder datos):

1. `usuarios.sql`
2. `programas.sql`
3. `plan_cuentas.sql`
4. `formulacion.sql`
5. `admin.sql`
6. `limpieza.sql` (una vez: borra `catalogo`, `devengado` y `jurisdicciones`)

**App:**

```bash
pip install -r requirements.txt
# .streamlit/secrets.toml con [supabase] url y key (la clave pública / anon)
streamlit run app.py
```

El primer administrador se crea a mano una sola vez:

```sql
insert into usuarios (usuario, nombre_apellido, rol) values ('admin', 'Administrador', 'admin');
-- queda con la contraseña cambiar123 y debe cambiarla al ingresar
```

El resto de los usuarios, programas y presupuestos se administran desde la app.

## Qué hace cada vista

- **Carga**: Programa (solo los asignados al usuario) y Prioridad; **Partida** (nivel 2 del plan de
  cuentas) → **Ítem** (nivel 3, o la misma partida si no tiene ítems) → **Clasificador** (nivel 1,
  automático). Todos los campos son obligatorios. Avisa si el ítem **ya está cargado** en el programa
  (por cualquier usuario) y muestra el saldo del presupuesto con el ítem que se está cargando.
- **Registros**: tabla editable (cantidades, precio, unidad, prioridad, justificación), borrado de
  filas y exportación a Excel. Cada usuario ve lo suyo; el admin ve todo.
- **Resumen**: presupuesto, utilizado y saldo por programa, con el **escenario mínimo** (suma de los
  montos mínimos) y si entra o no en el presupuesto; montos por prioridad y por partida.
- **Admin** (solo rol admin): fecha límite · programas y presupuestos · usuarios · historial de cambios.

## Reglas (las aplica la base, no solo la app)

**Presupuesto.** Cada registro descuenta su monto (cantidad requerida × precio) del presupuesto de su
programa, contando lo cargado por todos los usuarios:

- hasta el presupuesto → cualquier prioridad;
- por encima → solo prioridad **Baja**, y hasta un **10 %** extra (`_margen_baja()` en `formulacion.sql`);
- programa sin presupuesto cargado → sin control.

**Fecha límite.** Pasada la fecha, los usuarios no pueden agregar, editar ni borrar (sí consultar y
exportar). El admin no tiene cierre. Se cambia desde Admin › Fecha límite; valor inicial
09/10/2026 00:00 (el último día completo de carga es el 08/10).

**Programas por usuario.** Un usuario solo puede cargar en sus programas asignados. Sin programas
asignados (o rol admin) = todos.

**Campos obligatorios.** Programa, partida, ítem, cantidades (mínima ≥ 1 y ≤ requerida), unidad,
precio, prioridad y justificación.

## Usuarios y contraseñas

- Contraseña por defecto **cambiar123** (usuarios nuevos y restablecidos); en el primer ingreso se pide
  cambiarla. La nueva: mínimo 4 caracteres y distinta de la actual.
- 5 intentos fallidos bloquean la cuenta 15 minutos (restablecer la contraseña la desbloquea).
- Alta, modificación, baja lógica (inactivo) y restablecer contraseña: Admin › Usuarios.
- La sesión dura 12 horas; al recargar la página hay que volver a ingresar.

## Historial de cambios

La tabla `formulacion_historial` se llena sola (trigger) con cada alta, edición y baja: quién, cuándo,
valores anteriores y nuevos. También registra los cambios hechos a mano desde el SQL Editor (usuario
`sql`). Se consulta y exporta desde Admin › Historial.

```sql
-- Historial completo de un registro
select fecha, usuario, accion, antes, despues from formulacion_historial where registro_id = 123 order by fecha;
-- Recuperar un registro borrado (queda entero en "antes")
select antes from formulacion_historial where accion = 'baja' order by fecha desc;
```

## Seguridad

- Ninguna tabla con datos propios (`usuarios`, `sesiones`, `formulacion`, `formulacion_historial`,
  `configuracion`) se puede leer ni escribir con la clave pública: RLS activado y sin políticas.
- La app solo llama a funciones. `login` entrega un token de sesión; el resto de las funciones lo
  validan. Las `admin_*` exigen además rol admin.
- `programas` y `plan_cuentas` son de lectura pública, **excepto la columna presupuesto**.
- La clave **secret / service_role** no se usa en la app; solo en `cargar_excel.py`, por consola.

## Consultas útiles

```sql
select * from formulacion order by creado_en desc;
select cargado_por, count(*), sum(monto) from formulacion group by 1 order by 3 desc;
-- Saldo por programa
select p.nro_programa, p.presupuesto, coalesce(sum(f.monto), 0) utilizado,
       p.presupuesto - coalesce(sum(f.monto), 0) saldo, coalesce(sum(f.monto_minimo), 0) minimo
  from programas p left join formulacion f using (nro_programa) group by 1, 2 order by 1;
```
