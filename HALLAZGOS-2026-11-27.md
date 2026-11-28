# Hallazgos — 27 de noviembre de 2026

## Alcance

Línea base de SAMI 0.4.3 en Windows 11, usando una copia de los resultados en una carpeta temporal. El PDF original y su Markdown en Downloads se conservan sin cambios. No se ha aplicado ninguna corrección del extractor.

Las bibliotecas instaladas son Marker 2.0.0, pdftext 0.7.1 y pypdfium2 5.10.1. El caso real tiene 13 páginas y contiene texto seleccionable, matemáticas, tablas y figuras. No se incorpora el PDF al repositorio. El equipo tiene una NVIDIA GeForce RTX 3050 Laptop con 4 GB de VRAM.

## Hallazgos confirmados

- El Markdown generado por la conversión previa contiene 660 caracteres de reemplazo Unicode `�`. El archivo es UTF-8 válido, por lo que no se trata únicamente de un problema de visualización.
- El PDF sí contiene los símbolos. Por ejemplo, donde el Markdown dice `�� = 5`, los extractores independientes Poppler y PyMuPDF recuperan `𝑁 = 5`.
- La extracción `pdftext.dictionary_output` del PDF en Windows produce 1.890 caracteres de reemplazo antes de generar el Markdown. PDFium devuelve 945 pares consecutivos de sustitutos UTF-16 válidos y la función `pdftext.pdf.chars.get_chars` instalada reemplaza cada mitad individualmente por U+FFFD. Este es el origen confirmado de la pérdida en la capa de texto.
- En el registro del modelo de la conversión previa, la ejecución que escuchó en el puerto 63113 trabajó durante aproximadamente 17 minutos y 34 segundos. Una tarea alcanzó el contexto máximo tres veces antes de terminar una cuarta generación larga. El registro no identifica con certeza la página ni demuestra una relación causal con el fallo Unicode.

## Pruebas de conversión

### Modo rápido, Windows, CLI 0.4.3

La conversión terminó con código 0 en 47,47 segundos de tiempo real (45,99 segundos para el trabajo), con dispositivo CPU. El Markdown generado contiene **0 caracteres de reemplazo**, 44 apariciones de `𝑁` y 33 de `𝑤`. Incluye 34 líneas de tablas, pero ninguna imagen. El resultado registra que las figuras se excluyeron por política y no se verificó su contenido. Esto confirma que `fast` conserva estos símbolos, pero no equivale al resultado de `balanced` para figuras y estructura.

### Modo balanced, Windows, CLI 0.4.3

La repetición terminó con código 0 y estado `succeeded` en **1.155,41 segundos** de tiempo real, es decir, **19 minutos y 15 segundos**. El trabajo registró 1.149,70 segundos. Se solicitó dispositivo automático y SAMI seleccionó CUDA.

| Etapa | Tiempo registrado |
|---|---:|
| Lectura del PDF | 4,3 s |
| Estructura inicial | 1,4 s |
| Detección de diseño | 12,1 s |
| Extracción de líneas | 9,0 s |
| Renderizado de páginas para OCR | 0,6 s |
| **OCR de 2 páginas** | **1.100,4 s — 18 min 20 s** |
| Procesamiento de tabla | 9,4 s |
| Renderizado de Markdown | 1,7 s |

El OCR representa aproximadamente el 95 % del tiempo total medido. SAMI informó que 11 páginas tenían capa de texto y dos requerían OCR. El log del servidor contiene cuatro salidas con `truncated = 1`. Una petición larga de la segunda página fue seguida de otras generaciones largas. El código de Surya admite hasta tres reintentos ante errores o texto repetitivo, aunque el registro disponible no demuestra por sí solo el motivo de cada nueva petición. No se ha identificado cuál de las dos páginas provocó la generación larga.

