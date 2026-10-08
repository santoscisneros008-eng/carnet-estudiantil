"""
arreglar_app_final.py
Arregla el final de app.py para que Render pueda arrancarlo.
Guarda una copia (app.py.copia_antes_del_arreglo), corrige el archivo,
prueba que se importe como lo hace Render y, si la prueba falla,
restaura tu app.py original.
Uso: python arreglar_app_final.py
"""

import ast
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
APP = CARPETA / "app.py"
COPIA = CARPETA / "app.py.copia_antes_del_arreglo"
IMPORTAR = "from superadmin import crear_blueprint_superadmin"
REGISTRAR = "app.register_blueprint(crear_blueprint_superadmin(get_conn, NOMBRE_INSTITUCION))"
PATRON_MAIN = re.compile(r"""^if __name__ == ["']__main__["']\s*:\s*$""")


def ejecutar_python(codigo):
    entorno = dict(os.environ, PYTHONUTF8="1")
    return subprocess.run(
        [sys.executable, "-c", codigo], cwd=CARPETA, capture_output=True,
        encoding="utf-8", errors="replace", timeout=90, env=entorno,
    )


def ultima_linea(resultado):
    texto = (resultado.stderr or resultado.stdout or "").strip().splitlines()
    return texto[-1] if texto else "(sin mensaje)"


def probar_como_render():
    """Importa app.py sin ejecutarlo como programa principal, igual que gunicorn."""
    try:
        r = ejecutar_python("import app")
    except subprocess.TimeoutExpired:
        return False, "se quedo esperando (probablemente intento arrancar el servidor al importar)"
    if r.returncode != 0:
        return False, ultima_linea(r)
    if "Carn" in (r.stdout or "") and "corriendo" in (r.stdout or ""):
        return False, "al importar se ejecuto el bloque de arranque del servidor"
    return True, ""


def probar_pagina_login():
    """Pide /superadmin/login sin base de datos. Devuelve '200', otro codigo, o 'ERROR ...'."""
    codigo = (
        "import app\n"
        "app.app.config['PROPAGATE_EXCEPTIONS'] = True\n"
        "c = app.app.test_client()\n"
        "try:\n"
        "    print(c.get('/superadmin/login').status_code)\n"
        "except Exception as e:\n"
        "    print('ERROR ' + type(e).__name__ + ': ' + str(e)[:150])\n"
    )
    try:
        r = ejecutar_python(codigo)
    except subprocess.TimeoutExpired:
        return None
    lineas = (r.stdout or "").strip().splitlines()
    return lineas[-1] if r.returncode == 0 and lineas else None


def main():
    print("=" * 62)
    print(" Arreglo del final de app.py")
    print("=" * 62)

    if not APP.exists():
        print("No encuentro app.py aqui. Copia este script a la carpeta del proyecto.")
        return
    if not (CARPETA / "superadmin.py").exists():
        print("No encuentro superadmin.py en esta carpeta. Copialo primero (viene en superadmin-fase1.zip).")
        return

    original = APP.read_bytes().decode("utf-8")
    salto = "\r\n" if "\r\n" in original else "\n"
    texto = original.replace("\r\n", "\n")
    lineas = texto.split("\n")

    posiciones = [i for i, linea in enumerate(lineas) if PATRON_MAIN.match(linea)]
    if not posiciones:
        print('No encontre la linea  if __name__ == "__main__":  en app.py. No cambie nada.')
        return
    idx = posiciones[-1]

    es_nuestra = lambda l: l.strip().startswith(("from superadmin import", "app.register_blueprint(crear_blueprint_superadmin("))

    # Si hay mas de un "if __name__", los anteriores son restos de pegados viejos:
    # se quitan, pero solo si adentro no tienen codigo que no sea nuestro.
    quitar = set()
    for p in posiciones[:-1]:
        quitar.add(p)
        j = p + 1
        while j < len(lineas) and (not lineas[j].strip() or lineas[j].startswith((" ", "\t"))):
            if lineas[j].strip() and not es_nuestra(lineas[j]):
                print(f"Hay otro bloque 'if __name__' (linea {p + 1}) con codigo que no reconozco. No cambie nada.")
                return
            j += 1

    cabeza = [l for i, l in enumerate(lineas[:idx]) if i not in quitar and not es_nuestra(l)]
    cola = [l for l in lineas[idx + 1:] if not es_nuestra(l)]
    while cola and not cola[0].strip():
        cola.pop(0)
    if not any(l.strip() for l in cola):
        print("El bloque de arranque quedo vacio; no es lo esperado. No cambie nada.")
        return
    if any(l.strip() and not l.startswith((" ", "\t")) for l in cola):
        cola = [("    " + l) if l.strip() else l for l in cola]  # devolver la sangria

    while cabeza and not cabeza[-1].strip():
        cabeza.pop()
    nuevo = cabeza + ["", "", IMPORTAR, REGISTRAR, "", "", lineas[idx]] + cola
    nuevo_texto = "\n".join(nuevo).rstrip("\n") + "\n"

    try:
        ast.parse(nuevo_texto)
    except SyntaxError as e:
        print(f"El resultado no seria valido (linea {e.lineno}: {e.msg}). No cambie nada de tu app.py.")
        return

    cambiado = nuevo_texto.rstrip() != texto.rstrip()
    if cambiado:
        shutil.copy2(APP, COPIA)
        APP.write_bytes(nuevo_texto.replace("\n", salto).encode("utf-8"))
        print("Hecho el arreglo. Copia de seguridad: app.py.copia_antes_del_arreglo")
    else:
        print("El final de app.py ya tenia la estructura correcta; no hizo falta cambiar nada.")

    print("\nProbando que app.py se importe como lo hace Render...")
    ok, detalle = probar_como_render()
    if not ok:
        if cambiado:
            shutil.copy2(COPIA, APP)
            print("LA PRUEBA FALLO y deje tu app.py exactamente como estaba.")
        else:
            print("LA PRUEBA FALLO.")
        print("Motivo:", detalle)
        print("Copia ese motivo y mandamelo.")
        return

    print("  OK: app.py se importa sin errores y sin arrancar el servidor.")
    resultado = probar_pagina_login()
    if resultado == "200":
        print("  OK: la pagina /superadmin/login responde (codigo 200).")
    elif resultado and resultado.startswith("ERROR"):
        print("  Aviso: la pagina de login del Administrador general dio un error:")
        print("   ", resultado)
        print("  El arreglo del arranque esta hecho, pero mandame ese aviso.")
    elif resultado:
        print(f"  Aviso: /superadmin/login respondio con codigo {resultado} (esperado 200).")

    print("\nTodo listo. Ahora corre 'python app.py' una vez para confirmar, y despues sube a GitHub.")
    if cambiado:
        print("Despues borra el archivo app.py.copia_antes_del_arreglo (es solo tu respaldo).")


if __name__ == "__main__":
    main()