-- ============================================================
-- Registros de la formulación — ejecutar DESPUÉS de usuarios.sql, programas.sql y plan_cuentas.sql
-- Ejecutar en: Supabase > SQL Editor
-- ============================================================
-- La tabla no se puede tocar con la anon key (RLS sin políticas).
-- La app usa estas funciones, que validan el token de sesión del login:
--   formulacion_agregar · formulacion_listar · formulacion_actualizar · formulacion_borrar
-- Visibilidad: cada usuario ve y edita lo suyo; el rol admin ve y edita todo.
-- Programas: cada usuario solo puede cargar en los programas asignados (usuarios.programas);
--            admin o usuarios sin programas asignados pueden cargar en cualquiera.
-- Presupuesto: cada registro descuenta su monto (cantidad × precio) del presupuesto de su programa.
--   · Si el total no supera el presupuesto → se acepta cualquier prioridad.
--   · Si lo supera → solo prioridad Baja, y hasta un 10 % por encima del presupuesto.
--   · Programas sin presupuesto cargado (null) → sin control.
-- Ítem / Partida / Clasificador: se toman del plan de cuentas (plan_cuentas.sql) a partir del código del ítem.
-- Todos los campos son obligatorios (también la cantidad mínima y la justificación).
-- Fecha límite: pasada la fecha (tabla configuracion), solo el admin puede agregar, editar o borrar.
-- Se puede volver a ejecutar sin perder registros.
-- ============================================================

-- La versión anterior de schema.sql creaba "formulacion" con otra estructura.
-- Si está vacía (nunca se guardó nada), se reemplaza. Si tiene datos, frena y avisa.
do $$
begin
  if to_regclass('public.formulacion') is not null
     and not exists (select 1 from information_schema.columns
                      where table_schema = 'public' and table_name = 'formulacion'
                        and column_name = 'cargado_por') then
    if exists (select 1 from public.formulacion) then
      raise exception 'La tabla formulacion tiene datos con la estructura vieja. Revisala antes de continuar.';
    end if;
    drop table public.formulacion;
  end if;
end $$;

create table if not exists public.formulacion (
  id               bigint generated always as identity primary key,
  nro_programa     text references public.programas (nro_programa) on update cascade,
  programa         text,
  jurisdiccion     text,            -- histórico: registros cargados antes de la tabla programas
  area             text,
  codigo           bigint,
  item             text not null,
  objeto_gasto     bigint,
  clasificador     text,
  cantidad         integer not null check (cantidad > 0),
  cantidad_minima  integer not null default 0 check (cantidad_minima >= 0),
  unidad           text,
  precio_unitario  numeric(18, 2) not null check (precio_unitario > 0),
  monto            numeric(18, 2) generated always as (cantidad * precio_unitario) stored,
  monto_minimo     numeric(18, 2) generated always as (cantidad_minima * precio_unitario) stored,
  prioridad        text not null check (prioridad in ('Alta', 'Media', 'Baja')),
  justificacion    text,
  cargado_por      text not null references public.usuarios (usuario) on update cascade,
  creado_en        timestamptz not null default now(),
  actualizado_en   timestamptz not null default now(),
  constraint minima_menor_requerida check (cantidad_minima <= cantidad)
);
-- Migración desde la versión con "jurisdiccion" (no borra registros)
alter table public.formulacion add column if not exists nro_programa text
  references public.programas (nro_programa) on update cascade;
alter table public.formulacion add column if not exists programa text;
alter table public.formulacion add column if not exists partida_codigo bigint;
alter table public.formulacion add column if not exists partida text;
alter table public.formulacion alter column jurisdiccion drop not null;

create index if not exists formulacion_cargado_por_idx on public.formulacion (cargado_por);
create index if not exists formulacion_programa_idx    on public.formulacion (nro_programa);

alter table public.formulacion enable row level security;
revoke all on public.formulacion from anon, authenticated;


-- ------------------------------------------------------------
-- Configuración general y fecha límite de carga
-- ------------------------------------------------------------
create table if not exists public.configuracion (
  clave            text primary key,
  valor            text,
  actualizado_por  text,
  actualizado_en   timestamptz not null default now()
);
alter table public.configuracion enable row level security;
revoke all on public.configuracion from anon, authenticated;

-- Fecha límite inicial: 09/10/2026 00:00 (hora de Argentina). Si ya hay una cargada, no se pisa.
insert into public.configuracion (clave, valor, actualizado_por)
values ('fecha_limite', '2026-10-09T00:00:00-03:00', 'instalación')
on conflict (clave) do nothing;

