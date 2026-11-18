# 01 — Contratos, motores y salidas del CLI 0.2.0

Fecha: 2026-11-18, America/Bogota. Estado: especificación para implementación futura.
Rama futura: `refactor/0_2_0_sami_cli`. Unidades: U00, U01 y U02.
Leer primero: [índice y decisiones del usuario](2026-11-18_10-31-38_analisis-diseno-refactor-sami.md).
Siguiente: [02 — diagnóstico e instalación](02-cli-diagnostico-runtime-instalacion.md).

## Resultado de esta etapa

Un contrato público probado y dos adaptadores de motor que producen resultados comparables a sus referencias, sin depender de terminal, instalación o UI. Las pruebas de esta etapa pueden inyectar un runtime preparado; su preparación final se implementa en el plan 02. No declarar el CLI listo para release hasta terminar el plan 03.

## Archivos y responsabilidades

| Archivo actual o futuro | Trabajo concreto |
|---|---|
| `sami/cli.py` | Conservar entrada pública; mover parsing/dispatch a una capa ligera. Nada de modelos, señales o descarga al importar el módulo. |
| `sami/contracts.py` | Petición, opciones, resultado, referencias recuperadas y errores tipados. Dataclasses/esquemas simples. |
| `sami/events.py` | Envelope y serialización del protocolo 1; stdout JSONL independiente del logging. |
| `sami/engines/marker.py` | Mover `VerboseConverter`, construcción/renderizado y escritura de figuras de la integración actual sin cambiar su lógica de contenido. |
| `sami/engines/fast.py` | Extraer funciones necesarias de Caste y configurar la ruta efectiva del lote. |
| `sami/engines/__init__.py` | Elegir adaptador mediante tabla de modos; imports diferidos. |
| `sami/outputs.py` | Reservar identidad, staging, numerar y publicar sin pisar salidas. |
| `sami/validation.py` | Estados parciales, vacíos y consistencia, separados de transformaciones. |
| `tests/test_contracts.py`, `test_engines.py`, `test_outputs.py`, `test_references.py` | Contrato y resultados observables, no copias de las funciones de producción. |
| `test-pdfs/`, `tests/fixtures/` | Corpus mínimo reproducible con expectativas de contenido/links/tablas. |

## U00 — Viabilidad y línea base, antes de refactorizar

1. Registrar SHA, versiones resueltas de Marker/Surya/Torch y modelos de la instalación de referencia. El proyecto fija Marker `2.0.0`; no actualizarlo silenciosamente como parte de mover funciones.
2. Convertir los dos PDF existentes con los dos modos actuales, conservando referencias mediante `--no-strip-refs`. Guardar resultados y métricas fuera del árbol de fuentes; fijar expectativas pequeñas de texto, figuras, tablas y ecuaciones.
3. Medir el lote Caste con `high/ocr=False/images=False`, separando conversión de la auditoría aleatoria posterior. Medir arranque y conversión estable por separado, sobre los mismos PDF/equipo.
4. Probar una ruta CPU real para ambos perfiles Marker en Windows 11 y en una base Debian/Ubuntu elegida. Confirmar binario del servidor, dependencias y que los modelos pueden quedar completamente locales. El motor `fast` no necesita esa inferencia.
5. Registrar matriz `SO/arquitectura/driver/runtime/modelo/motor → probado/no probado/no compatible` y restricciones de RAM. Proponer x86_64 inicialmente; fijar versiones mínimas con evidencia, no por el nombre de la distribución.

**Cierre:** evidencia reproducible de la base y de viabilidad CPU. Si un perfil no puede ejecutar en CPU en una plataforma obligatoria, resolver esa dependencia antes de declarar soporte; no sustituir Marker por otro conversor ni reducir el modo sin discutir el cambio de producto.

## U01 — Contrato y preservación de Marker

### Tabla de modos

| Modo público | Implementación | Default |
|---|---|---|
| `fast` | Caste con su configuración interna `high`, OCR e imágenes apagados. | No. |
| `balanced` | SAMI/Marker con el modo interno `fast`. | Sí. |
| `quality` | SAMI/Marker con el modo interno `balanced`. | No. |

