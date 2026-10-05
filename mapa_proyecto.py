"""
mapa_proyecto.py
================
Arma un "mapa" de tu proyecto para saber que se usa y que sobra.

ES SOLO DE LECTURA: no borra, no mueve y no cambia ningun archivo.
No lee el contenido de .env ni de venv: el mapa solo trae NOMBRES y TAMANOS.

Uso (terminal de VS Code, dentro de la carpeta del proyecto, donde esta app.py):

    python mapa_proyecto.py

Crea mapa_proyecto.txt (y tambien lo muestra en pantalla).
"""

import re
import struct
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SALIDA = RAIZ / "mapa_proyecto.txt"
SCRIPT = Path(__file__).name

# Carpetas en las que NO se entra (solo se anota que existen)
PODAR = {"venv", ".venv", ".venv-1", ".git", "node_modules", "__pycache__"}

SIEMPRE_EN_USO = {
    "app.py": "la aplicacion",
    "requirements.txt": "dependencias (Render las instala)",
    ".gitignore": "lista de lo que NO va a GitHub",
    ".env.example": "plantilla de variables (sin contrasenas)",
    ".env": "tus contrasenas; vive SOLO en tu PC",
}
SCRIPTS_CONOCIDOS = {
    "crear_admin.py", "crear_login_estudiante.py", "vincular_tarjeta.py",
    "kiosko_nfc.py", "generate_qr.py", "juntar_proyecto.py", SCRIPT,
}


def leer(ruta):
    try:
        return ruta.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def archivos_git():
    """Archivos que git rastrea (lee .git/index). None si no se puede saber."""
    idx = RAIZ / ".git" / "index"
    try:
        data = idx.read_bytes()
        if data[:4] != b"DIRC":
            return None
        version, cuenta = struct.unpack(">II", data[4:12])
        if version not in (2, 3):
            return None
        pos, rutas = 12, set()
        for _ in range(cuenta):
            flags = struct.unpack(">H", data[pos + 60:pos + 62])[0]
            cabecera = 62 + (2 if (version == 3 and flags & 0x4000) else 0)
            nlen = flags & 0x0FFF
            ini = pos + cabecera
            fin = ini + nlen if nlen < 0xFFF else data.index(b"\x00", ini)
            nombre = data[ini:fin]
            rutas.add(nombre.decode("utf-8", "replace"))
            pos += (cabecera + len(nombre) + 8) & ~7
        return rutas
    except Exception:
        return None


def kb(n):
    return f"{max(1, round(n / 1024))} KB" if n else "0 KB"


