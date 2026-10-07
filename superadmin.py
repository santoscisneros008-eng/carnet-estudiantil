"""
superadmin.py
=============
Panel del ADMINISTRADOR GENERAL (fase 1).

Es un módulo aparte: se conecta a app.py con 2 líneas y NO modifica el login,
los paneles ni la cuenta de Dirección que ya existen.

Qué permite:
  - Gestionar cuentas de Dirección y de docentes (crear, editar, cambiar el
    usuario, restablecer contraseña, eliminar).
  - Editar estudiantes (datos, foto, estado), restablecer su contraseña del
    portal y quitar tarjetas NFC.
  - Ver la bitácora: quién cambió qué y cuándo (nunca guarda contraseñas).

Seguridad:
  - Login propio (/superadmin/login) con su propia tabla de cuentas.
  - Se bloquea 10 minutos tras 5 intentos fallidos con el mismo usuario.
  - La sesión se cierra tras 30 minutos sin actividad.
  - Todos los formularios llevan un token anti-falsificación (CSRF).
"""

import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from io import BytesIO

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from PIL import Image
from werkzeug.security import check_password_hash, generate_password_hash

try:  # igual que app.py: así la foto se guarda bien en PostgreSQL
    from psycopg2 import Binary as _Binario
except ImportError:  # pragma: no cover  (solo en pruebas sin PostgreSQL)
    _Binario = lambda datos: datos

# El Salvador no usa horario de verano: siempre UTC-6.
ZONA_HORARIA = timezone(timedelta(hours=-6))

MINUTOS_INACTIVIDAD = 30
MAX_INTENTOS = 5
BLOQUEO_MINUTOS = 10
POR_PAGINA = 50
LIMITE_ESTUDIANTES = 300
CLAVE_MINIMA = 6

ESTADOS = ("ACTIVO", "INACTIVO", "GRADUADO")
ROLES = ("director", "profesor")
ROL_NOMBRE = {"director": "Dirección", "profesor": "Docente"}
PATRON_USUARIO = re.compile(r"^[A-Za-z0-9._-]{3,50}$")
ALFABETO_CLAVES = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O, 1/l/I
CAMPOS_ESTUDIANTE = ("nombres", "apellidos", "carrera", "seccion", "grado",
                     "correo", "telefono", "estado", "fecha_nacimiento")
CAMPOS_OBLIGATORIOS = ("nombres", "apellidos", "estado")

ETIQUETAS_ACCION = {
    "login_ok": "Inició sesión",
    "login_fallido": "Intento de ingreso fallido",
    "logout": "Cerró sesión",
    "cuenta_creada": "Creó una cuenta",
    "cuenta_editada": "Editó una cuenta",
    "cuenta_clave": "Restableció la contraseña de una cuenta",
    "cuenta_eliminada": "Eliminó una cuenta",
    "estudiante_editado": "Editó un estudiante",
    "estudiante_clave": "Restableció la contraseña de un estudiante",
    "tarjeta_quitada": "Quitó una tarjeta NFC",
    "superadmin_creado": "Se creó un administrador general",
    "superadmin_clave": "Se cambió la contraseña de un administrador general",
}


def procesar_foto(archivo):
    """Redimensiona la foto a máx. 500x500 y la guarda como JPEG."""
    try:
        img = Image.open(archivo.stream).convert("RGB")
        img.thumbnail((500, 500))
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return buffer.getvalue(), "image/jpeg"
    except Exception:
        return None, None


def es_duplicado(error):
    """True si el error de la base de datos es 'ya existe' (valor único repetido)."""
    return getattr(error, "pgcode", None) == "23505" or type(error).__name__ in ("UniqueViolation", "IntegrityError")


