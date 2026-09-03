# JARVIS — Estado del Proyecto

Documento vivo de control de estado, arquitectura, avances y pendientes de JARVIS.  
Cada afirmación de este documento está verificada contra el estado **real y actual** del repositorio (código fuente, base de datos, git log y resultados de pytest).

---

## 1. Resumen Ejecutivo

**JARVIS** es un asistente de automatización y ejecución segura reprogramado desde cero bajo una arquitectura modular de plugins aislados por sandbox y capacidades restringidas; actualmente se encuentra en la **transición entre la Fase 4 de cimientos y la Fase 5 de interfaces**, implementando el subsistema de **instalación segura de plugins desde GitHub (Catálogo Curado vs. Modo Avanzado)** y el visualizador reactivo de voz.

---

## 2. Fases y Componentes Completados

La siguiente tabla refleja exclusivamente el trabajo consolidado, commiteado y verificado en la suite automatizada de pruebas:

| Fase / Componente | Nombre y Alcance | Qué se construyó en la práctica | Commit(s) | Tests pytest (resultado real) | Estado de Aprobación |
|---|---|---|---|---|---|
| **Fase 0** | Fundación del Repositorio | Árbol de carpetas canónico (`core/`, `plugins/`, `versions/`, `database/`, `tests/`, `docs/`), virtualenv Python 3.13, `.gitignore` estricto excluyendo `.env`, `*.db`, logs y temporales desde el inicio. | `8937294` | N/A (Estructural) | **Aprobada** |
| **Fase 1** | Núcleo y Modelo de Capacidades | Catálogo cerrado de 6 capacidades (`core/capability_catalog.py`), perfiles de permisos (`core/version_profiles.py`), cargador de manifiestos con `schema_version="1"` y namespacing de acciones (`core/plugin_loader.py`), dispatcher con confirmación de usuario por sesión (`core/dispatcher.py`), sandbox con allowlist y exclusión de `_SENSITIVE_SUBDIRS` (`core/sandbox.py`), auditoría persistente en SQLite (`core/audit_log.py`), gestor de secretos (`core/secrets.py`) y logging unificado (`core/logging_setup.py`). | `fc6d1f7`<br>`5e213d8`<br>`5f3b303` | **8 pasados**<br>(`test_plugin_loader.py`: NUC-01 a NUC-06 + 2 de aislamiento de cwd) | **Aprobada** |
| **Fase 2** | Plugin de Prueba (`toy`) | Implementación de `plugins/toy/` (`manifest.json`, `plugin.py`) con la acción `toy.get_time` (capacidad `system_info`) para validar ciclo de vida, recarga limpia y aislamiento del núcleo sin riesgos. | `218b3d3` | **4 pasados**<br>(`test_toy_plugin.py`: TOY-01 a TOY-03 + basic_execution) | **Aprobada** |
| **Fase 3** | Perfil `core-lite` | Primera versión ejecutable (`versions/core_lite/main.py`), restringida a cero servidores de red/GUI escuchando, sin capacidades de filesystem ni ejecución de código, auditando rechazos al intentar cargar manifiestos ajenos. | `9b9efb1`<br>`087a54f` | **3 pasados**<br>(`test_core_lite.py`: LITE-01 a LITE-03) | **Aprobada** |
| **Fase 4** | Plugin Open Interpreter y Confinamiento Adversarial | Implementación de `plugins/open_interpreter/` con 5 acciones (`run_python`, `write_file`, `read_file`, `create_presentation`, `search_local_files`). Aislamiento de red forzoso en `run_python` con Bubblewrap (`bwrap`) bajo política fail-closed; allowlist estricta de extensiones seguras (`.txt`, `.md`, `.py`, `.pptx`, `.csv`, `.log`, `.png`, `.jpg`, `.jpeg`, `.pdf` — sin `.json`); bloqueo de path traversal y exclusión estricta de subdirectorios de credenciales (`.ssh`, `.aws`, `.gnupg`, etc.); timeout de ejecución. | `d5da517`<br>`18934f9`<br>`97fbf00`<br>`305d273` | **8 pasados**<br>(`test_open_interpreter.py`: OI-01 a OI-08) | **Aprobada** |
| **Gestión Plugins (Subfase A)** | Modelo de Datos `plugin_registry` | Tabla SQLite `plugin_registry` en `database/jarvis.db` (`core/plugin_registry.py`) con control estricto de `active_commit_hash` y `candidate_commit_hash`. La unidad de confianza es el par `(plugin_id, commit_hash)`. `register_plugin()` fuerza siempre status `no_verificado`. Promoción únicamente mediante `promote_to_curated()`. Resolución canónica de ruta contra `_REPO_ROOT` e inicialización lazy sin efectos secundarios en imports. | `bf705c2`<br>`7d109ca` | **5 pasados**<br>(`test_plugin_registry.py`) | **Construida, pendiente de revisión** |
| **Gestión Plugins (Subfase B)** | Instalación desde Catálogo y Modo Avanzado | `PluginInstaller` (`core/plugin_installer.py`) y catálogo curado `database/curated_catalog.json` (`is_placeholder_data: true`). Soporte de `install_from_catalog(plugin_id)` (UI final sólo envía ID, preserva auditoría histórica `reviewed_by` y `reviewed_at`) e `install_from_url(source_url, plugin_id, ref)` (resuelve commit concreto 40 hex mediante `git ls-remote` / `rev-parse`, siempre `no_verificado`). Protección fail-closed anti-inyección de argumentos hacia Git (flags con `-`) y separador defensivo `--` / `--end-of-options`. | `17971b0`<br>`c3f1de2` | **8 pasados**<br>(`test_plugin_installer.py`: 5 funcionales + 3 adversariales) | **Construida, pendiente de revisión** |

