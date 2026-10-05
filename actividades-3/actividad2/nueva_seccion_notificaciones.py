# =========================================================
# ACTIVIDAD 2 — Notificaciones de permisos para maestros/Dirección
# =========================================================
# Todo este bloque se pega en app.py. Ver instrucciones de dónde va
# cada parte en el mensaje del chat.


# ---------------------------------------------------------------------------
# Funciones de notificaciones (pegar junto a las demás funciones de BD,
# por ejemplo después de guardar_permiso / listar_permisos)
# ---------------------------------------------------------------------------

def crear_notificacion_permiso(nie, nombres, apellidos, grado, fecha_inicio, fecha_fin):
    """Avisa al maestro del salón (y a Dirección) que se subió una constancia."""
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notificaciones (nie, nombres, apellidos, grado, fecha_inicio, fecha_fin)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (nie, nombres, apellidos, grado, fecha_inicio, fecha_fin),
            )
        conn.commit()
    except Exception:
        if conn is not None:
            conn.rollback()
    finally:
        if conn is not None:
            conn.close()


def obtener_notificaciones(usuario_admin, es_dir, grado_propio):
    """Notificaciones visibles para esta cuenta: Dirección ve todas,
    un profesor solo las de su propio salón. Incluye si ya la leyó."""
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            consulta = """
                SELECT n.id, n.nie, n.nombres, n.apellidos, n.grado,
                       n.fecha_inicio, n.fecha_fin, n.creado_en,
                       (l.admin_usuario IS NOT NULL) AS leida
                FROM notificaciones n
                LEFT JOIN notificaciones_leidas l
                    ON l.notificacion_id = n.id AND l.admin_usuario = %s
            """
            parametros = [usuario_admin]
            if not es_dir:
                consulta += " WHERE LOWER(TRIM(n.grado)) = LOWER(TRIM(%s))"
                parametros.append(grado_propio)
            consulta += " ORDER BY n.creado_en DESC"
            cur.execute(consulta, parametros)
            return cur.fetchall()
    finally:
        if conn is not None:
            conn.close()


def contar_notificaciones_no_leidas(usuario_admin, es_dir, grado_propio):
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            consulta = """
                SELECT COUNT(*)
                FROM notificaciones n
                LEFT JOIN notificaciones_leidas l
                    ON l.notificacion_id = n.id AND l.admin_usuario = %s
                WHERE l.admin_usuario IS NULL
            """
            parametros = [usuario_admin]
            if not es_dir:
                consulta += " AND LOWER(TRIM(n.grado)) = LOWER(TRIM(%s))"
                parametros.append(grado_propio)
            cur.execute(consulta, parametros)
            fila = cur.fetchone()
            return fila[0] if fila else 0
    finally:
        if conn is not None:
            conn.close()


def marcar_notificacion_leida(notificacion_id, usuario_admin):
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notificaciones_leidas (notificacion_id, admin_usuario)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (notificacion_id, usuario_admin),
            )
        conn.commit()
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Context processor: deja el contador de avisos sin leer disponible en
# CUALQUIER plantilla de admin automáticamente (pegar junto al otro
# @app.context_processor que ya tienes, el de la foto del portal)
# ---------------------------------------------------------------------------

@app.context_processor
def inyectar_notificaciones_admin():
    if not session.get("admin_usuario"):
        return {}
    try:
        n = contar_notificaciones_no_leidas(session["admin_usuario"], es_director(), grado_sesion())
        return {"notif_no_leidas": n}
    except Exception:
        return {"notif_no_leidas": 0}


# ---------------------------------------------------------------------------
# Rutas (pegar junto a las demás rutas de /admin)
# ---------------------------------------------------------------------------

@app.route("/admin/notificaciones")
@requiere_login
def admin_notificaciones():
    usuario = session["admin_usuario"]
    notificaciones = obtener_notificaciones(usuario, es_director(), grado_sesion())
    return render_template(
        "admin_notificaciones.html",
        notificaciones=notificaciones,
        institucion=NOMBRE_INSTITUCION,
        es_director=es_director(),
    )


@app.route("/admin/notificaciones/<int:notif_id>/leida", methods=["POST"])
@requiere_login
def admin_notificacion_leida(notif_id):
    marcar_notificacion_leida(notif_id, session["admin_usuario"])
    return redirect(request.referrer or url_for("admin_notificaciones"))
