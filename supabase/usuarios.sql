-- ============================================================
-- Usuarios y login — todo el hash se hace en Postgres (pgcrypto / bcrypt)
-- Ejecutar en: Supabase > SQL Editor. Se puede volver a ejecutar: no borra usuarios.
-- ============================================================
-- Cómo funciona:
--   * La tabla "usuarios" guarda solo el hash bcrypt, nunca la contraseña.
--   * RLS activado y SIN políticas: con la anon key nadie puede leer la tabla
--     (ni siquiera los hashes). La app solo puede llamar a las funciones de abajo.
--   * Las funciones son SECURITY DEFINER: corren con permisos del dueño y
--     devuelven únicamente los datos del usuario, nunca el hash.
-- ============================================================

create extension if not exists pgcrypto with schema extensions;

create table if not exists public.usuarios (
  id                     bigint generated always as identity primary key,
  usuario                text not null unique check (usuario = lower(trim(usuario))),
  nombre_apellido        text not null,
  secretaria             text,
  sub_secretaria         text,
  programas              text[] not null default '{}',   -- ej: {552,555-1}; vacío = todos (admin)
  rol                    text not null default 'usuario' check (rol in ('admin', 'usuario')),
  password_hash          text not null,
  debe_cambiar_password  boolean not null default true,
  activo                 boolean not null default true,
  intentos_fallidos      integer not null default 0,
  bloqueado_hasta        timestamptz,
  ultimo_login           timestamptz,
  password_cambiada_en   timestamptz,
  creado_en              timestamptz not null default now()
);

alter table public.usuarios enable row level security;
revoke all on public.usuarios from anon, authenticated;

-- Contraseña por defecto: "cambiar123" (se pide cambiarla en el primer ingreso)
alter table public.usuarios
  alter column password_hash set default extensions.crypt('cambiar123', extensions.gen_salt('bf', 10)),
  alter column debe_cambiar_password set default true;

-- Los usuarios que todavía no cambiaron su contraseña pasan a tener la contraseña por defecto
update public.usuarios
   set password_hash = extensions.crypt('cambiar123', extensions.gen_salt('bf', 10)),
       intentos_fallidos = 0, bloqueado_hasta = null
 where debe_cambiar_password;

-- Sesiones: login entrega un token; las funciones de datos lo validan
create table if not exists public.sesiones (
  token      uuid primary key default gen_random_uuid(),
  usuario    text not null references public.usuarios (usuario) on update cascade on delete cascade,
  creada_en  timestamptz not null default now(),
  expira_en  timestamptz not null default now() + interval '12 hours'
);
alter table public.sesiones enable row level security;
revoke all on public.sesiones from anon, authenticated;

-- Devuelve el usuario dueño de un token válido (uso interno de otras funciones)
create or replace function public._usuario_sesion(p_token uuid)
returns public.usuarios
language plpgsql
security definer
set search_path = public
as $$
declare
  v public.usuarios%rowtype;
begin
  select u.* into v
    from public.sesiones s join public.usuarios u on u.usuario = s.usuario
   where s.token = p_token and s.expira_en > now() and u.activo;
  if not found then
    raise exception 'Tu sesión venció. Volvé a ingresar.';
  end if;
  -- Deja anotado quién opera en esta transacción (lo usa el historial de cambios)
  perform set_config('app.usuario', v.usuario, true);
  return v;
end;
$$;
revoke all on function public._usuario_sesion(uuid) from public, anon, authenticated;


-- ------------------------------------------------------------
-- login(usuario, password)
-- Devuelve 1 fila con los datos del usuario + token de sesión si la contraseña
-- es correcta, 0 filas si no. Tras 5 intentos fallidos bloquea 15 minutos.
-- ------------------------------------------------------------
drop function if exists public.login(text, text);  -- cambió el tipo de retorno (agrega token)
create or replace function public.login(p_usuario text, p_password text)
returns table (
  usuario text, nombre_apellido text, secretaria text, sub_secretaria text,
  programas text[], rol text, debe_cambiar_password boolean, token uuid
)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v public.usuarios%rowtype;
  v_token uuid;
