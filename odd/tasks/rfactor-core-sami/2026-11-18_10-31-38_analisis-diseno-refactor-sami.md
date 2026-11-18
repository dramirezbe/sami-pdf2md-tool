# SAMI: índice de implementación del CLI 0.2.0 y la UI 0.3.0

Apertura: 2026-11-18 10:31:38. División del plan: 2026-11-18 11:39:08, America/Bogota (UTC−05:00).
Base de código revisada: `6452f12`; versión actual declarada: `0.1.0`.
Estado: **solo documentación de diseño; no implementar, crear ramas ni publicar hasta recibir una instrucción posterior**.

El trabajo se divide en cinco planes ejecutables en orden. Cada uno identifica archivos, contratos, unidades de trabajo, pruebas, evidencias y condiciones de cierre. Los requisitos del usuario están fijados aquí; las decisiones técnicas propuestas dentro de cada etapa pueden ajustarse con evidencia sin cambiar esos requisitos.

## Orden de implementación

| Orden | Plan | Unidades | Rama y resultado |
|---|---|---|---|
| 1 | [Contratos y motores CLI](01-cli-contratos-motores-salidas.md) | U00–U02 | `refactor/0_2_0_sami_cli`: viabilidad, contrato público, preservar Marker, motor Caste y salidas. |
| 2 | [Diagnóstico, runtimes e instalación](02-cli-diagnostico-runtime-instalacion.md) | U03–U05 | Misma rama CLI: diagnóstico persistido, health rápido, fallback CPU y bootstrap completo. |
| 3 | [Lotes, progreso, validación y release CLI](03-cli-lotes-validacion-release-0.2.0.md) | U06–U07 | Cerrar CLI, integrar en `main` y publicar **`v0.2.0`**. |
| 4 | [Aplicación Electron](04-ui-aplicacion-electron-0.3.0.md) | U08–U09 | `feat/0_3_0_sami_ui`, desde `main` con CLI publicado: interfaz que ejecuta comandos. |
| 5 | [Despliegue y release UI](05-ui-despliegue-release-0.3.0.md) | U10–U11 | Cerrar instalador gráfico, integrar en `main` y publicar **`v0.3.0`**. |

La release CLI no espera la UI. No crear la rama UI durante la implementación inicial del CLI. Los tags nunca se mueven para añadir posteriormente componentes.

## Requisitos que no debe reinterpretar el implementador

| Área | Decisión del usuario |
|---|---|
| Conversión | Preservar la lógica MD de SAMI/Marker; Caste se utiliza únicamente como motor rápido. |
| Modos | `fast`, **`balanced` por defecto**, `quality`. Mapeo técnico de trabajo: Caste, Marker `fast`, Marker `balanced`, respectivamente. Validarlo en U00/U01. |
| Configuración Caste | Tomar su invocación real: `quality="high", ocr=False, images=False`. Conservar texto, tablas, layout heurístico, marcadores y controles existentes sin añadir modelos pesados. |
| Referencias | Conservar siempre texto bibliográfico y enlaces recuperables dentro del `.md`. Sin `.bib` ni dependencia de artefactos bibliográficos externos; no inventar URL. |
| Salidas existentes | Crear una nueva salida numerada, conservando las anteriores. |
| Ejecución | Todo local y sin claves; tras instalar, los tres modos funcionan sin descargas adicionales. |
| Hardware | Priorizar CPU y VRAM; comprobar también RAM, SO, arquitectura, drivers y componentes relevantes. |
| Diagnóstico | Profundo durante instalación. Persistir resultados positivos y negativos; consulta rápida al usar CLI/UI. |
| Instalación | Dejar los tres modos, modelos y ruta CPU listos. Preparar dependencias privadas automáticamente; drivers del sistema en paso explícito. |
| Fallo GPU | Warning y continuación CPU con el mismo modo, sin preguntar ni bloquear por la aceleración. |
| Plataformas | Windows 11 y Linux Debian-based prioritarios. macOS secundario, no bloquea estas releases. |
| Entradas y progreso | Archivos individuales/múltiples y carpetas; progreso por documento y por cantidad de documentos. |
| CLI primero | Debe estar completo, probado, instalable y publicado antes de construir la UI. |
| UI | Electron + JavaScript + HTML/CSS; depende exclusivamente de comandos/eventos del CLI. Sin copiar/importar su motor Python. |
| Windows gráfico | Ejecutable de doble clic, escritorio, menú Inicio, `PATH`, actualización y desinstalación coordinados. |
| UX gráfica | Arrastre entrada/salida, visores PDF/MD, rutas, abrir carpeta y elección de trabajo/salida. |

