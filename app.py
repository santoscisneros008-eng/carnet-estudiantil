"""
Carné Digital de Estudiantes
=============================
Aplicación Flask liviana que consulta un estudiante por su NIE en una
base de datos PostgreSQL alojada en Aiven y renderiza su carné digital.

Incluye un panel de administración con cuentas por rol:
  - DIRECTOR: ve todos los salones, siempre organizados por salón.
  - PROFESOR: ve y administra únicamente su propio salón (grado).

Al guardar un estudiante nuevo, su código QR se genera automáticamente.
Al abrir el carné (QR hoy, NFC en el futuro), se registra automáticamente
la hora de entrada o salida según la hora del día.

Pensada para correr localmente en una PC con Windows y ser accedida
desde celulares conectados a la MISMA red Wi-Fi.
"""

import os
from datetime import date, datetime
from functools import wraps
from io import BytesIO

import qrcode
from flask import Flask, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from werkzeug.security import check_password_hash

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from qr_utils import generar_qr_para_nie, get_local_ip

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "cambia-esta-clave-en-produccion")
# Permite que Flask detecte correctamente el dominio real (https, host) cuando
# corre detrás del proxy de Render (o cualquier otro hosting con proxy).
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

NOMBRE_INSTITUCION = os.getenv("NOMBRE_INSTITUCION", "Institución Educativa")

# Hora del día (0-23) que separa "entrada" de "salida" al abrir el carné.
HORA_CORTE_ASISTENCIA = int(os.getenv("HORA_CORTE_ASISTENCIA", "12"))

ESTADOS_VALIDOS = ("ACTIVO", "INACTIVO", "GRADUADO")


