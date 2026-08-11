"""
Utilidades compartidas para generar códigos QR y detectar la IP local.
Usado tanto por generate_qr.py (script manual) como por app.py
(generación automática al dar de alta un estudiante desde el formulario).
"""

import os
import socket

import qrcode

CARPETA_QR = os.path.join("static", "qr")


def get_local_ip() -> str:
    """Obtiene la IP local (LAN) de esta PC en la red."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def generar_qr_para(nie: str, url: str, carpeta: str = CARPETA_QR) -> str:
    """Genera el PNG del QR para un NIE dado, apuntando a `url`. Devuelve la ruta guardada."""
    os.makedirs(carpeta, exist_ok=True)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1B2A4A", back_color="white")
    ruta = os.path.join(carpeta, f"{nie}.png")
    img.save(ruta)
    return ruta


def generar_qr_para_nie(nie: str, puerto: str) -> str:
    """Arma la URL del carné a partir del NIE y el puerto, y genera su QR."""
    ip_local = get_local_ip()
    url = f"http://{ip_local}:{puerto}/student/{nie}"
    return generar_qr_para(nie, url)
