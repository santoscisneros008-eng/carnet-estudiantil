"""
Vincula una tarjeta NFC física al NIE de un estudiante.

Uso:
    python vincular_tarjeta.py

Requiere: pip install pyscard
"""

import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()

try:
    from smartcard.CardMonitoring import CardMonitor, CardObserver
    from smartcard.util import toHexString
except ImportError:
    print("Falta instalar la librería del lector. Corre primero:")
    print("    pip install pyscard")
    sys.exit(1)


def get_conn():
    return psycopg2.connect(
        host=os.getenv("PGHOST"),
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


def vincular(nie: str):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM estudiantes WHERE nie = %s", (nie,))
            if cur.fetchone() is None:
                print(f"No existe ningún estudiante con NIE '{nie}'. Revisa el dato e intenta de nuevo.")
                return
    finally:
        conn.close()

    print("\nAcerca la tarjeta al lector ahora... (Ctrl+C para cancelar)")

    resultado = {"uid": None}

    class Observador(CardObserver):
        def update(self, observable, actions):
            (agregadas, _quitadas) = actions
            for tarjeta in agregadas:
                try:
                    conexion = tarjeta.createConnection()
                    conexion.connect()
                    uid = obtener_uid_de_atr(conexion)
                    if uid:
                        resultado["uid"] = uid
                except Exception:
                    pass

    monitor = CardMonitor()
    observador = Observador()
    monitor.addObserver(observador)

    import time
    segundos_espera = 0
    while resultado["uid"] is None and segundos_espera < 20:
        time.sleep(0.3)
        segundos_espera += 0.3

    monitor.deleteObserver(observador)

    if resultado["uid"] is None:
        print("No se detectó ninguna tarjeta en 20 segundos. Intenta de nuevo.")
        return

    uid = resultado["uid"]
    print(f"Tarjeta detectada. UID: {uid}")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tarjetas_nfc (uid, nie)
                VALUES (%s, %s)
                ON CONFLICT (uid) DO UPDATE SET nie = EXCLUDED.nie, asignada_en = NOW()
                """,
                (uid, nie),
            )
        conn.commit()
        print(f"Listo. La tarjeta {uid} quedó vinculada al NIE {nie}.")
    finally:
        conn.close()


def main():
    print("=" * 55)
    print(" Vincular tarjeta NFC a un estudiante")
    print("=" * 55)
    nie = input("\nNIE del estudiante: ").strip()
    if not nie:
        print("El NIE no puede quedar vacío.")
        return
    vincular(nie)


if __name__ == "__main__":
    main()