create or replace function public._fecha_limite() returns timestamptz
language sql stable security definer set search_path = public as $$
  select nullif(valor, '')::timestamptz from public.configuracion where clave = 'fecha_limite'
$$;
revoke all on function public._fecha_limite() from public, anon, authenticated;

-- Corta si la carga ya cerró (el admin puede seguir operando)
create or replace function public._validar_carga_abierta(u public.usuarios)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_limite timestamptz := public._fecha_limite();
begin
  if u.rol <> 'admin' and v_limite is not null and now() >= v_limite then
    raise exception 'La carga cerró el % hs. Ya no se pueden agregar, editar ni borrar registros.',
      to_char(v_limite at time zone 'America/Argentina/Buenos_Aires', 'DD/MM/YYYY HH24:MI');
  end if;
end;
$$;
revoke all on function public._validar_carga_abierta(public.usuarios) from public, anon, authenticated;

-- Estado de la carga para mostrar en la app
create or replace function public.carga_estado(p_token uuid)
returns table (fecha_limite timestamptz, abierta boolean, ahora timestamptz)
language plpgsql
security definer
set search_path = public
as $$
declare
  u public.usuarios;
  v_limite timestamptz := public._fecha_limite();
begin
  u := public._usuario_sesion(p_token);
  return query select v_limite, (u.rol = 'admin' or v_limite is null or now() < v_limite), now();
end;
$$;


-- ------------------------------------------------------------
-- Presupuesto: reglas compartidas por agregar y actualizar
-- ------------------------------------------------------------
create or replace function public._margen_baja() returns numeric
language sql immutable as $$ select 0.10::numeric $$;   -- 10 % extra solo para prioridad Baja

create or replace function public._ars(v numeric) returns text
language sql immutable as $$
  select '$ ' || translate(to_char(round(v, 2), 'FM999,999,999,999,990.00'), ',.', '.,')
$$;

-- Valida que un monto entre en el presupuesto del programa. Bloquea la fila del programa
-- mientras dura la transacción para que dos cargas simultáneas no lo sobrepasen.
create or replace function public._validar_presupuesto(
  p_nro text, p_monto numeric, p_prioridad text, p_excluir_id bigint default null)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_presupuesto numeric;
  v_otros numeric;
  v_total numeric;
  v_limite numeric;
begin
  select presupuesto into v_presupuesto from public.programas where nro_programa = p_nro for update;
  if v_presupuesto is null then
    return;  -- sin presupuesto cargado: no se controla
  end if;

  select coalesce(sum(monto), 0) into v_otros
    from public.formulacion
   where nro_programa = p_nro and (p_excluir_id is null or id <> p_excluir_id);

  v_total  := v_otros + p_monto;
  v_limite := v_presupuesto * (1 + public._margen_baja());

  if v_total <= v_presupuesto then
    return;
  end if;
  if p_prioridad <> 'Baja' then
    raise exception 'Supera el presupuesto del programa % (saldo disponible: %). Por encima del presupuesto solo se aceptan registros de prioridad Baja.',
      p_nro, public._ars(greatest(v_presupuesto - v_otros, 0));
  end if;
  if v_total > v_limite then
    raise exception 'Supera el margen del 10%% del programa % (disponible para prioridad Baja: %).',
      p_nro, public._ars(greatest(v_limite - v_otros, 0));
  end if;
end;
$$;
revoke all on function public._validar_presupuesto(text, numeric, text, bigint) from public, anon, authenticated;


-- ------------------------------------------------------------
-- Estado del presupuesto de los programas del usuario (admin: todos)
-- comprometido = suma de lo cargado por TODOS los usuarios en el programa
-- ------------------------------------------------------------
drop function if exists public.presupuesto_estado(uuid);  -- cambió el tipo de retorno (agrega minimo)
create or replace function public.presupuesto_estado(p_token uuid)
returns table (nro_programa text, programa text, presupuesto numeric, comprometido numeric,
               comprometido_baja numeric, registros bigint, margen numeric, minimo numeric)
language plpgsql
security definer
set search_path = public
as $$
declare
  u public.usuarios;
