-- =========================================================
-- Foto de perfil del estudiante
-- =========================================================
-- Ejecutar en PG Studio (Aiven) UNA VEZ.
--
-- Guardamos la foto DENTRO de la base de datos (no como archivo en el
-- servidor), porque en Render los archivos subidos en tiempo de
-- ejecución no persisten entre despliegues. Así la foto queda segura
-- igual que el resto de los datos del estudiante.
--
-- Quitamos foto_url porque nunca llegó a usarse desde el formulario;
-- lo reemplazamos por el archivo real de la foto.

ALTER TABLE estudiantes DROP COLUMN IF EXISTS foto_url;
ALTER TABLE estudiantes ADD COLUMN IF NOT EXISTS foto BYTEA;
ALTER TABLE estudiantes ADD COLUMN IF NOT EXISTS foto_tipo VARCHAR(30);
