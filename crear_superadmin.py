"""
Crea (o cambia la contraseña de) una cuenta de ADMINISTRADOR GENERAL.

Es la única forma de crear la primera cuenta, porque desde la web hace
falta estar dentro para poder entrar.

Uso (terminal de VS Code, con el entorno activo):
    python crear_superadmin.py

Usa una contraseña LARGA (mínimo 10 caracteres) y no la compartas: esta
cuenta puede cambiar casi todo en el sistema.
"""

import getpass
import os
import re
from datetime import datetime, timedelta, timezone

import psycopg2
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

PATRON_USUARIO = re.compile(r"^[A-Za-z0-9._-]{3,50}$")


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
    print(" Cuenta de ADMINISTRADOR GENERAL")
    print("=" * 55)

    usuario = input("\nNombre de usuario (3 a 50 letras, números, punto, guion): ").strip()
    if not PATRON_USUARIO.match(usuario):
        print("Usuario no válido: usa solo letras, números, punto, guion o guion bajo, sin espacios. Cancelado.")
        return

    clave = getpass.getpass("Contraseña (mínimo 10 caracteres; no se mostrará): ")
    clave2 = getpass.getpass("Repite la contraseña: ")
    if clave != clave2:
        print("Las contraseñas no coinciden. Cancelado.")
        return
    if len(clave) < 10:
        print("Usa una contraseña de al menos 10 caracteres. Cancelado.")
        return

    ahora = datetime.now(timezone(timedelta(hours=-6))).replace(tzinfo=None)
    hash_clave = generate_password_hash(clave)

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM superadmins WHERE usuario = %s", (usuario,))
            existe = cur.fetchone() is not None
            if existe:
                cur.execute("UPDATE superadmins SET password_hash = %s WHERE usuario = %s", (hash_clave, usuario))
            else:
                cur.execute("INSERT INTO superadmins (usuario, password_hash) VALUES (%s, %s)", (usuario, hash_clave))
            cur.execute(
                "INSERT INTO bitacora (fecha, actor, accion, objeto, detalle) VALUES (%s, %s, %s, %s, %s)",
                (ahora, "(terminal)", "superadmin_clave" if existe else "superadmin_creado", usuario,
                 "contraseña cambiada desde la terminal" if existe else "cuenta creada desde la terminal"),
            )
        conn.commit()
    except psycopg2.errors.UndefinedTable:
        conn.rollback()
        print("\nFalta crear las tablas. Ejecuta primero schema_superadmin.sql en PG Studio.")
        return
    finally:
        conn.close()

    print(f"\nListo. Cuenta '{usuario}' {'actualizada' if existe else 'creada'}.")
    print("Entra en:  /superadmin/login")


if __name__ == "__main__":
    main()
