# 02 — Diagnóstico persistido, runtimes e instalación completa

Fecha: 2026-11-18, America/Bogota. Estado: especificación para implementación futura.
Rama futura: `refactor/0_2_0_sami_cli`. Unidades U03–U05.
Depende de [01 — contratos/motores](01-cli-contratos-motores-salidas.md).
Siguiente: [03 — CLI y release 0.2.0](03-cli-lotes-validacion-release-0.2.0.md).

## Resultado de esta etapa

Una instalación que deja los tres modos utilizables y una ruta CPU validada. La aceleración es opcional: si falla, el usuario recibe un warning y la conversión continúa en CPU con el mismo modo. El análisis costoso ocurre al instalar; las siguientes ejecuciones consultan un perfil persistido y un health check breve.

## Archivos y límites

| Archivo actual/futuro | Trabajo |
|---|---|
| `sami/hardware.py` | Inventario de SO/CPU/RAM/GPU/drivers, sin depender de que Torch ya exista. |
| `sami/compatibility.py` | Lectura/escritura atómica, esquema y validación ligera del perfil. |
| `sami/runtime.py` | Plan y ejecución de instalación, selección de entorno y modelos offline. |
| `sami/worker.py` | Entrada interna para ejecutar el adaptador dentro del runtime seleccionado. No se expone como función UI. |
| `sami/processes.py` | Proceso/árbol propio, salida, control, timeout, cancelación y fallback. |
| `sami/cli.py` | Dispatch de `setup`, `health`, `doctor` e invocación del coordinador; sin diagnóstico al importar. |
| `packaging/runtime-manifest.json`, `packaging/constraints/` | Versiones, fuentes, checksums, modelos y recetas probadas por plataforma/backend. |
| `install.sh`, `install.ps1`, `setup.sh` | Bootstraps finos y consistentes, sin repetir la lógica de compatibilidad. |
| `pyproject.toml`, `requirements.txt`, lock elegido | Base ligera y runtimes reproducibles; evitar que un instalador genérico reemplace Torch GPU por CPU o viceversa. |
| `tests/test_hardware.py`, `test_compatibility.py`, `test_runtime.py`, `test_processes.py` | Pruebas sin hardware real de estados, recuperación y contratos. |
| `tests/integration/` | Procesos y bootstrap reales en entornos de aceptación, separados de las pruebas rápidas. |

## U03 — Inventario y perfil persistente

### Recolección durante instalación

Separar `detect_hardware()` sin modificaciones del sistema de `validate_runtime()` que necesita componentes ya preparados. Inventariar SO/versión/distro/arquitectura y WSL/contenedor, núcleos físicos/lógicos/cuotas, RAM disponible, GPUs identificables, VRAM total/libre y drivers. Añadir espacio libre y permisos de destino.

Usar APIs/comandos disponibles con timeout y salida acotada. Ejemplos de fuentes de inventario: información del SO, psutil, NVIDIA SMI, AMD SMI/rocminfo o mecanismos del sistema. Una herramienta ausente significa dato desconocido; no obliga a instalar utilidades globales para detectar el resto del equipo.

Distinguir cuatro evidencias: GPU física, driver, runtime y motor de inferencia. En ROCm, `torch.cuda` no identifica NVIDIA por sí mismo. La prueba de instalación debe comprobar dónde ejecuta el VLM real, no solo una operación Torch. El resultado negativo se guarda también.

### Estado de instalación, no archivos versionados del repo

Propuesta de ubicaciones:

| Dato | Windows 11 | Linux Debian-based |
|---|---|---|
| Aplicación/lanzador | Ubicación estable bajo `%LOCALAPPDATA%\Programs\SAMI\cli`. | Lanzador `~/.local/bin/sami`, entorno privado bajo el estado SAMI. |
| Estado/runtimes/modelos | `%LOCALAPPDATA%\SAMI`. | `$XDG_DATA_HOME/sami`, o `~/.local/share/sami`. |
| Override | `SAMI_HOME` cambia el estado/runtimes; registrar la ubicación real del ejecutable. | Igual. Adoptar una instalación previa `~/.sami` si es válida antes de migrar/copiar caches. |

No derivar ubicación del CLI desde el cwd ni desde el primer resultado de `PATH` para la futura UI. Registrar `installation.json` con identidad, ejecutable absoluto, versión y protocolo. Separar ese registro del diagnóstico GPU y de resultados PDF.

Archivos internos propuestos: `installation.json`, `compatibility.json`, su copia válida anterior y `logs/`. Los modelos/cache no se incluyen en el Git ni en el diagnóstico de texto. Resolver rutas adecuadas a macOS solo en su alcance secundario.

### Esquema persistido mínimo