begin
  select * into v from public.usuarios u
   where u.usuario = lower(trim(p_usuario)) and u.activo;

  if not found then
    return;  -- mismo resultado que contraseña incorrecta: no revela si el usuario existe
  end if;

  if v.bloqueado_hasta is not null and v.bloqueado_hasta > now() then
    raise exception 'Usuario bloqueado por intentos fallidos. Probá de nuevo en % minutos.',
      ceil(extract(epoch from v.bloqueado_hasta - now()) / 60)::int;
  end if;

  if v.password_hash = crypt(p_password, v.password_hash) then
    update public.usuarios u
       set intentos_fallidos = 0, bloqueado_hasta = null, ultimo_login = now()
     where u.id = v.id;
    delete from public.sesiones s where s.expira_en < now();  -- limpieza
    insert into public.sesiones (usuario) values (v.usuario) returning sesiones.token into v_token;
    return query select v.usuario, v.nombre_apellido, v.secretaria, v.sub_secretaria,
                        v.programas, v.rol, v.debe_cambiar_password, v_token;
  else
    update public.usuarios u
       set intentos_fallidos = case when v.intentos_fallidos + 1 >= 5 then 0
                                    else v.intentos_fallidos + 1 end,
           bloqueado_hasta   = case when v.intentos_fallidos + 1 >= 5
                                    then now() + interval '15 minutes' end
     where u.id = v.id;
  end if;
end;
$$;


-- ------------------------------------------------------------
-- cambiar_password(usuario, actual, nueva)
-- Verifica la actual, valida la nueva y baja la marca de "debe cambiar".
-- ------------------------------------------------------------
create or replace function public.cambiar_password(p_usuario text, p_actual text, p_nueva text)
returns boolean
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v public.usuarios%rowtype;
begin
  select * into v from public.usuarios u
   where u.usuario = lower(trim(p_usuario)) and u.activo;

  if not found or v.password_hash <> crypt(p_actual, v.password_hash) then
    raise exception 'La contraseña actual no es correcta.';
  end if;
  if length(coalesce(p_nueva, '')) < 4 then
    raise exception 'La nueva contraseña debe tener al menos 4 caracteres.';
  end if;
  if p_nueva = p_actual then
    raise exception 'La nueva contraseña tiene que ser distinta de la actual.';
  end if;

  update public.usuarios u
     set password_hash = crypt(p_nueva, gen_salt('bf', 10)),
         debe_cambiar_password = false,
         password_cambiada_en = now(),
         intentos_fallidos = 0,
         bloqueado_hasta = null
   where u.id = v.id;
  return true;
end;
$$;


-- ------------------------------------------------------------
-- resetear_password(admin, clave_admin, usuario [, temporal])
-- Vuelve la contraseña a "cambiar123" (o a la temporal indicada) y fuerza el cambio en el próximo ingreso.
-- ------------------------------------------------------------
create or replace function public.resetear_password(
  p_admin text, p_admin_password text, p_usuario text, p_temporal text default 'cambiar123')
returns boolean
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  a public.usuarios%rowtype;
begin
  select * into a from public.usuarios u
   where u.usuario = lower(trim(p_admin)) and u.activo and u.rol = 'admin';
  if not found or a.password_hash <> crypt(p_admin_password, a.password_hash) then
    raise exception 'Credenciales de administrador inválidas.';
  end if;
  if length(coalesce(p_temporal, '')) < 4 then
    raise exception 'La contraseña temporal debe tener al menos 4 caracteres.';
  end if;

  update public.usuarios u
     set password_hash = crypt(p_temporal, gen_salt('bf', 10)),
         debe_cambiar_password = true,
         intentos_fallidos = 0,
         bloqueado_hasta = null
   where u.usuario = lower(trim(p_usuario));
  if not found then
    raise exception 'No existe el usuario %.', p_usuario;
  end if;
  return true;
end;
$$;


-- ------------------------------------------------------------
-- logout(token): cierra la sesión
-- ------------------------------------------------------------
create or replace function public.logout(p_token uuid)
returns void
language sql
security definer
set search_path = public
as $$ delete from public.sesiones where token = p_token; $$;


-- Solo estas funciones quedan expuestas a la app
revoke all on function public.login(text, text)                              from public;
revoke all on function public.cambiar_password(text, text, text)             from public;
revoke all on function public.resetear_password(text, text, text, text)      from public;
grant execute on function public.login(text, text)                           to anon, authenticated;
grant execute on function public.cambiar_password(text, text, text)          to anon, authenticated;
grant execute on function public.resetear_password(text, text, text, text)   to anon, authenticated;
revoke all on function public.logout(uuid)                                   from public;
grant execute on function public.logout(uuid)                                to anon, authenticated;


-- ------------------------------------------------------------
-- Para dar de alta un usuario nuevo más adelante (desde el SQL Editor):
-- ------------------------------------------------------------
-- (queda con la contraseña "cambiar123" y debe cambiarla al ingresar)
-- insert into public.usuarios (usuario, nombre_apellido, secretaria, programas)
-- values ('nombre.apellido', 'Nombre Apellido', 'SECRETARIA ...', '{552,554}');

-- Que la API vea los cambios enseguida
notify pgrst, 'reload schema';
