# Referencia histórica — sustituida por los planes por etapas

Este documento conserva íntegro el diseño anterior para consulta. La entrada vigente es [el índice del plan](2026-11-18_10-31-38_analisis-diseno-refactor-sami.md) y sus cinco planes numerados. Ante diferencias, usar el índice y los planes activos; no implementar desde esta referencia histórica.

---

# Refactor de SAMI: hardware, tres modos, CLI e instalación multiplataforma

Fecha de apertura: **2026-11-18 10:31:38**, America/Bogota (UTC−05:00).
Última actualización: **2026-11-18 11:29:26**, America/Bogota (UTC−05:00).
Autor: Codex, a partir de los requisitos y decisiones del usuario.
Estado: **análisis para discusión; implementación no autorizada**.
Base revisada: commit `6452f12`, código local de SAMI y referencia de Caste.

La propuesta conserva la lógica de conversión a Markdown de SAMI y añade un motor rápido basado en Caste. El refactor separa diagnóstico del equipo, preparación de dependencias, selección de recursos, conversión y presentación. La primera entrega contempla núcleo, CLI e instaladores con prioridad en Windows 11 y Linux basado en Debian; macOS queda como objetivo secundario. La UI queda para una entrega posterior independiente que se comunica exclusivamente mediante comandos y eventos del CLI.

Lectura rápida: la sección 7.5 reúne las funcionalidades finales previstas del CLI; la sección 8 define el despliegue CLI primero y UI después; la sección 9 conserva el stack Electron y los requisitos gráficos. La sección 12 consolida las decisiones de uso diario ya cerradas. La sección 13 detalla ramas y archivos; la sección 14 publica el CLI `0.2.0` tras su merge a `main`, y la sección 15 publica la UI `0.3.0` posteriormente. Todo el alcance corresponde al diseño futuro, no a funcionalidades ya implementadas.

Esta tarea produce únicamente este documento. No se han instalado componentes, cambiado drivers, ejecutado conversiones ni modificado código de la herramienta. Los comandos, módulos y comportamientos descritos a continuación son propuestas.

## 1. Decisiones confirmadas y asuntos abiertos

| Tema | Estado y alcance |
|---|---|
| Conversión actual de SAMI | **Conservar** su lógica de conversión MD mediante Marker. La adaptación de hardware no debe sustituirla por las heurísticas de Caste. |
| Caste | Usarlo únicamente como base del modo `fast`; no reemplaza los modos de mayor calidad de SAMI. |
| Modos públicos | `fast`, `balanced`, `quality`. Nombre intermedio corregido por el usuario. La correspondencia concreta de los dos últimos con los modos de Marker se propone en la sección 5. |
| Modo predeterminado | **`balanced`**, confirmado por el usuario. |
| Comportamiento de `fast` | Usar la configuración efectiva del lote de Caste: `quality="high"`, `ocr=False`, `images=False`; conservar extracción ligera de texto/tablas y evitar trabajo pesado añadido. |
| Referencias | **Conservar siempre** bibliografía y enlaces dentro del propio Markdown. No eliminarlos ni exportarlos como artefactos bibliográficos externos. |
| Archivos existentes | Crear una nueva salida numerada por defecto, conservando las anteriores. |
| Diagnóstico persistente | Diagnóstico completo durante la instalación; guardar sus resultados y reutilizarlos. En uso habitual, solo health check rápido de compatibilidad. |
| Ejecución y privacidad | Todo local, sin claves de API ni servicios externos de conversión, incluido `quality`. Descargas de instalación/modelos no equivalen a enviar documentos. |
| Preparación automática | Dejar los tres modos y su ruta CPU preparados durante la instalación, con GPU compatible cuando corresponda. Sin pedir instalaciones de modos/modelos al usuario después. Drivers del sistema gestionados en un paso explícito. |
| Fallo GPU | Avisar y continuar automáticamente en CPU, manteniendo el modo; no bloquear la conversión ni pedir confirmación por un fallo de aceleración. |
| Plataformas | Prioridad confirmada: **Windows 11 y Linux basado en Debian**. macOS es secundario y no condiciona el cierre de la primera entrega. Versiones concretas de distribuciones y arquitecturas por delimitar. |
| Entradas CLI | Uno o varios archivos, carpetas de PDF y combinación de ambos; progreso por archivo y por lote. |
| UI | Segunda entrega. Aplicación independiente que depende del CLI, sin reutilizar ni importar su código de conversión. Priorizar utilidad y facilidad de desarrollo; tamaño del paquete y rendimiento de UI no son criterios prioritarios. Stack recomendado: Electron con JavaScript, HTML y CSS. |
| Orden de despliegue | El CLI debe quedar instalado, validado y utilizable por sí solo antes de instalar la UI. La instalación gráfica depende del health del CLI y, al terminar, su `.exe` debe abrir por doble clic sin preparación manual. |
| Integración UI en Windows | Al desplegar la UI, crear acceso directo en el escritorio y entrada en el menú Inicio, y dejar los lanzadores disponibles en `PATH`. La aplicación debe quedar lista para abrir sin configuración manual. |
| Restricción de trabajo | Discutir decisiones antes de implementar. |
| Ramas de desarrollo | `refactor/0_2_0_sami_cli` para núcleo/CLI/instaladores; `feat/0_3_0_sami_ui` para Electron y su despliegue dependiente del CLI. |
| Releases objetivo | **CLI `0.2.0`**, tag `v0.2.0`, después de su merge a `main`; **UI `0.3.0`**, tag `v0.3.0`, después de su merge posterior. La publicación del CLI no espera a la UI. |

Las decisiones de perfil predeterminado, comportamiento de Caste, referencias, archivos existentes, preparación completa y fallback CPU ya están cerradas. Quedan detalles técnicos de capacidades, flags y matriz de versiones, recogidos al final.

## 2. Punto de partida comprobado en el repositorio

| Pieza actual | Comportamiento observado | Consecuencia para el refactor |
|---|---|---|
| [sami/cli.py](../../../sami/cli.py) | Integra Marker, reproduce sus etapas en `VerboseConverter`, escribe Markdown y figuras. | Mantener el pipeline y el resultado; aislar la integración sin reescribir las reglas de conversión. |
| Modos actuales | Expone `fast` y `balanced`; sin flag delega parte de la decisión en Marker. | Los nombres nuevos necesitan una migración explícita; el antiguo `fast` y el nuevo `fast` tendrán motores diferentes. |
| Hardware | Ajusta hilos CPU; consulta VRAM de CUDA y usa un umbral de 8 GiB para elegir `fast` cuando corresponde. | Falta inventario independiente de PyTorch, memoria disponible, AMD y distinción del backend del servidor de inferencia. |
| Preparación | Descarga `llama-server`; crea directorios antes de interpretar argumentos. | `--help`, `--version` y diagnóstico de solo lectura deben poder funcionar sin descargas ni modelos. |
| Ciclo de procesos | Usa señales POSIX y seguimiento de procesos hijos. | Hace falta un supervisor con implementación Windows; conservar la limpieza de procesos propios. |
| Entradas y progreso | Acepta varios archivos explícitos; imprime etapas, tiempos e índice del lote. | No acepta carpetas ni implementa actualmente dos barras de progreso. Eso forma parte del trabajo nuevo. |
| Salida | Subcarpeta por PDF salvo `--flat`; elimina referencias por defecto; publicación por movimientos individuales desde staging. | Cambiar a conservación permanente de referencias/enlaces y salidas numeradas; reforzar publicación conservando la conversión Marker. |
| [install.sh](../../../install.sh), [setup.sh](../../../setup.sh) | Bash; instalación uv/micromamba y preparación NVIDIA Docker en ciertos entornos Linux. | No constituyen un instalador Windows; no deben seguir suponiendo `apt` para todo Linux. |
| [pyproject.toml](../../../pyproject.toml) | Marker es dependencia obligatoria; Python `>=3.11,<3.14`. | Separar base rápida de componentes pesados requiere revisar el empaquetado, no solo añadir flags. |
| [Código de Caste](../refactor-core-sami/PDF2MD_caste.py) | PyMuPDF, pdfplumber, Tesseract opcional, heurísticas de layout, manifiesto y auditoría. | Extraer solo el motor rápido y conceptos útiles de diagnóstico; no importar las celdas con ejecución global. |

La referencia de Caste permanece en `refactor-core-sami/`. Este análisis se guarda en `rfactor-core-sami/`, respetando la ruta solicitada para esta tarea.

## 3. Diagnóstico del equipo: qué medir y cuándo

El inventario completo debe realizarse durante la instalación, preceder a la selección de runtime y funcionar aunque no exista PyTorch. Sus resultados se guardan para las siguientes ejecuciones. No se está auditando ahora este equipo: se define lo que hará SAMI en cada dispositivo donde se instale.

| Área | Datos necesarios | Uso |
|---|---|---|
| SO y arquitectura | Windows/Linux/macOS, versión, distribución, kernel, x86_64/arm64, WSL o contenedor. | Elegir artefactos y recetas compatibles. WSL se trata como entorno Linux con capacidades propias. |
| CPU | Arquitectura, núcleos físicos/lógicos, afinidad y cuotas cuando existan. | Dimensionar procesos e hilos sin exceder lo realmente asignado. |
| RAM | Total y disponible, memoria compartida/unificada. | Limitar rasterización, concurrencia y modelos. |
| GPU | Todas las GPU, fabricante, identificador, arquitectura, driver, VRAM total/libre cuando se pueda consultar. | Distinguir existencia física de compatibilidad efectiva y seleccionar dispositivo. |
| Componentes | Runtimes, bibliotecas, servidor de inferencia, Tesseract e idiomas, modelos, gestores disponibles. | Reutilizar solo lo compatible y evitar descargas repetidas. |
| Calidad de vida | Espacio libre, permisos de escritura y disponibilidad de energía/red cuando sea relevante. | Detectar imposibilidad de preparar o escribir la salida antes de convertir. |

Si un dato no puede consultarse, registrar `unknown`; no interpretarlo como ausencia de GPU ni como compatibilidad confirmada. Evitar recopilar rutas personales ajenas a la tarea o variables de entorno completas.