def get_conn():
    """Abre una conexión nueva contra la base de datos de Aiven."""
    return psycopg2.connect(
        host=os.getenv("PGHOST"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        sslmode=os.getenv("PGSSLMODE", "require"),
        connect_timeout=8,
    )


def _norm(txt):
    """Normaliza texto para comparar salones sin importar mayúsculas/espacios."""
    return (txt or "").strip().lower()


# ---------------------------------------------------------------------------
# Estudiantes
# ---------------------------------------------------------------------------

def obtener_estudiante_por_nie(nie: str):
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT nie, nombres, apellidos, carrera, seccion, grado,
                       correo, telefono, tipo_sangre, foto_url, estado,
                       fecha_ingreso
                FROM estudiantes
                WHERE nie = %s
                """,
                (nie,),
            )
            return cur.fetchone()
    finally:
        if conn is not None:
            conn.close()


def listar_estudiantes(grado: str = None):
    """Si `grado` viene dado, filtra solo ese salón (comparación sin distinguir
    mayúsculas/espacios). Si es None, devuelve todos, ordenados por salón."""
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if grado:
                cur.execute(
                    """
                    SELECT nie, nombres, apellidos, carrera, seccion, grado, estado
                    FROM estudiantes
                    WHERE LOWER(TRIM(grado)) = LOWER(TRIM(%s))
                    ORDER BY nombres, apellidos
                    """,
                    (grado,),
                )
            else:
                cur.execute(
                    """
                    SELECT nie, nombres, apellidos, carrera, seccion, grado, estado
                    FROM estudiantes
                    ORDER BY grado NULLS LAST, nombres, apellidos
                    """
                )
            return cur.fetchall()
    finally:
        if conn is not None:
            conn.close()


def obtener_grados_distintos():
    """Lista de salones ya usados en la base, para autocompletar/filtrar."""
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT grado FROM estudiantes WHERE grado IS NOT NULL AND grado <> '' ORDER BY grado"
            )
            return [fila[0] for fila in cur.fetchall()]
    finally:
        if conn is not None:
            conn.close()


def agrupar_por_grado(filas):
    """Agrupa una lista de estudiantes/registros (dict-like, con clave 'grado')
    en un diccionario ordenado {grado: [filas...]}."""
    grupos = {}
    for fila in filas:
        clave = fila.get("grado") or "Sin salón asignado"
        grupos.setdefault(clave, []).append(fila)
    return grupos


def crear_estudiante(datos: dict):
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO estudiantes
                    (nie, nombres, apellidos, carrera, seccion, grado,
                     correo, telefono, tipo_sangre, estado, fecha_ingreso)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    datos["nie"],
                    datos["nombres"],
                    datos["apellidos"],
                    datos["carrera"] or None,
                    datos["seccion"] or None,
                    datos["grado"] or None,
                    datos["correo"] or None,
                    datos["telefono"] or None,
                    datos["tipo_sangre"] or None,
                    datos["estado"],
                    datos["fecha_ingreso"] or None,
                ),
            )
        conn.commit()
        return True, None
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return False, f"Ya existe un estudiante registrado con el NIE '{datos['nie']}'."
    except Exception as e:
        if conn is not None:
            conn.rollback()
        return False, f"Ocurrió un error al guardar: {e}"
    finally:
        if conn is not None:
            conn.close()


def eliminar_estudiante(nie: str) -> bool:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM estudiantes WHERE nie = %s", (nie,))
            filas_borradas = cur.rowcount
        conn.commit()
        return filas_borradas > 0
    except Exception:
        if conn is not None:
            conn.rollback()
        return False
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Asistencia
# ---------------------------------------------------------------------------

def registrar_asistencia(nie: str):
    ahora = datetime.now()
    hoy = ahora.date()
    es_manana = ahora.hour < HORA_CORTE_ASISTENCIA
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            if es_manana:
                cur.execute(
                    """
                    INSERT INTO asistencias (nie, fecha, hora_entrada)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (nie, fecha)
                    DO UPDATE SET hora_entrada = COALESCE(asistencias.hora_entrada, EXCLUDED.hora_entrada)
                    """,
                    (nie, hoy, ahora.time()),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO asistencias (nie, fecha, hora_salida)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (nie, fecha)
                    DO UPDATE SET hora_salida = COALESCE(asistencias.hora_salida, EXCLUDED.hora_salida)
                    """,
                    (nie, hoy, ahora.time()),
                )
        conn.commit()
    except Exception:
        if conn is not None:
            conn.rollback()
    finally:
        if conn is not None:
            conn.close()


def listar_asistencia_por_fecha(fecha, grado: str = None):
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            consulta = """
                SELECT e.nie, e.nombres, e.apellidos, e.estado, e.grado,
                       a.hora_entrada, a.hora_salida
                FROM estudiantes e
                LEFT JOIN asistencias a
                    ON a.nie = e.nie AND a.fecha = %s
            """
            parametros = [fecha]
            if grado:
                consulta += " WHERE LOWER(TRIM(e.grado)) = LOWER(TRIM(%s))"
                parametros.append(grado)
            consulta += " ORDER BY e.grado NULLS LAST, e.nombres, e.apellidos"
            cur.execute(consulta, parametros)
            return cur.fetchall()
    finally:
        if conn is not None:
            conn.close()


