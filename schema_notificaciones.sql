-- =========================================================
-- Notificaciones: aviso al maestro/Dirección cuando un
-- estudiante sube una constancia de permiso
-- =========================================================
-- Ejecutar en PG Studio (Aiven) UNA VEZ.

CREATE TABLE IF NOT EXISTS notificaciones (
    id             SERIAL PRIMARY KEY,
    nie            VARCHAR(20) NOT NULL REFERENCES estudiantes(nie) ON DELETE CASCADE,
    nombres        VARCHAR(100) NOT NULL,
    apellidos      VARCHAR(100) NOT NULL,
    grado          VARCHAR(40),
    fecha_inicio   DATE NOT NULL,
    fecha_fin      DATE NOT NULL,
    creado_en      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notificaciones_grado ON notificaciones (grado);

-- Qué administrador ya vio/leyó cada notificación. Director y Profesor
-- son cuentas distintas, así que cada una lleva su propio registro de
-- "ya la vi" sobre la misma notificación.
CREATE TABLE IF NOT EXISTS notificaciones_leidas (
    notificacion_id  INTEGER NOT NULL REFERENCES notificaciones(id) ON DELETE CASCADE,
    admin_usuario    VARCHAR(50) NOT NULL,
    leida_en         TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (notificacion_id, admin_usuario)
);