Separar el diagnóstico completo de instalación del health check de uso habitual. El diagnóstico de instalación incluye inventario, validación del runtime y prueba mínima del motor real. Ver una GPU en el sistema o ejecutar una operación PyTorch no prueba por sí solo que el servidor VLM esté acelerado.

### 3.1 Perfil de compatibilidad persistido

Propuesta de formato: archivo JSON local versionado dentro del estado privado de SAMI, respetando `SAMI_HOME`. Guardar fecha del diagnóstico, versión de esquema, SO/arquitectura, identificadores de GPU, driver, versiones de runtimes y motores, modelos validados, backend/dispositivo efectivo, resultados de pruebas y razones de incompatibilidad. Registrar siempre la ruta CPU validada para los tres modos: es el fallback obligatorio ante fallos de aceleración.

Persistir tanto resultados positivos como negativos: una GPU no compatible o un driver ausente no debe disparar el mismo análisis costoso en cada invocación. Asociar cada resultado con una huella de sus componentes para detectar cambios relevantes. Guardar el perfil de manera atómica y coordinarlo con el instalador; no exponer un entorno parcialmente preparado como listo.

No caducar el perfil por el simple paso del tiempo ni repetir automáticamente el diagnóstico completo por cada archivo, lote o apertura del CLI. Invalidar únicamente las capacidades afectadas cuando exista evidencia de cambios. Una actualización del motor o sus modelos debe validar sus propios componentes durante esa instalación y actualizar el perfil.

### 3.2 Health check rápido antes de convertir

Antes de iniciar un lote, leer el perfil y comprobar su esquema, el entorno activo y la existencia de los componentes necesarios para el modo elegido. Comparar huellas ligeras de componentes/driver cuando estén disponibles; no recalcular hashes de todos los modelos ni recorrer los paquetes instalados. La comprobación se realiza una vez por invocación/lote, no por PDF.

El camino habitual no importa PyTorch ni Marker, no carga modelos, no inicia servidores de inferencia, no consulta la red y no instala nada. Las consultas externas al SO, si se necesitan, tienen timeout y presupuesto global acotados. Objetivo inicial propuesto para medir: menos de un segundo de coste añadido en un equipo ya preparado, evitando incluso ese coste en `--help` y `--version`.

La RAM/VRAM libre puede variar sin que haya cambiado la compatibilidad. Consultarla de forma ligera antes de reservar recursos para el trabajo, con tiempo limitado; si no se obtiene, usar un presupuesto conservador y reflejar la incertidumbre. La carga normal de modelos para convertir sigue siendo necesaria y se muestra como etapa de preparación del trabajo, pero no repite el diagnóstico de instalación.

Si cambia la capacidad GPU o falla su comprobación, emitir un warning y continuar por la ruta CPU preparada durante instalación, conservando el perfil solicitado y sin pedir confirmación. No iniciar un diagnóstico profundo al abrir el CLI ni degradar de `quality` a `fast`. Si el registro general falta o está corrupto, tratarlo como un problema de integridad de instalación: el instalador debe mantener un registro recuperable de la ruta CPU; no interpretar la pérdida de evidencia GPU como motivo para detener una conversión CPU válida.

La comprobación rápida no puede garantizar que un backend nunca falle después. Si la inicialización real detecta una incompatibilidad, registrar el fallo e invalidar esa capacidad; no repetir intentos costosos con la misma huella en cada ejecución. El análisis profundo se reserva al flujo explícito de instalación, actualización de componentes o reparación.

## 4. Aceleración y preparación automática

### 4.1 Backend de cómputo y servidor de inferencia son decisiones distintas

El resultado del diagnóstico debe distinguir: hardware detectado, driver utilizable, runtime disponible y motor validado. Para un modo con VLM también se debe registrar qué servidor ejecuta el modelo y en qué dispositivo.