begin
  u := public._usuario_sesion(p_token);
  return query
    select p.nro_programa, p.programa, p.presupuesto,
           coalesce(sum(f.monto), 0)::numeric,
           coalesce(sum(f.monto) filter (where f.prioridad = 'Baja'), 0)::numeric,
           count(f.id),
           public._margen_baja(),
           coalesce(sum(f.monto_minimo), 0)::numeric
      from public.programas p
      left join public.formulacion f on f.nro_programa = p.nro_programa
     where u.rol = 'admin' or cardinality(u.programas) = 0 or p.nro_programa = any (u.programas)
     group by p.nro_programa, p.programa, p.presupuesto, p.orden
     order by p.orden;
end;
$$;


-- ------------------------------------------------------------
-- Agregar: recibe los datos como JSON, devuelve el id
-- ------------------------------------------------------------
create or replace function public.formulacion_agregar(p_token uuid, p_datos jsonb)
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
  u public.usuarios;
  v_id bigint;
  v_nro text := trim(p_datos->>'nro_programa');
  v_programa text;
  v_codigo bigint := nullif(p_datos->>'codigo', '')::bigint;
  v_item public.plan_cuentas;
  v_partida public.plan_cuentas;
  v_clasif public.plan_cuentas;
  v_faltan text[] := '{}';
begin
  u := public._usuario_sesion(p_token);
  perform public._validar_carga_abierta(u);

  -- Todos los campos son obligatorios
  if coalesce(v_nro, '') = ''                                   then v_faltan := array_append(v_faltan, 'programa'); end if;
  if v_codigo is null                                           then v_faltan := array_append(v_faltan, 'partida e ítem'); end if;
  if coalesce((p_datos->>'cantidad')::numeric, 0) <= 0          then v_faltan := array_append(v_faltan, 'cantidad requerida'); end if;
  if coalesce((p_datos->>'cantidad_minima')::numeric, 0) <= 0   then v_faltan := array_append(v_faltan, 'cantidad mínima'); end if;
  if coalesce(trim(p_datos->>'unidad'), '') = ''                then v_faltan := array_append(v_faltan, 'unidad'); end if;
  if coalesce((p_datos->>'precio_unitario')::numeric, 0) <= 0   then v_faltan := array_append(v_faltan, 'precio unitario'); end if;
  if coalesce(p_datos->>'prioridad', '') not in ('Alta', 'Media', 'Baja') then v_faltan := array_append(v_faltan, 'prioridad'); end if;
  if coalesce(trim(p_datos->>'justificacion'), '') = ''         then v_faltan := array_append(v_faltan, 'justificación'); end if;
  if cardinality(v_faltan) > 0 then
    raise exception 'Faltan datos obligatorios: %.', array_to_string(v_faltan, ', ');
  end if;
  if (p_datos->>'cantidad_minima')::numeric > (p_datos->>'cantidad')::numeric then
    raise exception 'La cantidad mínima no puede superar a la cantidad requerida.';
  end if;

  -- Ítem (nivel 3, o nivel 2 si la partida no tiene ítems) → partida → clasificador
  select * into v_item from public.plan_cuentas where codigo = v_codigo and nivel in (2, 3);
  if not found
     or (v_item.nivel = 2 and exists (select 1 from public.plan_cuentas where codigo_superior = v_codigo)) then
    raise exception 'Elegí un ítem válido del plan de cuentas.';
  end if;
  if v_item.nivel = 3 then
    select * into v_partida from public.plan_cuentas where codigo = v_item.codigo_superior;
  else
    v_partida := v_item;
  end if;
  select * into v_clasif from public.plan_cuentas where codigo = v_partida.codigo_superior;

  select p.programa into v_programa from public.programas p where p.nro_programa = v_nro;
  if v_programa is null then
    raise exception 'Elegí un programa válido.';
  end if;
  if u.rol <> 'admin' and cardinality(u.programas) > 0 and not (v_nro = any (u.programas)) then
    raise exception 'No tenés asignado el programa %.', v_nro;
  end if;

  perform public._validar_presupuesto(
    v_nro,
    (p_datos->>'cantidad')::int * (p_datos->>'precio_unitario')::numeric,
    coalesce(p_datos->>'prioridad', 'Alta'));

  insert into public.formulacion
    (nro_programa, programa, codigo, item, objeto_gasto, clasificador, cantidad, cantidad_minima,
     unidad, precio_unitario, prioridad, justificacion, cargado_por, partida_codigo, partida)
  values
    (v_nro, v_programa, v_item.codigo, v_item.denominacion,
     v_item.codigo, v_clasif.denominacion, (p_datos->>'cantidad')::int,
     coalesce((p_datos->>'cantidad_minima')::int, 0), p_datos->>'unidad',
     (p_datos->>'precio_unitario')::numeric, coalesce(p_datos->>'prioridad', 'Alta'),
     trim(p_datos->>'justificacion'), u.usuario, v_partida.codigo, v_partida.denominacion)
  returning id into v_id;
  return v_id;