| Campo | Contenido |
|---|---|
| `schema_version`, `installation_id` | Versión de esquema e identidad local estable. |
| `validated_at`, `cli_version`, `protocol_version` | Fecha y versiones de la validación completa. |
| `platform` | SO, versión, arquitectura y características del entorno. |
| `hardware` | CPU/RAM e identidades GPU; ausencia diferenciada de dato desconocido. |
| `runtimes` | Ruta, backend, versión, fingerprint de componentes y estado por entorno. |
| `modes` | `fast/balanced/quality`, ruta CPU validada y aceleradores realmente probados. |
| `models` | Identidades/versiones, rutas y evidencias de integridad de instalación. |
| `warnings`, `failures` | Código, motivo y huella a la que afecta; distinguir transitorio de permanente. |

Guardar tras validar, con escritura temporal y reemplazo atómico más backup válido. Un instalador interrumpido no reemplaza un perfil listo por uno medio escrito. Un esquema futuro desconocido no provoca borrado ni reinstalación automática al consultar health.

### Health rápido

`health_check()` lee registro/perfil y comprueba esquema, rutas necesarias y huellas ligeras del modo elegido. Sin red, Torch/Marker, hash de modelos enteros ni servidor de inferencia. Una consulta del SO opcional tiene timeout y entra en un presupuesto global; no sumar esperas ilimitadas por proveedor.

Objetivo a medir: coste añadido menor a un segundo en instalación sana. Medir varias ejecuciones, reportar mediana/p95 y entorno; no tratarlo como una garantía ya cumplida. Ayuda y versión ni siquiera ejecutan este health.

Invalidar solo lo afectado por evidencia de cambio. No expirar por tiempo ni repetir un diagnóstico fallido con la misma huella en cada archivo. Consultar RAM/VRAM libre antes de reservar recursos no equivale a invalidar compatibilidad.

| Health | Significado | Exit code de `sami health` |
|---|---|---|
| `ready` | Núcleo y tres rutas CPU listos; backend seleccionado utilizable. | 0 |
| `degraded` | GPU no utilizable, pero CPU completa y validada. | 0, con warning |
| `repair_required` | Falta un componente obligatorio/núcleo o registro no recuperable. | 3, razón precisa |

Esquema JSON de health: `protocol_version`, `installation_id`, `cli_version`, `status`, `modes`, `selected_device`, `warnings`, `repair_reasons`. Un fallo GPU por sí solo nunca da `repair_required`. `doctor` explica datos guardados; no es un alias de diagnóstico profundo.

### Pruebas y cierre U03

Simular perfiles listos, negativos, corruptos, backup, esquema desconocido, cambio GPU y runtime CPU intacto. Bloquear red/imports pesados en pruebas de health. Comprobar que resultados negativos se reutilizan y que la segunda ejecución no repite sondas profundas. No guardar datos sensibles del entorno completo.

**Rollback:** conservar copia válida y registro de ejecutable; revertir el esquema con migración explícita, nunca borrar modelos/documentos.

## U04 — Entornos, supervisor y fallback

### Preparación de entornos

Mantener una base CLI ligera y entornos worker separados cuando CPU y GPU necesiten variantes incompatibles. La instalación completa incluye el runtime CPU y los modelos para ambos perfiles Marker, incluso si hay GPU. `fast` usa la ruta ligera de extracción sin importar modelos.

Usar Python administrado por uv como propuesta inicial de bootstrap, evitando exigir Python previo. Fijar la versión Python comprobada en U00, compatible con el proyecto actual. Registrar versiones exactas y fuentes en manifest/locks; no resolver `latest` en cada invocación ni compilar dependencias grandes como fallback automático.

Cada runtime worker recibe la misma versión de los contratos/adaptadores SAMI que el CLI coordinador. Lanzarlo por su ruta absoluta, con petición JSON y configuración explícita de modelos/backend. Reutilizar el worker por lote cuando sea viable; no cargar modelos por página ni por PDF sin necesidad.

### Máquina de instalación

`planned → preparing → validating → ready`, con `failed` recuperable. Las tareas de descarga pueden correr en background supervisado, pero el bootstrap espera su validación antes de anunciar éxito.

1. Leer release/manifest y localizar componentes compatibles existentes.
2. Preparar en staging, verificar integridad y resolver CPU antes de GPU.
3. Descargar todos los modelos necesarios y efectuar una conversión mínima por modo en instalación.
4. Preparar GPU si es compatible y validar el dispositivo real del motor. Si falla, warning y conservar CPU lista.
5. Activar entornos y persistir registro/perfil solo cuando estén consistentes. Conservar el entorno previo hasta validar el nuevo.

Para el uso normal, configurar las dependencias para trabajar con sus modelos locales y sin descargas automáticas. Un modelo ausente se detecta como instalación incompleta; no abrir un diálogo para descargarlo al primer uso de `quality`.

### Fallback de ejecución

