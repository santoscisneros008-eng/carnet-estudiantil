"""
Crea o actualiza una cuenta de administración: DIRECTOR (ve todos los
salones) o PROFESOR (ve únicamente su propio salón/grado).

La contraseña nunca se guarda en texto plano — este script la encripta
(hashea) antes de mandarla a la base de datos.

Uso:
    python crear_admin.py
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
    print(" Crear cuenta de administración")
    print("=" * 55)

    print("\n¿Qué tipo de cuenta es?")
    print("  1) Director  (ve TODOS los salones)")
    print("  2) Profesor  (ve solo UN salón)")
    opcion = input("Elige 1 o 2: ").strip()

    if opcion == "1":
        rol = "director"
        grado = None
    elif opcion == "2":
        rol = "profesor"
        grado = input("Grado/salón exacto que administrará (ej. 'Segundo Año'): ").strip()
        if not grado:
            print("El grado no puede quedar vacío para un profesor. Cancelado.")
            return
    else:
        print("Opción no válida. Cancelado.")
        return

    usuario = input("Nombre de usuario (para iniciar sesión): ").strip()
    if not usuario:
        print("El usuario no puede quedar vacío. Cancelado.")
        return

    password = getpass.getpass("Contraseña (no se mostrará en pantalla): ")
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
                """
                INSERT INTO admins (usuario, password_hash, rol, grado)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (usuario)
                DO UPDATE SET password_hash = EXCLUDED.password_hash,
                              rol = EXCLUDED.rol,
                              grado = EXCLUDED.grado
                """,
                (usuario, password_hash, rol, grado),
            )
        conn.commit()
    finally:
        conn.close()

    if rol == "director":
        print(f"\nListo. Cuenta DIRECTOR '{usuario}' creada/actualizada (ve todos los salones).")
    else:
        print(f"\nListo. Cuenta PROFESOR '{usuario}' creada/actualizada para el salón '{grado}'.")


if __name__ == "__main__":
    main()
