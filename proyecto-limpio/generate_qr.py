"""
Genera un código QR por cada estudiante, como archivo PNG local — útil
si quieres imprimir los QR físicos como respaldo (por ejemplo, para
pegarlos en un carné de papel o una lista).

Nota: esto es un respaldo opcional. El QR también se puede ver en
cualquier momento sin correr este script, entrando directamente a
/qr/<NIE>.png en el sitio (funciona local o ya desplegado, se genera
al vuelo).

Uso:
    python generate_qr.py

Los PNG se guardan en static/qr/<nie>.png, apuntando a la IP local de
esta PC. Vuelve a correrlo si cambias de red Wi-Fi.
"""

import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from qr_utils import CARPETA_QR, generar_qr_para, get_local_ip

load_dotenv()


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


def main():
    puerto = os.getenv("FLASK_PORT", "5000")
    ip_local = get_local_ip()
    base_url = f"http://{ip_local}:{puerto}/student"

    print(f"IP local detectada: {ip_local}")
    print(f"Los QR apuntarán a URLs como: {base_url}/<NIE>\n")

    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT nie, nombres, apellidos FROM estudiantes ORDER BY nie")
            estudiantes = cur.fetchall()
    finally:
        conn.close()

    if not estudiantes:
        print("No hay estudiantes en la base de datos todavía.")
        return

    for est in estudiantes:
        url = f"{base_url}/{est['nie']}"
        ruta = generar_qr_para(est["nie"], url, CARPETA_QR)
        print(f"OK  {est['nie']}  -  {est['nombres']} {est['apellidos']}  ->  {ruta}")

    print(f"\nListo. {len(estudiantes)} código(s) QR generado(s) en '{CARPETA_QR}'.")


if __name__ == "__main__":
    main()