---

## Fuera de alcance — Parqueado

### Visualizador de Audio Reactivo 3D (`ui/audio_visualizer.py`)
- **Estado:** Parqueado. No forma parte de la revisión actual ni se considera completado ni aprobado.
- **Qué se construyó:** Widget `ReactiveAudioVisualizer` en PyQt6 (`ui/audio_visualizer.py`) con proyección matemática 3D→2D sobre esfera de Fibonacci (144 nodos, aristas precalculadas, rotación NumPy), renderizado puro en 2D sobre `QPainter` (sin OpenGL ni Qt3D), sprites de glow radial precomputados en memoria, reactividad FFT en escucha y pulso sincrónico en habla. Cuenta con 7 tests automatizados en `tests/test_audio_visualizer.py`.
- **Motivo de parqueo:** Su desarrollo se adelantó e intercaló sin pasar por la ronda de revisión y aprobación formal. Queda congelado fuera del alcance de las fases del núcleo hasta que se abra formalmente la etapa de interfaces de usuario (Fase 5+).

---

## 3. Fase Actual y Estado de Avance

El proyecto se encuentra ejecutando el **Desglose de Instalación y Ciclo de Vida de Plugins** (capa previa al Dashboard de la Fase 5).

### Estado por subfases:
- [ ] **Subfase A — Modelo de datos:** Construida, pendiente de revisión formal (commits `bf705c2`, `7d109ca`). Pasará a "Aprobada" tras la confirmación de la revisión.
- [ ] **Subfase B — Instalación de plugins (Catálogo vs. URL):** Construida con protección anti-inyección, pendiente de revisión formal (commits `17971b0`, `c3f1de2`). Pasará a "Aprobada" tras la confirmación de la revisión.
- [ ] **Subfase C — Caché de confirmación y status `no_verificado` en Dispatcher:** Pendiente de implementación.
- [ ] **Subfase D — Chequeo de actualizaciones en background y `candidate_commit_hash`:** Pendiente de implementación.
- [ ] **Subfase E — Modo Avanzado (habilitación controlada):** Pendiente de implementación.
- [ ] **Subfase F — Integración con UI / Dashboard:** Pendiente de implementación.

### Correcciones pendientes de rondas anteriores:
- **0 correcciones pendientes de código.** Todos los hallazgos de las revisiones previas (remoción de `network_access`, depuración de capacidades no usadas en el catálogo, fail-closed en bwrap, blindaje de `register_plugin`, resolución de `db_path` independiente de `cwd`, eliminación de instanciación en import de módulo, y sanitización anti-inyección de opciones hacia Git) fueron resueltos y verificados con tests dedicados.

---

## 4. Decisiones de Diseño Vigentes (Reglas Fijas)

Estas reglas rigen el diseño arquitectónico del proyecto y son de aplicación obligatoria:

