-- =========================================================
-- Tabla de asistencia (entrada / salida) por estudiante
-- =========================================================
CREATE TABLE IF NOT EXISTS asistencias (
    id            SERIAL PRIMARY KEY,
    nie           VARCHAR(20) NOT NULL REFERENCES estudiantes(nie) ON DELETE CASCADE,
    fecha         DATE NOT NULL,
    hora_entrada  TIME,
    hora_salida   TIME,
    UNIQUE (nie, fecha)
);

CREATE INDEX IF NOT EXISTS idx_asistencias_fecha ON asistencias (fecha);