| Situación | Acción |
|---|---|
| Equipo sin GPU compatible | CPU normal; no repetir warnings de fallo de una GPU inexistente. |
| Health detecta que la GPU preparada dejó de estar lista | Warning, CPU, mismo modo y una única consulta por lote. |
| GPU falla al iniciar o inferir | Terminar intento/worker GPU propio, limpiar su staging, emitir `job_retrying` y reintentar ese documento en CPU. |
| GPU falla en un documento del lote | Usar CPU en los siguientes; no reintentar GPU por cada documento con la misma condición. |
| PDF inválido/cifrado, permisos de salida o disco lleno | Error del documento/operación correspondiente; no fingir que es un fallo de GPU. Continuar otros documentos cuando corresponda. |

Un fallo GPU permite **un** reintento CPU por documento, no un bucle CPU↔GPU. Si la conversión CPU termina bien, exit de conversión 0 salvo otros errores/parciales. El aviso y dispositivo efectivo quedan en el resultado. Si ya había una salida anterior, el intento fallido nunca la sustituye.

No desactivar para siempre una GPU por falta temporal de memoria; registrar el motivo y alcance. Tampoco repetir la prueba profunda cada vez que el usuario ejecuta el CLI. Diseñar recuperación con huella de componente y estado de la sesión.

### Cancelación y procesos propios

El coordinador controla workers y servidores iniciados para su instalación/trabajo; no mata procesos globales por nombre. Implementar POSIX y Windows sin asumir `SIGKILL` universal. En Windows, cerrar el árbol propio mediante mecanismo del SO adecuado; probarlo con procesos hijos/grandhijos reales de prueba.

Propuesta de presupuesto: petición de cancelación cooperativa y hasta 5 s para cerrar, terminación y otros 5 s antes de forzar cierre. Son límites operativos por validar, no esperas repetidas por cada PID en serie. Cancelar no dispara fallback CPU. No matar un servidor externo preexistente que no pertenece al trabajo.

### Pruebas y cierre U04

Procesos de prueba con stdout fragmentado, stderr abundante, error antes/durante inferencia, proceso nieto y cancelación. Verificar salida CPU única, contadores sin duplicados, limpieza limitada a procesos/staging propios y no contaminación del protocolo. Luego ejecutar prueba real de ambos perfiles Marker en CPU y al menos las combinaciones GPU anunciadas.

**Rollback:** volver al runtime anterior validado; desactivar solo el entorno nuevo y conservar modelos reutilizables. El estado de una GPU no invalida la ruta CPU íntegra.

## U05 — Bootstraps completos, reparación y mantenimiento

| Entrada futura | Comportamiento |
|---|---|
| `install.sh` / `install.ps1` | Obtener release CLI `0.2.0`, verificar assets, preparar Python/entornos/tres modos, registrar ubicación, configurar `PATH` y consultar health. |
| `setup.sh` | Compatibilidad con instalación existente; delegar la preparación al mismo flujo. No conservar una receta de runtimes divergente. |
| `sami setup` | Entrada explícita a preparación/reparación; puede hacer diagnóstico profundo y descargar. |
| Bootstrap `update` | Preparar nueva versión sin destruir la anterior antes de validar. |
| Bootstrap `uninstall` | Retirar aplicación/integración propia; conservar PDF/resultados. Política de caches explícita. |

En `0.2.0` no instalar UI, NSIS gráfico ni accesos a un ejecutable inexistente. En Windows configurar el `PATH` del usuario sin reemplazar entradas y registrar la ruta CLI; ayuda/health deben funcionar desde un proceso nuevo con entorno actualizado. La futura UI se abrirá por ruta absoluta, sin depender del entorno de Explorer.

No elevar, instalar drivers ni reiniciar servicios automáticamente en el flujo normal. Si GPU requiere driver, explicar el estado una vez y completar CPU sin bloquear. Cualquier acción privilegiada de driver pertenece a un paso solicitado explícitamente, independiente de tener el CLI utilizable.

Preparar el bootstrap con funciones testeables: resolver versión/artefacto, verificar, instalar, activar y comprobar. No descargar código móvil de `main` como implementación del motor. El manifiesto de release debe distinguir datos publicados de los diagnósticos locales.

### Pruebas y cierre U05

1. Windows 11 y Debian/Ubuntu de la matriz U00, sin Python previo ni privilegios admin para instalación por usuario.
2. Todos los modos funcionan con red bloqueada después de instalar; ayuda/health no preparan nada.
3. Reinstalación idempotente, rutas unicode/espacios, fallo de descarga, disco insuficiente y proceso de instalación interrumpido.
4. GPU ausente/fallida termina con CPU lista y warning; instalación CPU incompleta no anuncia éxito.
5. Update conserva fallback/recovery; uninstall elimina solo lo propio y no los PDF/resultados.

Registrar SO, arquitectura, versiones, comandos, salida y duración de instalación/conversión por separado. **Cierre:** los tres modos listos, registro consistente, health rápido y CLI accesible; falta completar superficie de lotes/release en el plan 03. No publicar todavía desde esta unidad.