1. **Catálogo Cerrado Estricto:** Las únicas capacidades reconocidas por el núcleo son las 6 activas en `core/capability_catalog.py`: `system_info`, `filesystem_read`, `filesystem_write`, `code_execution`, `notify_user` y `telegram_send`. Capacidades aspiracionales (`audio_capture`, `audio_synthesis`, `device_management`, `network_access`) fueron removidas y solo se agregarán cuando la fase correspondiente las implemente de verdad.
2. **Namespacing Obligatorio de Acciones:** Ninguna acción se invoca por nombre suelto. Todas siguen la convención `plugin_id.action_name` (ej. `open_interpreter.run_python`), haciendo estructuralmente imposibles las colisiones de nombres.
3. **Política Fail-Closed en Confinamiento de Código:** La acción `open_interpreter.run_python` exige el aislamiento de red provisto por Bubblewrap (`bwrap`). Si `bwrap` no está presente en el sistema operativo, la ejecución se cancela con error explícito; jamás se degrada silenciosamente a ejecución sin aislamiento.
4. **Sanitización de Filesystem por Allowlist:** La allowlist por defecto del sistema (`DEFAULT_ALLOWED_EXTENSIONS` en `core/sandbox.py`) autoriza exclusivamente extensiones seguras de texto, código, multimedia y documentos: `.txt`, `.md`, `.py`, `.pptx`, `.csv`, `.log`, `.png`, `.jpg`, `.jpeg`, `.pdf`. **NO incluye `.json`** (evitando escritura inadvertida de archivos de credenciales/configuración). `open_interpreter.write_file` aplica esta allowlist por defecto a menos que el llamador especifique una lista permitida explícita, y bloquea de raíz rutas sensibles (`_SENSITIVE_SUBDIRS`: `.ssh`, `.aws`, `.gnupg`, `credentials`, `id_rsa`, etc.).
5. **Independencia de Directorio de Trabajo (`cwd`):** Ninguna ruta del sistema (`sandbox_root`, `jarvis.db`, `curated_catalog.json`) puede resolverse contra `os.getcwd()`. Se calculan siempre de forma determinista a partir de `__file__` (`_REPO_ROOT = Path(__file__).resolve().parent.parent`), con anulación permitida por parámetro programático o variables de entorno (`JARVIS_SANDBOX_ROOT`, `JARVIS_DB_PATH`, `JARVIS_CURATED_CATALOG_PATH`).
6. **Sin Efectos Secundarios en Import:** La importación de módulos Python (`core.plugin_registry`, etc.) no puede ejecutar sentencias DDL (`CREATE TABLE`), instanciar conexiones o tocar el disco. La creación de esquemas se ejecuta bajo demanda en la primera conexión requerida (*lazy initialization*).
7. **Dos Canales de Instalación Separados:**
   - *Catálogo Curado:* Interfaz para el usuario final. La función pública `install_from_catalog(plugin_id)` **sólo** acepta `plugin_id`. No expone URLs ni commit hashes. Conserva intactos en la base de datos la fecha original (`reviewed_at`) y el auditor (`reviewed_by`) de la revisión humana previa registrada en el catálogo.
   - *Modo Avanzado:* Instalación directa por URL Git mediante `install_from_url(source_url, plugin_id, ref)`.
8. **Pinning Obligatorio por Commit Hash:** Ningún plugin se almacena bajo una referencia mutable (`HEAD`, nombre de rama o tag). La instalación resuelve siempre el SHA-1 de 40 caracteres hexadecimales del commit concreto.
9. **Unidad de Confianza `(plugin_id, commit_hash)`:** La confianza y el status `curado` pertenecen al par indivisible `(plugin_id, commit_hash)`. Un nuevo commit para un plugin previamente curado pasa obligatoriamente a status `no_verificado`.
10. **Promoción Exclusivamente Humana:** No existe ningún mecanismo automático para cambiar un plugin a status `curado`. El único camino autorizado en el código es la invocación directa de `promote_to_curated()`.
11. **Anti-Inyección de Opciones hacia Procesos Externos:** Toda interacción con binarios de sistema (ej. `git`) rechaza en frontera (*fail-closed*) entradas donde `source_url`, `ref` o `plugin_id` inicien con `-`, e incorpora el separador `--` / `--end-of-options` antes de argumentos posicionales.

### Decisiones Acordadas PENDIENTES de Implementación en Código:
- **Exclusión de la Caché de Confirmación por Sesión para Plugins `no_verificado`:** *(Decidido, pendiente de implementar en Subfase C)*. `session_confirmed_capabilities` en `Dispatcher` debe ignorar a cualquier plugin cuyo status actual en `plugin_registry` sea `no_verificado`, exigiendo confirmación de usuario en **cada invocación individual**.
- **Chequeo Automático de Actualizaciones en Background con Aplicación Manual:** *(Decidido, pendiente de implementar en Subfase D)*. Un daemon/job verificará periódicamente contra el remoto si existen commits posteriores al `active_commit_hash`, registrándolos en `candidate_commit_hash` sin alterar el código en ejecución ni el status del plugin hasta que el usuario decida manualmente aplicar la actualización.
- **Habilitación Condicional de Modo Avanzado:** *(Decidido, pendiente de implementar en Subfase E)*. El Modo Avanzado debe permanecer oculto y desactivado por defecto en la UI.

---

## 5. Qué Sigue (Próximo Paso Concreto)

