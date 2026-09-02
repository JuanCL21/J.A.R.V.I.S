# JARVIS desde cero — Desglose del proyecto (con revisión de auditor)

Orden de construcción, estructura de carpetas, formatos de datos y lenguaje de
cada pieza. Esto es el mapa de referencia — antes de escribir código de
cualquier fase, volver acá para confirmar dónde va cada cosa.

**Estado de esta revisión:** alcance limitado a Fases 0-4 (los cimientos, sin
interfaz). Fases 5-9 quedan con la descripción original, sin expandir
todavía — se auditan cuando les toque el turno.

---

## Estructura de carpetas (repo único, todas las versiones adentro)

```
jarvis/
├── core/                        # el motor — Python, compartido por TODAS las versiones
│   ├── plugin_loader.py         # carga manifiestos, hace cumplir permisos
│   ├── capability_catalog.py    # lista cerrada de capacidades válidas
│   ├── version_profiles.py      # qué capacidades tiene cada versión
│   ├── dispatcher.py            # único punto de entrada para invocar acciones
│   ├── sandbox.py               # resuelve sandbox_root, is_safe_path()
│   ├── audit_log.py             # NUEVO — escribe cada invoke() a SQLite
│   ├── secrets.py               # lectura/escritura de .env
│   └── logging_setup.py         # logging estructurado, un solo lugar
│
├── plugins/                     # cada plugin, aislado en su propia carpeta
│   ├── toy/                     # NUEVO — plugin de juguete de la Fase 2
│   │   ├── manifest.json
│   │   └── plugin.py
│   └── open_interpreter/
│       ├── manifest.json        # formato fijo (ver sección 3)
│       └── plugin.py            # implementa las acciones declaradas
│
├── versions/                    # cada versión = perfil + arranque, NO lógica propia
│   ├── core_lite/
│   │   ├── main.py
│   │   └── config.json
│   ├── core_full/                # (fuera de alcance de esta ronda)
│   ├── asistente/                 # (fuera de alcance de esta ronda)
│   ├── local/                     # (fuera de alcance de esta ronda)
│   └── movil/                     # (fuera de alcance de esta ronda)
│
├── protocol/                     # (fuera de alcance — Fase 7)
│
├── database/
│   └── jarvis.db                 # SQLite — dispositivos, auditoría, cola de trabajos
│
├── tests/
│   ├── test_plugin_loader.py     # Fase 1
│   ├── test_toy_plugin.py        # Fase 2
│   ├── test_core_lite.py         # Fase 3
│   └── test_open_interpreter.py  # Fase 4 — incluye batería adversarial
│
└── docs/
    └── (los documentos que ya venimos armando)
```

**Regla de la estructura:** `versions/*` nunca contiene lógica de negocio
propia — solo arma qué perfil de permisos usar y arranca el núcleo. Si algo
que "debería" ir en `core_full/main.py` termina siendo útil también para
`asistente`, es señal de que en realidad pertenece a `core/`, no a una
versión — se mueve, no se copia.

---

## Revisión de auditor — detalles que faltaban en la versión anterior

Estos son huecos reales del diseño original, no cosmética. Cada uno se
agrega porque, si se deja para después, tiende a resolverse "de pasada" bajo
presión — que es exactamente el patrón que produjo los hallazgos de la
auditoría de JARVIS_Custom.

1. **El manifiesto necesita `schema_version`.** Sin esto, el día que cambie
   el formato del manifiesto (va a pasar), no hay forma de que el núcleo
   distinga un plugin viejo de uno nuevo sin adivinar. Se agrega como campo
   obligatorio desde el primer plugin, aunque hoy solo exista la versión "1".

2. **Cada `invoke()` — permitido o denegado — se escribe al log de
   auditoría, no solo al logger de texto.** El diseño anterior solo
   mencionaba `logger.warning()` en el rechazo. Un `logger.warning()` en un
   archivo de texto es fácil de perder; una tabla en `database/jarvis.db`
   con `plugin_id, action, resultado, timestamp` es consultable después.
   Esto es lo mismo que `ADV-C10` de la auditoría anterior — un log que
   "existe" pero nadie puede consultar de forma confiable no cumple su
   función.

3. **Colisión de nombres de acción entre plugins.** El diseño no decía qué
   pasa si dos plugins declaran una acción con el mismo `name`. Regla:
   las acciones se invocan siempre como `plugin_id.action` (ej.
   `open_interpreter.write_file`), nunca por nombre de acción suelto —
   así la colisión es estructuralmente imposible, no algo que haya que
   evitar por convención.