En PyTorch, ROCm reutiliza interfaces bajo `torch.cuda`; por eso ese nombre no identifica por sí solo una GPU NVIDIA. La detección debe diferenciar HIP y CUDA. Véase [semántica HIP de PyTorch](https://docs.pytorch.org/docs/2.15/notes/hip.html).

| Entorno | Objetivo propuesto | Condición para declararlo listo |
|---|---|---|
| Windows/Linux + NVIDIA | CUDA, cuando la combinación esté soportada. | Driver, runtime, binarios y ejecución real del motor verificados. |
| Windows/Linux + AMD | ROCm/HIP en combinaciones expresamente compatibles. | Validación por GPU, SO, driver, framework y backend de inferencia. |
| macOS compatible | Metal/MPS y/o backend Metal del servidor elegido. | Prueba del backend real y presupuesto de memoria unificada. |
| Equipo sin aceleración utilizable | CPU. | Preparación de dependencias CPU y ejecución del motor dentro de sus límites. |

AMD publica una matriz por hardware y entorno: no debe inferirse que cualquier Radeon o cualquier Windows/Linux soportan el stack requerido. El soporte del framework tampoco demuestra el de Marker/Surya. Véase [matriz oficial ROCm](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html). macOS necesita contemplar [MPS](https://docs.pytorch.org/docs/2.15/notes/mps.html), además de los backends que use el servidor.

La documentación de Marker 2.0 describe un servidor VLM separado: vLLM/Docker en NVIDIA y llama.cpp en otros casos. Por tanto, instalar una rueda CUDA/ROCm de PyTorch no basta para acelerar el VLM. La viabilidad de un backend AMD y de Windows nativo es un punto de validación temprana, no una capacidad ya demostrada. Véase [Marker 2.0: uso e inferencia](https://github.com/datalab-to/marker/blob/v2.0.0/README.md#usage).

### 4.2 Flujo propuesto de preparación durante la instalación

1. Inventariar CPU, GPU, SO, componentes existentes y espacio disponible.
2. Resolver una combinación versionada y compatible para cada motor solicitado.
3. Reutilizar componentes del sistema solo si su versión y funcionamiento se verifican.
4. Preparar los componentes que falten en un entorno privado de SAMI, mediante un trabajo supervisado en segundo plano.
5. Validar ese entorno antes de marcarlo como activo; no modificar el entorno que esté convirtiendo documentos.
6. Si el problema requiere un driver, indicar el paso explícito correspondiente y mantener lista la ruta CPU para continuar sin bloquear la conversión por falta de aceleración.
7. Persistir el resultado y mostrar qué está listo, qué está preparándose y por qué hay una limitación.

Este flujo completo pertenece al instalador y a la instalación/reparación explícita de componentes. Las ejecuciones normales del CLI reutilizan el perfil y realizan exclusivamente el health check de la sección 3.2. Si la preparación de instalación continúa en segundo plano, el CLI consulta su estado persistido sin iniciar otro diagnóstico.

Estados de preparación sugeridos: `not_checked`, `preparing`, `ready`, `needs_driver`, `unsupported`, `failed`. Cada estado debe incluir una razón recuperable.

"En segundo plano" significa trabajo con seguimiento, logs y resultado consultable; no un proceso abandonado. Si el usuario pide un modo que depende de la descarga, mostrar preparación y esperar o permitir cancelación. No cambiar el motor de un lote a mitad de ejecución cuando termine una instalación.

La preparación privada no debe requerir alterar Python global, reiniciar Docker, cambiar módulos del kernel ni actualizar drivers automáticamente. Esas operaciones pertenecen al paso explícito confirmado por el usuario. Si requieren reinicio, el diagnóstico debe distinguir instalación completada de aceleración ya utilizable.

Recomendación: recetas cerradas por SO/arquitectura/backend, dependencias y modelos fijados, descargas verificables y activación de un entorno nuevo después de su prueba. Bloquear preparaciones simultáneas incompatibles y conservar el entorno anterior ante un fallo. No compilar grandes dependencias desde fuentes como fallback automático.

### 4.3 Qué significa soporte multiplataforma

Separar dos compromisos: SAMI instala y convierte en el SO; una GPU concreta acelera un motor concreto. El primero no puede depender de disponer del segundo.

Prioridad de plataformas confirmada: **Windows 11 nativo y Linux basado en Debian**. Propuesta inicial de arquitectura: x86_64 en ambos, con versiones de Debian/Ubuntu y derivados a concretar según disponibilidad de dependencias y pruebas. Ser Debian-based no garantiza por sí solo que todas sus versiones tengan los mismos binarios/drivers. Windows nativo no debe presentarse como resuelto únicamente por funcionar en WSL.

macOS queda como compatibilidad secundaria: conservar adaptadores y posibilidad de empaquetado, sin bloquear la primera entrega por Intel/Apple Silicon, versiones mínimas o aceleración Apple. Linux arm64 y Windows arm64 no se incorporan automáticamente a la matriz estable.

En las plataformas prioritarias, los tres perfiles deben tener una ruta CPU local comprobada y preparada al instalar. Es un criterio de aceptación para cumplir el fallback solicitado, no una capacidad que este análisis ya haya demostrado. Verificar modelos, servidor de inferencia, limpieza de procesos y artefactos; GPU es una mejora sobre esa base. No prometer paridad de velocidad CPU/GPU.

## 5. Tres modos conservando la conversión de SAMI

| Modo público | Motor propuesto | Prioridad y comportamiento |
|---|---|---|
| `fast` | Extracción basada en el lote de Caste: PyMuPDF y pdfplumber con su configuración interna `high`, OCR e imágenes desactivados. | Mantener su ruta rápida de texto/tablas, sin cargar Marker, PyTorch, Tesseract ni VLM. |
| `balanced` | Pipeline actual de SAMI con Marker configurado en `fast`. | Conservar el tratamiento estructural de Marker con menor coste que su modo `balanced`. |
| `quality` | Pipeline actual de SAMI con Marker configurado en `balanced`. | Priorizar reconstrucción y reconocimiento de contenido; siempre local, sin API ni claves. |

La separación Caste/Marker responde a la instrucción expresa del usuario. El mapeo de los dos perfiles de Marker es una propuesta para confirmar con un corpus representativo. Los nombres no prometen superioridad de calidad en todas las páginas.

No aplicar al Markdown de Marker las normalizaciones, reconstrucción de párrafos ni heurísticas de encabezados de Caste. La integración nueva debe conservar su contenido, figuras y lógica de renderizado; el trabajo de refactor se concentra en las interfaces y la gestión alrededor del motor. Las mejoras de validación pueden producir un informe separado sin reescribir esa salida.

La documentación de Marker 2.0 diferencia sus perfiles y el uso de OCR/VLM; no basta con copiar los nombres de Caste. Los ajustes exactos quedarán ligados a la versión validada. Véase [configuración de modos de Marker 2.0](https://github.com/datalab-to/marker/blob/v2.0.0/README.md#usage).

### 5.1 Decisiones de perfiles y recursos

| Decisión | Comportamiento fijado o criterio técnico |
|---|---|
| Perfil predeterminado | **`balanced`**, confirmado. Debe quedar preparado en la instalación junto con los demás modos. |
| Fallo GPU o VRAM insuficiente | Warning y continuación automática en CPU con el mismo modo, sin diálogo ni bloqueo por la aceleración. Preparar y probar el fallback al instalar. |
| `fast` sobre páginas escaneadas | **Sin OCR automático**, igual que la configuración efectiva de Caste. Registrar página sin texto extraíble y estado parcial; no cargar un motor pesado ni cambiar de modo silenciosamente. |
| Calidad por página | Evaluar señales concretas de texto ilegible, estructura de tablas y lectura; no usar solo cantidad de texto. |
| Recursos | Separar modo de calidad de dispositivo y concurrencia. El umbral actual de 8 GiB no será una regla universal para todos los modelos. |

Para los límites de memoria, considerar modelo, precisión/cuantización, resolución, contexto, lote y memoria libre. En Apple Silicon, no sumar RAM y memoria GPU como si fueran reservas independientes.

Si falla la GPU durante una conversión, descartar la salida temporal incompleta del intento y reintentar ese documento en CPU. Desactivar el backend fallido para el resto del lote y registrar el motivo para evitar reintentos costosos con la misma condición. Distinguir incompatibilidad persistente de presión de memoria transitoria; la recuperación posterior no exige molestar al usuario en cada invocación. Un warning por fallback no equivale por sí solo a conversión fallida si termina correctamente en CPU.

### 5.2 Qué tomar y qué revisar de Caste

Tomar extracción rápida, tablas, orden heurístico y registro de vacíos. Separar la auditoría del motor para no ejecutar conversiones o muestreos al importar un módulo.

La decisión sobre rapidez se toma de la **invocación real** de Caste en `PDF2MD_caste.py`, no del nombre de su preset `fast`: el lote usa `Options(quality="high", ocr=False, images=False, overwrite=True)`. Su preset interno `fast` desactiva funcionalidades que el lote sí usa. Por tanto, el modo público `fast` de SAMI conserva detección de tablas/encabezados, orden de lectura, marcadores, estilo de tabla `pipe` y controles de consistencia de `run`, con OCR e imágenes apagados. La política de sobrescritura original sí se sustituye por salidas numeradas, porque el usuario eligió conservar conversiones previas.

No ejecutar automáticamente la celda separada de auditoría aleatoria ni añadir OCR, VLM o modelos de layout a esta ruta. Preservar enlaces bibliográficos requiere recuperar los enlaces disponibles en el PDF mediante extracción ligera; Caste no tiene un tratamiento explícito de todas las anotaciones de enlace. Medir el coste de esa adaptación y del refactor frente al lote original sobre el mismo equipo/corpus. La velocidad de Caste es el objetivo de aceptación; no hay aún una medición que permita prometer igualdad exacta entre equipos.

No trasladar sin revisión el rescate OCR: compara una salida con el mismo texto OCR con que se construyó y puede aparentar una mejora sin evidencia independiente. La comparación de tokens de celdas tampoco valida posiciones de filas/columnas, y los marcadores de rescate no coinciden con el patrón del auditor. La clasificación de PDF debe observar el origen antes del OCR, no clasificar como nativo el texto recién reconocido.

La rapidez de Caste se toma como motivación del usuario; no existe todavía un benchmark local de ambos motores con condiciones equivalentes.

## 6. Núcleo del CLI y límites entre componentes

Propuesta de responsabilidades, no estructura de archivos implementada:

| Componente | Responsabilidad |
|---|---|
| `hardware` | Diagnóstico completo de instalación, perfil de compatibilidad persistente y health check rápido, independiente de modelos pesados. |
| `runtime` | Resolver, preparar y verificar dependencias/modelos durante su instalación; gestionar backends y procesos propios al convertir sin repetir el diagnóstico. |
| `engines` | Adaptadores de Caste y del pipeline SAMI/Marker, sin lógica de terminal o ventanas. |
| `jobs` | Descubrir entradas, crear el plan de lote, asignar recursos, cancelar y continuar tras fallos. |
| `outputs` | Rutas, colisiones, recursos, staging y publicación de resultados. |
| `validation` | Diagnósticos y estados de calidad, con alcance de verificación explícito. |
| `events` | Progreso y resultados estructurados para CLI y futura UI. |
| `cli` / futura `ui` | CLI como única entrada al núcleo para la UI. La aplicación gráfica ejecuta sus comandos y consume el protocolo público de trabajos, sin importar módulos Python ni duplicar reglas de conversión. |

Definir una petición de conversión con entradas, modo, opciones, política de salida y dispositivo. Devolver un resultado con archivos, estado, advertencias, métricas y motor/dispositivo efectivo. Identificar cada trabajo y página para que los eventos puedan relacionarse sin interpretar mensajes impresos.

Los motores pesados deberían ejecutarse en procesos supervisados. Esto facilita cancelación, aislamiento de entornos y recuperación de memoria. Usar eventos versionados, por ejemplo JSON Lines sobre pipes locales; no hace falta introducir un servicio HTTP ni un daemon permanente. La elección del transporte sigue abierta.

La limpieza debe terminar exclusivamente procesos que SAMI haya creado para el trabajo. Windows necesita gestión de árboles de procesos; POSIX, grupos/señales apropiados. No buscar y matar procesos globales por contener `llama` en su nombre.

## 7. CLI y comportamiento de archivos

### 7.1 Selección y opciones

Conservar el uso directo `sami archivo.pdf`, múltiples archivos, `-o/--output`, `--mode`, `--flat`, `-q/--quiet`, ayuda y códigos de salida documentados. La conservación de referencias pasa a ser permanente: aceptar `--no-strip-refs` como opción de compatibilidad sin efecto adicional; no exponer una opción nueva que borre referencias ni ejecutar `strip_references` en la ruta de conversión.

Ejemplos de interfaz futura, no comandos disponibles todavía:

```text
sami documento.pdf --mode fast
sami uno.pdf dos.pdf --mode balanced
sami carpeta-pdfs/ --recursive --mode quality
sami uno.pdf carpeta-pdfs/ --output resultados/
sami health --json
sami doctor
sami setup
```

Propuesta adicional: exponer selección de dispositivo, concurrencia, OCR/idiomas, extracción de imágenes, marcadores de página, selección/límite de páginas y política de archivos existentes. Rechazar claramente opciones que un motor no soporte; no aceptarlas para después ignorarlas. Las opciones avanzadas propias de Marker pueden tener configuración separada y validada.

No todas esas opciones están hoy en SAMI. Los controles de Caste se evalúan como ampliaciones, manteniendo diferenciada la compatibilidad existente.

Ambos nombres existentes presentan cambios de significado en el mapeo propuesto: el antiguo `--mode fast` de SAMI corresponde al nuevo `balanced`, mientras el antiguo `--mode balanced` corresponde al nuevo `quality`. El nuevo `fast` usa Caste. `balanced` no puede conservarse simultáneamente como alias de `quality` porque pasa a ser un perfil público propio. Documentar y probar la migración, incluidos defaults guardados y scripts de usuario.

### 7.2 Carpetas y lotes

Recursividad mediante flag, orden estable y deduplicación de archivos por identidad/ruta normalizada. Resolver enlaces y diferencias de mayúsculas según el SO; evitar ciclos. No recorrer automáticamente directorios de salida ni procesar dos veces un PDF pasado como archivo y encontrado en una carpeta.

Un PDF dañado no debe abortar todo el lote. Registrar cifrados, ilegibles, fallidos, parciales y omitidos con explicación. Conservar los PDF originales. El progreso del lote cuenta trabajos únicos, no argumentos de entrada.

### 7.3 Carpeta de trabajo y salida

Propuesta: `--output` determina la salida; sin él, cada PDF utiliza su carpeta de origen, como SAMI actual. Por defecto, crear una subcarpeta por documento con Markdown y recursos; `--flat` conserva su significado actual.

Si entran PDF de varias carpetas, cada uno mantiene ese comportamiento salvo que se elija una carpeta común. No derivar todos los destinos de la carpeta del primer PDF. La futura UI debe mostrar origen y destino efectivo antes de iniciar.

Separar carpeta de trabajo elegida para documentos/resultados de cachés, modelos y logs privados de la aplicación. Usar ubicaciones adecuadas para cada SO y conservar `SAMI_HOME` como override.

Decisión confirmada: ante una salida existente, crear una nueva salida numerada, conservando ambas versiones. Aplicar la misma identidad de salida al Markdown y sus recursos, evitando colisiones entre PDF homónimos de distintas carpetas, especialmente con salida común o `--flat`. Las políticas alternativas, si se exponen, deben ser explícitas y nunca sustituir este valor predeterminado.

La publicación debe coordinar Markdown y recursos: una conversión fallida no debe estropear un resultado anterior. El mecanismo dependerá de si se reemplaza una carpeta completa o se publican recursos inmutables y luego el Markdown.

La bibliografía y los enlaces de referencia deben permanecer dentro del mismo `.md`, sin producir un `.bib`, JSON bibliográfico ni otro artefacto externo necesario para leerlos. Interpretación operativa: conservar el texto y usar enlaces Markdown inline al destino recuperable del PDF; conservar también sus enlaces internos cuando puedan representarse con anclas del propio documento. No inventar URL ni resolver referencias consultando servicios externos. La recuperación de anotaciones debe formar parte de los casos de prueba de ambos motores.

### 7.4 Dos niveles de progreso

Mostrar progreso del archivo actual y progreso del lote, incluidos nombre, etapa y archivos terminados/total. Separar preparación de modelos de conversión para explicar el tiempo del primer uso.

Contar páginas o unidades reales donde el motor las exponga. Si una etapa Marker no aporta progreso medible, mostrar actividad indeterminada y etapa; no inventar un porcentaje. No reescribir el pipeline de conversión solo para simular una barra.

La barra del lote puede representar trabajos terminados/total: no debe presentarse como estimación del tiempo restante cuando los tamaños son diferentes. Los contadores distinguen éxito, parcial, fallo y cancelación. Con varios trabajos simultáneos, cada uno debe tener su progreso identificable.

El modo silencioso, terminales sin TTY y salida estructurada requieren presentación propia. La futura UI consume los mismos eventos; no analiza logs de texto.

### 7.5 Funcionalidades finales previstas del CLI

Esta es la lista consolidada de alcance para la primera entrega, actualizada con las decisiones del usuario. Las ampliaciones de flags y detalles técnicos pendientes se distinguen al final; no se consideran decisiones confirmadas por aparecer en un ejemplo de sintaxis.

| Funcionalidad | Resultado esperado |
|---|---|
| Uso independiente | Instalar y usar SAMI por completo desde terminal, antes de que exista la UI y sin depender de ella. |
| Entradas | Convertir uno o varios PDF, una carpeta o una combinación de archivos y carpetas; recorrido recursivo opcional, orden estable y deduplicación. |
| Tres modos | `fast` según la configuración efectiva de Caste sin OCR ni imágenes; **`balanced` por defecto** y `quality` conservando SAMI/Marker. El mapeo técnico propuesto es Marker `fast` y Marker `balanced`, respectivamente. |
| Contenido de salida | Markdown con texto y, según motor/opciones, estructura, tablas, ecuaciones y figuras. Conservar el comportamiento del pipeline Marker; indicar las limitaciones del motor rápido. |
| Procesamiento local | Convertir sin claves ni servicios externos; los componentes de los tres modos quedan preparados al instalar para funcionar después sin conexión. |
| Diagnóstico de instalación | Detectar CPU, RAM, GPU/VRAM, SO, arquitectura, drivers y componentes; verificar los motores y persistir resultados positivos y negativos. |
| Health habitual | Consulta rápida antes del lote, sin cargar modelos, descargar ni repetir el análisis profundo; detectar cambios relevantes e indicar si hace falta reparación. |
| Recursos CPU/GPU | CUDA/ROCm según compatibilidad validada en plataformas prioritarias; ante fallo GPU, warning y continuación automática en CPU, manteniendo el modo. Metal queda en el objetivo secundario macOS. |
| Preparación y mantenimiento | Dejar los tres modos, modelos y fallback CPU listos al instalar; no pedir al usuario completar dependencias en el uso normal. Consultar estado, actualizar o reparar y conservar una instalación utilizable ante fallos. Drivers en un paso explícito. |
| Progreso | Barra por archivo y por cantidad de archivos del lote, etapas y tiempos; actividad indeterminada cuando el motor no exponga porcentaje real. |
| Directorio de salida | Elegir destino, mantener salida junto a cada PDF por defecto, subcarpeta por documento y opción `--flat`; crear una nueva salida numerada cuando ya exista otra. |
| Referencias y controles actuales | Conservar siempre bibliografía y enlaces embebidos en el Markdown; mantener `--no-strip-refs` como compatibilidad sin efecto adicional, modo silencioso, ayuda y códigos de salida; documentar la migración de modos. |
| Errores y cancelación | Continuar el lote tras un PDF fallido, explicar errores/parciales, cancelar y limpiar procesos propios; conservar PDF originales y resultados anteriores válidos. |
| Resultados y diagnóstico | Resumen por documento/lote con estado, rutas, advertencias y motor/dispositivo efectivo; informes de consistencia con alcance explícito, sin confundir ausencia de excepciones con fidelidad certificada. |
| Automatización y futura UI | Health JSON, eventos de progreso/resultados JSON Lines y control de cancelación mediante un contrato versionado; logs separados para scripts y la aplicación Electron. |
| Instalación multiplataforma | Prioridad Windows 11 mediante `irm` y Linux Debian-based mediante `curl`, comando disponible en `PATH`, actualización y desinstalación. macOS secundario. |

Ampliaciones propuestas para la interfaz pública: dispositivo, concurrencia, OCR/idiomas, imágenes, marcadores de página y rango/límite de páginas. Exponer solo opciones soportadas por el motor o devolver un error claro; no prometer paridad de capacidades entre Caste y Marker. Definir los flags exactos y capacidades durante el cierre del diseño.

Comandos de gestión propuestos: `sami health` consulta rápida en formato humano o JSON; `sami doctor` explica el diagnóstico persistido y sus problemas sin ejecutar pruebas profundas; `sami setup` entra explícitamente al flujo de instalación/preparación/reparación. La actualización y desinstalación usan el registro de componentes del instalador; los nombres de comandos adicionales no están fijados.

Comportamientos de uso diario cerrados: `balanced` por defecto, `fast` como el lote Caste sin OCR/imágenes, referencias/enlaces siempre en el Markdown, nuevas salidas numeradas, tres modos preparados durante instalación y warning con fallback CPU automático ante fallo GPU. El soporte GPU se declara por combinaciones verificadas, no para cualquier tarjeta del fabricante.

## 8. Instaladores y distribución

Primera entrega prioritaria: bootstrap Bash para Linux basado en Debian con `curl` y PowerShell para Windows 11 con `irm`. Mantener macOS como objetivo secundario. Las URL públicas se definirán después de existir los artefactos; no publicar instrucciones de instalación de componentes aún inexistentes.

Propuesta: instalación por usuario con Python administrado y entornos privados, reutilizando lo compatible cuando corresponda. uv puede obtener una versión de Python sin exigir que el usuario la prepare manualmente; véase [gestión de Python de uv](https://docs.astral.sh/uv/guides/install-python/). Esta opción debe compararse con distribuir el CLI empaquetado; el usuario aún no eligió un formato binario para el CLI.

Instalar la base rápida y **ambos perfiles Marker**, incluidos todos sus modelos/componentes necesarios y la ruta CPU de respaldo, dentro del flujo inicial de instalación. Preparar también la aceleración compatible y persistir el diagnóstico completo. El usuario no debe tener que elegir ni instalar modos después. El primer uso habitual no debe convertirse en otro análisis profundo ni descarga de modelos; ejecutar ayuda tampoco descarga componentes.

Separar núcleo, motor rápido, motor Marker, runtimes y modelos. Una dependencia pesada obligatoria de Marker en la base impediría cumplir la instalación ligera de `fast`. No asumir que extras Python por sí solos resuelven todas las variantes CUDA/ROCm: el entorno debe fijarse por plataforma y runtime.

Fijar versiones de release, artefactos y combinaciones probadas en lugar de resolver siempre `latest`. Actualización recuperable, reparación y desinstalación deben compartir el registro de componentes. Funcionar sin red tras completar la preparación de los tres modos; una instalación interrumpida por falta de red conserva el estado recuperable sin anunciar una preparación completa.

Construir y verificar artefactos en cada SO/arquitectura incluidos en la matriz. Una release multiplataforma necesita probar instalación limpia, actualización, desinstalación, ejecución local y cancelación; el soporte GPU requiere además hardware real apropiado. Los instaladores no sustituyen esas pruebas.

En Windows, el bootstrap PowerShell y el instalador descargable de la futura UI deben converger en la misma instalación y su registro de componentes. La primera entrega CLI configura su lanzador y `PATH`; cuando se distribuya la UI, el despliegue añade los accesos de escritorio e Inicio y el ejecutable gráfico descritos en la sección 9.1. Reejecutar el instalador no debe crear una segunda instalación independiente ni accesos duplicados.

### 8.1 Un instalador, dos etapas ordenadas

Separar la entrega temporal del producto de sus pasos de instalación. Primero se publica un CLI completo e independiente; la UI se publica después. Cuando ambas piezas existan, un único bootstrap invocado desde `irm` podrá encadenar las dos etapas, sin exigir dos comandos al usuario. También se podrá instalar solo el CLI o añadir posteriormente la UI sobre un CLI existente.

| Paso | Acción del despliegue Windows | Resultado que permite continuar |
|---|---|---|
| 1. Resolver instalación | Detectar una instalación de SAMI propia y las versiones compatibles publicadas. | Plan explícito: instalar CLI, reutilizarlo o actualizarlo antes de añadir la UI. |
| 2. Instalar CLI y núcleo | Ejecutar el diagnóstico completo si es instalación nueva; preparar los tres modos y su fallback CPU, GPU compatible, guardar compatibilidad y configurar lanzador y `PATH`. | CLI independiente, todos los modos preparados y registro persistente completo. |
| 3. Validar CLI | Realizar las pruebas de instalación y consultar su health estructurado. Si ya estaba instalado, empezar por el health rápido y reparar explícitamente solo si hace falta. | Núcleo ejecutable, versión/protocolo compatible y tres perfiles listos; un fallo GPU activa CPU con warning. |
| 4. Instalar UI | Desplegar el ejecutable gráfico y sus dependencias de presentación sobre ese núcleo. | UI vinculada al CLI validado, sin duplicar motores, modelos ni diagnóstico. |
| 5. Integrar y comprobar | Crear accesos de escritorio e Inicio, verificar destinos y comprobar la comunicación UI–CLI y el arranque gráfico. | Instalación finalizada: el usuario puede abrir el `.exe` o sus accesos con doble clic. |

El instalador debe esperar a que termine la preparación de los tres modos y su fallback CPU antes de anunciar que el producto está listo. Preparar en segundo plano no significa completar la instalación dejando dependencias o modelos pendientes para el primer doble clic o para un modo aún no usado. Si no puede habilitar GPU, avisar y terminar con CPU preparada, sin bloquear por la aceleración.

Mientras la UI aún no se haya publicado, el bootstrap instala y valida el CLI y termina ahí. No crea accesos a ejecutables gráficos inexistentes. Cuando se distribuya la UI, la instalación completa incluye ambas etapas; el modo CLI solo sigue disponible.

Si falla el CLI, no continuar con la instalación gráfica ni anunciar éxito completo. Si falla la UI después de validar el CLI, conservar el CLI operativo y permitir reintentar únicamente la etapa gráfica. Si faltan drivers, mantener el paso explícito acordado: una ruta CPU válida puede satisfacer el health sin reducir silenciosamente el perfil de calidad.

### 8.2 Contrato de health entre instalador, CLI y UI

Propuesta de comando futuro: `sami health --json`, con salida estructurada versionada y código de salida documentado. Es una operación rápida de consulta del estado persistido y comprobaciones ligeras; nunca inicia un diagnóstico profundo, descarga o instalación. El instalador ejecuta las pruebas profundas en sus pasos propios y después consulta este contrato.

El resultado debe identificar instalación, versión del CLI/núcleo, versión del protocolo de trabajos, validez del perfil de compatibilidad, estado de preparación, tres modos y motivos concretos si algo requiere reparación. Distinguir fallo del núcleo de GPU no utilizable: CPU validada con warning permite continuar y abrir la UI. Una instalación completa no debe dejar perfiles pendientes de descarga.

La UI declara qué versiones del protocolo y del núcleo admite. El despliegue verifica esa compatibilidad antes de instalarla y conserva un registro que enlaza ambas piezas. Usar la ruta absoluta registrada del lanzador privado del CLI: la UI no depende de que Explorer haya actualizado `PATH`, de una terminal abierta ni de que otra instalación de `sami` aparezca primero en el entorno.

Propuesta de comunicación: proceso local del CLI/núcleo con argumentos estructurados y eventos JSON Lines mediante pipes, sin consola visible. La UI consume resultados y eventos del protocolo; no reproduce la lógica MD, no analiza logs y no ejecuta comandos mediante cadenas de shell. El ejecutable gráfico puede empaquetarse de forma independiente sin duplicar el entorno pesado de conversión.

Actualizar la UI debe comprobar primero el health y la compatibilidad del núcleo instalado. Actualizar el CLI debe mantener una pareja compatible o actualizar ambas piezas mediante un plan recuperable. Desinstalar solo la UI conserva CLI, modelos y configuración; retirar un núcleo del que depende la UI debe tratarse como una operación coordinada y explicada al usuario.

### 8.3 Primer doble clic y aperturas posteriores

La UI localiza su instalación registrada, consulta el health rápido una sola vez y abre su ventana con los motores preparados. No solicita activar Python, escribir comandos ni repetir la preparación de GPU. El diagnóstico completo queda en instalación; cargar el motor al comenzar una conversión es una etapa normal del trabajo.

Si después de instalar cambian drivers o se borran componentes, mostrar una explicación gráfica y una acción explícita para reparar la instalación, sin cerrar silenciosamente ni abrir una consola. Ofrecer las capacidades que continúen validadas. Este caso de recuperación no debe convertir cada apertura en una reinstalación automática.

## 9. UI de escritorio empaquetada por SO: alcance posterior

Requisitos conservados para la segunda entrega: arrastrar archivos/carpetas desde Explorer, Finder y gestores Linux; arrastrar resultados hacia otras aplicaciones; visor PDF y MD embebido; rutas visibles; botón para abrir la carpeta; elección de carpeta de trabajo y destino por defecto junto al PDF; cola y progreso.

### 9.1 Despliegue Windows: aplicación lista para usar

El usuario confirma que desplegar la UI incluye su integración en el escritorio, el menú Inicio y `PATH`. Estos elementos forman parte del resultado de instalación; no deben quedar como pasos manuales para el usuario.

| Elemento | Comportamiento requerido o propuesta técnica |
|---|---|
| Instalación de aplicación | Propuesta por usuario, bajo una ubicación estable como `%LOCALAPPDATA%\Programs\SAMI`; separar ejecutables de cachés, modelos, diagnóstico y documentos. |
| Escritorio | Crear `SAMI.lnk` con icono propio y destino al lanzador gráfico instalado. Resolver la carpeta real de escritorio mediante las API del SO, incluidas ubicaciones redirigidas como OneDrive. |
| Menú Inicio | Crear una entrada `SAMI` en Programas del usuario para abrir la UI y facilitar su búsqueda desde Inicio. Resolver la carpeta con Known Folders, sin construir rutas a partir del idioma de Windows. |
| Terminal | Publicar un lanzador estable `sami.exe` para CLI. Propuesta adicional: `sami-gui.exe` para abrir la UI desde terminal o desde los accesos. Los nombres del ejecutable gráfico siguen sujetos al empaquetado elegido. |
| `PATH` | Añadir solo el directorio estable de lanzadores al `PATH` persistente del usuario, preservando las demás entradas y evitando duplicados. No añadir entornos internos ni carpetas de versiones temporales. |
| Apertura gráfica | Doble clic en escritorio o Inicio abre la UI sin consola visible, sin depender del directorio actual y sin exigir activar un entorno Python. |
| Registro de aplicación | Registrar versión y desinstalador para que SAMI aparezca entre las aplicaciones instaladas. Mantener una identidad de aplicación estable entre versiones. |
| Actualización y reparación | Mantener accesos y lanzadores apuntando a una ubicación estable; reemplazar componentes de forma recuperable y reparar accesos rotos sin duplicarlos. Conservar configuración y diagnóstico válido de componentes que no cambiaron. |
| Desinstalación | Retirar los accesos, lanzadores, registro y entrada de `PATH` creados por SAMI. Conservar PDF originales y resultados del usuario; definir por separado la limpieza de modelos/cachés. |

Microsoft documenta la creación de accesos de Inicio mediante Shell Links y `FOLDERID_Programs`; usar el mismo enfoque de carpetas conocidas para localizar el escritorio. Véanse [accesos de Inicio](https://learn.microsoft.com/en-us/windows/win32/shell/how-to-add-shortcuts-to-the-start-menu) e [identificadores Known Folders](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid).

La actualización persistente de `PATH` debe notificarse al entorno de Windows. El bootstrap puede actualizar además su propia sesión PowerShell; no debe prometer modificar el entorno de terminales que ya estaban abiertas y son procesos independientes. La UI queda disponible de inmediato desde sus accesos, y la instalación debe comprobar el CLI en un proceso con el entorno actualizado. Véase [variables de entorno de Windows](https://learn.microsoft.com/en-us/windows/win32/procthread/environment-variables).

Con el stack Electron propuesto, usar `electron-builder` y su target NSIS para producir el instalador gráfico `.exe`, invocado también desde el bootstrap `irm`. NSIS expone la creación de accesos de escritorio e Inicio; el bootstrap compartido conserva la responsabilidad de instalar/validar CLI, registrar su ruta y preparar `PATH`. Esas tareas no se resuelven por crear el paquete Electron. Véase [NSIS en electron-builder](https://www.electron.build/v26/docs/nsis/). Los drivers mantienen su paso explícito independiente.

Al abrir la UI, reutilizar el diagnóstico persistido y el health check rápido del núcleo. No repetir el análisis profundo por pulsar el icono. La creación de accesos no cambia la carpeta de trabajo: al añadir PDF, el destino predeterminado sigue su carpeta de origen según la política definida.

### 9.2 Stack propuesto: Electron como interfaz del CLI

La prioridad indicada por el usuario es una herramienta útil y fácil de codificar, dependiente del CLI. No es necesario compartir código con Python ni optimizar el tamaño del paquete o el rendimiento gráfico. La elección de diseño recomendada es **Electron + JavaScript + HTML/CSS**, con `electron-builder` para distribuirla.

Electron presenta una interfaz hecha con tecnología web dentro de una aplicación de escritorio empaquetada para cada SO. El ejecutable Windows abre con doble clic. El tamaño de Chromium/Node es una consecuencia aceptable de las prioridades indicadas. No exige Node instalado por el usuario final.

| Pieza | Elección propuesta | Trabajo que resuelve |
|---|---|---|
| Ventana y controles | Electron con HTML, CSS y JavaScript sencillos. | Lista de PDF, opciones, botones, progreso y panel de resultados. Empezar sin framework de componentes ni servidor web. |
| Ejecución de comandos | `node:child_process.spawn` en el proceso principal de Electron. | Invocar el CLI instalado, consumir `stdout`/`stderr`, recibir fin de proceso y gestionar cancelación mediante el protocolo del CLI. |
| Puente ventana/proceso | `preload.js`, `contextBridge` e IPC con operaciones concretas. | Pedir health, convertir, cancelar, seleccionar carpetas, abrir destinos y exportar resultados. |
| Protocolo CLI | Health JSON y progreso/resultados JSON Lines, versionados. | Toda decisión de conversión, compatibilidad, rutas de salida, descubrimiento de carpetas y estado de trabajos reside en el CLI. |
| Visor PDF | PDF.js empaquetado localmente. | Previsualización embebida de documentos PDF. |
| Visor MD | markdown-it; KaTeX para ecuaciones cuando corresponda. | Previsualización local del Markdown, recursos relativos y fórmulas sin cambiar el archivo generado. |
| Instalación gráfica | electron-builder: NSIS en Windows; evaluar DMG en macOS y AppImage/paquete para Linux. | Artefactos por SO, iconos y distribución de la interfaz. El contrato CLI-first sigue vigente. |

Node ofrece creación asíncrona de procesos y flujos de entrada/salida, adecuados para mantener una UI mientras SAMI convierte. Usar una ruta absoluta al ejecutable registrado y argumentos separados, con `shell: false` y `windowsHide: true`; no concatenar comandos a partir de nombres de archivo. Véase [child_process de Node](https://nodejs.org/api/child_process.html). Esta es la integración con comandos de terminal que necesita la herramienta; no requiere una terminal embebida ni emular un shell.

Mantener el acceso a procesos en el proceso principal y exponer a la ventana solo operaciones específicas mediante [context isolation/contextBridge](https://www.electronjs.org/docs/latest/tutorial/context-isolation). El CLI envía eventos estructurados por `stdout` y logs por `stderr`; la UI debe manejar mensajes fragmentados por el transporte sin interpretar texto humano como progreso. La cancelación debe ser una operación del CLI que cierre sus procesos propios, incluida la ejecución en Windows.

El arrastre hacia dentro usa los eventos de archivos y `webUtils.getPathForFile`; hacia fuera, la API de arrastre nativo de Electron. Véanse [rutas de archivos](https://www.electronjs.org/docs/latest/api/web-utils) y [drag and drop nativo](https://www.electronjs.org/docs/latest/tutorial/native-file-drag-drop/). Abrir la carpeta de salida se resuelve con las operaciones de escritorio del proceso principal, usando la ruta devuelta por el CLI.

Los visores usan [PDF.js](https://mozilla.github.io/pdf.js/), [markdown-it](https://github.com/markdown-it/markdown-it) y [KaTeX](https://katex.org/docs/browser). Empaquetar scripts, fuentes y estilos localmente; no depender de CDN. Mostrar HTML de tablas y recursos locales mediante una política de previsualización controlada; el contenido del documento no debe poder ejecutar comandos. La UI representa los archivos que el CLI produjo y no implementa otra conversión PDF→MD.

La UI se mantiene en un proyecto independiente con su propio `package.json` y versiones, y una dependencia declarada del CLI/protocolo compatible. No importar `sami` como biblioteca, no empaquetar una copia de sus motores Python y no levantar un backend HTTP para comunicar ambas piezas. El empaquetado por SO puede coexistir con el CLI distribuido separadamente.

Prototipo posterior propuesto: ventana con selección/arrastre, selector de modo, carpeta de salida, ejecutar/cancelar, dos niveles de progreso y botón para abrir resultados. Añadir después visores y exportación por arrastre sobre el mismo contrato. Esta secuencia no autoriza implementación ahora.

Pendientes de UX y validación:

- Arrastrar hacia fuera debe exportar archivos reales mediante el protocolo del SO. La aplicación receptora decide qué acepta; no puede garantizarse literalmente cualquier destino.
- Un Markdown que referencia imágenes no es un documento autocontenido. Proponer exportar la carpeta de resultado o un paquete junto con sus recursos; definir la opción de arrastrar solo el `.md`.
- Usar copia para exportar inicialmente; discutir movimientos por separado para no romper rutas ni perder el origen.
- Verificar el visor MD con LaTeX, HTML de tablas e imágenes de Marker; ajustar la previsualización sin modificar el Markdown de salida.
- Mantener responsive la UI durante preparación y conversión mediante el supervisor compartido. Incluir navegación, zoom/búsqueda PDF, errores y apertura del destino en la validación de la entrega gráfica.

## 10. Validación que permitirá aceptar el refactor

| Área | Evidencia exigida antes de declarar soporte |
|---|---|
| Conservación de SAMI | Comparar salida estructural y contenido de Marker antes/después en los mismos PDF, con versiones/modelos fijados y opciones equivalentes. Explicar toda diferencia material. |
| Motor Caste | PDF nativos simples, columnas, tablas, imágenes y escaneos con/sin OCR; no pérdida silenciosa de páginas. |
| Perfil rápido elegido | Comparación con el lote Caste `high/ocr=False/images=False`, manteniendo su ruta y controles; sin carga de modelos ni auditoría aleatoria añadida. |
| Referencias embebidas | Bibliografía conservada en ambos motores, enlaces URL/DOI recuperables inline y anclas internas cuando procedan; sin artefactos bibliográficos externos ni consultas de red. |
| Fallback GPU | Fallo en health, inicialización y ejecución: warning, reintento del documento en CPU, mismo modo y continuación del lote sin pedir confirmación. Tres rutas CPU preparadas durante instalación. |
| Tres modos | Medir tiempo, RAM/VRAM, cobertura, orden de lectura, estructura de tablas, ecuaciones y figuras. Separar arranque/descarga de conversión estable. |
| Hardware | Sin GPU, driver ausente, runtime incompatible, múltiples GPU, poca VRAM, memoria unificada y fallo de prueba del motor. |
| Persistencia y health check | Reutilización de resultados positivos/negativos, esquema desconocido, perfil ausente/corrupto, invalidación selectiva tras cambios, sin repetición del diagnóstico profundo al usar el CLI; medir latencia sin red ni carga de modelos. |
| Instalación | Equipo limpio por SO, sin Python, con runtime existente compatible/incompatible, sin permisos admin, sin red y actualización interrumpida. |
| Integración Windows de la UI | Instalación por usuario desde bootstrap/instalador; escritorio normal/redirigido, menú Inicio y búsqueda, doble clic sin consola, CLI en entorno actualizado, reinstalación sin duplicados y desinstalación que retire únicamente la integración de SAMI. |
| Despliegue CLI → UI | Instalación CLI independiente; añadir UI a CLI sano; detectar versiones incompatibles; bloquear etapa gráfica si falla el núcleo; conservar CLI si falla UI; health por ruta registrada; doble clic funcional sin depender de `PATH`, de la terminal ni de descargas pendientes. |
| Archivos | Rutas Unicode/espacios, carpetas recursivas, duplicados, homónimos, cifrados, salida sin permisos y espacio insuficiente. |
| Recuperación | Cancelación, fallo de un documento y fallo durante publicación; conservar resultados anteriores y no dejar procesos propios activos. |
| CLI | Flags actuales, alias acordados, ayuda sin descargas, códigos de salida, progreso real y uso sin TTY. |

Los dos PDF de `test-pdfs/` son punto de partida, no cobertura suficiente. Añadir un corpus pequeño representativo con expectativas revisadas. Comparar retención de tokens ayuda a detectar pérdidas, pero no certifica por sí sola fidelidad ni calidad de OCR.

No fijar en este documento porcentajes de mejora, segundos por página ni umbrales universales de VRAM sin mediciones. Las pruebas se diseñarán con la implementación; no se han creado ni ejecutado aquí.

## 11. Secuencia propuesta de trabajo, después de discutir el diseño

| Fase | Resultado revisable | Condición de cierre |
|---|---|---|
| 0. Decisiones y viabilidad | Acordar modos/defaults y comprobar dependencias de Marker por plataforma/backend. | Matriz concreta y rutas CPU/GPU viables; incertidumbres visibles. |
| 1. Aislar el núcleo actual | Adaptador SAMI/Marker y contrato de trabajos/eventos. | Conversión MD preservada en comparación con la base actual. |
| 2. Diagnóstico y runtimes | Diagnóstico de instalación persistido, health check rápido, preparación privada y paso explícito de drivers. | Reutilización e invalidación selectiva comprobables, latencia de arranque medida y prueba real de motor durante instalación. |
| 3. Tres perfiles y CLI | Incorporar Caste en `fast`, carpetas, opciones y dos niveles de progreso. | Perfiles definidos, resultados verificables y compatibilidad CLI acordada. |
| 4. Instalación multiplataforma | Bootstrap `curl`/`irm`, CLI independiente listo, contrato de health, paquetes probados y actualización. | Cierre de la matriz estable de SO/arquitecturas y aceleración declarada; CLI completo antes de la UI. |
| 5. UI | Segunda etapa del despliegue, condicionada al health del CLI; aplicación compilada/empaquetada por SO e integración Windows en escritorio, Inicio y `PATH`. | Instalar o reutilizar CLI, validar y después instalar UI; doble clic y flujos gráficos, exportación/visores y actualización/desinstalación verificados. Entrega separada. |

Las fases ordenan decisiones y entregables; no son una autorización de ejecución ni una estimación de calendario.

## 12. Decisiones cerradas y detalles técnicos pendientes

Decisiones de uso diario confirmadas por el usuario:

| Tema | Decisión final de diseño |
|---|---|
| Predeterminado | `balanced`. |
| Rapidez de `fast` | Tomar la configuración efectiva del código de Caste: `high`, OCR apagado e imágenes apagadas. Conservar su extracción de texto/tablas; verificar velocidad comparable sin añadir modelos pesados. |
| Referencias | Mantener siempre bibliografía y sus enlaces dentro del mismo Markdown; no eliminarlos ni depender de un artefacto bibliográfico externo. |
| Resultado existente | Crear una salida numerada y conservar la anterior. |
| Instalación inicial | Preparar todo lo necesario para los tres modos y el fallback CPU; no pedir instalaciones adicionales en el uso normal. |
| Fallo de aceleración | Emitir warning y continuar automáticamente en CPU; no bloquear por un fallo GPU ni pedir confirmación. Mantener el modo elegido. |
| Plataformas | Windows 11 y Linux Debian-based prioritarios; macOS secundario. |

Detalles aún por cerrar antes o durante la validación técnica: versiones concretas Debian/Ubuntu y arquitecturas; combinaciones GPU/runtime verificadas; flags de capacidades por motor; versionado del protocolo; y mecanismo de publicación atómica de Markdown/recursos. El mapeo técnico conservado como propuesta es `balanced → Marker fast` y `quality → Marker balanced`, a validar con el corpus sin cambiar el objetivo de preservar la conversión SAMI.

Se mantienen además diagnóstico profundo persistido al instalar, health rápido en uso habitual, conversión local sin claves, drivers explícitos, CLI terminado antes de UI y despliegue gráfico posterior mediante Electron con escritorio, Inicio y `PATH`. **Este cierre de decisiones no autoriza implementar todavía.**

## 13. Ramas, unidades de trabajo y archivos por cambiar

### 13.1 Dos ramas y orden de integración

| Orden | Rama exacta | Base y destino | Alcance y condición de cierre |
|---|---|---|---|
| 1 | `refactor/0_2_0_sami_cli` | Se crea desde `main` actualizado; PR hacia `main`. | Núcleo, tres modos, diagnóstico persistido, health rápido, fallback CPU, CLI, instaladores y CI. Debe instalar y convertir de forma independiente, sin UI. |
| 2 | `feat/0_3_0_sami_ui` | Se crea desde `main` después del merge y publicación del CLI `0.2.0`; PR hacia `main`. | UI Electron `0.3.0`, integración con el contrato CLI publicado, instalador gráfico, accesos y validación de doble clic. |

Estas son las dos ramas de desarrollo solicitadas. No crear ramas, hacer commits, abrir PR, realizar merges ni publicar nada durante la elaboración de este plan. La rama UI empieza después de disponer del CLI completo; así no necesita duplicar sus cambios ni apuntar su PR a una rama intermedia.

Decisión actualizada de versionado: **`0.2.0` entrega el CLI completo e independiente y `0.3.0` entrega la UI**. Publicar `v0.2.0` al terminar el refactor CLI, sin esperar trabajo gráfico. Después desarrollar, integrar y publicar `v0.3.0` sobre esa base. Ambos tags conservan su commit y assets; la UI no se añade retroactivamente a `v0.2.0`.

Dividir los commits por comportamiento completo, con sus pruebas y documentación. Para el CLI: preservar Marker; introducir diagnóstico/runtime persistido; añadir Caste y política de referencias/salidas; exponer lote/progreso/protocolo; cerrar instalación y release. Para la UI: health y ejecución de CLI; cola/progreso/cancelación; visores/arrastre; empaquetado e integración Windows. Cada unidad debe declarar verificación y alcance de rollback.

El tamaño previsto del refactor tiene riesgo alto de superar 400 líneas por PR. Registrar el tamaño real y facilitar revisión por unidades; dividir commits no equivale a tener varios PR pequeños. El plan conserva las dos ramas pedidas y no introduce una cadena de subramas. Si se mantienen PR mayores al presupuesto de revisión, documentar la justificación y estrategia de revisión al preparar esos PR, sin comprimir código ni borrar comentarios para reducir líneas.

### 13.2 Rama CLI: archivos existentes que se editarán

| Archivo existente | Cambio previsto |
|---|---|
| `sami/cli.py` | Reducirlo a la entrada pública: modos/defaults, archivos/carpetas, opciones, progreso, health/doctor/setup, JSON y códigos de salida. Extraer responsabilidades conservando el pipeline Marker y la compatibilidad acordada. |
| `sami/__init__.py` | Declarar la versión objetivo `0.2.0`; mantenerla alineada con metadatos y salida de versión. |
| `pyproject.toml` | Subir a `0.2.0`; ajustar dependencias, entrada CLI, empaquetado y herramientas de desarrollo/pruebas. Separar el entorno base de las variantes de runtime manteniendo la instalación completa de los tres modos. |
| `requirements.txt` | Alinear con el empaquetado y las versiones validadas. Evitar una segunda lista contradictoria o un `pip install` que sustituya la variante CPU/CUDA/ROCm preparada. |
| `install.sh` | Bootstrap versionado para Debian-based: instalar todo, preparar CPU/GPU, persistir health y configurar el comando; consumir release/manifest en lugar de instalar el `main` cambiante. |
| `setup.sh` | Alinear el flujo de instalación/reparación/actualización con el núcleo compartido de preparación, los tres modos y fallback CPU. Evitar mantener una receta antigua paralela con comportamiento distinto. |
| `.gitignore` | Añadir outputs temporales, entornos, cachés/modelos locales y artefactos de pruebas/build; mantener versionados código, manifiestos y locks necesarios. |
| `README.md` | Documentar `0.2.0`, instalación completa, tres modos, carpetas, health, referencias permanentes, salidas numeradas y fallback CPU. Explicar migración de los nombres antiguos. |
| `CLAUDE.md` | Actualizar arquitectura, comandos, plataformas, preparación al instalar y contrato para herramientas/agentes. |
| `.claude/agents/convert.md` | Actualizar modos, carpeta de entrada, salidas y referencias permanentes. |
| `.claude/agents/install-check.md` | Sustituir supuestos de descarga en primera conversión por verificaciones de instalación completa y health persistido; incluir Windows y CPU. |
| `.claude/agents/test.md` | Actualizar casos y expectativas por motor, referencias/enlaces, salidas numeradas y fallback. Conservar resultados históricos identificados como tales. |
| `test-pdfs/gen_test.py` | Extender solo lo necesario para producir casos reproducibles de referencias, links, tablas y otras estructuras de aceptación. Los PDF actuales sirven como base y no se regeneran sin necesidad. |
| Este documento de plan | Registrar decisiones finales, evidencias de verificación y relación con las dos ramas y la release. |

`odd/tasks/refactor-core-sami/PDF2MD_caste.py` es referencia de lectura para extraer el motor; no es el módulo que se importará en producción. No convertirlo en una segunda implementación mantenida. `cpu_monitor.py` no requiere cambios funcionales salvo necesidad concreta demostrada por el refactor. `.atl/` es información local ajena a esta entrega.

### 13.3 Rama CLI: archivos y directorios nuevos previstos

Los nombres de módulos son un mapa de responsabilidades para implementar; pueden fusionarse si simplifica el código, siempre que se conserven los límites y contratos. No crear módulos vacíos solo para reproducir esta tabla.

| Archivo/directorio nuevo propuesto | Responsabilidad |
|---|---|
| `sami/engines/__init__.py` | Contrato y selección de motor, con importación diferida. |
| `sami/engines/marker.py` | Encapsular el pipeline actual de SAMI/Marker, sus perfiles y eventos. Mantener sus reglas de conversión. |
| `sami/engines/fast.py` | Motor extraído de Caste con la configuración elegida, sin código global de notebook ni auditoría aleatoria automática. |
| `sami/hardware.py` | Inventario completo de instalación y consultas ligeras de recursos. |
| `sami/compatibility.py` | Perfil persistente, esquema, huellas, health rápido e invalidación selectiva. |
| `sami/runtime.py` | Resolver/preparar/validar los tres modos y runtimes privados; actualización y reparación. |
| `sami/processes.py` | Supervisar procesos propios, cancelación multiplataforma y recuperación CPU. |
| `sami/jobs.py` | Descubrir archivos/carpetas, deduplicar, ordenar y ejecutar lotes. |
| `sami/outputs.py` | Destinos, numeración, staging y publicación coherente de Markdown/recursos. |
| `sami/events.py` | Contrato versionado de eventos, resultados y control de trabajos usado por el CLI y consumido por la UI. |
| `sami/validation.py` | Controles de consistencia e informes con alcance explícito, sin reescribir el Markdown de Marker. |
| `install.ps1` | Bootstrap Windows 11: instalación completa por usuario, `PATH`, registro de ubicación/versión y health. En la etapa UI añadirá su instalación solo después de validar CLI. |
| `packaging/runtime-manifest.json` | Combinaciones publicables de runtimes, versiones/modelos, fuentes y verificaciones por plataforma. No contiene el diagnóstico personal de una máquina. |
| `packaging/constraints/` y lock del gestor elegido | Resolución reproducible de base y variantes CPU/CUDA/ROCm validadas. El nombre/formato exacto depende del mecanismo final de preparación. |
| `tests/` | Pruebas de preservación Marker, Caste, health/caché, fallback, carpetas, salidas y protocolo. Fixtures pequeños para enlaces, referencias y escaneos; sin descargar modelos en cada prueba unitaria. |
| `.github/workflows/ci.yml` | Verificación de PR y `main`: pruebas por unidades y smoke de artefactos en plataformas prioritarias. |
| `.github/workflows/release.yml` | Build desde tag/commit verificado, artefactos, checksums, release draft y publicación final. La etapa UI extenderá el workflow. |
| `CHANGELOG.md` | Notas de `0.2.0`, cambios de comportamiento y migración; no inventar releases históricas para `0.1.0`. |
| `docs/releasing.md` | Procedimiento operativo reproducible de release y recuperación, derivado de las secciones 14 y 15: CLI `0.2.0`, UI `0.3.0`. |

El diagnóstico persistente y los modelos viven en el estado privado de cada instalación; no son archivos para añadir al repositorio ni subir a una release.

### 13.4 Rama UI: archivos nuevos y puntos de integración

| Archivo/directorio nuevo propuesto | Responsabilidad |
|---|---|
| `ui/package.json`, `ui/package-lock.json` | Aplicación Electron independiente; versión `0.3.0`, dependencias y scripts de desarrollo/build, sin copiar el motor Python. |
| `ui/src/main.js` | Ventana, ubicación del CLI, health, `spawn`, eventos, cancelación y operaciones del SO. |
| `ui/src/preload.js` | Puente limitado de operaciones UI–proceso principal. |
| `ui/src/index.html`, `ui/src/renderer.js`, `ui/src/styles.css` | Archivos/carpetas, opciones, cola, dos niveles de progreso, resultados y recuperación gráfica. |
| `ui/src/viewers/` | Visor PDF.js y vista markdown-it/KaTeX con recursos locales. |
| `ui/assets/` | Iconos Windows/Linux/macOS y recursos propios de la aplicación. |
| `ui/electron-builder.yml` | Identidad estable y empaquetado, Windows NSIS, accesos y metadata; targets secundarios según la matriz cerrada. |
| `ui/tests/` | Health y protocolo con CLI de prueba, rutas Unicode, eventos fragmentados, errores, cancelación y flujos gráficos esenciales. |
| `packaging/windows/` | Personalizaciones mínimas NSIS cuando sean necesarias para coordinar la dependencia CLI, registro y ciclo de instalación. |

Editar en esta rama los puntos compartidos ya creados: `install.ps1` e `install.sh` para añadir la etapa gráfica; `packaging/runtime-manifest.json` para declarar artefactos UI `0.3.0` y su dependencia de un CLI `0.2.x` publicado y compatible; `.github/workflows/ci.yml` y `release.yml` para build/smoke de UI; `.gitignore`, `README.md`, `CLAUDE.md`, `CHANGELOG.md` y `docs/releasing.md` para instalación completa y uso. Cambiar módulos del CLI solo si la integración revela una carencia del contrato público, con pruebas y sin duplicar conversión en Electron.

Mantener sincronizados `ui/package.json` y su lock en `0.3.0`. El paquete Python conserva su versión CLI `0.2.x` si no tiene cambios: no subirla a `0.3.0` solo para igualar la UI. CI valida cada componente contra su propia versión y comprueba la compatibilidad de protocolo declarada en el manifiesto. El instalador fija la versión CLI exacta probada; no selecciona sin verificar cualquier `0.2.x`.

## 14. Release CLI `0.2.0` después del merge a `main`

### 14.1 Estado base y condición de publicación

Estado comprobado durante esta conversación: el código declara `0.1.0` en `pyproject.toml` y `sami/__init__.py`; GitHub no tiene releases ni tags publicados. El instalador actual consume el repositorio. Este documento no modifica esa versión ni crea una release: define el procedimiento futuro para CLI `0.2.0` y UI `0.3.0`.

La condición de publicación de `0.2.0` es que la rama CLI esté integrada, CI y pruebas de instalación pasen, y sus artefactos correspondan al mismo commit verificado de `main`. La UI no es requisito ni asset de esta release. Windows 11 y Debian-based son obligatorios; macOS es secundario y no debe bloquear la release ni anunciarse como verificado sin sus pruebas.

### 14.2 Preparación antes del tag

1. Terminar y verificar `refactor/0_2_0_sami_cli`: comparación con SAMI original y Caste, tres modos preparados, instalación CPU completa, health persistido, referencias/links inline, numeración y fallback con warning. Integrar su PR en `main`.
2. Cerrar el alcance CLI sin esperar la UI: tres modos, protocolo público y health, instaladores completos y comando disponible en `PATH`. No crear accesos gráficos ni anunciar un `.exe` de UI en `0.2.0`.
3. Llevar los bumps y notas de versión dentro del PR CLI: Python `0.2.0`, lock, manifiesto, changelog y documentación. Evitar cambios locales sin merge después de validar el candidato.
4. Registrar el SHA candidato exacto ya integrado en `main` y ejecutar allí CI/build de ensayo, comprobación de versiones y smoke de paquetes. Si hace falta corregir algo, integrarlo y repetir la validación sobre el nuevo SHA antes de etiquetar.
5. Revisar la matriz final: instalación limpia sin Python preinstalado; tres modos listos sin descargas posteriores; health rápido; GPU y fallback CPU con evidencia de hardware real; actualización/desinstalación y conservación de documentos. No presentar un runner CPU como evidencia de soporte CUDA/ROCm.
6. Confirmar que el instalador resuelve los artefactos CLI `0.2.0` y sus checksums, no un checkout móvil de `main`. Documentar los cambios de significado de los modos, referencias permanentes y que la UI se entregará en `0.3.0`.

### 14.3 Tag, build y publicación

1. Después del merge CLI y sus comprobaciones, sincronizar `main` y comprobar que el candidato contiene ese PR, está limpio y no existe `v0.2.0`. Crear el tag anotado **`v0.2.0` sobre ese SHA exacto** y subir únicamente ese tag. No etiquetar una rama de desarrollo ni usar `git push --tags` indiscriminadamente.
2. El workflow de release, ya presente en el commit etiquetado, se dispara por ese tag; verifica pertenencia del commit al historial de `main` y coincidencia de versiones. Construye siempre desde el tag, nunca desde el último estado de una rama que pueda cambiar.
3. Ejecutar jobs por plataforma para construir y verificar paquetes Python/CLI e instaladores. Conservar artefactos de CI para pruebas, pero adjuntar también los archivos finales a GitHub Releases: un artifact temporal de Actions no sustituye un asset de release para el instalador público.
4. Ejecutar smoke de los paquetes construidos y generar checksums de los bytes finales. El job de publicación depende del éxito de todos los targets obligatorios. Declarar permisos de escritura de release solo en ese job y fijar las versiones de herramientas/actions durante la implementación.
5. Crear una **release draft** `0.2.0` asociada al tag; adjuntar todos los assets y notas. Probar el bootstrap contra esos mismos archivos descargados, usando acceso al draft o artifacts idénticos, sin anunciar URLs públicas operativas antes de publicar.
6. Comprobar manifiesto, checksums, nombres/versiones, instalación completa y funcionamiento del CLI con los assets de release. Solo entonces publicar `0.2.0` estable como **Latest**; la publicación posterior de `0.3.0` podrá sustituir esa marca sin alterar los assets CLI de `0.2.0`.
7. Tras publicar, comprobar las URL públicas `irm`/`curl`, descarga de assets, instalación nueva y health. Registrar el SHA, tag, URL de release, identificadores de runs y resultados reales de verificación en el cierre de entrega.

GitHub documenta el uso de drafts, tags y assets en [gestión de releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository). El tag se sube mediante la identidad autorizada del mantenedor; no asumir que un tag creado por un job con `GITHUB_TOKEN` disparará otro workflow de `push`, por la prevención de recursión descrita en [triggers de Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

Si un build falla después de subir el tag, corregir/reintentar lo que corresponda sin mover el tag a otro commit. Si el código etiquetado tiene un defecto, corregir mediante una nueva versión; no reemplazar silenciosamente los bytes de una release estable ya consumida. Hasta completar los checks, el draft no se presenta como release utilizable.

### 14.4 Artefactos esperados y aceptación final

| Asset previsto | Contenido/uso |
|---|---|
| Wheel y sdist Python `0.2.0` | Distribución del CLI/núcleo con sus metadatos; el instalador administra sus runtimes/modelos fijados. Publicar en PyPI es una decisión aparte y no es requisito de esta release GitHub. |
| `install.ps1`, `install.sh` | Bootstraps de `0.2.0`: instalación CLI completa y componentes resueltos desde su manifiesto; sin etapa gráfica todavía. |
| Manifiesto de componentes `0.2.0` | URLs/identidades/checksums de artefactos y modelos requeridos, dependencias y protocolo compatible. No contiene diagnóstico de usuarios ni credenciales. |
| `SHA256SUMS` y notas de release | Integridad de assets finales, cambios, migración de modos, plataformas realmente probadas y limitaciones conocidas. |
| Asset macOS, si se valida | Opcional para `0.2.0`; no incluir un archivo no probado solo para aparentar una matriz completa. |

Modelos y runtimes grandes pueden descargarse desde sus fuentes fijadas por el manifiesto durante instalación; no es obligatorio duplicarlos como assets si hay una fuente reproducible y verificable. La instalación no se considera completa hasta dejarlos localmente listos para los tres modos.

Criterio final de `0.2.0`: una máquina Windows 11 o Debian-based dentro de la matriz publicada instala mediante su bootstrap, ejecuta el CLI sin UI, utiliza los tres modos sin nuevas instalaciones y conserva referencias/resultados. Health es rápido y un fallo GPU produce warning y continuación CPU. **Estos pasos quedan únicamente planificados; no se ejecutan en esta tarea.**

## 15. Release UI `0.3.0` sobre el CLI publicado

### 15.1 Desarrollo y dependencia versionada

Después de publicar el CLI `0.2.0`, crear `feat/0_3_0_sami_ui` desde `main` actualizado y realizar el trabajo gráfico de las secciones 9 y 13.4. La UI `0.3.0` depende del CLI `0.2.x` y de su protocolo, con versión exacta probada fijada en el manifiesto. El cambio de versión del producto gráfico no obliga a recompilar ni renombrar un paquete CLI sin cambios.

Si la UI necesita una corrección del CLI, publicarla con una nueva versión del componente y actualizar su dependencia explícita. No modificar la wheel o los modelos bajo una identidad `0.2.0` ya publicada. Toda compatibilidad declarada se verifica con las versiones que realmente instalará el bootstrap.

### 15.2 Merge, tag y publicación

1. Verificar la UI y su integración: instalación nueva con CLI→health→UI; añadir UI a un CLI ya sano; doble clic, escritorio/Inicio, `PATH`, visores, arrastre, progreso, cancelación y fallback CPU.
2. Actualizar metadatos UI/lock a `0.3.0`, manifiesto y changelog; conservar la versión real del CLI. Extender CI/release para validar versiones por componente y seleccionar el build gráfico para `v0.3.0`.
3. Integrar el PR UI en `main`, fijar su SHA candidato y pasar CI y las pruebas de empaquetado de esa revisión exacta. El CLI `0.2.0` permanece disponible independientemente durante esta fase.
4. Crear y subir el tag anotado **`v0.3.0`** sobre el commit verificado de `main`. Aplicar las mismas reglas de build desde tag, smoke de assets, checksums, draft y publicación de la sección 14.3; no reconstruir un supuesto CLI `0.3.0` si su versión sigue siendo `0.2.x`.
5. Publicar el instalador UI y los bootstraps completos que resuelven por separado el asset gráfico `0.3.0` y el CLI compatible publicado. Las URL de dependencia deben fijar versiones, no descargar ciegamente el asset `latest` de otro componente.
6. Comprobar desde las URL públicas que una máquina limpia queda lista tras la instalación y que un CLI existente puede reutilizarse. Publicar `0.3.0` como Latest cuando los targets obligatorios estén verificados; mantener `v0.2.0` accesible para instalación CLI sola.

### 15.3 Artefactos y criterio de aceptación

| Asset previsto | Contenido/uso |
|---|---|
| `SAMI-0.3.0-win-x64-setup.exe` | Instalador Electron/NSIS, condicionado al health del CLI; crea los accesos gráficos de escritorio e Inicio. |
| `SAMI-0.3.0-linux-x64.AppImage` o paquete Debian validado | UI Linux según el target probado; depende del CLI publicado mediante el mismo contrato. |
| `install.ps1`, `install.sh` de `0.3.0` | Coordinan ambas etapas, permiten CLI solo y reutilizan una instalación CLI compatible sin repetir el diagnóstico profundo. |
| Manifiesto de producto `0.3.0` | Identidades/checksums UI, versión exacta CLI `0.2.x` probada y protocolo compatible. |
| `SHA256SUMS` y notas de `0.3.0` | Integridad, funciones gráficas, componentes requeridos y plataformas realmente probadas. |
| Asset macOS, si se valida | Secundario y no bloqueante, con alcance de pruebas documentado. |

La instalación completa prepara el CLI si falta, verifica su health y después instala la UI. Al terminar, doble clic en el ejecutable o sus accesos abre la ventana sin consola, activación de Python ni instalaciones pendientes. La UI consume exclusivamente comandos/eventos del CLI y no duplica sus motores. El usuario puede seguir utilizando solo el CLI publicado en `0.2.0`. **No se crean ramas, tags, paquetes ni releases al actualizar este plan.**
