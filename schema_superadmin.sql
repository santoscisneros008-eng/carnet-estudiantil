-- =========================================================
-- Administrador general: cuentas y bitácora
-- =========================================================
-- Ejecutar en PG Studio (Aiven) UNA VEZ.
-- No cambia ni borra datos: solo agrega 'id' a admins y tarjetas_nfc SI NO LO TIENEN
-- (si ya lo tienen, esas dos líneas no hacen nada).

ALTER TABLE admins       ADD COLUMN IF NOT EXISTS id SERIAL;
ALTER TABLE tarjetas_nfc ADD COLUMN IF NOT EXISTS id SERIAL;

CREATE TABLE IF NOT EXISTS superadmins (
    id             SERIAL PRIMARY KEY,
    usuario        VARCHAR(50) NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    creado_en      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Registro de quién hizo qué. Nunca guarda contraseñas.
CREATE TABLE IF NOT EXISTS bitacora (
    id       SERIAL PRIMARY KEY,
    fecha    TIMESTAMP NOT NULL DEFAULT NOW(),
    actor    VARCHAR(50) NOT NULL,
    accion   VARCHAR(40) NOT NULL,
    objeto   VARCHAR(120),
    detalle  TEXT
);
CREATE INDEX IF NOT EXISTS idx_bitacora_fecha ON bitacora (fecha DESC);