def crear_blueprint_superadmin(get_conn, nombre_institucion):
    bp = Blueprint("superadmin", __name__, url_prefix="/superadmin")
    intentos_fallidos = {}
    clave_falsa = generate_password_hash("clave-que-no-existe")

    # ------------------------------------------------------------------
    # Acceso a la base de datos
    # ------------------------------------------------------------------
    def ahora():
        return datetime.now(ZONA_HORARIA).replace(tzinfo=None)

    def consulta(sql, params=(), uno=False):
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                columnas = [c[0] for c in cur.description]
                if uno:
                    fila = cur.fetchone()
                    return dict(zip(columnas, fila)) if fila else None
                return [dict(zip(columnas, fila)) for fila in cur.fetchall()]
        finally:
            conn.close()

    def escalar(sql, params=()):
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                fila = cur.fetchone()
                return fila[0] if fila else 0
        finally:
            conn.close()

    def ejecutar(*sentencias):
        """Ejecuta una o varias sentencias en UNA sola transacción: o se hacen todas, o ninguna."""
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                for sql, params in sentencias:
                    cur.execute(sql, params)
                filas = cur.rowcount
            conn.commit()
            return filas
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def registrar(accion, objeto="", detalle="", actor=None):
        """Anota en la bitácora. Si falla, avisa en consola pero no rompe la acción."""
        try:
            ejecutar((
                "INSERT INTO bitacora (fecha, actor, accion, objeto, detalle) VALUES (%s, %s, %s, %s, %s)",
                (ahora(), actor or session.get("sa_usuario", "?"), accion, (objeto or "")[:120], (detalle or "")[:2000]),
            ))
        except Exception as e:  # pragma: no cover
            print(f"[superadmin] No se pudo escribir en la bitácora: {e}")

    def grados_existentes():
        filas = consulta("SELECT DISTINCT grado FROM estudiantes WHERE grado IS NOT NULL AND grado <> '' ORDER BY grado")
        return [f["grado"] for f in filas]

    # ------------------------------------------------------------------
    # Contraseñas
    # ------------------------------------------------------------------
    def clave_automatica():
        return "".join(secrets.choice(ALFABETO_CLAVES) for _ in range(10))

    def resolver_clave(texto):
        """Devuelve (clave, fue_automatica, error). Vacío = generar una automática."""
        texto = texto or ""
        if not texto.strip():
            return clave_automatica(), True, None
        if len(texto) < CLAVE_MINIMA:
            return None, False, f"La contraseña debe tener al menos {CLAVE_MINIMA} caracteres."
        return texto, False, None

    # ------------------------------------------------------------------
    # Seguridad: token CSRF, sesión y protección de rutas
    # ------------------------------------------------------------------
    def csrf_token():
        if "sa_csrf" not in session:
            session["sa_csrf"] = secrets.token_hex(16)
        return session["sa_csrf"]

    def cerrar_sesion():
        for clave in ("sa_usuario", "sa_ultima", "sa_csrf"):
            session.pop(clave, None)

    @bp.context_processor
    def _contexto():
        return {
            "csrf_token": csrf_token,
            "institucion": nombre_institucion,
            "sa_usuario": session.get("sa_usuario"),
            "rol_nombre": ROL_NOMBRE,
        }

    @bp.app_template_filter("sa_fecha_hora")
    def _filtro_fecha_hora(valor):
        if valor is None:
            return "—"
        if hasattr(valor, "strftime"):
            return valor.strftime("%d/%m/%Y %I:%M %p")
        return str(valor)

    @bp.before_request
    def _proteger():
        es_login = request.endpoint == "superadmin.login"
        if not es_login:
            if not session.get("sa_usuario"):
                return redirect(url_for("superadmin.login"))
            ultima = session.get("sa_ultima")
            if ultima and ahora() - datetime.fromisoformat(ultima) > timedelta(minutes=MINUTOS_INACTIVIDAD):
                cerrar_sesion()
                flash("Tu sesión se cerró por inactividad. Entra de nuevo.", "aviso")
                return redirect(url_for("superadmin.login"))
        if request.method == "POST":
            enviado = request.form.get("csrf_token", "").encode()
            esperado = session.get("sa_csrf", "").encode()
            if not esperado or not hmac.compare_digest(enviado, esperado):
                abort(400)
        if not es_login:
            session["sa_ultima"] = ahora().isoformat()

    @bp.errorhandler(400)
    def _solicitud_invalida(_):
        return (
            "<p style='font-family:sans-serif;padding:40px'>La página caducó o la solicitud no es válida. "
            f"<a href='{url_for('superadmin.inicio')}'>Volver al inicio</a></p>",
            400,
        )

    # ------------------------------------------------------------------
    # Entrada y salida
    # ------------------------------------------------------------------
    @bp.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("sa_usuario"):
            return redirect(url_for("superadmin.inicio"))
        error = None
        if request.method == "POST":
            usuario = request.form.get("usuario", "").strip()
            clave = request.form.get("password", "")
            llave = usuario.lower()
            momento = ahora()
            if len(intentos_fallidos) > 1000:
                intentos_fallidos.clear()
            recientes = [t for t in intentos_fallidos.get(llave, []) if momento - t < timedelta(minutes=BLOQUEO_MINUTOS)]
            intentos_fallidos[llave] = recientes
            if len(recientes) >= MAX_INTENTOS:
                error = f"Demasiados intentos fallidos. Espera {BLOQUEO_MINUTOS} minutos e inténtalo de nuevo."
            else:
                fila = consulta("SELECT usuario, password_hash FROM superadmins WHERE usuario = %s", (usuario,), uno=True)
                coincide = check_password_hash(fila["password_hash"] if fila else clave_falsa, clave)
                if fila and coincide:
                    intentos_fallidos.pop(llave, None)
                    cerrar_sesion()
                    session["sa_usuario"] = fila["usuario"]
                    session["sa_ultima"] = ahora().isoformat()
                    session["sa_csrf"] = secrets.token_hex(16)
                    registrar("login_ok", actor=fila["usuario"])
                    return redirect(url_for("superadmin.inicio"))
                recientes.append(momento)
                registrar("login_fallido", objeto=usuario[:50], actor="(sin sesión)")
                error = "Usuario o contraseña incorrectos."
        return render_template("sa_login.html", error=error)

    @bp.route("/logout", methods=["POST"])
    def logout():
        registrar("logout")
        cerrar_sesion()
        return redirect(url_for("superadmin.login"))

    # ------------------------------------------------------------------
    # Inicio
    # ------------------------------------------------------------------
    def con_etiqueta(filas):
        for f in filas:
            f["etiqueta"] = ETIQUETAS_ACCION.get(f["accion"], f["accion"])
        return filas

    @bp.route("/")
    def inicio():
        datos = {
            "estudiantes": escalar("SELECT COUNT(*) FROM estudiantes"),
            "activos": escalar("SELECT COUNT(*) FROM estudiantes WHERE estado = %s", ("ACTIVO",)),
            "directores": escalar("SELECT COUNT(*) FROM admins WHERE rol = %s", ("director",)),
            "docentes": escalar("SELECT COUNT(*) FROM admins WHERE rol = %s", ("profesor",)),
            "sin_clave": escalar("SELECT COUNT(*) FROM estudiantes WHERE password_hash IS NULL OR password_hash = ''"),
            "sin_tarjeta": escalar(
                "SELECT COUNT(*) FROM estudiantes e WHERE NOT EXISTS (SELECT 1 FROM tarjetas_nfc t WHERE t.nie = e.nie)"
            ),
        }
        recientes = con_etiqueta(consulta("SELECT fecha, actor, accion, objeto FROM bitacora ORDER BY id DESC LIMIT 8"))
        return render_template("sa_inicio.html", datos=datos, recientes=recientes)

    # ------------------------------------------------------------------
    # Cuentas de Dirección y docentes
    # ------------------------------------------------------------------
    def listar_cuentas():
        return consulta("SELECT id, usuario, rol, grado, creado_en FROM admins ORDER BY rol, LOWER(usuario)")

    def obtener_cuenta(cuenta_id):
        return consulta("SELECT id, usuario, rol, grado, creado_en FROM admins WHERE id = %s", (cuenta_id,), uno=True)

    def validar_cuenta(usuario, rol, grado, validar_usuario=True):
        if validar_usuario and not PATRON_USUARIO.match(usuario):
            return "El usuario debe tener de 3 a 50 caracteres: letras, números, punto, guion o guion bajo, sin espacios."
        if rol not in ROLES:
            return "Elige un tipo de cuenta válido."
        if rol == "profesor" and not grado:
            return "Un docente necesita un salón asignado."
        return None

    def render_cuentas(form=None, clave_temporal=None):
        return render_template("sa_cuentas.html", cuentas=listar_cuentas(), grados=grados_existentes(),
                               form=form or {}, clave_temporal=clave_temporal, roles=ROLES)

    @bp.route("/cuentas")
    def cuentas():
        return render_cuentas()

    @bp.route("/cuentas/nueva", methods=["POST"])
    def cuenta_nueva():
        usuario = request.form.get("usuario", "").strip()
        rol = request.form.get("rol", "")
        grado = request.form.get("grado", "").strip()
        form = {"usuario": usuario, "rol": rol, "grado": grado}
        clave, automatica, error_clave = resolver_clave(request.form.get("password"))
        error = validar_cuenta(usuario, rol, grado) or error_clave
        if not error:
            grado_final = grado if rol == "profesor" else None
            try:
                ejecutar(("INSERT INTO admins (usuario, password_hash, rol, grado) VALUES (%s, %s, %s, %s)",
                          (usuario, generate_password_hash(clave), rol, grado_final)))
            except Exception as e:
                if not es_duplicado(e):
                    raise
                error = "Ya existe una cuenta con ese usuario."
        if error:
            flash(error, "error")
            return render_cuentas(form=form)
        detalle = f"tipo={ROL_NOMBRE[rol]}" + (f", salón={grado}" if rol == "profesor" else "")
        registrar("cuenta_creada", usuario, detalle)
        if automatica:
            return render_cuentas(clave_temporal={"para": usuario, "clave": clave})
        flash(f"Cuenta '{usuario}' creada.", "exito")
        return redirect(url_for("superadmin.cuentas"))

    def render_cuenta_editar(cuenta, clave_temporal=None):
        return render_template("sa_cuenta_editar.html", cuenta=cuenta, grados=grados_existentes(),
                               roles=ROLES, clave_temporal=clave_temporal)

    def cuenta_o_404(cuenta_id):
        cuenta = obtener_cuenta(cuenta_id)
        if cuenta is None:
            abort(404)
        return cuenta

    def es_ultimo_director(cuenta):
        return cuenta["rol"] == "director" and escalar("SELECT COUNT(*) FROM admins WHERE rol = %s", ("director",)) <= 1

    @bp.route("/cuentas/<int:cuenta_id>/editar", methods=["GET", "POST"])
    def cuenta_editar(cuenta_id):
        cuenta = cuenta_o_404(cuenta_id)
        if request.method == "GET":
            return render_cuenta_editar(cuenta)

        usuario = request.form.get("usuario", "").strip()
        rol = request.form.get("rol", "")
        grado = request.form.get("grado", "").strip()
        cambio_usuario = usuario != cuenta["usuario"]
        error = validar_cuenta(usuario, rol, grado, validar_usuario=cambio_usuario)
        if not error and not usuario:
            error = "El usuario no puede quedar vacío."
        if not error and es_ultimo_director(cuenta) and rol != "director":
            error = "No puedes cambiar el tipo de la única cuenta de Dirección: el colegio se quedaría sin acceso."
        grado_final = grado if rol == "profesor" else None
        if not error:
            cambios = []
            if cambio_usuario:
                cambios.append(f"usuario: '{cuenta['usuario']}' → '{usuario}'")
            if rol != cuenta["rol"]:
                cambios.append(f"tipo: {ROL_NOMBRE.get(cuenta['rol'], cuenta['rol'])} → {ROL_NOMBRE[rol]}")
            if (grado_final or "") != (cuenta["grado"] or ""):
                cambios.append(f"salón: '{cuenta['grado'] or ''}' → '{grado_final or ''}'")
            if not cambios:
                flash("No hiciste ningún cambio.", "aviso")
                return redirect(url_for("superadmin.cuenta_editar", cuenta_id=cuenta_id))
            sentencias = [("UPDATE admins SET usuario = %s, rol = %s, grado = %s WHERE id = %s",
                           (usuario, rol, grado_final, cuenta_id))]
            if cambio_usuario:  # que los avisos ya leídos sigan contando como leídos
                sentencias.append(("UPDATE notificaciones_leidas SET admin_usuario = %s WHERE admin_usuario = %s",
                                   (usuario, cuenta["usuario"])))
            try:
                ejecutar(*sentencias)
            except Exception as e:
                if not es_duplicado(e):
                    raise
                error = "Ya existe otra cuenta con ese usuario."
        if error:
            flash(error, "error")
            return render_cuenta_editar(dict(cuenta, usuario=usuario or cuenta["usuario"], rol=rol or cuenta["rol"], grado=grado))
        registrar("cuenta_editada", usuario, "; ".join(cambios))
        flash("Cuenta actualizada.", "exito")
        return redirect(url_for("superadmin.cuenta_editar", cuenta_id=cuenta_id))

    @bp.route("/cuentas/<int:cuenta_id>/clave", methods=["POST"])
    def cuenta_clave(cuenta_id):
        cuenta = cuenta_o_404(cuenta_id)
        clave, automatica, error = resolver_clave(request.form.get("password"))
        if error:
            flash(error, "error")
            return render_cuenta_editar(cuenta)
        ejecutar(("UPDATE admins SET password_hash = %s WHERE id = %s", (generate_password_hash(clave), cuenta_id)))
        registrar("cuenta_clave", cuenta["usuario"], "contraseña automática" if automatica else "contraseña definida por el administrador")
        if automatica:
            return render_cuenta_editar(cuenta, clave_temporal={"para": cuenta["usuario"], "clave": clave})
        flash("Contraseña actualizada.", "exito")
        return redirect(url_for("superadmin.cuenta_editar", cuenta_id=cuenta_id))

    @bp.route("/cuentas/<int:cuenta_id>/eliminar", methods=["POST"])
    def cuenta_eliminar(cuenta_id):
        cuenta = cuenta_o_404(cuenta_id)
        if es_ultimo_director(cuenta):
            flash("No puedes eliminar la única cuenta de Dirección: el colegio se quedaría sin acceso.", "error")
            return redirect(url_for("superadmin.cuenta_editar", cuenta_id=cuenta_id))
        ejecutar(
            ("DELETE FROM notificaciones_leidas WHERE admin_usuario = %s", (cuenta["usuario"],)),
            ("DELETE FROM admins WHERE id = %s", (cuenta_id,)),
        )
        registrar("cuenta_eliminada", cuenta["usuario"], f"tipo={ROL_NOMBRE.get(cuenta['rol'], cuenta['rol'])}, salón={cuenta['grado'] or '—'}")
        flash(f"Cuenta '{cuenta['usuario']}' eliminada.", "exito")
        return redirect(url_for("superadmin.cuentas"))

    # ------------------------------------------------------------------
    # Estudiantes
    # ------------------------------------------------------------------
    @bp.route("/estudiantes")
    def estudiantes():
        q = request.args.get("q", "").strip()
        grado = request.args.get("grado", "").strip()
        sql = (
            "SELECT e.nie, e.nombres, e.apellidos, e.grado, e.seccion, e.estado, "
            "(e.password_hash IS NOT NULL AND e.password_hash <> '') AS tiene_clave, "
            "(SELECT COUNT(*) FROM tarjetas_nfc t WHERE t.nie = e.nie) AS tarjetas "
            "FROM estudiantes e WHERE 1 = 1"
        )
        params = []
        if q:
            patron = f"%{q.lower()}%"
            sql += (" AND (LOWER(e.nombres) LIKE %s OR LOWER(e.apellidos) LIKE %s OR LOWER(e.nie) LIKE %s"
                    " OR LOWER(e.nombres || ' ' || e.apellidos) LIKE %s)")
            params += [patron, patron, patron, patron]
        if grado:
            sql += " AND LOWER(TRIM(e.grado)) = LOWER(TRIM(%s))"
            params.append(grado)
        sql += " ORDER BY e.grado, e.nombres, e.apellidos LIMIT %s"
        params.append(LIMITE_ESTUDIANTES + 1)
        filas = consulta(sql, params)
        hay_mas = len(filas) > LIMITE_ESTUDIANTES
        return render_template("sa_estudiantes.html", estudiantes=filas[:LIMITE_ESTUDIANTES], hay_mas=hay_mas,
                               limite=LIMITE_ESTUDIANTES, q=q, grado=grado, grados=grados_existentes())

    def obtener_estudiante(nie):
        return consulta(
            "SELECT nie, nombres, apellidos, carrera, seccion, grado, correo, telefono, estado, fecha_nacimiento, "
            "(foto IS NOT NULL) AS tiene_foto, "
            "(password_hash IS NOT NULL AND password_hash <> '') AS tiene_clave "
            "FROM estudiantes WHERE nie = %s", (nie,), uno=True)

    def estudiante_o_404(nie):
        est = obtener_estudiante(nie)
        if est is None:
            abort(404)
        return est

    def render_estudiante(est, clave_temporal=None):
        tarjetas = consulta("SELECT id, uid, asignada_en FROM tarjetas_nfc WHERE nie = %s ORDER BY id", (est["nie"],))
        return render_template("sa_estudiante_editar.html", est=est, tarjetas=tarjetas, grados=grados_existentes(),
                               estados=ESTADOS, clave_temporal=clave_temporal)

    def texto(valor):
        return "" if valor is None else str(valor)

    @bp.route("/estudiantes/<nie>/editar", methods=["GET", "POST"])
    def estudiante_editar(nie):
        est = estudiante_o_404(nie)
        if request.method == "GET":
            return render_estudiante(est)

        campos = {k: request.form.get(k, "").strip() for k in CAMPOS_ESTUDIANTE}
        error = None
        if any(not campos[k] for k in CAMPOS_OBLIGATORIOS):
            error = "Nombres, apellidos y estado son obligatorios."
        elif campos["estado"] not in ESTADOS:
            error = "El estado no es válido."
        if not error and campos["fecha_nacimiento"]:
            try:
                datetime.strptime(campos["fecha_nacimiento"], "%Y-%m-%d")
            except ValueError:
                error = "La fecha de nacimiento no es válida."
        foto_bytes = foto_tipo = None
        archivo = request.files.get("foto")
        if not error and archivo and archivo.filename:
            foto_bytes, foto_tipo = procesar_foto(archivo)
            if foto_bytes is None:
                error = "No pude leer esa imagen. Prueba con otra foto (JPG o PNG)."
        if error:
            flash(error, "error")
            return render_estudiante(dict(est, **campos))

        cambios = [f"{k}: '{texto(est.get(k))}' → '{campos[k]}'" for k in CAMPOS_ESTUDIANTE if texto(est.get(k)) != campos[k]]
        sentencias = []
        if cambios:
            sentencias.append((
                "UPDATE estudiantes SET nombres = %s, apellidos = %s, carrera = %s, seccion = %s, grado = %s, "
                "correo = %s, telefono = %s, estado = %s, fecha_nacimiento = %s WHERE nie = %s",
                (campos["nombres"], campos["apellidos"], campos["carrera"] or None, campos["seccion"] or None,
                 campos["grado"] or None, campos["correo"] or None, campos["telefono"] or None, campos["estado"],
                 campos["fecha_nacimiento"] or None, nie)))
        if foto_bytes:
            sentencias.append(("UPDATE estudiantes SET foto = %s, foto_tipo = %s WHERE nie = %s", (_Binario(foto_bytes), foto_tipo, nie)))
            cambios.append("foto actualizada")
        elif request.form.get("quitar_foto") == "1" and est["tiene_foto"]:
            sentencias.append(("UPDATE estudiantes SET foto = NULL, foto_tipo = NULL WHERE nie = %s", (nie,)))
            cambios.append("foto eliminada")
        if not sentencias:
            flash("No hiciste ningún cambio.", "aviso")
            return redirect(url_for("superadmin.estudiante_editar", nie=nie))
        ejecutar(*sentencias)
        registrar("estudiante_editado", f"{nie} {campos['nombres']} {campos['apellidos']}", "; ".join(cambios))
        flash("Estudiante actualizado.", "exito")
        return redirect(url_for("superadmin.estudiante_editar", nie=nie))

    @bp.route("/estudiantes/<nie>/clave", methods=["POST"])
    def estudiante_clave(nie):
        est = estudiante_o_404(nie)
        clave, automatica, error = resolver_clave(request.form.get("password"))
        if error:
            flash(error, "error")
            return render_estudiante(est)
        ejecutar(("UPDATE estudiantes SET password_hash = %s WHERE nie = %s", (generate_password_hash(clave), nie)))
        registrar("estudiante_clave", f"{nie} {est['nombres']} {est['apellidos']}",
                  "contraseña automática" if automatica else "contraseña definida por el administrador")
        if automatica:
            return render_estudiante(obtener_estudiante(nie), clave_temporal={"para": f"{est['nombres']} (NIE {nie})", "clave": clave})
        flash("Contraseña del portal actualizada.", "exito")
        return redirect(url_for("superadmin.estudiante_editar", nie=nie))

    @bp.route("/estudiantes/<nie>/tarjetas/<int:tarjeta_id>/quitar", methods=["POST"])
    def tarjeta_quitar(nie, tarjeta_id):
        est = estudiante_o_404(nie)
        tarjeta = consulta("SELECT id, uid FROM tarjetas_nfc WHERE id = %s AND nie = %s", (tarjeta_id, nie), uno=True)
        if tarjeta is None:
            abort(404)
        ejecutar(("DELETE FROM tarjetas_nfc WHERE id = %s AND nie = %s", (tarjeta_id, nie)))
        registrar("tarjeta_quitada", f"{nie} {est['nombres']} {est['apellidos']}", f"UID {tarjeta['uid']}")
        flash("Tarjeta quitada. Para vincular otra, usa vincular_tarjeta.py.", "exito")
        return redirect(url_for("superadmin.estudiante_editar", nie=nie))

    # ------------------------------------------------------------------
    # Bitácora
    # ------------------------------------------------------------------
    @bp.route("/bitacora")
    def bitacora():
        actor = request.args.get("actor", "").strip()
        accion = request.args.get("accion", "").strip()
        try:
            pagina = max(1, int(request.args.get("p", "1")))
        except ValueError:
            pagina = 1
        where, params = " WHERE 1 = 1", []
        if actor:
            where += " AND LOWER(actor) LIKE %s"
            params.append(f"%{actor.lower()}%")
        if accion:
            where += " AND accion = %s"
            params.append(accion)
        total = escalar("SELECT COUNT(*) FROM bitacora" + where, params)
        filas = con_etiqueta(consulta(
            "SELECT fecha, actor, accion, objeto, detalle FROM bitacora" + where + " ORDER BY id DESC LIMIT %s OFFSET %s",
            params + [POR_PAGINA, (pagina - 1) * POR_PAGINA]))
        paginas = max(1, -(-total // POR_PAGINA))
        return render_template("sa_bitacora.html", filas=filas, total=total, pagina=pagina, paginas=paginas,
                               actor=actor, accion=accion, acciones=ETIQUETAS_ACCION, por_pagina=POR_PAGINA)

    return bp
