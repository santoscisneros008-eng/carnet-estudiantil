"""
Asigna (o cambia) la contraseña de acceso al Portal del Estudiante.

El estudiante inicia sesión con su NIE como usuario — no hace falta
inventar un usuario aparte. Este script solo le pone/cambia la
contraseña.

Uso:
    python crear_login_estudiante.py

Corre este script una vez por cada estudiante al que quieras darle
acceso al portal (y de nuevo si alguna vez necesita restablecer su
contraseña).
"""

import getpass
import os

import psycopg2
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

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
    print("=" * 55)
    print(" Acceso al Portal del Estudiante")
    print("=" * 55)

    nie = input("\nNIE del estudiante: ").strip()
    if not nie:
        print("El NIE no puede quedar vacío. Cancelado.")
        return

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT nombres, apellidos FROM estudiantes WHERE nie = %s", (nie,))
            fila = cur.fetchone()
    finally:
        conn.close()

    if fila is None:
        print(f"No existe ningún estudiante con NIE '{nie}'. Revisa el dato e intenta de nuevo.")
        return

    print(f"Estudiante encontrado: {fila[0]} {fila[1]}")

    password = getpass.getpass("Contraseña nueva (no se mostrará en pantalla): ")
    password2 = getpass.getpass("Repite la contraseña: ")
    if password != password2:
        print("Las contraseñas no coinciden. Cancelado.")
        return
    if len(password) < 4:
        print("Usa una contraseña de al menos 4 caracteres. Cancelado.")
        return

    password_hash = generate_password_hash(password)

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE estudiantes SET password_hash = %s WHERE nie = %s",
                (password_hash, nie),
            )
        conn.commit()
    finally:
        conn.close()

    print(f"\nListo. {fila[0]} {fila[1]} ya puede entrar al portal con:")
    print(f"  NIE (usuario):  {nie}")
    print(f"  Contraseña:     la que acabas de escribir")


if __name__ == "__main__":
    main()
