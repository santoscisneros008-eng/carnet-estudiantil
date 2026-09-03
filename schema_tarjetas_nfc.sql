-- =========================================================
-- Tarjetas NFC vinculadas a estudiantes
-- =========================================================
-- Ejecutar en PG Studio (Aiven) UNA VEZ.
--
-- Cada tarjeta física tiene un código único de fábrica (UID). Aquí
-- guardamos qué UID corresponde a qué estudiante. Un estudiante podría
-- tener más de una tarjeta con el tiempo (ej. si pierde la primera y
-- se le da una de repuesto), por eso el NIE no es único en esta tabla,
-- solo el UID.

CREATE TABLE IF NOT EXISTS tarjetas_nfc (
    id            SERIAL PRIMARY KEY,
    uid           VARCHAR(64) NOT NULL UNIQUE,
    nie           VARCHAR(20) NOT NULL REFERENCES estudiantes(nie) ON DELETE CASCADE,
    asignada_en   TIMESTAMP NOT NULL DEFAULT NOW()
);
