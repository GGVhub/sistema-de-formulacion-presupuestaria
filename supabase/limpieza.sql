-- ============================================================
-- Limpieza: borra las tablas que la app ya no usa
-- Ejecutar UNA vez en: Supabase > SQL Editor
-- ============================================================
--   catalogo        → reemplazada por plan_cuentas
--   devengado       → ya no se muestra el devengado previo en la carga
--   jurisdicciones  → reemplazada por programas
-- No toca usuarios, programas, plan_cuentas, formulacion ni el historial.
-- ============================================================

drop table if exists public.catalogo;
drop table if exists public.devengado;
drop table if exists public.jurisdicciones;

notify pgrst, 'reload schema';