Mover desde `sami/cli.py` las funciones de conversión y el subclassing necesarios al adaptador. Mantener el orden provider → document → layout → líneas → highres → OCR → estructura → procesadores → renderizado. Reemplazar los `print` de progreso por callbacks; no cambiar algoritmos ni posprocesar su prosa con heurísticas Caste.

Eliminar la llamada a `strip_references` de la ruta nueva. `--no-strip-refs` se acepta para compatibilidad y no cambia el resultado. Mantener figuras y referencias generadas por Marker. La nueva política de bibliografía/enlaces y la publicación segura son diferencias intencionales respecto al default antiguo.

### Tipos mínimos

| Tipo | Campos y regla |
|---|---|
| `ConversionRequest` | `job_id`, ruta PDF absoluta, modo, opciones, carpeta staging, dispositivo y `attempt`. No contiene objetos UI. |
| `EngineResult` | Cuerpo Markdown, recursos relativos producidos, páginas procesadas, advertencias, vacíos y métricas. No publica archivos finales. |
| `JobResult` | Input, `mode`, motor/dispositivo efectivos, estado, rutas finales, advertencias/errores, duración y número de intentos. |
| `RunResult` | Totales por estado, lista de resultados y exit code. Un documento reintentado en CPU se cuenta una sola vez. |
| Error de entrada | PDF ilegible/cifrado/inválido; no es un fallo GPU ni provoca reintento de dispositivo. |
| Error de aceleración | Backend/driver/VRAM/inferencia GPU fallidos; habilita un reintento CPU en el plan 02. |

Las rutas se entregan como valores de ruta o argumentos separados, nunca como una cadena de shell. Los adaptadores escriben exclusivamente en staging; la publicación es responsabilidad común.

### Protocolo CLI 1, consumible sin importar Python

`sami health --json` emite **un objeto JSON**, no logs mezclados. La conversión con `--json` emite **JSON Lines UTF-8** por stdout; mensajes humanos y librerías van por stderr. No enviar cuerpos completos de documentos ni imágenes base64 como eventos; entregar rutas al resultado.

Envelope propuesto:

```json
{"protocol_version":1,"event":"job_progress","seq":7,"run_id":"r1","job_id":"j1","attempt":1,"data":{"stage":"extracting","completed":2,"total":5,"unit":"pages"}}
```

| Evento | Datos necesarios |
|---|---|
| `run_started` | Modo/default resuelto y versión CLI; `run_id` estable. |
| `inputs_resolved` | Número de documentos únicos, orden e incidencias de descubrimiento. |
| `job_started` | Input, índice, total del lote, motor/dispositivo y número de intento. |
| `job_progress` | Etapa y unidades reales; `total:null` si no es medible. |
| `warning` | Código estable, mensaje y contexto. `GPU_FALLBACK_CPU` incluye causa y cambio de dispositivo. |
| `job_retrying` | Dispositivo anterior/nuevo y motivo; no incrementa documentos terminados. |
| `job_finished` | Un `JobResult` terminal; solo uno por documento, después de todos sus intentos. |
| `run_finished` | Contadores, duración y exit code; exactamente uno al finalizar normalmente o cancelar. |

`seq` lo asigna el coordinador de forma creciente. Los consumidores ignoran campos/eventos aditivos desconocidos; no admiten una versión mayor incompatible. JSONL puede llegar en fragmentos; acumular hasta newline. Un crash sin evento terminal se interpreta como fallo de proceso, no como éxito.

Estados de documento: `succeeded`, `partial`, `failed`, `cancelled`; reservar `skipped` para una política de omisión que realmente se implemente. Duplicados eliminados no son documentos convertidos ni fallidos. No confundir warnings —por ejemplo GPU→CPU— con pérdida de contenido.

Para control de UI proponer `--control-stdin`: recibe líneas JSON como la siguiente; Ctrl+C del terminal se traduce al mismo mecanismo de cancelación. EOF en stdin no cancela por sí solo.

```json
{"protocol_version":1,"command":"cancel","run_id":"r1"}
```

### Pruebas y cierre U01

- Parsing/serialización de petición, eventos y resultados; unicode y rutas con espacios.
- Mismo corpus, versiones y opciones comparables: Markers nuevos versus base U00. Revisar contenido/estructura, no tiempos o metadatos variables.
- `import sami.cli`, ayuda y versión no descargan ni importan Torch/Marker ni registran handlers globales incompatibles con Windows.
- stdout en modo JSONL siempre parseable aunque una dependencia imprima logs; error o cancelación tiene salida terminal coherente.