La salida repetida contiene **660 caracteres de reemplazo**, cero apariciones literales de `𝑁` y `𝑤`, y 18 imágenes. Las 18 referencias de imagen encontradas apuntan a archivos existentes. Tiene 41 líneas de encabezado y 71 líneas de tabla. Esos conteos no demuestran que la estructura o el contenido visual sean correctos. **El resultado se reportó como exitoso y sin advertencias**, pese a los caracteres perdidos y los truncamientos observados en el log.

Durante la prueba, la interfaz recibió 91 % cuando aún figuraban 0 de 2 páginas OCR terminadas. Más tarde siguió en 91 % con 1 de 2. Es una estimación engañosa del trabajo restante, no una medición exacta. La repetición tardó unas 24 veces lo que `fast` en esta máquina y para este archivo, pero las salidas no son equivalentes: `fast` no incluyó imágenes.

Los artefactos de ambas pruebas se encuentran en `%LOCALAPPDATA%\Temp\sami-audit-20261127`. Allí están los resultados JSON, eventos JSONL, salidas Markdown, stderr y `evidence/llamacpp-repeat.log`. Los hashes del PDF y Markdown en Downloads se verificaron nuevamente sin cambios al terminar.

## Evaluación y siguientes pruebas

1. **Unicode, confirmado.** Añadir una prueba de regresión autónoma que exija conservar caracteres fuera del plano básico, incluidas `𝑁` y `𝑤`, sin corromper ASCII ni caracteres griegos. Probar pares válidos y sustitutos aislados. Repetir la extracción y conversión del paper después de la corrección.
2. **Calidad comunicada, confirmado.** La conversión `balanced` devolvió éxito sin advertencias pese a 660 caracteres de reemplazo. Añadir detección y advertencias o estado apropiado, sin inferir que todos los `�` siempre provienen de un mismo defecto.
3. **Rendimiento, confirmado.** Investigar por qué se generan y truncan respuestas largas para una página OCR y medir cualquier cambio con el mismo PDF. Evitar fijar un límite de tiempo universal sin comparar también exactitud y pérdida de contenido.
4. **Progreso, confirmado.** Ajustar o hacer explícita la incertidumbre del porcentaje en operaciones largas y reintentos.
5. **GPU, pendiente.** La selección de CUDA está confirmada, pero los registros de esta ejecución no muestran cuántas capas terminaron realmente en GPU. No se puede atribuir la lentitud a un reparto concreto CPU/GPU sin instrumentación adicional.
6. **Calidad visual, pendiente.** Revisar manualmente fórmulas, tablas, orden de lectura y figuras contra el PDF. La existencia de 18 imágenes y la ausencia de rutas rotas no certifican su corrección.

## Control independiente de Unicode

Se generó un PDF propio de una página con XeLaTeX y STIX Two Math, sin usar contenido del paper. Incluye `N = 5`, `𝑁 = 5`, `𝑤 = 3` y `α = 2`.

- Poppler y PyMuPDF conservan ambos símbolos matemáticos. PyMuPDF produce cero caracteres de reemplazo.
- `pdftext.dictionary_output` devuelve `�� = 5; �� = 3; α = 2`, con cuatro reemplazos. El ASCII y el griego BMP permanecen.
- Este control reproduce el defecto sin modelos, GPU ni dependencia del artículo. El primer intento de generar el PDF con `PyMuPDF.insert_text` no conservó los símbolos de origen y se descartó como control inválido.
- El control se puede reproducir con XeLaTeX, `fontspec`, la fuente STIX Two Math y una línea con `Control matematico: 𝑁 = 5; 𝑤 = 3; α = 2.`.
- Archivos de evidencia: `evidence/unicode-control-xelatex.pdf` y `evidence/unicode-xelatex-results.json` dentro de la carpeta temporal indicada arriba. El código fuente del control está en `/tmp/sami-audit-control.tex`.

## Controles de documentos del repositorio