exception
  when check_violation or not_null_violation or invalid_text_representation then
    raise exception 'Datos inválidos: cantidad, cantidad mínima y precio deben ser mayores a 0, y la cantidad mínima no puede superar a la requerida.';
end;
$$;


-- ------------------------------------------------------------
-- Listar: lo propio (o todo si es admin), más nuevo primero
-- ------------------------------------------------------------
create or replace function public.formulacion_listar(p_token uuid)
returns setof public.formulacion
language plpgsql
security definer
set search_path = public
as $$
declare
  u public.usuarios;
begin
  u := public._usuario_sesion(p_token);
  return query
    select * from public.formulacion f
     where u.rol = 'admin' or f.cargado_por = u.usuario
     order by f.creado_en desc, f.id desc;
end;
$$;


-- ------------------------------------------------------------
-- Actualizar: solo campos editables; lo que no viene en el JSON no cambia
-- ------------------------------------------------------------
create or replace function public.formulacion_actualizar(p_token uuid, p_id bigint, p_cambios jsonb)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  u public.usuarios;
  r public.formulacion;
  v_monto numeric;
  v_prioridad text;
begin
  u := public._usuario_sesion(p_token);
  perform public._validar_carga_abierta(u);

  select * into r from public.formulacion f
   where f.id = p_id and (u.rol = 'admin' or f.cargado_por = u.usuario)
   for update;
  if not found then
    raise exception 'No se encontró el registro o no tenés permiso para editarlo.';
  end if;

  -- Obligatorios: no se pueden vaciar al editar
  if p_cambios ? 'justificacion' and coalesce(trim(p_cambios->>'justificacion'), '') = '' then
    raise exception 'La justificación es obligatoria.';
  end if;
  if p_cambios ? 'unidad' and coalesce(trim(p_cambios->>'unidad'), '') = '' then
    raise exception 'La unidad es obligatoria.';
  end if;
  if p_cambios ? 'prioridad' and coalesce(p_cambios->>'prioridad', '') not in ('Alta', 'Media', 'Baja') then
    raise exception 'La prioridad es obligatoria.';
  end if;
  if (p_cambios ? 'cantidad_minima' and coalesce((p_cambios->>'cantidad_minima')::numeric, 0) <= 0)
     or (p_cambios ? 'cantidad' and coalesce((p_cambios->>'cantidad')::numeric, 0) <= 0)
     or (p_cambios ? 'precio_unitario' and coalesce((p_cambios->>'precio_unitario')::numeric, 0) <= 0) then
    raise exception 'Cantidad, cantidad mínima y precio deben ser mayores a 0.';
  end if;
  if coalesce((p_cambios->>'cantidad_minima')::int, r.cantidad_minima) > coalesce((p_cambios->>'cantidad')::int, r.cantidad) then
    raise exception 'La cantidad mínima no puede superar a la cantidad requerida.';
  end if;

  -- Presupuesto: se controla si el monto sube o si deja de ser prioridad Baja
  v_monto := coalesce((p_cambios->>'cantidad')::int, r.cantidad)
           * coalesce((p_cambios->>'precio_unitario')::numeric, r.precio_unitario);
  v_prioridad := coalesce(p_cambios->>'prioridad', r.prioridad);
  if r.nro_programa is not null
     and (v_monto > r.monto or (r.prioridad = 'Baja' and v_prioridad <> 'Baja')) then
    perform public._validar_presupuesto(r.nro_programa, v_monto, v_prioridad, r.id);
  end if;

  update public.formulacion f set
    cantidad        = case when p_cambios ? 'cantidad'        then (p_cambios->>'cantidad')::int            else f.cantidad end,
    cantidad_minima = case when p_cambios ? 'cantidad_minima' then (p_cambios->>'cantidad_minima')::int     else f.cantidad_minima end,
    unidad          = case when p_cambios ? 'unidad'          then p_cambios->>'unidad'                     else f.unidad end,
    precio_unitario = case when p_cambios ? 'precio_unitario' then (p_cambios->>'precio_unitario')::numeric else f.precio_unitario end,
    prioridad       = case when p_cambios ? 'prioridad'       then p_cambios->>'prioridad'                  else f.prioridad end,
    justificacion   = case when p_cambios ? 'justificacion'   then nullif(trim(p_cambios->>'justificacion'), '') else f.justificacion end,
    actualizado_en  = now()
  where f.id = p_id and (u.rol = 'admin' or f.cargado_por = u.usuario);
  if not found then
    raise exception 'No se encontró el registro o no tenés permiso para editarlo.';
  end if;
