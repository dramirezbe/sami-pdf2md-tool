# 05 — Despliegue de UI y release 0.3.0

Fecha: 2026-11-18, America/Bogota. Estado: especificación para implementación futura.
Rama futura: `feat/0_3_0_sami_ui`. Unidades U10–U11.
Depende de [04 — aplicación Electron](04-ui-aplicacion-electron-0.3.0.md) y CLI `0.2.x` publicado/probado.
Entrada general: [índice](2026-11-18_10-31-38_analisis-diseno-refactor-sami.md).

## Resultado de esta etapa

La instalación completa hace CLI → health → UI. Al terminar, el usuario abre el ejecutable o su acceso con doble clic y puede convertir sin consola, activación manual ni instalaciones pendientes. El CLI sigue siendo instalable y usable por separado.

## Archivos

| Archivo actual/futuro | Trabajo |
|---|---|
| `ui/electron-builder.yml` | Producto, identidad estable, iconos y target NSIS Windows; Linux según baseline probado. |
| `ui/package.json`, `package-lock.json` | Versión `0.3.0`, scripts y dependencias de empaquetado coherentes. |
| `packaging/windows/` | Hooks mínimos para dependencia CLI, health y registro; evitar duplicar bootstraps. |
| `install.ps1`, `install.sh` | Añadir selección CLI solo/completo/UI sobre instalación existente. Misma resolución de versiones y pruebas. |
| `packaging/runtime-manifest.json` | Producto gráfico `0.3.0`, versión CLI exacta compatible, protocolo y artefactos/checksums. |
| `.github/workflows/ci.yml`, `release.yml` | Build/smoke de UI, validación de pareja de componentes y release gráfica. |
| `.gitignore` | `node_modules` y outputs UI; conservar lock/config/assets fuente. |
| `README.md`, `CLAUDE.md`, `CHANGELOG.md`, `docs/releasing.md` | Instalar, actualizar, reparar y usar UI con CLI versionado. |
| `ui/tests/`, `tests/integration/` | Matriz de instalación, procesos y doble clic sin dependencias de desarrollo. |

## U10 — Instalación e integración de escritorio

### Una sola lógica de instalación

Propuesta de componentes del bootstrap: `cli`, `all` y `ui`. En `0.3.0`, la instalación completa usa `all`; `cli` sigue disponible. Los nombres/sintaxis se documentan después de implementar el parser. Tanto `irm` como el `.exe` descargable llaman a las mismas operaciones comprobadas.

| Paso | Acción | Regla de avance |
|---|---|---|
| Resolver | Leer manifiesto gráfico y registro local. | Fijar UI `0.3.0`, CLI exacto probado y protocolo compatible. |
| CLI | Instalarlo si falta; reutilizarlo si es compatible; actualizarlo de forma recuperable si procede. | Tres modos y CPU de respaldo listos. No repetir diagnóstico profundo si el CLI ya está sano. |
| Health | Consultar ejecutable registrado. | `ready/degraded` avanzan. GPU fallida con CPU lista no bloquea. Núcleo incompleto sí requiere reparar su instalación. |
| UI | Instalar la aplicación Electron de la release. | Paquete íntegro y versión/protocolo comprobados. |
| Integración | Registro, accesos y lanzadores. | Targets existentes y unívocos; no accesos a archivos temporales. |
| Finalización | Smoke gráfico y consulta de CLI. | Anunciar completo solo cuando doble clic y conversión puedan funcionar sin preparar dependencias. |

Si falla CLI, no presentar la instalación UI como exitosa. Si falla UI, conservar CLI operativo y permitir reintentar la etapa gráfica. La preparación de modelos termina antes de anunciar instalación lista, aunque se haya ejecutado en background supervisado.

### Windows 11

Usar electron-builder/NSIS como formato de distribución gráfica por usuario. Propuesta de ubicación estable: `%LOCALAPPDATA%\Programs\SAMI\ui`; el CLI mantiene su ubicación registrada. El paquete Electron no incluye Node/Python/modelos como prerrequisitos del usuario: Node va en Electron y Python/modelos los prepara el bootstrap CLI.

| Integración | Detalle exigido |
|---|---|
| Escritorio | `SAMI.lnk`, icono propio, destino al ejecutable gráfico estable. Resolver Known Folder real, incluido escritorio redirigido/OneDrive. |
| Inicio | Entrada `SAMI` en Programas del usuario; verificable desde el menú y búsqueda del SO tras su registro. |
| Doble clic | UI sin consola y sin depender del cwd ni `PATH` actualizado de Explorer. Health/CLI por ruta absoluta registrada. |
| `PATH` | Directorio de lanzadores estable añadido al usuario, sin duplicados ni reemplazar entradas. Mantener comando `sami`; lanzador gráfico propuesto `sami-gui`. |
| Registro | Versión/desinstalador y una identidad de aplicación estable entre updates. |
| Update | No duplicar accesos ni instalaciones. Conservar configuración y diagnóstico de componentes que no cambian. Mantener rollback de versión gráfica. |
| Uninstall UI | Quitar aplicación/accesos/registro propios de UI; mantener CLI y documentos. No quitar `sami` de `PATH` si CLI continúa instalado. |
| Uninstall completo | Coordinar dependencias, retirar solo integración propia y conservar PDF/resultados; limpieza de caches mediante política explícita. |