**Rollback:** revertir contrato/adaptación juntos; no cambiar documentos del usuario ni la referencia Caste.

## U02 — Motor rápido, referencias y salidas comunes

### Caste efectivo

Extraer `Options`, normalización, layout, prosa, tablas, extracción y QC útiles desde [la referencia](../refactor-core-sami/PDF2MD_caste.py). Conservar la invocación real, no su preset nominal `fast`: `high`, `ocr=False`, `images=False`, `markers=True`, tabla `pipe`, sin límite de páginas por defecto.

No importar el archivo del notebook convertido: contiene ejecución global. No ejecutar pip/apt, Tesseract, OCR reactivo, auditoría aleatoria, detección de modelos ni descarga alguna al convertir. Mantener los controles de consistencia de su función `run` dentro de la separación de responsabilidades; no añadir una segunda extracción pesada para aparentar verificación.

En escaneos sin texto: generar advertencia/vacío y `partial`; no inventar contenido ni activar OCR. El flag original `overwrite=True` se sustituye por numeración, según instrucción del usuario. La velocidad es un objetivo comparativo contra U00; medir el coste añadido de links, eventos y staging.

### Referencias dentro del Markdown

1. Mantener toda bibliografía que el motor extraiga; desactivar la eliminación propia de SAMI.
2. Conservar destinos URL/DOI ya presentes en el texto y anotaciones recuperables del PDF. Usar texto enlazado en Markdown inline, nunca un archivo bibliográfico externo.
3. En Caste, aprovechar las coordenadas/spans ya extraídas para relacionar enlaces con texto. No hacer matching global ciego que enlace la primera palabra repetida de la página.
4. Si una anotación tiene URL pero no se puede insertar de forma inequívoca en su posición, conservarla en una sección de enlaces recuperados dentro del mismo `.md`, con página/etiqueta disponible y warning. No inventar una relación cita–bibliografía.
5. Representar destinos internos mediante anclas si la página/sección destino existe en la salida; si no, registrar la limitación. No consultar la red para completar títulos o DOI.

Esta política es la adaptación de contenido permitida además de conservar la salida Marker. La preview UI no convierte ni reescribe los archivos.

### Nombres y publicación

| Entrada/destino | Resultado esperado |
|---|---|
| `paper.pdf`, sin salida previa | Carpeta `paper/`, con `paper.md` y recursos relativos. |
| Mismo PDF convertido otra vez | `paper_2/paper_2.md`; después `paper_3/…`, sin tocar versiones anteriores. |
| `--output out/` | Misma política bajo `out/`. |
| `--flat --output out/` | `out/paper.md`, después `out/paper_2.md`; recursos en un namespace único por intento publicado. |
| Dos PDF homónimos en un lote | Reservar nombres distintos de forma estable; no sobrescribir por compartir stem. |

Reservar la identidad de salida con exclusión entre procesos SAMI. Preparar en el mismo sistema de archivos del destino; el commit final no debe reemplazar un archivo ajeno aparecido entretanto. Para salida por carpeta, publicar una carpeta completa preparada. Para flat, publicar recursos únicos primero y el Markdown al final; si falla, retirar solo recursos nuevos no referenciados por un documento publicado.

No dejar una carpeta final vacía que parezca una conversión válida al comenzar. Si falla una GPU, el intento descartado nunca se publica. No borrar ni renombrar PDF originales. El resultado incluye las rutas reales finales para CLI/UI.

### Pruebas y cierre U02

- Tablas y columnas Caste con contenido esperado; escaneo con OCR apagado termina parcial sin cargar OCR.
- Bibliografía y enlaces de texto/anotaciones en ambos motores; referencia repetida, link sin asociación inequívoca y destino interno ausente.
- Salida normal/flat, segundo intento, homónimos, unicode y fallo inyectado entre recursos y Markdown: salida anterior intacta, limpieza limitada al intento propio.
- Comparación de latencia Caste antes/después en el mismo entorno, sin mezclar la auditoría ni el arranque de modelos.

**Cierre:** motores preservados, contrato v1 verificable y salidas seguras. **Rollback:** quitar U02 sin eliminar resultados ya publicados; una migración de formato nunca borra documentos.
