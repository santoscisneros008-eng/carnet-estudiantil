"""
Modo "kiosco": deja UNA sola pantalla abierta en el navegador que se
actualiza sola cada vez que se acerca una tarjeta NFC — sin acumular
pestañas nuevas como hacía abrir_carnet_nfc.py.

Uso:
    python kiosko_nfc.py

Se abre el navegador automáticamente una sola vez. Puedes dejarlo en
pantalla completa (F11) todo el día. Ctrl+C en la terminal para
detenerlo.

Requiere: pip install pyscard   (Flask ya lo tienes instalado)
"""

import base64
import os
import socket
import sys
import threading
import time
import webbrowser

import psycopg2
from dotenv import load_dotenv
from flask import Flask, jsonify

load_dotenv()

try:
    from smartcard.CardMonitoring import CardMonitor, CardObserver
    from smartcard.util import toHexString
except ImportError:
    print("Falta instalar la librería del lector. Corre primero:")
    print("    pip install pyscard")
    sys.exit(1)

SITIO_URL = os.getenv("SITIO_URL", "https://carnet-estudiantil.onrender.com").rstrip("/")
PUERTO_KIOSKO = int(os.getenv("PUERTO_KIOSKO", "5050"))
SEGUNDOS_ENTRE_LECTURAS_REPETIDAS = 4
REINTENTOS_CONEXION = 3
SEGUNDOS_ENTRE_REINTENTOS = 1.5

estado_lock = threading.Lock()
estado = {"version": 0, "nie": None, "mensaje": None}