1. **Cierre de Revisión de Subfases A y B:** Esperar la confirmación y aprobación explícita de la revisión de `core/plugin_registry.py` y `core/plugin_installer.py` para actualizar su estado a **Aprobada**.
2. **Retomar `docs/formato_plugins.md`:** Actualizar (sin reescribir) la especificación técnica de plugins para incorporar los nuevos campos que el instalador requiere:
   - Estado de verificación (`curado` / `no_verificado`).
   - `commit_hash` pineado (fijo de 40 caracteres hexadecimales).
   - Origen del plugin (catálogo curado vs. modo avanzado por URL).
   - Especificar cómo interactúan estos campos con el `manifest.json` ya definido en la Fase 4.
3. **Subfase C:** Implementar la exclusión de la caché de confirmación por sesión para plugins no verificados en `core/dispatcher.py`:
   - Conectar `core/dispatcher.py` con `core/plugin_registry.py` (o inyectar consulta de registro).
   - Modificar la lógica de despacho: cuando una acción requiera una capacidad con confirmación previa (`requires_confirmation=True`), si el plugin tiene status `no_verificado`, **no se consulta ni se guarda en la memoria de sesión** (`self.session_confirmed_capabilities`).
   - Construir la batería de pruebas automatizadas que verifique:
     - Plugin `curado` pide confirmación la primera vez y cachea para la segunda invocación en el mismo proceso.
     - Plugin `no_verificado` pide confirmación en la primera, segunda y en cada invocación subsecuente, sin importar si el usuario confirmó la anterior.
   - Mantener la suite de tests completa en verde y generar el reporte formal para aprobación.

---

## 6. Preguntas Abiertas sin Resolver (Decisiones de Producto/Diseño Pendientes)

Las siguientes decisiones quedaron expresamente postergadas y marcadas con `TODO` en el código fuente:

1. **Control de acceso por roles/cuentas para operaciones privilegiadas (`PENDIENTE 1` en `core/plugin_registry.py` y `core/plugin_installer.py`):**  
   Quién y mediante qué credenciales o sesión puede invocar `install_from_url`, `apply_candidate_update` y `promote_to_curated`. Se resolverá en la **Fase 5** junto con el diseño general de autenticación del dashboard.
2. **Modelo de Revocación/Bloqueo de Plugins Curados (`PENDIENTE 2` en `core/plugin_registry.py`):**  
   Cómo gestionar un plugin que ya fue marcado como `curado`, pero posteriormente se descubre una vulnerabilidad crítica en ese commit específico (ej. nuevo estado `bloqueado`/`revocado` en la tabla y rechazo en `dispatcher`). Todavía no ha sido definido si el bloqueo debe ser preventivo a nivel de carga o de ejecución.
3. **Criterio de Exposición del Modo Avanzado (`PENDIENTE 3` en `core/plugin_registry.py` y `core/plugin_installer.py`):**  
   Qué gatilla que un usuario vea el Modo Avanzado en la interfaz (¿un flag en `config.json`?, ¿una variable de entorno?, ¿un rol de usuario en la base de datos?). Por ahora la regla fija es únicamente que debe estar "oculto por defecto".

---

## 7. Riesgos Conocidos y No Resueltos

Hallazgos de auditoría y limitaciones de diseño aceptadas como "no bloqueantes de fase", pero que deben monitorearse:

- **R1 — Dependencia estricta de Bubblewrap en el host para Python aislado:**  
  La ejecución segura en `open_interpreter.run_python` opera bajo fail-closed: si el binario del sistema `bwrap` no está instalado en la máquina anfitriona (Linux), la acción se niega a correr. En entornos restringidos sin `bwrap`, no existe actualmente un sandbox alternativo de contingencia.
- **R2 — Concurrencia de SQLite en archivo único (`database/jarvis.db`):**  
  Tanto los logs de auditoría (`audit_logs`) como el registro de plugins (`plugin_registry`) convergen en el mismo archivo SQLite. Aunque el driver tiene configurado un `timeout=10.0` y modo transaccional seguro, SQLite bloquea el archivo ante escrituras concurrentes. No es un problema en la escala actual de procesos locales, pero requerirá revisión si múltiples agentes o workers asíncronos escriben en paralelo.
- **R3 — Entradas sintéticas en el catálogo curado (`is_placeholder_data: true`):**  
  Las 3 entradas actuales en `database/curated_catalog.json` (`toy`, `open_interpreter`, `system_monitor`) contienen URLs y commit hashes de prueba. Antes de un despliegue en producción o beta pública, este archivo debe reemplazarse obligatoriamente por un catálogo firmado y verificado con auditorías reales.
- **R4 — Dependencia de entrada de audio física para el visualizador en vivo:**  
  Las pruebas del visualizador se ejecutan en modo `offscreen` generando datos sintéticos. El comportamiento interactivo real en desktop depende de la configuración de servidores de sonido del sistema (ALSA / PulseAudio / PipeWire) y de la captura correcta de paquetes PCM del micrófono sin latencias excesivas.
