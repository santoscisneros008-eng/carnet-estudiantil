-- =========================================================
-- Actualización de campos: quitar tipo_sangre, renombrar
-- fecha_ingreso -> fecha_nacimiento
-- =========================================================
-- Ejecutar en PG Studio (Aiven) UNA VEZ.
--
-- IMPORTANTE: los estudiantes que ya tenían una fecha_ingreso guardada
-- van a quedar con ESA MISMA fecha en fecha_nacimiento (el dato no se
-- borra, solo cambia de nombre la columna) — probablemente no sea su
-- fecha de nacimiento real, así que conviene revisar/corregir esos
-- estudiantes ya existentes desde el panel después de este cambio.

ALTER TABLE estudiantes DROP COLUMN IF EXISTS tipo_sangre;
ALTER TABLE estudiantes RENAME COLUMN fecha_ingreso TO fecha_nacimiento;