def cargar_logo_base64():
    """
    Incrusta el escudo institucional directamente en la página del kiosco
    (como texto base64), para no depender de ninguna ruta web externa —
    esta pantalla la sirve un mini-servidor aparte, sin conexión con
    app.py ni con Render.
    """
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img", "logo-100-anos.png")
    try:
        with open(ruta, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    except FileNotFoundError:
        return ""

# Guardamos la IP de la base de datos ya resuelta, para no tener que
# volver a preguntarle a internet "¿cuál es la dirección de este nombre?"
# cada vez que se pasa una tarjeta — que es justo donde nos ha fallado el
# DNS un par de veces. Si alguna vez la conexión falla, se vuelve a
# resolver el nombre desde cero (por si la IP cambió).
_ip_cache = {"ip": None}


def resolver_host_inicial():
    host = os.getenv("PGHOST")
    for intento in range(1, 6):
        try:
            _ip_cache["ip"] = socket.gethostbyname(host)
            print(f"[info] Base de datos localizada: {host} -> {_ip_cache['ip']}")
            return
        except socket.gaierror:
            print(f"[info] No se pudo resolver el servidor todavía (intento {intento}/5)...")
            time.sleep(2)
    print("[!] No se pudo localizar la base de datos al iniciar. Se seguirá intentando con cada tarjeta.")


def get_conn(forzar_reresolver=False):
    if forzar_reresolver:
        _ip_cache["ip"] = None
    host = _ip_cache["ip"] or os.getenv("PGHOST")
    return psycopg2.connect(
        host=host,
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        sslmode=os.getenv("PGSSLMODE", "require"),
        connect_timeout=8,
    )


def obtener_uid_de_atr(conexion):
    COMANDO_GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
    datos, sw1, sw2 = conexion.transmit(COMANDO_GET_UID)
    if sw1 == 0x90:
        return toHexString(datos).replace(" ", "")
    return None


def buscar_estudiante_por_uid(uid: str):
    """
    Consulta la base de datos con reintentos automáticos. Usa la IP ya
    resuelta para ir más rápido y evitar el punto donde antes fallaba el
    DNS; si aun así falla, en el siguiente intento vuelve a resolver el
    nombre desde cero (por si la IP hubiera cambiado).
    """
    ultimo_error = None
    for intento in range(1, REINTENTOS_CONEXION + 1):
        conn = None
        try:
            conn = get_conn(forzar_reresolver=(intento > 1))
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT e.nie, e.nombres, e.apellidos
                    FROM tarjetas_nfc t
                    JOIN estudiantes e ON e.nie = t.nie
                    WHERE t.uid = %s
                    """,
                    (uid,),
                )
                return cur.fetchone(), None
        except Exception as e:
            ultimo_error = e
            if intento < REINTENTOS_CONEXION:
                time.sleep(SEGUNDOS_ENTRE_REINTENTOS)
        finally:
            if conn is not None:
                conn.close()
    return None, ultimo_error


class ObservadorLector(CardObserver):
    def __init__(self):
        self._ultimo_uid = None
        self._ultima_vez = 0

    def update(self, observable, actions):
        (agregadas, _quitadas) = actions
        for tarjeta in agregadas:
            try:
                conexion = tarjeta.createConnection()
                conexion.connect()
                uid = obtener_uid_de_atr(conexion)
            except Exception:
                continue
            if not uid:
                continue

            ahora = time.time()
            if uid == self._ultimo_uid and (ahora - self._ultima_vez) < SEGUNDOS_ENTRE_LECTURAS_REPETIDAS:
                continue
            self._ultimo_uid = uid
            self._ultima_vez = ahora
            self._procesar(uid)

    def _procesar(self, uid: str):
        fila, error = buscar_estudiante_por_uid(uid)

        with estado_lock:
            estado["version"] += 1
            if error is not None:
                estado["nie"] = None
                estado["mensaje"] = "Error de conexión al leer la tarjeta. Vuelve a acercarla."
                print(f"[ERROR] Fallo de conexión al procesar {uid}: {error}")
            elif fila:
                nie, nombres, apellidos = fila
                estado["nie"] = nie
                estado["mensaje"] = None
                print(f"[OK] {nombres} {apellidos} (NIE {nie})")
            else:
                estado["nie"] = None
                estado["mensaje"] = f"Tarjeta no reconocida (UID: {uid})"
                print(f"[!] Tarjeta no reconocida (UID: {uid})")


# ---------------------------------------------------------------------------
# Pantalla del kiosco (servida localmente)
# ---------------------------------------------------------------------------

app = Flask(__name__)

PAGINA_KIOSKO = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Carné Digital · Kiosco</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    height: 100vh;
    background: linear-gradient(155deg, #6E1423 0%, #430B15 100%);
    font-family: -apple-system, "Segoe UI", sans-serif;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }
  #espera { text-align: center; color: #F5F1E6; }
  #espera .icono {
    width: 90px; height: 90px;
    border: 3px solid #C9A227;
    border-radius: 50%;
    margin: 0 auto 22px;
    display: flex; align-items: center; justify-content: center;
    font-size: 38px;
    background: white;
    overflow: hidden;
  }
  #espera .icono img { width: 100%; height: 100%; object-fit: contain; padding: 6px; box-sizing: border-box; }
  #espera h1 { font-size: 22px; font-weight: 600; margin-bottom: 8px; letter-spacing: 0.02em; }
  #espera p { color: #d9c9a8; font-size: 14px; }
  #mensaje-error { margin-top: 18px; color: #ffb4a0; font-size: 13px; min-height: 18px; }
  iframe { width: 100vw; height: 100vh; border: none; display: none; }
</style>
</head>
<body>
  <div id="espera">
    <div class="icono">__ICONO_HTML__</div>
    <h1>Sistema de Carné Digital</h1>
    <p>Acerca tu tarjeta al lector...</p>
    <div id="mensaje-error"></div>
  </div>
  <iframe id="carnet-frame"></iframe>

<script>
let ultimaVersion = 0;
const SITIO_URL = "__SITIO_URL__";

async function revisar() {
  try {
    const r = await fetch("/estado");
    const datos = await r.json();
    if (datos.version === ultimaVersion) return;
    ultimaVersion = datos.version;

    const espera = document.getElementById("espera");
    const frame = document.getElementById("carnet-frame");
    const errorDiv = document.getElementById("mensaje-error");

    if (datos.nie) {
      frame.src = SITIO_URL + "/student/" + datos.nie;
      frame.style.display = "block";
      espera.style.display = "none";
    } else if (datos.mensaje) {
      frame.style.display = "none";
      espera.style.display = "block";
      errorDiv.textContent = datos.mensaje;
      setTimeout(() => { errorDiv.textContent = ""; }, 5000);
    }
  } catch (e) {
    // sin conexión momentánea; se reintenta solo en el siguiente ciclo
  }
}
setInterval(revisar, 1000);
</script>
</body>
</html>
"""


@app.route("/")
def kiosko():
    logo = cargar_logo_base64()
    icono_html = f'<img src="{logo}" alt="Escudo institucional">' if logo else "&#128179;"
    return (
        PAGINA_KIOSKO
        .replace("__SITIO_URL__", SITIO_URL)
        .replace("__ICONO_HTML__", icono_html)
    )


@app.route("/estado")
def obtener_estado():
    with estado_lock:
        return jsonify(dict(estado))


def main():
    print("=" * 60)
    print(" Modo kiosco iniciando...")
    print(f" Sitio configurado: {SITIO_URL}")
    print(f" Pantalla del kiosco: http://127.0.0.1:{PUERTO_KIOSKO}")
    print(" Sugerencia: una vez abierta, presiona F11 para pantalla completa.")
    print(" Ctrl+C para detener.")
    print("=" * 60)

    resolver_host_inicial()

    monitor = CardMonitor()
    observador = ObservadorLector()
    monitor.addObserver(observador)

    threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PUERTO_KIOSKO}")).start()

    app.run(host="127.0.0.1", port=PUERTO_KIOSKO, debug=False)


if __name__ == "__main__":
    main()
