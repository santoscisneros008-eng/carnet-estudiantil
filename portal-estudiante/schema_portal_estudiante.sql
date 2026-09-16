-- =========================================================
-- Portal del estudiante: contraseña propia + constancias de permiso
-- =========================================================
-- Ejecutar en PG Studio (Aiven) UNA VEZ.

-- Cada estudiante inicia sesión con su NIE como usuario. La contraseña
-- se asigna desde el panel de Dirección (nadie la escribe directo en SQL,
-- se guarda encriptada).
ALTER TABLE estudiantes ADD COLUMN IF NOT EXISTS password_hash TEXT;

-- Constancias de permiso: una por estudiante por fecha. Si existe una
-- fila aquí para un día que salió como "Inasistencia", los profesores y
-- Dirección ven automáticamente "Inasistencia con permiso" en su lugar.
CREATE TABLE IF NOT EXISTS permisos (
    id            SERIAL PRIMARY KEY,
    nie           VARCHAR(20) NOT NULL REFERENCES estudiantes(nie) ON DELETE CASCADE,
    fecha         DATE NOT NULL,
    imagen        BYTEA NOT NULL,
    imagen_tipo   VARCHAR(30) NOT NULL,
    comentario    TEXT,
    subido_en     TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (nie, fecha)
);