Actualizar el entorno persistente y notificar al SO; la sesión bootstrap puede refrescar su propio `PATH`, pero no prometer modificar procesos terminal ya abiertos. La UI nunca depende de ese refresco para encontrar CLI.

No confundir entrada en Inicio con autoarranque al iniciar sesión. No añadir autoarranque ni fijar barra de tareas como requisitos no solicitados. No pedir privilegios para instalar por usuario salvo un paso de driver que el usuario solicite explícitamente.

### Linux y macOS

En Linux Debian-based, empaquetar AppImage o paquete Debian **después de probarlo en el baseline CLI**; registrar aplicación y lanzador `.desktop` donde corresponda. El requisito es instalación usable, no producir una extensión concreta sin verificar runtime/gráficos del SO. Desktop shortcut Linux puede depender del entorno y permisos; documentar el alcance real.

macOS es secundario/no bloqueante. Si se distribuye, probar paquete/app y acceso al CLI instalado en esa plataforma, sin anunciar equivalencia a Windows/Linux no comprobada.

### Pruebas y cierre U10

1. Instalación Windows limpia sin Python/Node; tres modos del CLI listos y UI de doble clic.
2. Añadir UI a CLI publicado y sano sin repetir descargas/diagnóstico; detectar versión incompatible antes de activar una pareja inválida.
3. Escritorio normal y redirigido, usuario con unicode/espacios, Inicio, `PATH` previo y shell abierto antes de instalar.
4. Fallo GPU → warning/CPU y UI usable. Fallo de instalación CLI o UI → resultado claro y rollback limitado.
5. Reinstalación/update sin duplicados; quitar solo UI conserva `sami`; desinstalación completa no borra documentos.
6. Linux de la matriz: ejecutar paquete, abrir ventana, localizar CLI, convertir, abrir carpeta y drag real.

Registrar identidad/versiones/rutas y comandos; adjuntar evidencia de doble clic y accesos con el paquete real. **Rollback:** retirar/restaurar únicamente UI y sus accesos; CLI continúa disponible.

## U11 — CI y release gráfica 0.3.0

### Versiones independientes

| Componente | Versión/validación |
|---|---|
| UI Electron | `0.3.0` en `package.json` y lock. |
| CLI Python | `0.2.x` exacto probado, normalmente `0.2.0` si no necesitó correcciones. No renombrar wheel sin cambios como `0.3.0`. |
| Manifiesto producto | `0.3.0` con identidades de ambos componentes y protocolo. |
| Release/tag repo | `v0.3.0`, commit UI ya integrado en `main`. |

Si la UI revela una carencia del CLI, corregirla y publicar una versión CLI con identidad nueva, actualizando la dependencia. No sustituir bytes de `0.2.0`. El bootstrap no usa `latest` para adivinar la dependencia CLI porque Latest pasará a señalar la release UI.

### Pipeline y publicación

1. Cerrar U08–U11 y actualizar docs/changelog en `feat/0_3_0_sami_ui`, con versiones/protocolo comprobados por CI.
2. Integrar el PR en `main`; fijar SHA candidato y ejecutar build de ensayo más smoke de paquetes. Probar instalación limpia y sobre CLI existente con esos assets.
3. Crear/subir tag anotado `v0.3.0` sobre ese SHA integrado. Workflow construye desde tag y valida versiones **por componente**, no igualdad ciega UI=CLI.
4. Construir UI Windows/Linux obligatorias y macOS solo si se valida; producir checksums y draft. Descargar el CLI publicado exacto que usará el instalador y probar esa combinación real.
5. Adjuntar paquete UI, bootstraps, manifiesto, `SHA256SUMS` y notas de `0.3.0`. La wheel CLI puede referenciarse desde su release original; no reconstruirla bajo la misma versión para cambiar bytes.
6. Pasar U10 con los assets finales; publicar `0.3.0` como Latest y comprobar URL públicas `irm/curl`, instalación completa y CLI solo. Mantener `v0.2.0` accesible.
7. Registrar SHA/tag/run, pareja de componentes, matriz probada, resultados y rollback. Un fallo de build conserva draft; no mover tags ni reemplazar releases estables consumidas.

Assets propuestos: `SAMI-0.3.0-win-x64-setup.exe`, paquete Linux probado, `install.ps1`, `install.sh`, manifiesto y checksums. Nombres exactos deben coincidir con lo que realmente construye electron-builder. Node/npm no son dependencias de ejecución que deba instalar el usuario.

### Criterio final

El usuario instala desde `irm`, espera instalación CLI y health, completa UI y abre desde escritorio/Inicio o `.exe`. Puede añadir/arrastrar PDF/carpetas, elegir modo/salida, ver progreso/preview, cancelar y abrir/exportar resultados. Todo procesamiento y fallback depende del CLI publicado. La UI desinstalada no impide seguir usando CLI `0.2.x`.

Fuentes: [electron-builder NSIS](https://www.electron.build/v26/docs/nsis/), [accesos Inicio](https://learn.microsoft.com/en-us/windows/win32/shell/how-to-add-shortcuts-to-the-start-menu), [Known Folders](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid), [variables de entorno Windows](https://learn.microsoft.com/en-us/windows/win32/procthread/environment-variables), [gestión de releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

Este documento describe acciones futuras; no crea instaladores, ramas, tags ni releases al guardarse.