4. **Rate limiting — deferido explícitamente, no olvidado.** No se
   construye en la Fase 1, pero se deja un punto de extensión
   (`dispatcher.py` acepta un hook opcional de límite por plugin/minuto)
   para no tener que reescribir la firma de `invoke()` cuando se agregue.
   Se activa recién cuando haya un canal remoto real (Fase 7 en adelante).

5. **`_SENSITIVE_SUBDIRS` va en `sandbox.py` desde la Fase 1**, no se agrega
   cuando llegue el plugin de Open Interpreter. Lista mínima de arranque:
   `.ssh`, `.aws`, `.gnupg`, `.docker`, `.kube`, perfiles de navegador,
   `.password-store`. Cualquier plugin que use `sandbox.py` hereda esta
   protección automáticamente, sin tener que acordarse de aplicarla.

6. **Confirmación: decisión de default, no queda abierta.** Se propone:
   confirmación **por sesión de proceso** (se pregunta la primera vez que
   una capacidad de `requires_confirmation` se usa, se cachea en memoria
   mientras el proceso siga corriendo, se resetea al reiniciar). Es
   ajustable por versión más adelante — `asistente` podría relajarlo a "una
   vez por instalación" si hace falta — pero el default de arranque es el
   más conservador.

7. **Formato de error estructurado, no solo un string.** `invoke()` debe
   devolver algo como
   `{"ok": false, "reason": "capability_denied", "capability": "code_execution"}`
   en vez de `{"error": "capacidad no permitida"}` — para que los tests
   puedan verificar la *razón* exacta del rechazo, no solo que hubo un
   error genérico. Esto es lo que nos faltó varias veces en la auditoría
   anterior, donde "falló" no alcanzaba para saber si falló por lo correcto.

---

## Fases 0-4, explicadas en detalle (con matriz de pruebas)

### Fase 0 — Fundación del repo
Estructura de carpetas vacía (la de arriba), entorno virtual, `git init`,
`.gitignore` con `.env`, `__pycache__/`, `*.db`, `logs/` **desde el primer
commit** — no se agrega cuando ya hay secretos adentro, como pasó antes.

*No hay pruebas de comportamiento acá — solo una checklist de que la
estructura y el `.gitignore` existen antes del primer commit real.*

### Fase 1 — Núcleo
`plugin_loader.py`, `capability_catalog.py`, `version_profiles.py`,
`dispatcher.py`, `sandbox.py`, `audit_log.py`, `secrets.py`,
`logging_setup.py`. Ningún plugin real todavía.

| ID | Prueba | Resultado esperado |
|---|---|---|
| NUC-01 | Cargar manifiesto con una capacidad fuera del catálogo | `ValueError` en la carga, nunca llega a `invoke()` |
| NUC-02 | `invoke()` de una capacidad no incluida en el perfil de versión | `{"ok": false, "reason": "capability_denied"}`, sin ejecutar nada |
| NUC-03 | `invoke()` de una capacidad en `requires_confirmation` sin `user_confirmed` | `{"ok": false, "reason": "needs_confirmation"}`, sin ejecutar nada |
| NUC-04 | El plugin pasa un `sandbox_root` como ruta libre (ej. `/etc`) | El núcleo lo ignora — solo resuelve desde los valores fijos permitidos |
| NUC-05 | Cualquier `invoke()`, permitido o denegado | Queda una fila nueva en la tabla de auditoría de `jarvis.db` |
| NUC-06 | Dos plugins con acción del mismo nombre | Ambos cargan sin colisión, porque se invocan como `plugin_id.action` |

### Fase 2 — Plugin de juguete
Un plugin mínimo (ej. devolver la hora del sistema) para probar el núcleo
con algo real sin el riesgo de Open Interpreter todavía.

| ID | Prueba | Resultado esperado |
|---|---|---|
| TOY-01 | Invocar una acción no declarada en el manifiesto del toy plugin | Rechazo explícito, `reason: "action_not_declared"` |
| TOY-02 | Cargar el toy plugin contra un perfil que no tiene su capacidad | `load()` devuelve `False`, el plugin no queda en `loaded` |
| TOY-03 | Reiniciar el proceso del núcleo | El plugin se recarga limpio — sin ningún estado de la corrida anterior filtrado |

