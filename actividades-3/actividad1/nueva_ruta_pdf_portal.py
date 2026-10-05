@app.route("/portal/asistencia/pdf")
@requiere_estudiante
def portal_asistencia_pdf():
    nie = session["estudiante_nie"]
    estudiante = obtener_estudiante_por_nie(nie)
    if estudiante is None:
        return render_template("error.html", nie=nie, institucion=NOMBRE_INSTITUCION), 404

    anio, mes = leer_mes_de_query()
    historial = obtener_historial_asistencia(nie, anio, mes)
    nombre_mes = MESES_ES[mes]

    color_vino = colors.HexColor("#6E1423")
    color_pizarra = colors.HexColor("#6B7280")
    color_linea = colors.HexColor("#E1DBC9")
    color_franja = colors.HexColor("#F5F1E6")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
        title=f"Asistencia de {estudiante['nombres']} {estudiante['apellidos']}",
    )
    estilos = getSampleStyleSheet()
    estilo_institucion = ParagraphStyle("InstitucionPortal", parent=estilos["Normal"],
                                         textColor=color_pizarra, fontSize=10, spaceAfter=6)
    estilo_titulo = ParagraphStyle("TituloVinoPortal", parent=estilos["Title"],
                                    textColor=color_vino, fontSize=18, spaceAfter=10)
    estilo_info = ParagraphStyle("InfoPortal", parent=estilos["Normal"], fontSize=10.5, leading=16)

    contenido = [
        Paragraph(NOMBRE_INSTITUCION, estilo_institucion),
        Paragraph(f"Reporte de asistencia · {estudiante['nombres']} {estudiante['apellidos']}", estilo_titulo),
    ]
    info_lineas = [
        f"<b>NIE:</b> {estudiante['nie']}",
        f"<b>Salón / Grado:</b> {estudiante['grado'] or '—'}",
        f"<b>Carrera:</b> {estudiante['carrera'] or '—'}",
        f"<b>Sección:</b> {estudiante['seccion'] or '—'}",
        f"<b>Mes reportado:</b> {nombre_mes} {anio}",
        f"<b>Generado el:</b> {datetime.now().strftime('%d/%m/%Y %I:%M %p')}",
    ]
    for linea in info_lineas:
        contenido.append(Paragraph(linea, estilo_info))
    contenido.append(Spacer(1, 18))

    datos_tabla = [["Fecha", "Entrada", "Salida"]]
    if historial:
        for h in historial:
            if h["hora_entrada"] or h["hora_salida"]:
                datos_tabla.append([
                    h["fecha"].strftime("%d/%m/%Y"),
                    h["hora_entrada"].strftime("%I:%M %p") if h["hora_entrada"] else "—",
                    h["hora_salida"].strftime("%I:%M %p") if h["hora_salida"] else "—",
                ])
            elif h.get("tiene_permiso"):
                datos_tabla.append([h["fecha"].strftime("%d/%m/%Y"), "Inasistencia con permiso", ""])
            else:
                datos_tabla.append([h["fecha"].strftime("%d/%m/%Y"), "Inasistencia", ""])
    else:
        datos_tabla.append(["Sin marcaciones registradas en este mes.", "", ""])

    tabla = Table(datos_tabla, colWidths=[6 * cm, 5 * cm, 5 * cm])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), color_vino),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, color_linea),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, color_franja]),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]))
    contenido.append(tabla)

    doc.build(contenido)
    buffer.seek(0)
    nombre_archivo = f"mi_asistencia_{nie}_{anio}-{mes:02d}.pdf"
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=nombre_archivo)


