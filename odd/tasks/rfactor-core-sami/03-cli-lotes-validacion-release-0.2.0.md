# 03 — CLI completo, validación y release 0.2.0

Fecha: 2026-11-18, America/Bogota. Estado: especificación para implementación futura.
Rama futura: `refactor/0_2_0_sami_cli`. Unidades U06–U07.
Depende de [01 — motores/contrato](01-cli-contratos-motores-salidas.md) y [02 — instalación/runtime](02-cli-diagnostico-runtime-instalacion.md).
La UI comienza solo después de publicar esta entrega: [plan 04](04-ui-aplicacion-electron-0.3.0.md).

## Resultado de esta etapa

Un CLI independiente que instala completamente, convierte archivos/carpetas, mantiene referencias/resultados, muestra progreso real y entrega un protocolo estable. Su merge a `main` habilita publicar `v0.2.0`; no necesita UI ni Node.

## U06 — Superficie pública, lotes y progreso

### Archivos

| Archivo actual/futuro | Cambio |
|---|---|
| `sami/cli.py` | Parser/dispatch ligero, defaults, errores y presentación. Conservar argparse evita añadir otro framework de comandos sin necesidad. |
| `sami/jobs.py` | Descubrimiento estable, deduplicación, coordinación de documentos y resultados. |
| `sami/progress.py` | Adaptador de eventos a presentación de terminal; JSON no pasa por barras. |
| `sami/events.py`, `contracts.py` | Cerrar contrato, códigos, contadores y pruebas de compatibilidad con futuro consumidor UI. |
| `sami/outputs.py`, `processes.py` | Integración de numeración, reintento CPU y cancelación con el lote. |
| `tests/test_cli.py`, `test_jobs.py`, `test_progress.py`, `tests/integration/` | Comportamiento de terminal y programa consumidor. |

### Gramática mínima propuesta de 0.2.0

```text
sami INPUT [INPUT ...] [opciones]
sami convert INPUT [INPUT ...] [opciones]
sami health [--json]
sami doctor [--json]
sami setup
sami --help
sami --version
```

La forma directa se conserva; `convert` es una forma explícita útil para scripts. Resolver la ambigüedad de nombres reservados de subcomandos mediante parser explícito y `convert -- ruta` cuando haga falta. No deducir un subcomando a partir de la extensión del primer PDF.

| Opción mínima | Comportamiento |
|---|---|
| `--mode fast\|balanced\|quality` | Default `balanced`; mapeo del plan 01. |
| `-o/--output DIR` | Root de salida; sin él, junto a cada input. |
| `--recursive` | Buscar PDF en subcarpetas de las entradas directorio. Sin el flag, solo primer nivel. |
| `--flat` | Sin subcarpeta por documento; seguir publicando recursos con namespace único. |
| `-q/--quiet` | Sin barras ni logs informativos; errores y warning de fallback siguen siendo visibles. |
| `--no-strip-refs` | Compatibilidad: referencias siempre se conservan. No existe un flag para borrarlas. |
| `--device auto\|cpu\|cuda\|rocm` | Propuesta de control de recursos; selección final sujeta al health. Incluso una GPU pedida explícitamente vuelve a CPU con warning si falla, según requisito del usuario. |
| `--json` | Conversión JSONL por stdout, logs/warnings humanos por stderr; los warnings se representan también en eventos. |
| `--control-stdin` | Cancelación estructurada del protocolo; no leer stdin en modo terminal normal. |

No usar el hardware para cambiar automáticamente `balanced` por `fast`. Dispositivo y perfil de contenido son controles distintos. macOS/MPS se añade a selección solo cuando se verifique su alcance secundario; no aceptar opciones que se ignoren.

Propuestas previas que permanecen en backlog técnico: rango/límite de páginas, OCR/idiomas, imágenes, marcadores, tablas y concurrencia configurable. No son necesarias para preservar las opciones actuales de SAMI. Si se incluyen en `0.2.0`, definir antes capacidades/defaults por motor y probarlas; `fast` conserva por defecto OCR/imágenes apagados y velocidad Caste. No exponer un flag que un motor acepte pero no aplique.

### Descubrimiento de documentos

