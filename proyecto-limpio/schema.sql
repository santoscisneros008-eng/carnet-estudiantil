-- =========================================================
-- Esquema COMPLETO del Carné Digital de Estudiantes
-- (versión consolidada — refleja el estado actual del proyecto)
-- =========================================================
-- Seguro de ejecutar de nuevo: todo usa IF NOT EXISTS, así que si ya
-- tienes las tablas creadas, no pasa nada al volver a correrlo.
--
-- Reemplaza a los scripts de migración anteriores (schema_asistencia.sql,
-- schema_admins.sql, schema_actualizar_campos.sql, schema_agregar_foto.sql,
-- schema_tarjetas_nfc.sql) — ya aplicados uno por uno a lo largo del
-- proyecto. Este archivo único es el que usarías si alguna vez necesitas
-- montar la base de datos desde cero (por ejemplo, en otra institución).

-- ---------------------------------------------------------
-- Estudiantes
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS estudiantes (
    id                SERIAL PRIMARY KEY,
    nie               VARCHAR(20)  NOT NULL UNIQUE,
    nombres           VARCHAR(100) NOT NULL,
    apellidos         VARCHAR(100) NOT NULL,
    carrera           VARCHAR(120),
    seccion           VARCHAR(20),
    grado             VARCHAR(40),               -- salón (ej. "Segundo Año")
    correo            VARCHAR(150),
    telefono          VARCHAR(30),
    estado            VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',  -- ACTIVO / INACTIVO / GRADUADO
    fecha_nacimiento  DATE,
    foto              BYTEA,                     -- foto de perfil (JPEG, redimensionada)
    foto_tipo         VARCHAR(30),                -- mimetype de la foto, ej. 'image/jpeg'
    creado_en         TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_estudiantes_nie ON estudiantes (nie);
CREATE INDEX IF NOT EXISTS idx_estudiantes_grado ON estudiantes (grado);

-- ---------------------------------------------------------
-- Asistencia (entrada / salida por día)
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS asistencias (
    id            SERIAL PRIMARY KEY,
    nie           VARCHAR(20) NOT NULL REFERENCES estudiantes(nie) ON DELETE CASCADE,
    fecha         DATE NOT NULL,
    hora_entrada  TIME,
    hora_salida   TIME,
    UNIQUE (nie, fecha)
);

CREATE INDEX IF NOT EXISTS idx_asistencias_fecha ON asistencias (fecha);

-- ---------------------------------------------------------
-- Cuentas de administración (director ve todo, profesor solo su salón)
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS admins (
    id             SERIAL PRIMARY KEY,
    usuario        VARCHAR(50) NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,                -- nunca texto plano; usa crear_admin.py
    rol            VARCHAR(20) NOT NULL DEFAULT 'profesor',  -- 'director' o 'profesor'
    grado          VARCHAR(40),                  -- NULL para director
    creado_en      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------
-- Tarjetas NFC vinculadas a estudiantes
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS tarjetas_nfc (
    id            SERIAL PRIMARY KEY,
    uid           VARCHAR(64) NOT NULL UNIQUE,
    nie           VARCHAR(20) NOT NULL REFERENCES estudiantes(nie) ON DELETE CASCADE,
    asignada_en   TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------
-- (Opcional) Un par de estudiantes de ejemplo para probar de inmediato
-- en una base de datos nueva. No hace nada si el NIE ya existe.
-- ---------------------------------------------------------
INSERT INTO estudiantes (nie, nombres, apellidos, carrera, seccion, grado, correo, telefono, estado, fecha_nacimiento)
VALUES
    ('N0001', 'Ana Lucía', 'Ramírez Pérez', 'Desarrollo de Software', 'A', 'Tercer Año', 'ana.ramirez@example.edu', '7000-1111', 'ACTIVO', '2008-05-12')
ON CONFLICT (nie) DO NOTHING;