En Windows, la extracción sin modelos de `test-pdfs/test_document.pdf` y `test-pdfs/radio_env_5pages.pdf` produjo cero caracteres `�` tanto con PyMuPDF como con pdftext. Esto verifica dos casos adicionales, pero no garantiza que todas sus tablas, figuras o fórmulas se hayan extraído correctamente.

## Identidad de los archivos

- PDF original SHA-256: `ecbe5bd6e1ae6215cd961a6b0e3a78b972e4cfa27ff753780b683d8ecfd42ca4`.
- Markdown previo SHA-256: `9cac55ae8bcb87913ceb773a5656cf00670c11b7951d48bc189fffa183200641`.

## Comparación con Papersmith actual

Se revisó el código de Papersmith en el commit `7356edc9dafe77621d9872dd35a07362f8485bc8`. El primer commit de SAMI, `9083c56`, declara que desacopló el conversor de Papersmith y utilizaba Marker 2.0.0. Papersmith actual ha evolucionado: su configuración por defecto es `auto/fast`, con selección por página entre PDFium y Docling 2.141.0. Marker permanece como alternativa opcional.

Su ruta PDFium une expresamente los pares sustitutos UTF-16 válidos antes de convertirlos a caracteres. Se ejecutaron directamente el clasificador y la ruta PDFium de Papersmith sobre las 13 páginas del PDF original, sin moverlo ni ejecutar Docling. Los resultados fueron:

- Clasificación: 3 páginas de texto, 7 con ecuaciones y 3 con tablas. Con CUDA y Docling disponibles, su configuración predeterminada enviaría las 10 páginas de matemáticas o tablas al motor pesado. Esta asignación se infiere del código y no es una medición de Docling.
- Recorrido de todas las páginas forzadas por PDFium: 1,65 segundos incluyendo el clasificador de 0,65 segundos; sin procesos de OCR ni Docling.
- Markdown producido: 0 caracteres `�`, 44 apariciones de `𝑁` y 33 de `𝑤`. La frase de control conserva `𝑁 = 5` y los pesos `𝑤`.
- La prueba PDFium sola generó 0 imágenes y 0 líneas de tablas Markdown. No es una comparación funcional equivalente con SAMI balanced: la ruta completa de Papersmith enviaría 10 páginas a Docling, que no se ejecutó en esta prueba. Tampoco se evaluaron íntegramente el orden, las fórmulas ni la fidelidad de tablas.
- Evidencia y salida bajo `%LOCALAPPDATA%\\Temp\\sami-audit-20261127\\papersmith`. El PDF original conservó su checksum.

Conclusión: la corrección Unicode de Papersmith es directamente relevante y se comprobó en este PDF. Su clasificación por página y Docling son alternativas plausibles para mejorar el comportamiento, pero aún no hay una medición del modo `auto` completo en este equipo, ni evidencia de que conserve todas las figuras en este documento. Para decidir una migración hace falta comparar ambas salidas, especialmente tablas, fórmulas e imágenes, y considerar el costo de modelos y la integración con las funciones de SAMI.

## OCR de Papersmith frente al caso del paper

Papersmith `7356edc` usa **RapidOCR con backend Torch e idioma inglés dentro de Docling 2.141.0** para páginas clasificadas como `scan`. En las rutas `math` y `table` el código llama a Docling con `do_ocr = false`; la reconstrucción de fórmulas y tablas puede usar otros modelos y consumir tiempo aunque el OCR esté desactivado.

En el análisis real del paper de 13 páginas, su clasificador no marcó ninguna página como `scan`: clasificó 3 como texto, 7 como matemáticas y 3 como tablas. Por tanto, según el código y esa clasificación, el modo predeterminado no activaría RapidOCR para este PDF. Esto evita la etapa concreta de OCR de Surya que en SAMI tardó 1.100,4 s, pero no demuestra aún cuál sería el tiempo total ni la fidelidad de Docling.

