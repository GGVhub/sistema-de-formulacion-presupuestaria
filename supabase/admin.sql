-- ============================================================
-- Administración: historial de cambios + funciones del panel de administrador
-- Ejecutar en: Supabase > SQL Editor, DESPUÉS de formulacion.sql
-- Se puede volver a ejecutar sin perder datos.
-- ============================================================
-- Todas las funciones admin_* validan el token de sesión Y que el usuario tenga rol 'admin'.
-- Ninguna tabla queda accesible con la clave pública.
-- ============================================================


-- ------------------------------------------------------------
-- Historial de cambios de la tabla formulacion
-- Lo llena un trigger: registra altas, ediciones y bajas hechas desde la app
-- y también las hechas a mano desde el SQL Editor (figuran como usuario "sql").
-- ------------------------------------------------------------
create table if not exists public.formulacion_historial (
  id           bigint generated always as identity primary key,
  registro_id  bigint not null,
  accion       text not null check (accion in ('alta', 'edición', 'baja')),
  usuario      text not null,
  fecha        timestamptz not null default now(),
  antes        jsonb,
  despues      jsonb
);
create index if not exists formulacion_historial_fecha_idx    on public.formulacion_historial (fecha desc);
create index if not exists formulacion_historial_registro_idx on public.formulacion_historial (registro_id);

alter table public.formulacion_historial enable row level security;
revoke all on public.formulacion_historial from anon, authenticated;

create or replace function public._formulacion_auditar()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_usuario text := coalesce(nullif(current_setting('app.usuario', true), ''), 'sql');
begin
  if tg_op = 'INSERT' then
    insert into public.formulacion_historial (registro_id, accion, usuario, despues)
    values (new.id, 'alta', v_usuario, to_jsonb(new));
  elsif tg_op = 'UPDATE' then
    -- No se registra si lo único que cambió es la marca de tiempo
    if (to_jsonb(old) - 'actualizado_en') is distinct from (to_jsonb(new) - 'actualizado_en') then
      insert into public.formulacion_historial (registro_id, accion, usuario, antes, despues)
      values (new.id, 'edición', v_usuario, to_jsonb(old), to_jsonb(new));
    end if;
  else
    insert into public.formulacion_historial (registro_id, accion, usuario, antes)
    values (old.id, 'baja', v_usuario, to_jsonb(old));
  end if;
  return null;
end;
$$;

drop trigger if exists formulacion_auditar on public.formulacion;
create trigger formulacion_auditar
  after insert or update or delete on public.formulacion
  for each row execute function public._formulacion_auditar();


-- ------------------------------------------------------------
-- Uso interno: exige sesión válida con rol admin
-- ------------------------------------------------------------
create or replace function public._admin_sesion(p_token uuid)
returns public.usuarios
language plpgsql
security definer
set search_path = public
as $$
declare
  u public.usuarios;
begin
  u := public._usuario_sesion(p_token);
  if u.rol <> 'admin' then
    raise exception 'Esta función es solo para administradores.';
  end if;
  return u;
end;
$$;
revoke all on function public._admin_sesion(uuid) from public, anon, authenticated;


-- ------------------------------------------------------------
-- Fecha límite de carga (null = sin fecha límite)
-- ------------------------------------------------------------
create or replace function public.admin_fecha_limite_guardar(p_token uuid, p_fecha timestamptz)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  u public.usuarios;
begin
  u := public._admin_sesion(p_token);
  insert into public.configuracion (clave, valor, actualizado_por, actualizado_en)
  values ('fecha_limite', to_char(p_fecha at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), u.usuario, now())
  on conflict (clave) do update
     set valor = excluded.valor, actualizado_por = excluded.actualizado_por, actualizado_en = now();
end;
$$;


-- ------------------------------------------------------------
-- Programas y presupuestos
-- ------------------------------------------------------------
create or replace function public.admin_programas_listar(p_token uuid)
returns table (nro_programa text, programa text, presupuesto numeric, utilizado numeric,
               minimo numeric, registros bigint, orden integer)
language plpgsql
security definer
set search_path = public
as $$
begin
  perform public._admin_sesion(p_token);
  return query
    select p.nro_programa, p.programa, p.presupuesto,
           coalesce(sum(f.monto), 0)::numeric, coalesce(sum(f.monto_minimo), 0)::numeric,
           count(f.id), p.orden
      from public.programas p
      left join public.formulacion f on f.nro_programa = p.nro_programa
     group by p.nro_programa, p.programa, p.presupuesto, p.orden
     order by p.orden, p.nro_programa;
