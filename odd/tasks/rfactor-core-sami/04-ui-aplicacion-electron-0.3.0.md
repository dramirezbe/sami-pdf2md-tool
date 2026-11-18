# 04 — Aplicación Electron dependiente del CLI, versión 0.3.0

Fecha: 2026-11-18, America/Bogota. Estado: especificación para implementación futura.
Rama futura: `feat/0_3_0_sami_ui`, creada desde `main` después de publicar CLI `0.2.0`.
Unidades U08–U09. Depende de [03 — CLI publicado](03-cli-lotes-validacion-release-0.2.0.md).
Siguiente: [05 — despliegue y release UI](05-ui-despliegue-release-0.3.0.md).

## Resultado de esta etapa

Una aplicación de escritorio útil que ejecuta el CLI instalado y muestra sus resultados. El stack es Electron + JavaScript + HTML/CSS, PDF.js y markdown-it/KaTeX. Priorizar facilidad de desarrollo; no añadir un framework de componentes, servidor HTTP o backend Python embebido para una primera interfaz funcional.

No importa módulos `sami`, no convierte PDF, no detecta GPU, no prepara modelos y no decide qué backend de conversión es compatible. Puede abrir archivos para mostrarlos y ejecutar operaciones de escritorio; todo trabajo de conversión/health/cancelación pasa por el protocolo CLI.

## Archivos

| Archivo nuevo/propuesto | Responsabilidad |
|---|---|
| `ui/package.json`, `ui/package-lock.json` | Versión `0.3.0`, dependencias fijadas, scripts de desarrollo, pruebas y build. |
| `ui/src/main.js` | Ventana y lifecycle de la aplicación. |
| `ui/src/cli-runner.js` | Ubicación de instalación, health, spawn, framing JSONL, estados de proceso y cancelación. |
| `ui/src/preload.js` | Operaciones explícitas y eventos mediante contextBridge. |
| `ui/src/index.html`, `renderer.js`, `styles.css` | Pantalla y estado de presentación, sin acceso directo al shell. |
| `ui/src/viewers/pdf.js`, `markdown.js` | Visores y lectura de recursos de documentos autorizados. Los nombres no sustituyen las dependencias PDF.js/markdown-it. |
| `ui/assets/` | Iconos y recursos propios, sin CDN. |
| `ui/tests/` | Runner, contrato, componentes y smoke gráfico. |

Fijar Electron/Node integrado y dependencias al implementar; el usuario final no instala Node ni npm. El paquete contiene los recursos de preview y sus workers/fuentes. No incluye una segunda copia de modelos, Torch o motores Python.

## U08 — Localización, health y ejecución del CLI

### Localización e identidad

1. Leer el registro de instalación generado por el bootstrap CLI, con ruta absoluta y `installation_id`.
2. Consultar esa ruta con `health --json`. No usar el primer `sami` que aparezca en `PATH`, cwd o directorio del documento.
3. Comprobar protocolo v1, versión CLI admitida y rutas CPU listas. El manifiesto gráfico fija la versión exacta CLI probada; no asumir que compartir prefijo `0.2` basta.
4. `ready/degraded` permiten abrir/trabajar; `degraded` muestra aviso de GPU→CPU. Si falta CLI o el contrato es incompatible, la UI explica cómo recuperar la instalación sin fingir que puede convertir.

Health no carga modelos ni descarga. Hacerlo una vez al abrir y al solicitar una acción que justifique verificar un cambio; no repetirlo por cada render de pantalla o cada PDF añadido. La conversión tiene su propio health por lote, como el CLI normal.

### Ejecución

El proceso principal usa `child_process.spawn` con ruta absoluta, array de argumentos, `shell:false` y `windowsHide:true`. El CLI es un ejecutable directo; no depender de un `.cmd` ni de una activación de shell para funcionar en Windows.

Petición gráfica propuesta:

```text
<ruta-cli> convert <inputs...> --mode balanced --json --control-stdin
```