def main():
    tracked = archivos_git()

    codigo_py = {p.name: leer(p) for p in RAIZ.glob("*.py")}
    plantillas = {p.name: leer(p) for p in (RAIZ / "templates").glob("*.html")} if (RAIZ / "templates").is_dir() else {}
    fuente = "\n".join(list(codigo_py.values()) + list(plantillas.values()))

    plantillas_usadas = set(re.findall(r"""render_template\(\s*["']([^"']+)["']""", "\n".join(codigo_py.values())))
    for t in plantillas.values():
        plantillas_usadas |= set(re.findall(r"""\{%\s*(?:extends|include)\s+["']([^"']+)["']""", t))
    estaticos_usados = set(re.findall(r"""filename\s*=\s*["']([^"']+)["']""", fuente))
    estaticos_usados |= set(re.findall(r"""/static/([A-Za-z0-9_./-]+)""", fuente))

    def importado_por(stem):
        patron = re.compile(r"^\s*(?:from|import)\s+" + re.escape(stem) + r"\b", re.M)
        return [n for n, t in codigo_py.items() if n != stem + ".py" and patron.search(t)]

    def git_de(rel, es_dir=False):
        if tracked is None:
            return ""
        if es_dir:
            return "git: si" if any(t.startswith(rel + "/") for t in tracked) else "git: NO"
        return "git: si" if rel in tracked else "git: NO"

    def clasificar_archivo(rel):
        """Devuelve (etiqueta, motivo) para un archivo."""
        p = Path(rel)
        partes = p.parts
        nombre = p.name
        if len(partes) == 1:
            if nombre in SIEMPRE_EN_USO:
                return "EN USO", SIEMPRE_EN_USO[nombre]
            if nombre.endswith(".py"):
                if nombre in SCRIPTS_CONOCIDOS:
                    return "EN USO", "script que se corre desde la terminal"
                quien = importado_por(p.stem)
                if quien:
                    return "EN USO", "lo importa " + ", ".join(quien)
                if "__main__" in codigo_py.get(nombre, ""):
                    return "REVISAR", "script con nombre que no reconozco"
                return "NO USO", "ningun archivo la importa y no es un script"
            if nombre.endswith(".sql"):
                return "REFERENCIA", "SQL ya aplicado en Aiven (respaldo/documentacion)"
            if nombre in ("proyecto_completo.txt", "mapa_proyecto.txt"):
                return "GENERADO", "archivo creado por un script, se puede borrar"
            if nombre.lower().endswith(".zip"):
                return "NO USO", "resto de una descarga"
            if nombre.lower() == "readme.md" or nombre.startswith("resumen"):
                return "REFERENCIA", "documentacion (puede estar desactualizada)"
            return "REVISAR", "no se que es"
        if partes[0] == "templates" and len(partes) == 2:
            if nombre in plantillas_usadas:
                return "EN USO", "una ruta o plantilla la usa"
            return "NO USO", "ninguna ruta ni plantilla la llama"
        if partes[0] == "static":
            sub = "/".join(partes[1:])
            if len(partes) > 1 and partes[1] in ("qr", "fotos"):
                return "REVISAR", "carpeta de una version antigua (hoy QR y fotos van en la base de datos)"
            if sub in estaticos_usados:
                return "EN USO", "una plantilla o el codigo la usa"
            return "NO USO", "nadie la referencia"
        return None, ""

    lineas = []
    resumen = {}

    def anotar(etq, rel, motivo, tam, git):
        resumen.setdefault(etq, []).append(rel)
        return f"[{etq:10}] {rel:46} {kb(tam):>8}  {git:9} {motivo}"

    alertas = []
    if tracked is not None:
        if ".env" in tracked:
            alertas.append("ALERTA: .env esta en GitHub (tiene tus contrasenas). Hay que quitarlo YA.")
        if any(t.startswith(("venv/", ".venv/")) for t in tracked):
            alertas.append("AVISO: la carpeta venv esta en GitHub y no deberia.")

    def recorrer(directorio, extra_etq=None, extra_motivo=""):
        for p in sorted(directorio.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            rel = p.relative_to(RAIZ).as_posix()
            if p.is_dir():
                if p.name in PODAR:
                    lineas.append(f"[IGNORADO  ] {rel + '/':46} {'':>8}  {'':9} contenido no se lee")
                    continue
                es_extra = directorio == RAIZ and p.name not in ("templates", "static")
                total = sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and not (set(f.relative_to(RAIZ).parts) & PODAR))
                if es_extra:
                    lineas.append(anotar("REVISAR", rel + "/", "carpeta extra del proyecto", total, git_de(rel, True)))
                    recorrer(p, "CARPETA EXTRA", "dentro de una carpeta extra")
                else:
                    lineas.append(f"             {rel + '/':46} {kb(total):>8}  {git_de(rel, True):9}")
                    recorrer(p, extra_etq, extra_motivo)
            else:
                if extra_etq:
                    etq, motivo = "REVISAR", extra_motivo
                else:
                    etq, motivo = clasificar_archivo(rel)
                    if etq is None:
                        etq, motivo = "REVISAR", "no se que es"
                lineas.append(anotar(etq, rel, motivo, p.stat().st_size, git_de(rel)))

    recorrer(RAIZ)

    salida = []
    salida.append("=" * 100)
    salida.append(" MAPA DEL PROYECTO  (solo lectura: este script no borra nada)")
    salida.append("=" * 100)
    salida.append("EN USO = el codigo lo necesita | NO USO = nadie lo referencia | REFERENCIA = documentacion/respaldo")
    salida.append("REVISAR = no estoy seguro | GENERADO = lo creo un script | IGNORADO = no se lee (venv, .git...)")
    if tracked is None:
        salida.append("(No pude leer la informacion de git; la columna 'git' queda vacia.)")
    salida.append("")
    salida.extend(alertas)
    if alertas:
        salida.append("")
    salida.extend(lineas)
    salida.append("")
    salida.append("RESUMEN")
    for etq in ("NO USO", "GENERADO", "REVISAR", "REFERENCIA", "EN USO"):
        if etq in resumen:
            salida.append(f"  {etq:10}: {len(resumen[etq])} archivo(s)")
    texto = "\n".join(salida)
    SALIDA.write_text(texto, encoding="utf-8")
    print(texto)
    print(f"\nListo. Tambien quedo guardado en {SALIDA.name}")


if __name__ == "__main__":
    main()