end;
$$;

-- Crea el programa si no existe; si existe, actualiza nombre y presupuesto (null = sin presupuesto)
create or replace function public.admin_programa_guardar(
  p_token uuid, p_nro text, p_programa text, p_presupuesto numeric)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_nro text := trim(coalesce(p_nro, ''));
begin
  perform public._admin_sesion(p_token);
  if v_nro = '' or trim(coalesce(p_programa, '')) = '' then
    raise exception 'El número y el nombre del programa son obligatorios.';
  end if;
  if p_presupuesto is not null and p_presupuesto < 0 then
    raise exception 'El presupuesto no puede ser negativo.';
  end if;
  insert into public.programas (nro_programa, programa, presupuesto, orden)
  values (v_nro, trim(p_programa), p_presupuesto,
          (select coalesce(max(orden), 0) + 1 from public.programas))
  on conflict (nro_programa) do update
     set programa = excluded.programa, presupuesto = excluded.presupuesto;
end;
$$;


-- ------------------------------------------------------------
-- Usuarios
-- ------------------------------------------------------------
create or replace function public.admin_usuarios_listar(p_token uuid)
returns table (usuario text, nombre_apellido text, secretaria text, sub_secretaria text,
               programas text[], rol text, activo boolean, debe_cambiar_password boolean,
               bloqueado boolean, ultimo_login timestamptz, registros bigint)
language plpgsql
security definer
set search_path = public
as $$
begin
  perform public._admin_sesion(p_token);
  return query
    select u.usuario, u.nombre_apellido, u.secretaria, u.sub_secretaria, u.programas, u.rol, u.activo,
           u.debe_cambiar_password, coalesce(u.bloqueado_hasta > now(), false), u.ultimo_login,
           (select count(*) from public.formulacion f where f.cargado_por = u.usuario)
      from public.usuarios u
     order by u.activo desc, u.nombre_apellido;
end;
$$;

-- Alta o modificación. p_datos: usuario, nombre_apellido, secretaria, sub_secretaria,
-- programas (lista), rol, activo. Los usuarios nuevos quedan con la contraseña "cambiar123".
create or replace function public.admin_usuario_guardar(p_token uuid, p_datos jsonb)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  a public.usuarios;
  v_usuario text := lower(trim(coalesce(p_datos->>'usuario', '')));
  v_nombre  text := trim(coalesce(p_datos->>'nombre_apellido', ''));
  v_rol     text := coalesce(nullif(p_datos->>'rol', ''), 'usuario');
  v_activo  boolean := coalesce((p_datos->>'activo')::boolean, true);
  v_progs   text[] := coalesce(array(select jsonb_array_elements_text(coalesce(p_datos->'programas', '[]'::jsonb))), '{}');
  v_inexistentes text;
begin
  a := public._admin_sesion(p_token);
  if v_usuario = '' or v_nombre = '' then
    raise exception 'El usuario y el nombre y apellido son obligatorios.';
  end if;
  if v_usuario !~ '^[a-z0-9._-]+$' then
    raise exception 'El usuario solo puede tener letras sin acentos, números, punto, guion y guion bajo.';
  end if;
  if v_rol not in ('admin', 'usuario') then
    raise exception 'Rol inválido.';
  end if;
  select string_agg(p, ', ') into v_inexistentes
    from unnest(v_progs) p where not exists (select 1 from public.programas where nro_programa = p);
  if v_inexistentes is not null then
    raise exception 'Programas inexistentes: %.', v_inexistentes;
  end if;
  -- Un admin no puede quitarse a sí mismo el rol ni desactivarse (evita quedarse sin acceso)
  if v_usuario = a.usuario and (v_rol <> 'admin' or not v_activo) then
    raise exception 'No podés quitarte el rol de administrador ni desactivar tu propio usuario.';
  end if;

  insert into public.usuarios (usuario, nombre_apellido, secretaria, sub_secretaria, programas, rol, activo)
  values (v_usuario, v_nombre, nullif(trim(p_datos->>'secretaria'), ''),
          nullif(trim(p_datos->>'sub_secretaria'), ''), v_progs, v_rol, v_activo)
  on conflict (usuario) do update
     set nombre_apellido = excluded.nombre_apellido, secretaria = excluded.secretaria,
         sub_secretaria = excluded.sub_secretaria, programas = excluded.programas,
         rol = excluded.rol, activo = excluded.activo;

  if not v_activo then
    delete from public.sesiones where usuario = v_usuario;  -- corta sesiones abiertas
  end if;