exception
  when check_violation or not_null_violation or invalid_text_representation then
    raise exception 'Datos inválidos: cantidad, cantidad mínima y precio deben ser mayores a 0, y la cantidad mínima no puede superar a la requerida.';
end;
$$;


-- ------------------------------------------------------------
-- Borrar
-- ------------------------------------------------------------
create or replace function public.formulacion_borrar(p_token uuid, p_id bigint)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  u public.usuarios;
begin
  u := public._usuario_sesion(p_token);
  perform public._validar_carga_abierta(u);
  delete from public.formulacion f
   where f.id = p_id and (u.rol = 'admin' or f.cargado_por = u.usuario);
  if not found then
    raise exception 'No se encontró el registro o no tenés permiso para borrarlo.';
  end if;
end;
$$;


-- ------------------------------------------------------------
-- Duplicados: registros ya cargados (por cualquier usuario) del mismo ítem en el mismo programa
-- ------------------------------------------------------------
create or replace function public.formulacion_duplicados(p_token uuid, p_nro text, p_codigo bigint)
returns table (id bigint, cargado_por text, nombre_apellido text, cantidad integer, unidad text,
               monto numeric, prioridad text, creado_en timestamptz)
language plpgsql
security definer
set search_path = public
as $$
declare
  u public.usuarios;
begin
  u := public._usuario_sesion(p_token);
  if u.rol <> 'admin' and cardinality(u.programas) > 0 and not (p_nro = any (u.programas)) then
    return;  -- no es un programa suyo: no se informa nada
  end if;
  return query
    select f.id, f.cargado_por, us.nombre_apellido, f.cantidad, f.unidad, f.monto, f.prioridad, f.creado_en
      from public.formulacion f
      join public.usuarios us on us.usuario = f.cargado_por
     where f.nro_programa = p_nro and f.codigo = p_codigo
     order by f.creado_en;
end;
$$;


-- Permisos: solo las funciones
revoke all on function public.formulacion_agregar(uuid, jsonb)            from public;
revoke all on function public.formulacion_listar(uuid)                    from public;
revoke all on function public.formulacion_actualizar(uuid, bigint, jsonb) from public;
revoke all on function public.formulacion_borrar(uuid, bigint)            from public;
revoke all on function public.presupuesto_estado(uuid)                    from public;
grant execute on function public.presupuesto_estado(uuid)                    to anon, authenticated;
revoke all on function public.carga_estado(uuid)                          from public;
grant execute on function public.carga_estado(uuid)                          to anon, authenticated;
revoke all on function public.formulacion_duplicados(uuid, text, bigint)  from public;
grant execute on function public.formulacion_duplicados(uuid, text, bigint)  to anon, authenticated;
grant execute on function public.formulacion_agregar(uuid, jsonb)            to anon, authenticated;
grant execute on function public.formulacion_listar(uuid)                    to anon, authenticated;
grant execute on function public.formulacion_actualizar(uuid, bigint, jsonb) to anon, authenticated;
grant execute on function public.formulacion_borrar(uuid, bigint)            to anon, authenticated;

-- Que la API vea las funciones nuevas enseguida
notify pgrst, 'reload schema';


-- ------------------------------------------------------------
-- Consultas útiles desde el SQL Editor
-- ------------------------------------------------------------
-- select * from formulacion order by creado_en desc;
-- select cargado_por, count(*), sum(monto) from formulacion group by 1 order by 3 desc;
-- select nro_programa, prioridad, sum(monto) from formulacion group by 1, 2 order by 1, 2;
-- Saldo por programa:
-- select p.nro_programa, p.presupuesto, coalesce(sum(f.monto),0) comprometido,
--        p.presupuesto - coalesce(sum(f.monto),0) saldo
--   from programas p left join formulacion f using (nro_programa) group by 1, 2 order by 1;