Añadir salida/recursividad/flat solo cuando el usuario las elija. La lista de opciones/capacidades debe corresponder al CLI publicado; no mostrar toggles que se ignoran. Cada invocación representa un lote, no un proceso por página o por mensaje.

`cli-runner` recibe fragmentos stdout, los decodifica como UTF-8 de forma incremental y enmarca líneas JSON. Entrega eventos v1 al renderer con métodos propios, conservando `run_id/job_id/attempt`. stderr alimenta un panel de diagnóstico; no se usa para inferir porcentajes.

Proponer un objeto de estado de presentación: instalación/health, inputs elegidos, opciones, ejecución actual y resultados terminales. No duplicar en JS las reglas de deduplicación, nombres finales, calidad o fallback: la respuesta CLI es la autoridad.

### Estados y recuperación

| Situación | Estado/UI |
|---|---|
| Esperando health | Ventana visible con actividad breve, sin congelar el hilo de presentación. |
| CLI listo | Puede elegir archivos y convertir. |
| GPU fallida, CPU lista | Warning informativo; ejecutar/cancelar siguen disponibles. |
| Instalación/protocolo inválido | Vista de diagnóstico y acción de reparación explícita del instalador; no descargar en secreto al abrir. |
| Lote en curso | Input/opciones del lote fijados; cambios se aplican al siguiente lote, no al actual. |
| Crash sin `run_finished` | Error gráfico con exit/stderr útil; no marcar como convertido ni quedarse indefinidamente en progreso. |
| Documento parcial/fallido | Mostrar la explicación y conservar los otros resultados del lote. |

### Cancelación y cierre de ventana

El botón Cancelar envía el comando v1 por stdin y espera resultado terminal/limpieza del CLI. No lanzar `taskkill` global desde el renderer ni intentar gestionar servidores VLM en JS.

Si el usuario cierra mientras hay trabajo, ofrecer cancelar/cerrar o continuar con la ventana abierta. Para el comportamiento de cierre acordado, pedir cancelación al CLI y aplicar el timeout del supervisor si no responde; no salir dejando un proceso de conversión huérfano. La necesidad de una interacción aquí es de UX, no del fallback GPU, que siempre es automático.

Si un hijo necesita cierre forzado, limitarlo al proceso propio y su árbol, usando la misma política documentada del CLI. Probar que la app no mata un `sami` lanzado por separado en otra terminal.

### Bridge mínimo

Operaciones propuestas: `getHealth`, `selectFiles`, `selectFolder`, `startConversion`, `cancelConversion`, `openOutputFolder`, `loadPreview`, `startResultDrag`; suscripciones a eventos/diagnósticos y unsubscribe al cerrar vista. No exponer `exec(command)` ni el IPC entero a la página de preview.

Las rutas seleccionadas por el usuario o devueltas por el CLI definen qué recursos puede previsualizar/exportar la UI. Mantener aislada la vista de contenido del documento de las operaciones de proceso.

### Pruebas y cierre U08

Usar un CLI de prueba que emite eventos, no importar el paquete Python: Unicode, líneas fragmentadas, stderr simultáneo, warning, parcial, crash, cancelación y versión incompatible. Probar CLI por ruta con espacios, lanzamiento sin `PATH` actualizado y cierre con un hijo/grandhijo propio.

Después conectar con el CLI publicado real: health, convertir una página, cancelar y conservar resultados. **Cierre:** ninguna regla de conversión duplicada; todos los caminos de ejecución tienen estado terminal visible. **Rollback:** quitar la UI/runner no altera la instalación CLI ni sus resultados.

## U09 — Pantalla, visores y arrastre

### Pantalla funcional mínima

| Zona | Elementos y comportamiento |
|---|---|
| Entradas | Añadir PDF, añadir carpeta, drop de archivos/carpetas y quitar selección. Mostrar nombres/rutas, no contenido completo en la lista. |
| Opciones | Modo `balanced` seleccionado inicialmente; recursividad para carpetas, destino opcional y flat. |
| Estado | Compatibilidad/CPU-GPU efectiva resumida, sin exponer listas de paquetes al flujo principal. |
| Ejecución | Convertir, cancelar, documento actual/etapa y progreso de cantidad de documentos. |
| Resultados | Estado por documento, rutas reales de salida, warnings y botón Abrir carpeta. |
| Visores | PDF origen y Markdown convertido embebidos, con selección del resultado a visualizar. |