end;
$$;

-- Vuelve la contraseña a "cambiar123", desbloquea y obliga a cambiarla en el próximo ingreso
create or replace function public.admin_usuario_resetear(p_token uuid, p_usuario text)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  perform public._admin_sesion(p_token);
  update public.usuarios
     set password_hash = crypt('cambiar123', gen_salt('bf', 10)),
         debe_cambiar_password = true, intentos_fallidos = 0, bloqueado_hasta = null
   where usuario = lower(trim(p_usuario));
  if not found then
    raise exception 'No existe el usuario %.', p_usuario;
  end if;
  delete from public.sesiones where usuario = lower(trim(p_usuario));
end;
$$;


-- ------------------------------------------------------------
-- Historial (más nuevo primero). "detalle" resume qué cambió.
-- ------------------------------------------------------------
create or replace function public.admin_historial(p_token uuid, p_limite integer default 500)
returns table (id bigint, fecha timestamptz, usuario text, accion text, registro_id bigint,
               nro_programa text, item text, detalle text)
language plpgsql
security definer
set search_path = public
as $$
begin
  perform public._admin_sesion(p_token);
  return query
    select h.id, h.fecha, h.usuario, h.accion, h.registro_id,
           coalesce(h.despues, h.antes)->>'nro_programa',
           coalesce(h.despues, h.antes)->>'item',
           case h.accion
             when 'edición' then (
               select string_agg(format('%s: %s → %s', k, coalesce(h.antes->>k, '—'), coalesce(h.despues->>k, '—')),
                                 ' · ' order by k)
                 from jsonb_object_keys(h.despues) k
                where h.antes->k is distinct from h.despues->k
                  and k not in ('actualizado_en', 'monto', 'monto_minimo'))
             else format('cantidad %s · mínima %s · precio %s · monto %s · prioridad %s',
                         coalesce(h.despues, h.antes)->>'cantidad',
                         coalesce(h.despues, h.antes)->>'cantidad_minima',
                         coalesce(h.despues, h.antes)->>'precio_unitario',
                         coalesce(h.despues, h.antes)->>'monto',
                         coalesce(h.despues, h.antes)->>'prioridad')
           end
      from public.formulacion_historial h
     order by h.fecha desc, h.id desc
     limit greatest(coalesce(p_limite, 500), 1);
end;
$$;


-- ------------------------------------------------------------
-- Permisos
-- ------------------------------------------------------------
revoke all on function public.admin_fecha_limite_guardar(uuid, timestamptz)        from public;
revoke all on function public.admin_programas_listar(uuid)                         from public;
revoke all on function public.admin_programa_guardar(uuid, text, text, numeric)    from public;
revoke all on function public.admin_usuarios_listar(uuid)                          from public;
revoke all on function public.admin_usuario_guardar(uuid, jsonb)                   from public;
revoke all on function public.admin_usuario_resetear(uuid, text)                   from public;
revoke all on function public.admin_historial(uuid, integer)                       from public;
grant execute on function public.admin_fecha_limite_guardar(uuid, timestamptz)     to anon, authenticated;
grant execute on function public.admin_programas_listar(uuid)                      to anon, authenticated;
grant execute on function public.admin_programa_guardar(uuid, text, text, numeric) to anon, authenticated;
grant execute on function public.admin_usuarios_listar(uuid)                       to anon, authenticated;
grant execute on function public.admin_usuario_guardar(uuid, jsonb)                to anon, authenticated;
grant execute on function public.admin_usuario_resetear(uuid, text)                to anon, authenticated;
grant execute on function public.admin_historial(uuid, integer)                    to anon, authenticated;

notify pgrst, 'reload schema';


-- ------------------------------------------------------------
-- Consultas útiles
-- ------------------------------------------------------------
-- Historial completo de un registro:
--   select fecha, usuario, accion, antes, despues from formulacion_historial where registro_id = 123 order by fecha;
-- Recuperar un registro borrado (está entero en "antes"):
--   select antes from formulacion_historial where accion = 'baja' order by fecha desc;
