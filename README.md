# Carné Digital de Estudiante — Flask + PostgreSQL (Aiven) + QR

Aplicación web liviana que muestra el carné digital de un estudiante al
escanear un código QR único (uno por cada NIE). Corre localmente en una
PC con Windows; cualquier celular en la **misma red Wi-Fi** puede
escanear el QR y ver el carné al instante. Los datos viven en una base
de datos PostgreSQL en la nube (Aiven).

```
carnet-estudiantil/
├── app.py                 # aplicación Flask
├── generate_qr.py         # genera un QR por cada estudiante
├── schema.sql              # script para crear la tabla en Aiven
├── requirements.txt
├── .env.example             # copiar como .env y rellenar
├── templates/
│   ├── inicio.html
│   ├── carnet.html
│   └── error.html
└── static/
    ├── css/style.css
    ├── qr/                  # aquí se guardan los PNG generados
    └── fotos/                # opcional, si guardas fotos localmente
```

---

## 1. Crear la base de datos en Aiven

1. Crea una cuenta en https://aiven.io y un servicio **PostgreSQL** (el plan
   gratuito "Hobbyist" alcanza para este proyecto).
2. Cuando el servicio esté "Running", entra a la pestaña **Overview /
   Connection information**. Ahí verás: `Host`, `Port`, `User`, `Password`,
   `Database name` y que exige SSL (`sslmode=require`).
3. Copia esos datos, los usarás en el paso 3.
4. Crea la tabla ejecutando `schema.sql` contra tu base. Dos formas:
   - **Desde la consola web de Aiven**: pestaña "Query editor" → pega el
     contenido de `schema.sql` → ejecutar.
   - **Desde tu PC con psql** (si lo tienes instalado):
     ```
     psql "postgresql://USUARIO:PASSWORD@HOST:PUERTO/BASEDATOS?sslmode=require" -f schema.sql
     ```

`schema.sql` crea la tabla `estudiantes` con un campo `nie` **único** (uno
por estudiante) y deja 2 registros de ejemplo para que puedas probar de
inmediato.

---

## 2. Preparar el proyecto en Windows

Requisitos: **Python 3.10+** instalado (verifica con `python --version`
en una terminal; si no lo tienes, instálalo desde python.org marcando
la opción "Add Python to PATH").

Abre **PowerShell** o **CMD** dentro de la carpeta del proyecto:

```bat
cd carnet-estudiantil

REM crear entorno virtual (recomendado)
python -m venv venv
venv\Scripts\activate

REM instalar dependencias
pip install -r requirements.txt
```

## 3. Configurar las credenciales de Aiven

Copia `.env.example` como `.env`:

```bat
copy .env.example .env
```

Abre `.env` con el Bloc de notas y coloca los datos reales de tu servicio
de Aiven (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`).
Deja `PGSSLMODE=require` tal cual (Aiven lo exige).

**Nunca subas el archivo `.env` a un repositorio público** — contiene la
contraseña de tu base de datos.

---

## 4. Levantar el servidor local

```bat
python app.py
```

Verás algo como:

```
Carné Digital corriendo
En esta misma PC:   http://127.0.0.1:5000
Desde el celular:   http://192.168.1.35:5000
   (el celular debe estar en la MISMA red Wi-Fi que esta PC)
```

Deja esa ventana abierta mientras uses el sistema: ahí vive el servidor.

> **Firewall de Windows**: la primera vez que ejecutes `app.py`, Windows
> puede preguntarte si permites el acceso a "redes privadas". Acepta,
> o los celulares no podrán conectarse.

---

## 5. Generar los códigos QR (uno por NIE)

Con el `.env` ya configurado y, idealmente, con `app.py` corriendo (para
confirmar la IP que se está usando), abre **otra** terminal en la misma
carpeta y ejecuta:

```bat
venv\Scripts\activate
python generate_qr.py
```

Esto:
1. Detecta automáticamente la IP local de tu PC en la red Wi-Fi actual.
2. Lee todos los NIE de la tabla `estudiantes` en Aiven.
3. Genera un PNG por estudiante en `static/qr/<NIE>.png`, codificando la
   URL exacta `http://TU_IP:5000/student/<NIE>`.

Cada vez que tu PC cambie de red (y por tanto de IP), vuelve a correr
`generate_qr.py` para regenerar los QR con la nueva IP — si no, los
códigos viejos apuntarán a una dirección que ya no existe.

Imprime o comparte esos PNG (por ejemplo, pégalos en el carné físico o
en una lista de estudiantes) para que cada quien escanee el suyo.

---

## 6. Probar desde el celular

1. Conecta el celular al **mismo Wi-Fi** que la PC (no datos móviles).
2. Escanea el QR de un estudiante, o entra manualmente a
   `http://TU_IP:5000/student/N0001` desde el navegador del celular.
3. Debe abrirse el carné digital de ese estudiante.

Si no carga: revisa que el Firewall de Windows no esté bloqueando Python,
que ambos dispositivos estén en la misma red (no en "redes de invitado"
aisladas), y que la IP en la URL sea la que imprimió `app.py`.

---

## 7. Siguientes pasos / mejoras posibles

- Agregar un panel de administración para dar de alta/baja estudiantes
  sin tocar SQL directamente.
- Subir fotos reales (hoy `foto_url` acepta cualquier URL de imagen; si
  luego quieres subir archivos desde la PC habría que añadir un endpoint
  de carga).
- Cuando quieras que el carné sea accesible fuera de tu red local (no solo
  LAN), desplegar `app.py` en un servicio en la nube (Render, Railway,
  Fly.io, etc.) — como ya usas Aiven para la base de datos, el cambio es
  mínimo: solo cambia dónde corre Flask, no cómo se conecta a la base.