## Cómo ejecutar estos planes cuando se autorice

1. Leer este índice y el plan 01. U00 es una comprobación de viabilidad, no una autorización para cambiar el motor si una dependencia falla.
2. Completar cada unidad con código, pruebas y documentación del mismo comportamiento. Registrar resultados reales y límites; una casilla marcada no es evidencia.
3. Mantener pruebas rápidas sin modelos/red; ejecutar pruebas de motores e instalación por separado cuando la unidad lo requiera.
4. No saltar al plan siguiente con un contrato incompleto que obligue a duplicar reglas en la UI.
5. La release de cada etapa exige un SHA integrado en `main`, artefactos probados y versiones consistentes por componente.

Los planes nombran módulos para aclarar responsabilidades; pueden fusionarse si resulta más simple. No crear capas vacías, mocks de producción, un servidor HTTP, un daemon permanente ni una terminal embebida para cumplir la estructura del documento.

El cambio tiene riesgo alto de superar 400 líneas por PR. Conservar las dos ramas solicitadas y unidades revisables; documentar tamaño, estrategia y justificación al preparar los PR. No reducir líneas eliminando comentarios ni presentar varios commits como si fueran varios PR pequeños.

## Registro de evidencia por unidad

Usar esta plantilla dentro del seguimiento de la implementación; no rellenar con resultados supuestos:

| Campo | Contenido |
|---|---|
| Identidad | Unidad, rama, commit y base comparada. |
| Cambio | Comportamiento cerrado y archivos concretos. |
| Pruebas focalizadas | Comando exacto, salida/exit code y entorno. |
| Ejecución real | Caso/artefacto/resultado; o `N/A` con motivo si no cruza un límite de ejecución. |
| Alcance validado | SO, arquitectura, CPU/GPU, runtime/modelo y versiones cuando aplique. |
| Riesgos abiertos | Fallos pendientes y efecto real sobre la entrega. |
| Rollback | Unidad que puede revertirse sin borrar documentos ni resultados del usuario. |

## Qué sigue abierto técnicamente

- Matriz exacta de versiones Debian/Ubuntu, arquitecturas y combinaciones GPU/backend: U00 debe comprobarla antes de comprometer soporte. Propuesta inicial x86_64; no equivale a soporte de todo derivado/versionado de Debian.
- Locks, paquetes y backend CPU/GPU: resolver y fijar en U00/U04. Tener CUDA/ROCm en PyTorch no prueba que el VLM use la GPU.
- El transporte, nombres de eventos y comandos descritos en el plan 01 son la especificación técnica propuesta. Fijarlos en pruebas antes de desarrollar Electron.
- Flags avanzados adicionales de OCR, imágenes, páginas y concurrencia permanecen como ampliaciones propuestas, con alcance explícito en el plan 03. No deben modificar el perfil rápido elegido ni retrasar requisitos acordados sin una razón documentada.

## Referencias de trabajo

- [Diseño anterior completo, conservado como referencia histórica](00-referencia-diseno-anterior.md). Sus secciones antiguas no sustituyen estos planes activos.
- [Código Caste de referencia](../refactor-core-sami/PDF2MD_caste.py).
- [Entrada actual de SAMI](../../../sami/cli.py), [metadatos](../../../pyproject.toml) y [guía del repositorio](../../../CLAUDE.md).

En esta división solo se crean/modifican documentos dentro de esta carpeta. No se cambia la versión real, no se crean ramas y no se ejecutan los pasos de instalación o release.
