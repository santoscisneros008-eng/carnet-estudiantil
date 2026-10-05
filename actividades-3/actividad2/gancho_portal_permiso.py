# =========================================================
# Gancho a agregar DENTRO de portal_permiso() en app.py
# =========================================================
# Busca este bloque, que ya tienes (al final del "if dias_guardados:"):
#
#     if dias_guardados:
#         if fecha_inicio == fecha_fin:
#             flash(f"Constancia del {fecha_inicio.strftime('%d/%m/%Y')} subida correctamente.", "exito")
#         else:
#             flash(
#                 f"Constancia subida para {dias_guardados} día(s), "
#                 f"del {fecha_inicio.strftime('%d/%m/%Y')} al {fecha_fin.strftime('%d/%m/%Y')}.",
#                 "exito",
#             )
#     else:
#         flash("El rango elegido no tenía ningún día hábil por marcar.", "error")
#     return redirect(url_for("portal_permiso"))
#
# Reemplázalo por esta versión (le agrega la notificación antes del
# mensaje de éxito; todo lo demás queda igual):

    if dias_guardados:
        estudiante_notif = obtener_estudiante_por_nie(nie)
        if estudiante_notif:
            crear_notificacion_permiso(
                nie,
                estudiante_notif["nombres"],
                estudiante_notif["apellidos"],
                estudiante_notif["grado"],
                fecha_inicio,
                fecha_fin,
            )
        if fecha_inicio == fecha_fin:
            flash(f"Constancia del {fecha_inicio.strftime('%d/%m/%Y')} subida correctamente.", "exito")
        else:
            flash(
                f"Constancia subida para {dias_guardados} día(s), "
                f"del {fecha_inicio.strftime('%d/%m/%Y')} al {fecha_fin.strftime('%d/%m/%Y')}.",
                "exito",
            )
    else:
        flash("El rango elegido no tenía ningún día hábil por marcar.", "error")
    return redirect(url_for("portal_permiso"))