def obtener_historial_asistencia(nie: str):
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT fecha, hora_entrada, hora_salida
                FROM asistencias
                WHERE nie = %s
                ORDER BY fecha DESC
                """,
                (nie,),
            )
            return cur.fetchall()
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Cuentas de administración (director / profesor por salón)
# ---------------------------------------------------------------------------

def obtener_admin(usuario: str):
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT usuario, password_hash, rol, grado FROM admins WHERE usuario = %s",
                (usuario,),
            )
            return cur.fetchone()
    finally:
        if conn is not None:
            conn.close()


def es_director() -> bool:
    return session.get("admin_rol") == "director"


def grado_sesion():
    """Salón de la cuenta logueada. None si es director (ve todos)."""
    return session.get("admin_grado")


def puede_administrar(estudiante) -> bool:
    """True si la cuenta logueada tiene permiso sobre este estudiante."""
    if es_director():
        return True
    return _norm(estudiante.get("grado")) == _norm(grado_sesion())


def requiere_login(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if not session.get("admin_usuario"):
            return redirect(url_for("admin_login", siguiente=request.path))
        return vista(*args, **kwargs)
    return envoltura


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        admin = obtener_admin(usuario)
        if admin and check_password_hash(admin["password_hash"], password):
            session["admin_usuario"] = admin["usuario"]
            session["admin_rol"] = admin["rol"]
            session["admin_grado"] = admin["grado"]
            siguiente = request.args.get("siguiente") or url_for("admin_lista")
            return redirect(siguiente)
        error = "Usuario o contraseña incorrectos."
    return render_template("admin_login.html", institucion=NOMBRE_INSTITUCION, error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


# ---------------------------------------------------------------------------
# Panel de administración
# ---------------------------------------------------------------------------

@app.route("/admin")
@requiere_login
def admin_lista():
    if es_director():
        grado_filtro = request.args.get("grado") or None
    else:
        grado_filtro = grado_sesion()

    estudiantes = listar_estudiantes(grado_filtro)
    grupos = agrupar_por_grado(estudiantes)

    return render_template(
        "admin_lista.html",
        grupos=grupos,
        institucion=NOMBRE_INSTITUCION,
        es_director=es_director(),
        grado_sesion=grado_sesion(),
        grado_filtro=grado_filtro,
        grados_existentes=obtener_grados_distintos() if es_director() else [],
    )


@app.route("/admin/nuevo", methods=["GET", "POST"])
@requiere_login
def admin_nuevo():
    salon_fijo = None if es_director() else grado_sesion()
    grados_existentes = obtener_grados_distintos()

    if request.method == "POST":
        datos = {
            "nie": request.form.get("nie", "").strip(),
            "nombres": request.form.get("nombres", "").strip(),
            "apellidos": request.form.get("apellidos", "").strip(),
            "carrera": request.form.get("carrera", "").strip(),
            "seccion": request.form.get("seccion", "").strip(),
            "grado": (salon_fijo or request.form.get("grado", "")).strip(),
            "correo": request.form.get("correo", "").strip(),
            "telefono": request.form.get("telefono", "").strip(),
            "tipo_sangre": request.form.get("tipo_sangre", "").strip(),
            "estado": request.form.get("estado", "ACTIVO"),
            "fecha_ingreso": request.form.get("fecha_ingreso", "").strip(),
        }

        if not datos["nie"] or not datos["nombres"] or not datos["apellidos"]:
            flash("NIE, nombres y apellidos son obligatorios.", "error")
            return render_template(
                "admin_nuevo.html", institucion=NOMBRE_INSTITUCION, datos=datos,
                salon_fijo=salon_fijo, grados_existentes=grados_existentes,
            )

        if not datos["grado"]:
            flash("Debes indicar el grado/salón del estudiante.", "error")
            return render_template(
                "admin_nuevo.html", institucion=NOMBRE_INSTITUCION, datos=datos,
                salon_fijo=salon_fijo, grados_existentes=grados_existentes,
            )

        if datos["estado"] not in ESTADOS_VALIDOS:
            datos["estado"] = "ACTIVO"

        ok, error = crear_estudiante(datos)
        if not ok:
            flash(error, "error")
            return render_template(
                "admin_nuevo.html", institucion=NOMBRE_INSTITUCION, datos=datos,
                salon_fijo=salon_fijo, grados_existentes=grados_existentes,
            )

        try:
            puerto = os.getenv("FLASK_PORT", "5000")
            generar_qr_para_nie(datos["nie"], puerto)
        except Exception:
            flash(
                "El estudiante se guardó, pero no se pudo generar su QR automáticamente. "
                "Puedes correr generate_qr.py manualmente.",
                "aviso",
            )

        flash(f"Estudiante '{datos['nombres']} {datos['apellidos']}' agregado correctamente.", "exito")
        return redirect(url_for("admin_lista"))

    return render_template(
        "admin_nuevo.html", institucion=NOMBRE_INSTITUCION, datos={},
        salon_fijo=salon_fijo, grados_existentes=grados_existentes,
    )


@app.route("/admin/eliminar/<nie>", methods=["POST"])
@requiere_login
def admin_eliminar(nie):
    estudiante = obtener_estudiante_por_nie(nie)
    if estudiante is None:
        flash(f"No se encontró ningún estudiante con NIE '{nie}'.", "error")
        return redirect(url_for("admin_lista"))

    if not puede_administrar(estudiante):
        flash("No tienes permiso para eliminar estudiantes de otro salón.", "error")
        return redirect(url_for("admin_lista"))

    borrado = eliminar_estudiante(nie)
    if borrado:
        ruta_qr = os.path.join("static", "qr", f"{nie}.png")
        if os.path.exists(ruta_qr):
            try:
                os.remove(ruta_qr)
            except OSError:
                pass
        flash(f"Estudiante con NIE '{nie}' eliminado.", "exito")
    else:
        flash(f"No se encontró ningún estudiante con NIE '{nie}'.", "error")
    return redirect(url_for("admin_lista"))


@app.route("/admin/asistencia")
@requiere_login
def admin_asistencia():
    fecha_str = request.args.get("fecha")
    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else date.today()
    except ValueError:
        fecha = date.today()

    if es_director():
        grado_filtro = request.args.get("grado") or None
    else:
        grado_filtro = grado_sesion()

    registros = listar_asistencia_por_fecha(fecha, grado_filtro)
    grupos = agrupar_por_grado(registros)

    return render_template(
        "admin_asistencia.html",
        grupos=grupos,
        fecha=fecha,
        hoy=date.today(),
        institucion=NOMBRE_INSTITUCION,
        es_director=es_director(),
        grado_filtro=grado_filtro,
        grados_existentes=obtener_grados_distintos() if es_director() else [],
    )


@app.route("/admin/asistencia/<nie>")
@requiere_login
def admin_asistencia_estudiante(nie):
    estudiante = obtener_estudiante_por_nie(nie)
    if estudiante is None:
        return render_template("error.html", nie=nie, institucion=NOMBRE_INSTITUCION), 404
    if not puede_administrar(estudiante):
        flash("No tienes permiso para ver la asistencia de otro salón.", "error")
        return redirect(url_for("admin_lista"))
    historial = obtener_historial_asistencia(nie)
    return render_template(
        "admin_asistencia_estudiante.html",
        est=estudiante,
        historial=historial,
        institucion=NOMBRE_INSTITUCION,
    )


@app.route("/admin/asistencia/<nie>/pdf")
@requiere_login
def admin_asistencia_estudiante_pdf(nie):
    estudiante = obtener_estudiante_por_nie(nie)
    if estudiante is None:
        return render_template("error.html", nie=nie, institucion=NOMBRE_INSTITUCION), 404
    if not puede_administrar(estudiante):
        flash("No tienes permiso para ver la asistencia de otro salón.", "error")
        return redirect(url_for("admin_lista"))

    historial = obtener_historial_asistencia(nie)

    color_vino = colors.HexColor("#6E1423")
    color_pizarra = colors.HexColor("#6B7280")
    color_linea = colors.HexColor("#E1DBC9")
    color_franja = colors.HexColor("#F5F1E6")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        title=f"Asistencia de {estudiante['nombres']} {estudiante['apellidos']}",
    )
    estilos = getSampleStyleSheet()
    estilo_institucion = ParagraphStyle(
        "Institucion", parent=estilos["Normal"], textColor=color_pizarra, fontSize=10, spaceAfter=6
    )
    estilo_titulo = ParagraphStyle(
        "TituloVino", parent=estilos["Title"], textColor=color_vino, fontSize=18, spaceAfter=10
    )
    estilo_info = ParagraphStyle("Info", parent=estilos["Normal"], fontSize=10.5, leading=16)

    contenido = []
    contenido.append(Paragraph(NOMBRE_INSTITUCION, estilo_institucion))
    contenido.append(
        Paragraph(f"Reporte de asistencia · {estudiante['nombres']} {estudiante['apellidos']}", estilo_titulo)
    )

    info_lineas = [
        f"<b>NIE:</b> {estudiante['nie']}",
        f"<b>Salón / Grado:</b> {estudiante['grado'] or '—'}",
        f"<b>Carrera:</b> {estudiante['carrera'] or '—'}",
        f"<b>Sección:</b> {estudiante['seccion'] or '—'}",
        f"<b>Generado el:</b> {datetime.now().strftime('%d/%m/%Y %I:%M %p')}",
    ]
    for linea in info_lineas:
        contenido.append(Paragraph(linea, estilo_info))
    contenido.append(Spacer(1, 18))

    datos_tabla = [["Fecha", "Entrada", "Salida"]]
    if historial:
        for h in historial:
            datos_tabla.append(
                [
                    h["fecha"].strftime("%d/%m/%Y"),
                    h["hora_entrada"].strftime("%I:%M %p") if h["hora_entrada"] else "—",
                    h["hora_salida"].strftime("%I:%M %p") if h["hora_salida"] else "—",
                ]
            )
    else:
        datos_tabla.append(["Sin marcaciones registradas todavía.", "", ""])

    tabla = Table(datos_tabla, colWidths=[6 * cm, 5 * cm, 5 * cm])
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), color_vino),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, color_linea),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, color_franja]),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    contenido.append(tabla)

    doc.build(contenido)
    buffer.seek(0)

    nombre_archivo = f"asistencia_{estudiante['nie']}.pdf"
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=nombre_archivo)


@app.route("/qr/<nie>.png")
def qr_estudiante(nie):
    """
    Genera el QR de un estudiante al vuelo (sin guardar archivos en disco),
    apuntando siempre al dominio real desde donde se está accediendo —
    funciona igual en local (IP de tu PC) que ya subido a internet
    (tu dominio de Render), sin necesitar reconfigurar nada.
    """
    estudiante = obtener_estudiante_por_nie(nie)
    if estudiante is None:
        return "", 404

    url = url_for("carnet", nie=nie, _external=True)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#6E1423", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")


# ---------------------------------------------------------------------------
# Rutas públicas (carné)
# ---------------------------------------------------------------------------

@app.route("/")
def inicio():
    return render_template("inicio.html", institucion=NOMBRE_INSTITUCION)


@app.route("/student/<nie>")
def carnet(nie):
    estudiante = obtener_estudiante_por_nie(nie)
    if estudiante is None:
        return render_template("error.html", nie=nie, institucion=NOMBRE_INSTITUCION), 404
    # No registrar marcación si quien abre el carné es un admin logueado
    # revisándolo desde el panel (evita marcaciones falsas).
    if not session.get("admin_usuario"):
        registrar_asistencia(nie)
    return render_template("carnet.html", est=estudiante, institucion=NOMBRE_INSTITUCION)


@app.errorhandler(404)
def no_encontrado(e):
    return render_template("error.html", nie=None, institucion=NOMBRE_INSTITUCION), 404


if __name__ == "__main__":
    puerto = int(os.getenv("FLASK_PORT", "5000"))
    ip_local = get_local_ip()
    print("=" * 60)
    print(" Carné Digital corriendo")
    print(f" En esta misma PC:   http://127.0.0.1:{puerto}")
    print(f" Desde el celular:   http://{ip_local}:{puerto}")
    print("   (el celular debe estar en la MISMA red Wi-Fi que esta PC)")
    print(f" Panel de administración: http://127.0.0.1:{puerto}/admin")
    print("=" * 60)
    app.run(host="0.0.0.0", port=puerto, debug=True)
