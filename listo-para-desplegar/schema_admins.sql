-- =========================================================
-- Cuentas de administración (director y profesores por salón)
-- =========================================================
-- Ejecutar en PG Studio (Aiven) UNA VEZ. No toca `estudiantes` ni `asistencias`.

CREATE TABLE IF NOT EXISTS admins (
    id             SERIAL PRIMARY KEY,
    usuario        VARCHAR(50) NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    rol            VARCHAR(20) NOT NULL DEFAULT 'profesor',  -- 'director' o 'profesor'
    grado          VARCHAR(40),  -- NULL para director (ve todos los salones); obligatorio para profesor
    creado_en      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- No insertamos cuentas de ejemplo aquí a propósito: las contraseñas deben
-- quedar encriptadas (hasheadas), y eso se hace con el script crear_admin.py,
-- no escribiéndolas directamente en SQL.
