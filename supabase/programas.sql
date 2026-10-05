-- ============================================================
-- Programas presupuestarios — reemplaza a la tabla "jurisdicciones"
-- Ejecutar en: Supabase > SQL Editor, ANTES de formulacion.sql
-- Se puede volver a ejecutar: actualiza nombres sin pisar el presupuesto cargado.
-- Los programas 555 y 558 se quitaron (se usan sus subprogramas 555-1, 555-2, 558-1, 558-2, 558-3).
-- ============================================================

create table if not exists public.programas (
  nro_programa    text primary key check (nro_programa = trim(nro_programa)),  -- '555', '555-1'
  programa        text not null,
  programa_padre  text generated always as (split_part(nro_programa, '-', 1)) stored,
  presupuesto     numeric(18, 2),                                               -- todavía no se usa en la app
  orden           integer not null default 0
);

-- Datos de programas.xlsx
insert into public.programas (nro_programa, programa, presupuesto, orden) values
  ('552', 'Desarrollo Sostenible', null, 1),
  ('554', 'Ordenamiento Territorial', null, 2),
  ('555-1', 'Gastos Comunes', null, 4),
  ('555-2', 'Coordinacion', null, 5),
  ('556', 'Ambiente- Recursos Afectados', null, 6),
  ('558-1', 'Biodiversidad', null, 8),
  ('558-2', 'Direccion General de Viveros', null, 9),
  ('558-3', 'ANP', null, 10),
  ('559', 'Economía Circular Y Empleo Verde', null, 11),
  ('560', '(C.E) Fondo Para La Gestión De Residuos Sólidos Urbanos Ley N° 9088 - Cuenta Especial', null, 12),
  ('561', 'Ordenamiento De Bosques Nativos', null, 13),
  ('570', 'Cambio Climático', null, 14),
  ('765', 'Fondo Financiamiento Ambiental - Plan Provincial Para La Gestion Integral De Residuos - Ley 10.896', null, 15)
on conflict (nro_programa) do update
   set programa    = excluded.programa,
       orden       = excluded.orden,
       presupuesto = coalesce(excluded.presupuesto, public.programas.presupuesto);

-- ------------------------------------------------------------
-- Seguridad: la app puede leer número y nombre, pero NO el presupuesto
-- ------------------------------------------------------------
alter table public.programas enable row level security;
revoke all on public.programas from anon, authenticated;
grant select (nro_programa, programa, programa_padre, orden) on public.programas to anon, authenticated;

drop policy if exists "lectura programas" on public.programas;
create policy "lectura programas" on public.programas for select to anon, authenticated using (true);

-- ------------------------------------------------------------
-- La tabla vieja ya no se usa
-- ------------------------------------------------------------
drop table if exists public.jurisdicciones;

notify pgrst, 'reload schema';

-- Control: programas asignados a usuarios que no existen en la tabla (debería dar 0 filas)
-- select u.usuario, p from usuarios u, unnest(u.programas) p
--  where not exists (select 1 from programas where nro_programa = p);