La decisión de Papersmith es por página: para clasificar una página como escaneada exige menos de 20 caracteres visibles y una cobertura de imagen de al menos el 30 %. Una página con capa de texto pero también texto dentro de imágenes no se clasifica como `scan`, por lo que puede perder ese texto. El control PDFium forzado tampoco produjo imágenes en este paper; esa prueba no mide Docling.

No se ejecutó RapidOCR ni Docling, que no están instalados en el entorno de SAMI. Por tanto, no se ha comparado su velocidad ni precisión de reconocimiento con Surya. En especial, RapidOCR está orientado al reconocimiento textual y la fidelidad de símbolos científicos, ecuaciones y tablas debe medirse por separado.

Nota de verificación: la documentación de Papersmith describe `--force-ocr` como OCR en todas las páginas. El código revisado activa `do_ocr` para ellas, pero no configura explícitamente `force_full_page_ocr`; no se verificó si eso sustituye por completo la capa de texto en Docling 2.141.0. No se debe asumir ese comportamiento sin una prueba.

## Comparación práctica con Papersmith en otro artículo

### Método

Se usó `test-pdfs/radio_env_5pages.pdf`, un fragmento de cinco páginas del artículo *Explainable Machine Learning for Radio Environment Mapping*. SHA-256: `cb17aa94bb490fe0a136fdccccb48b2c4e7d763262a137cfa00ad6cf53f26d4c`.

Ambas conversiones se ejecutaron de forma secuencial en el mismo Windows 11 con RTX 3050 de 4 GB. SAMI 0.4.3 se ejecutó en modo `balanced`, dispositivo automático, y seleccionó CUDA. Papersmith se ejecutó con el código del commit `7356edc9dafe77621d9872dd35a07362f8485bc8`, `engine=auto`, `mode=balanced`, fórmulas con CodeFormulaV2 y CUDA disponible, sin caché de páginas y sin eliminar referencias. En Papersmith `balanced` envía todas las páginas a Docling, pero la estructura de tablas y OCR se activan según la clasificación. Los dos modos no usan algoritmos ni opciones idénticas, por lo que no hay una equivalencia garantizada de calidad.

Docling 2.141.0 se instaló en un entorno temporal aislado con PyTorch 2.14.1+cu132, la misma versión CUDA que SAMI. Papersmith utilizó pypdfium2 5.15.2, mientras que SAMI utilizó 5.10.1. Para el tiempo con modelos ya descargados se ejecutó Papersmith en un proceso nuevo, sin caché de páginas. Los tiempos externos incluyen el inicio del proceso. La primera ejecución de Papersmith descargó modelos; su temporizador interno registró 108,23 s y no incluye el inicio de Python ni la importación inicial de Torch, por lo que no es comparable directamente con el tiempo externo.

### Artículo digital de cinco páginas

| Métrica | SAMI | Papersmith |
|---|---:|---:|
| Tiempo externo con modelos descargados | 52,39 s | 15,21 s |
| Páginas terminadas | 5 | 5 |
| Caracteres de reemplazo `�` | 0 | 0 |
| Encabezados Markdown detectados | 9 | 9 |
| Tabla de frecuencias en Markdown | 13 líneas, incluida cabecera | 0 líneas |
| Referencias de imagen | 3 | 8 |

Ambos conservan el título, el resumen y los datos de 6.543, 3.645 y 2.898 mediciones en las comprobaciones realizadas. SAMI extrajo la tabla 1 con las filas verificadas, entre ellas `900`, `925–959.8 MHz` y `1800`, `1805.2–1880 MHz`. Papersmith conserva el título de la tabla pero omitió sus filas. Las ocho imágenes de Papersmith incluyen imágenes pequeñas de encabezados; no son ocho figuras científicas. Ambos resultados incluyen el diagrama de la página 3 y el mapa de la página 5.

No se ejecutó OCR de página en SAMI para este caso, que tiene capa de texto en las cinco páginas. Este resultado no compara la capacidad OCR. Tampoco prueba fidelidad de ecuaciones: este fragmento no aportó una muestra adecuada para evaluarlas.

