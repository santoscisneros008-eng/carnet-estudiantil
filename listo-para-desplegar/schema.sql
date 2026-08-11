-- =========================================================
-- Esquema: Carné Digital de Estudiantes
-- Motor: PostgreSQL (pensado para Aiven)
-- =========================================================

CREATE TABLE IF NOT EXISTS estudiantes (
    id              SERIAL PRIMARY KEY,
    nie             VARCHAR(20)  NOT NULL UNIQUE,
    nombres         VARCHAR(100) NOT NULL,
    apellidos       VARCHAR(100) NOT NULL,
    carrera         VARCHAR(120),
    seccion         VARCHAR(20),
    grado           VARCHAR(40),
    correo          VARCHAR(150),
    telefono        VARCHAR(30),
    tipo_sangre     VARCHAR(5),
    foto_url        TEXT,
    estado          VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
    fecha_ingreso   DATE,
    creado_en       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_estudiantes_nie ON estudiantes (nie);
CREATE INDEX IF NOT EXISTS idx_estudiantes_grado ON estudiantes (grado);