1. Expandir rutas del usuario, comprobar inputs y enumerar `.pdf` sin distinguir mayúsculas en la extensión.
2. Recorrer carpetas según el flag; no seguir enlaces de directorio por defecto, evitar ciclos y excluir outputs/staging propios.
3. Deduplicar identidad/ruta normalizada respetando el SO. No convertir a minúsculas todas las rutas Linux ni asumir que todas las variantes de macOS son iguales.
4. Orden de trabajo: orden de inputs explícitos; dentro de una carpeta, relativo ordenado por nombre de forma estable. La primera aparición conserva posición al deduplicar.
5. Crear jobs/incidencias para inputs explícitos inválidos sin abandonar otros válidos. Un PDF roto/cifrado falla individualmente; el siguiente sigue.

Inicialmente ejecutar documentos secuencialmente, como SAMI actual, con un worker/modelo reutilizable por lote cuando sea posible. El ajuste de hilos CPU no equivale a lanzar varios servidores VLM. No introducir paralelismo de documentos sin mediciones de memoria y coordinación de inferencia.

Directorio vacío: mensaje claro y error de selección; no cargar modelos. No mutar ni mover entradas. Los duplicados descartados son información de descubrimiento, no jobs fallidos.

### Progreso y salida

Recomendación de presentación: Rich con una barra de lote y tarea de documento; [Rich soporta varias tareas y progreso indeterminado](https://rich.readthedocs.io/en/stable/progress.html). Fijar su versión al implementar y declarar dependencia directa si se usa.

El lote representa documentos terminales/total único. El documento muestra nombre, etapa, páginas u otras unidades reales y tiempo. Un reintento CPU reinicia su progreso de intento y no incrementa el lote dos veces. En etapas Marker sin contador, actividad indeterminada; no repartir porcentajes falsos entre etapas.

Sin TTY: líneas legibles sin códigos de control. Con JSON: solo eventos por stdout, sin Rich; separar stderr. Limitar frecuencia de eventos visuales sin perder inicios, finales o warnings. El resumen devuelve rutas finales y totales por estado.

### Exit codes propuestos

| Código | Conversión | Gestión |
|---|---|---|
| 0 | Todos los jobs completados sin vacíos; warnings GPU→CPU no cambian el éxito. | Health `ready/degraded`; setup completo. |
| 1 | Algún documento `failed/partial`, sin impedir otros. | Fallo de instalación/preparación explícita. |
| 2 | Sintaxis/opciones incompatibles o selección sin PDF. | Uso inválido. |
| 3 | Falta instalación íntegra y no hay runtime CPU recuperable. No usar por GPU fallida. | Health `repair_required`. |
| 130 | Cancelación solicitada, con limpieza y resultados anteriores conservados. | Cancelación de preparación cuando se soporte. |

Si hay un input explícito inexistente y otros válidos, registrar fallo de ese input y terminar con 1 al acabar los demás. No transformar errores de argumento o corrupción de instalación en errores GPU. En modo JSON, representar los errores de ejecución mediante eventos; los errores previos al arranque llevan respuesta estructurada de error cuando el modo puede identificarse, además del exit code.

### Pruebas y cierre U06

Casos: archivo, varios, directorio no recursivo/recursivo, inputs mixtos, duplicados, `.PDF`, enlaces/ciclos, unicode, vacío, roto, referencia, segunda salida y flat. Consumidor JSON externo comprueba framing, estado final y contadores durante fallback/cancelación. Probar terminal, pipe y quiet.

Ejemplos de validación futura, disponibles solo tras implementar:

```text
python -m pytest tests/test_cli.py tests/test_jobs.py tests/test_progress.py
sami test-pdfs/test_document.pdf --mode fast --json
sami test-pdfs/test_document.pdf --mode balanced
sami test-pdfs/radio_env_5pages.pdf --mode quality
sami health --json
```

Usar un directorio temporal para outputs. Las pruebas rápidas inyectan adaptadores; las ejecuciones de aceptación usan motores reales y cache preparada. **Rollback:** revertir coordinador/presentación conservando contratos y resultados ya publicados.

## U07 — CI, documentación y release CLI

### Archivos de cierre

| Archivo | Trabajo |
|---|---|
| `pyproject.toml`, `sami/__init__.py` | Versión `0.2.0`, comprobación de coherencia y comandos instalados; mantener límites Python verificados en U00. |
| `requirements.txt`, locks/constraints | Misma resolución que usa instalación; no mantener instrucciones incompatibles. |
| `.github/workflows/ci.yml` | Checks rápidos de PR/main, import/help, contrato, build Python y smoke CPU por plataforma. |
| `.github/workflows/release.yml` | Tag CLI `v0.2.0`, builds/checksums, draft, assets, validación y publicación. |
| `.gitignore` | Ignorar entornos/modelos/resultados, no manifests/locks. |
| `README.md`, `CLAUDE.md` | Uso, arquitectura, instalación completa, fallback y limitaciones reales. |
| `.claude/agents/convert.md`, `install-check.md`, `test.md` | Quitar supuestos de primera descarga en conversión; actualizar pruebas/defaults. No usar expectativas históricas de figuras para el motor Caste sin imágenes. |
| `CHANGELOG.md`, `docs/releasing.md` | Notas `0.2.0`, migración y runbook reproducible. |

No modificar `cpu_monitor.py` sin necesidad demostrada. No incluir `.atl/`, caches ni diagnósticos personales en commits/assets. La referencia Caste se conserva como contexto, no como paquete de producción.

### Matriz de aceptación

| Grupo | Evidencia requerida |
|---|---|
| Contratos y lógica | Pruebas rápidas sin red/modelos, stdout válido, ayuda sin efectos e invariantes de salida. |
| Motores | Corpus U00 con resultados de ambos perfiles Marker y Caste; texto, tablas, ecuaciones/figuras donde correspondan y links. |
| Instalación CPU | Windows 11 y Debian-based de la matriz: sin Python previo, tres modos preparados, convertir con red bloqueada. |
| Aceleración | Hardware real de cada combinación anunciada; comprobar servidor VLM/dispositivo y fallo→CPU. Hosted runner CPU no demuestra GPU. |
| Persistencia | Segunda ejecución sin diagnóstico profundo, health medido, cache negativa y cambio selectivo. |
| Recuperación | Descarga interrumpida, publicación fallida, cancelar árbol, actualización y desinstalación; documentos intactos. |

El corpus mínimo añade enlaces/anotaciones, bibliografía, columnas, tabla compleja, escaneo, texto ilegible y nombres repetidos. No exigir OCR al `fast` elegido: esperar `partial` con explicación. No equiparar cobertura de tokens con fidelidad visual.

CI distingue pruebas rápidas de pruebas de runtime/instalación. Los tests de build usan artefactos que después se distribuyen. Elegir imágenes runner y baseline Linux después de U00; macOS puede ejecutarse como secundario y no bloqueante, sin anunciar soporte no probado.

### Secuencia de publicación de 0.2.0

1. Cerrar U00–U07 y la documentación en `refactor/0_2_0_sami_cli`. Registrar commits, resultados y alcance. El CLI debe funcionar completo sin Electron/Node.
2. Revisar e integrar el PR en `main`. Fijar SHA candidato; no crear un tag sobre la rama de desarrollo ni incorporar cambios locales no integrados.
3. Build de ensayo desde ese SHA: Python `0.2.0`, lock, manifiesto y changelog consistentes. Smoke de assets en plataformas obligatorias.
4. Crear/subir tag anotado `v0.2.0` sobre ese SHA. El workflow comprueba tag/versión y que el commit está integrado en `main`.
5. Construir wheel/sdist y bootstraps/manifiesto desde el tag. Generar `SHA256SUMS` sobre bytes finales. Crear draft y adjuntar assets; un artifact de Actions no sustituye un asset público de release.
6. Verificar instalación completa contra los mismos assets, offline posterior, health y conversión. Publicar estable como Latest al pasar los targets obligatorios.
7. Probar URL públicas `irm/curl`, assets y health; guardar SHA/tag/run/resultados. No publicar un instalador gráfico ni accesos a UI en esta release.

Assets mínimos: wheel/sdist `0.2.0`, `install.sh`, `install.ps1`, manifiesto, checksums y notas. Modelos/runtimes pueden tener fuentes externas fijadas/verificadas; deben quedar descargados al terminar instalación. PyPI es una decisión separada.

Si falla el build, el draft no se anuncia como listo. No mover el tag a otro commit ni reemplazar una release estable consumida; correcciones de código publicadas requieren versión nueva. Si el tag lo crea un workflow, considerar las restricciones de recursión de `GITHUB_TOKEN`; preferir un tag explícito del mantenedor o dispatch bien definido.

### Cierre de la entrega

Un equipo de la matriz instala el CLI, utiliza los tres modos sin red/instalación adicional, consulta health rápido, conserva referencias, recibe salidas numeradas y continúa CPU si falla GPU. Se publica `v0.2.0`. Solo entonces comienza `feat/0_3_0_sami_ui`.

Fuentes operativas: [releases GitHub](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository), [triggers Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow). Estos pasos son futuros; no se ejecutan al escribir este plan.