### Fase 3 — `core-lite`
Primera versión real. Sin interfaz, sin `filesystem_write`, sin
`code_execution` en su perfil.

| ID | Prueba | Resultado esperado |
|---|---|---|
| LITE-01 | Arrancar el proceso y listar puertos/procesos abiertos (`ss -tulnp`) | Cero servidores HTTP/GUI escuchando |
| LITE-02 | Intentar cargar el manifiesto de Open Interpreter contra el perfil `core-lite` | `load()` devuelve `False`, con entrada de auditoría del rechazo |
| LITE-03 | Leer `VERSION_PROFILES["core-lite"]` directamente en el test | No contiene ninguna capacidad de filesystem ni `code_execution` |

### Fase 4 — Plugin Open Interpreter
Las 4 acciones: `run_python`, `write_file`/`read_file`,
`create_presentation`, `search_local_files`. Esta es la fase donde hace
falta pensar como atacante, no solo como quien construye — mismo criterio
que las pruebas adversariales de la auditoría de JARVIS-CORE/LOCAL.

| ID | Prueba adversarial | Resultado esperado |
|---|---|---|
| OI-01 | `run_python` con `os.system("whoami")` o `subprocess` dentro del código | Corre aislado (sin red si `bwrap`/`firejail` está disponible); si no está disponible, se documenta como hallazgo, no se ignora |
| OI-02 | `write_file` con ruta `../../.ssh/id_rsa` | Rechazado antes de tocar el disco |
| OI-03 | `write_file` con nombre `credentials.json` dentro del sandbox permitido | Rechazado por **allowlist de extensiones**, no por blacklist de nombres (repetir el error de `CORE-SEC-07` es la señal de que hay que parar) |
| OI-04 | `create_presentation` con contenido que intenta rutas externas o macros | Solo usa `python-pptx` con datos estructurados — nunca ejecuta código a partir del contenido |
| OI-05 | `search_local_files` con patrón que intenta escapar del `sandbox_root` | Resultados acotados al root, sin excepción |
| OI-06 | `run_python` sin `user_confirmed=True` | Bloqueado igual que cualquier otra capacidad con `requires_confirmation` |
| OI-07 | `run_python` con un script en bucle infinito | Se corta por timeout — confirmar el valor real del timeout, no solo que existe la opción |

---

## Formatos de datos

| Qué | Formato | Dónde vive |
|---|---|---|
| Manifiesto de plugin | JSON, schema fijo (con `schema_version`) | `plugins/<nombre>/manifest.json` |
| Configuración por versión | JSON | `versions/<version>/config.json` |
| Secretos (API keys, tokens) | `.env` (texto plano, permisos 600) — nunca JSON | `.env` en la raíz de cada versión que lo necesite |
| Resultado de `invoke()` | JSON estructurado (`ok`, `reason`, datos) | en memoria, y logueado a `jarvis.db` |
| Registro de dispositivos, auditoría, cola de trabajos | SQLite | `database/jarvis.db` |
| Logs | Texto plano estructurado (timestamp, nivel, módulo, mensaje), rotado por tamaño | `logs/` por versión |

---

## Lenguajes por componente

| Componente | Lenguaje / stack | Motivo |
|---|---|---|
| `core/`, todos los plugins, todas las versiones de servidor/PC | Python 3.13 | Continuidad con todo lo ya construido, mismas librerías (FastAPI, Pydantic, LiteLLM) |
| Dashboard web de `core-full` (fuera de alcance ahora) | HTML/CSS/JS (servido por FastAPI) | Necesita ser alcanzable desde un navegador remoto sin depender de una pantalla física en el servidor |
| Interfaz de `asistente` y `local` (fuera de alcance ahora) | PyQt6 (Python) | Es la interfaz que ya existe y se pidió reutilizar, no reconstruir |
| Base de datos | SQL (SQLite) | Ya se usó así en el diseño de dispositivos/auditoría, sin necesidad de un motor más pesado a esta escala |
| Scripts de despliegue/mitigación (firewall, systemd, etc.) | Bash | Nivel de sistema operativo, no aplica un lenguaje de aplicación |
| `movil` | **Sin decidir** | Fase 9, no urgente |

---

## Próximo paso concreto

Fases 0 a 4 son el alcance de esta ronda — ver los prompts separados
entregados junto con este documento.