La carpeta de trabajo es una preferencia de selección/navegación. La carpeta de salida es una opción distinta: si no se elige, **cada PDF** se convierte junto a su origen como define el CLI. No usar la carpeta del ejecutable, la del acceso directo ni la del primer PDF como destino implícito de todo el lote.

Para no duplicar reglas, al añadir carpetas la UI puede listar la selección como carpeta; el CLI resuelve el número y orden efectivos al comenzar y emite `inputs_resolved`. Los duplicados y homónimos se reflejan desde su resultado.

### Visores

- PDF.js local: carga del PDF seleccionado, páginas, zoom y navegación; añadir búsqueda si su integración de viewer lo permite sin rehacerlo.
- markdown-it + KaTeX locales: Markdown y fórmulas, con HTML de tablas saneado y recursos relativos al documento final. No modificar el `.md` al mostrarlo.
- Presentar un mensaje gráfico si un recurso no existe. Un fallo de preview no cambia el estado de conversión reportado por el CLI.
- El contenido del documento no ejecuta comandos, scripts ni navega por rutas arbitrarias del sistema. Enlaces externos solo se abren mediante acción explícita del usuario.

Las librerías se empaquetan localmente con estilos/fuentes/worker PDF. Evitar CDN para que la UI sea usable offline tras instalar. No usar el visor integrado del navegador como sustituto sin comprobar la interacción y el manejo de archivos locales en los SO objetivo.

### Arrastre y carpeta de salida

Entrada: eventos drag/drop, rutas nativas recuperadas con `webUtils.getPathForFile` y selección estándar para carpetas. No usar `File.path` antiguo ni confiar en rutas de un objeto web fabricado.

Salida: arrastre nativo de Electron de archivos existentes, con icono y rutas del resultado. Para resultados con imágenes, ofrecer como unidad principal la carpeta de resultado para conservar sus vínculos; si se exporta solo el MD, indicarlo sin cambiar silenciosamente sus referencias. En modo flat, la exportación debe acompañar los recursos devueltos por el CLI o usar una carpeta preparada de exportación; no asumir que el `.md` es autocontenido.

La UI puede copiar archivos ya generados para exportarlos: es una operación de presentación/archivos, no una conversión alternativa. No interpretar el Markdown para reconstruir una lista de recursos si el CLI ya devuelve sus rutas. Empezar con copia, conservando origen; cualquier acción de mover requiere una decisión de UX posterior.

Probar drag hacia Explorer y al menos un gestor Linux de la matriz; el destino receptor decide qué acepta. Cuando no acepte el tipo exportado, el botón Abrir carpeta permite manipular los archivos desde el gestor del SO. No prometer compatibilidad literal con cualquier aplicación receptora.

### Pruebas y cierre U09

Flujos: dos PDF y una carpeta, rutas distintas, destino por defecto por input, salida común/flat, segunda conversión numerada, error/partial, warning CPU, visores con tabla/ecuaciones/figuras, links de referencia, drag entrada/salida y offline.

No exigir acabado visual profesional ni optimización del peso del bundle. Exigir controles útiles, navegación por teclado básica y una ventana responsive mientras el CLI trabaja. **Cierre:** aplicación funcional de desarrollo; aún falta su despliegue final y release en el plan 05.

Fuentes: [Node child_process](https://nodejs.org/api/child_process.html), [contextBridge/context isolation](https://www.electronjs.org/docs/latest/tutorial/context-isolation), [arrastre Electron](https://www.electronjs.org/docs/latest/tutorial/native-file-drag-drop/), [rutas webUtils](https://www.electronjs.org/docs/latest/api/web-utils), [PDF.js](https://mozilla.github.io/pdf.js/), [markdown-it](https://github.com/markdown-it/markdown-it), [KaTeX](https://katex.org/docs/browser).