### Página escaneada de control

Se generó una copia rasterizada a 144 DPI de la página 5 del mismo artículo, sin capa de texto, en la carpeta temporal. El PDF original no fue modificado. SHA-256 del control: `69f6f008bbc3408147b580fbd286d93d983c75492139294ff4dd693b6d52706c`.

| Métrica | SAMI / Surya | Papersmith / RapidOCR |
|---|---:|---:|
| Tiempo externo con modelos descargados | 148,90 s | 19,23 s |
| Tiempo de la etapa OCR reportado por SAMI | 122,4 s | No aislado |
| Tabla en Markdown | 13 líneas | 13 líneas |
| Código de la fila de 925–959,8 MHz | `900`, correcto | `006`, incorrecto |
| Referencias de imagen | 1 | 2 |
| Caracteres de reemplazo `�` | 0 | 0 |

Ambos conservaron en las comprobaciones las cifras 6543, 3645, 2898, 2023a, 2023b y 25 V/m y extrajeron el mapa. La segunda imagen de Papersmith es un encabezado pequeño. El error `900 → 006` se repitió en las dos ejecuciones de Papersmith. No se revisó exhaustivamente cada palabra, celda o imagen, y un escaneo sintético de una página no equivale a una muestra representativa de documentos escaneados reales.

### Interpretación

En esta muestra, Papersmith fue considerablemente más rápido, pero perdió una tabla completa del PDF digital y cometió un error numérico en el escaneo. SAMI fue más fiel en la tabla examinada, pero tardó más. El caso no permite afirmar que uno sea globalmente mejor, ni que la misma diferencia de tiempos y calidad se mantenga en el paper de 13 páginas.

La calidad de las fórmulas científicas, el comportamiento ante distintas resoluciones y lenguas, y una comparación completa del paper original siguen pendientes. Evidencia temporal en `%LOCALAPPDATA%\Temp\sami-papersmith-compare`, que contiene entradas, Markdown, figuras, eventos y registros. No se modificó el PDF original ni la instalación de SAMI.

## Corrección inicial Unicode en la rama `fix/pdf-unicode-quality`

Se aplicó una adaptación temporal y acotada a `pdftext 0.7.1` durante la extracción de Marker. Reconstruye pares UTF-16 válidos antes de que `pdftext` agrupe los caracteres, conserva sus posiciones y deja como reemplazos los pares incompletos. También funciona en los procesos de extracción creados con `spawn` en Windows. Si se instala otra versión de `pdftext`, esta adaptación no se aplica y hay que volver a validar su comportamiento.

En Windows, usando la instalación existente de dependencias pero el código de esta rama, la extracción del paper original completo produjo 0 caracteres U+FFFD (antes: 1.890 en la extracción), con 44 `𝑁` y 33 `𝑤`, tanto con la configuración de 1 como de 2 workers. Como el paper tiene 13 páginas, `pdftext` no necesariamente crea 2 procesos por su umbral de páginas. Un control de 20 páginas sí ejercitó dos procesos: 20 `𝑁`, 20 `𝑤` y 0 U+FFFD. El PDF original no se modificó.

La conversión de extremo a extremo en Windows del control de una página terminó en 23 s. La detección de U+FFFD en el Markdown ahora genera una advertencia para la CLI y los eventos usados por la UI; la advertencia no identifica por sí sola la causa ni detecta todo tipo de error de OCR. Las pruebas automatizadas pasan con 118 pruebas y 50 subtests.

Una muestra de las primeras dos páginas del paper original se convirtió completa con el código de la rama y la GPU en Windows en 24,2 s: el Markdown final contiene 1 `𝑁`, 5 `𝑤` y 0 U+FFFD. Esas páginas no requirieron OCR. Queda pendiente validar el Markdown final de las 13 páginas, en particular las páginas que sí requieren OCR, y medir y mejorar su duración; la extracción completa sin OCR no sustituye esa prueba.

