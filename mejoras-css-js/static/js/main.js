/**
 * Carné Digital — interactividad compartida.
 *  - Los mensajes de aviso (flash) se desvanecen solos después de unos segundos.
 *  - El buscador en vivo filtra las tablas de estudiantes/asistencia mientras escribes.
 *  - Pequeñas animaciones de entrada para que las filas no aparezcan de golpe.
 *
 * Nota: se usan bucles for clásicos en vez de NodeList.forEach a propósito,
 * para que funcione también en navegadores/WebViews más antiguos.
 */

document.addEventListener("DOMContentLoaded", function () {
  desvanecerAvisos();
  activarBuscador();
  animarFilasEnCascada();
  activarBotonesDeCarga();
});

/* ---------- Avisos (flash) que se desvanecen solos ---------- */
function desvanecerAvisos() {
  var avisos = document.querySelectorAll(".flash");
  for (var i = 0; i < avisos.length; i++) {
    (function (aviso, indice) {
      setTimeout(function () {
        aviso.className += " flash--saliendo";
        setTimeout(function () {
          if (aviso.parentNode) aviso.parentNode.removeChild(aviso);
        }, 400);
      }, 4500 + indice * 300);
    })(avisos[i], i);
  }
}

/* ---------- Buscador en vivo para tablas agrupadas por salón ---------- */
function activarBuscador() {
  var buscador = document.getElementById("buscador");
  if (!buscador) return;

  var mensajeVacio = document.getElementById("buscador-sin-resultados");

  buscador.addEventListener("input", function () {
    var termino = normalizarTexto(buscador.value.replace(/^\s+|\s+$/g, ""));
    var huboResultados = false;

    var secciones = document.querySelectorAll(".salon-seccion");
    for (var s = 0; s < secciones.length; s++) {
      var seccion = secciones[s];
      var filas = seccion.querySelectorAll("tbody tr");
      var filasVisiblesEnSeccion = 0;

      for (var f = 0; f < filas.length; f++) {
        var fila = filas[f];
        var texto = normalizarTexto(fila.textContent || fila.innerText || "");
        var coincide = termino === "" || texto.indexOf(termino) !== -1;
        fila.style.display = coincide ? "" : "none";
        if (coincide) filasVisiblesEnSeccion++;
      }

      var seccionTieneResultados = filasVisiblesEnSeccion > 0;
      seccion.style.display = seccionTieneResultados ? "" : "none";
      if (seccionTieneResultados) huboResultados = true;
    }

    if (mensajeVacio) {
      mensajeVacio.style.display = (huboResultados || termino === "") ? "none" : "block";
    }
  });
}

function normalizarTexto(texto) {
  texto = texto.toLowerCase();
  if (typeof texto.normalize === "function") {
    texto = texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  } else {
    // Respaldo simple para navegadores muy antiguos sin String.normalize
    var mapa = { "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n" };
    texto = texto.replace(/[áéíóúñ]/g, function (letra) { return mapa[letra]; });
  }
  return texto;
}

/* ---------- Animación de entrada en cascada para filas de tabla ---------- */
function animarFilasEnCascada() {
  var filas = document.querySelectorAll(".admin-tabla tbody tr");
  for (var i = 0; i < filas.length; i++) {
    filas[i].style.animationDelay = Math.min(i * 25, 400) + "ms";
    filas[i].className += " fila-entrada";
  }
}

/* ---------- Botones: muestran un texto de "cargando" al enviar ----------
   Por defecto dice "Guardando..." (o "Eliminando..." si es btn-eliminar),
   pero se puede personalizar poniendo data-cargando="Entrando..." en el
   botón, como se hace en el de iniciar sesión. */
function activarBotonesDeCarga() {
  var formularios = document.querySelectorAll("form");
  for (var i = 0; i < formularios.length; i++) {
    formularios[i].addEventListener("submit", function () {
      // Si el formulario tenía un confirm() (como el de "Eliminar") y el
      // usuario canceló, este evento nunca llega a dispararse — así que
      // si llegamos aquí es porque el envío sí va a ocurrir de verdad.
      var boton = this.querySelector("button[type=submit]");
      if (!boton || boton.disabled) return;

      var textoCarga = boton.getAttribute("data-cargando");
      if (!textoCarga) {
        textoCarga = boton.className.indexOf("btn-eliminar") !== -1 ? "Eliminando..." : "Guardando...";
      }

      boton.disabled = true;
      boton.className += " btn--cargando";
      boton.textContent = textoCarga;
    });
  }
}