## Límite por página y nueva medición completa

En la rama `fix/pdf-unicode-quality` se probaron el progreso por páginas terminadas y un límite predeterminado de 120 s por página para el OCR de Surya mediante llama.cpp. La respuesta del modelo se lee de forma incremental; al alcanzarse el límite se conserva lo recibido, se informa `OCR_PAGE_TIMEOUT` y el documento se publica como `partial` (código de salida 1). El tiempo incluye los reintentos de esa página; `SAMI_OCR_PAGE_TIMEOUT` permite seleccionar otro valor positivo. También se registra el tiempo por página y se advierte sobre reintentos, límite de salida o truncamiento de contexto detectado en el log. La detección de truncamiento por log depende de la disponibilidad y el formato del registro de llama.cpp.

### Paper original completo, Windows y GPU

Se repitió la conversión de las 13 páginas en modo balanced usando las dependencias instaladas y el código de la rama: **54,5 s** totales, frente a los **1.155,4 s** de la medición anterior. Marker clasificó las 13 páginas como texto y no realizó OCR; previamente había enviado dos a OCR. La corrección Unicode es una diferencia relevante, pero esta medición no aísla experimentalmente todas las posibles causas de la diferente clasificación. El Markdown contiene 0 caracteres U+FFFD, 44 `𝑁`, 28 `𝑤` y 18 referencias a imágenes.

El frontmatter de esta ejecución muestra `sami_version: 0.2.4` porque se usó el Python de la instalación previa con el código de la rama en `PYTHONPATH`; ese campo refleja los metadatos instalados, no el código usado en la prueba.

La rapidez no demuestra equivalencia de calidad. La salida anterior tenía 71 líneas de tabla Markdown y la nueva 7. En una inspección puntual, ambas contienen los marcadores de las 25 líneas de un algoritmo, pero la nueva agrupa sus instrucciones en un párrafo. El comentario `Resources required for a packing` sigue presente, aunque dividido por etiquetas de formato que impiden encontrar la frase literalmente. Las tablas, fórmulas y el orden no se han revisado exhaustivamente; hay una regresión de presentación y no puede descartarse pérdida de contenido.

### Control escaneado, límite predeterminado

La página escaneada sintética usada en la comparación anterior requirió OCR. La etapa de página alcanzó el límite en **120,2 s**, se conservó el contenido recibido y el documento terminó en **149,4 s** con estado `partial`, una advertencia `OCR_PAGE_TIMEOUT` para la página 1 y código de salida 1. La salida tuvo 13 líneas de tabla, conservó `900` y una referencia de imagen, igual que la anterior en estas comprobaciones puntuales; no se ha cotejado palabra por palabra y el corte puede dejar texto incompleto. Evidencia: `%LOCALAPPDATA%\\Temp\\sami-budget-scan-validation` y `sami-budget-scan-events.jsonl`. La prueba anterior sin límite había tardado 148,9 s en total con 122,4 s de OCR; al tratarse de un único control no es una estimación general de calidad ni de rendimiento.

### Continuación entre dos páginas escaneadas

Se duplicó el control escaneado en un PDF temporal de dos páginas. Con el límite predeterminado, la primera página terminó a los **120,3 s**, el modelo inició una solicitud nueva para la segunda y esta terminó a los **120,1 s**. Los eventos de progreso pasaron de 0/2 a 1/2. El resultado final se publicó en **266,8 s** como `partial`, con advertencias `OCR_PAGE_TIMEOUT` para las páginas 1 y 2. El Markdown contiene 26 líneas de tabla, 4 apariciones de `900`, 2 referencias a imagen y 0 U+FFFD; estas comprobaciones no garantizan que el contenido esté completo. Al terminar no quedaron procesos `sami.exe`, `python.exe` ni `llama-server.exe` activos en Windows. Evidencia: `%LOCALAPPDATA%\\Temp\\sami-budget-two-validation` y `sami-budget-two-events.jsonl`.
