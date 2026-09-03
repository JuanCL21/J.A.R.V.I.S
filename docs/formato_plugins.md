# Formato y Especificación Técnica de Plugins — JARVIS

Este documento es la especificación técnica definitiva para la creación de plugins compatibles con el núcleo de JARVIS. Cualquier agente o desarrollador puede utilizar esta guía para implementar nuevos plugins sin necesidad de contexto previo sobre el desarrollo del motor.

---

## 1. Estructura de Carpetas de un Plugin

Cada plugin debe residir en su propio subdirectorio dentro de `plugins/<plugin_id>/` con al menos dos archivos obligatorios:

```text
plugins/<plugin_id>/
├── manifest.json       # Manifiesto declarativo con schema y permisos
└── plugin.py           # Código ejecutable con las funciones/clase de las acciones
```

---

## 2. Schema JSON de `manifest.json`

El archivo `manifest.json` declara la identidad, capacidades requeridas y acciones expuestas por el plugin.

### Ejemplo de Manifest:
```json
{
  "schema_version": "1",
  "id": "toy",
  "name": "Toy Plugin",
  "version": "1.0.0",
  "capabilities": [
    "system_info"
  ],
  "actions": [
    {
      "name": "get_time",
      "capability": "system_info",
      "description": "Devuelve la fecha y hora actual del sistema en formato ISO UTC"
    }
  ]
}
```

### Descripción de Campos:
- **`schema_version` (string, OBLIGATORIO)**: Versión del formato del manifiesto. Actualmente solo se soporta `"1"`. Es obligatorio para que el núcleo pueda validar compatibilidad hacia adelante y versionado formal sin heurísticas.
- **`id` (string, OBLIGATORIO)**: Identificador único del plugin en formato `snake_case` (ej. `toy`, `open_interpreter`).
- **`name` (string, opcional)**: Nombre descriptivo legible para humanos.
- **`version` (string, opcional)**: Versión del plugin (ej. `"1.0.0"`).
- **`capabilities` (array de strings, OBLIGATORIO)**: Lista de capacidades del sistema que el plugin necesita para operar. Todas deben pertenecer al catálogo cerrado.
- **`actions` (array de objetos, OBLIGATORIO)**: Lista de acciones que el plugin exporta:
  - `actions[].name` (string): Nombre de la función o método en `plugin.py`.
  - `actions[].capability` (string): Capacidad específica del catálogo requerida para invocar esta acción. Debe estar incluida en `capabilities`.
  - `actions[].description` (string): Descripción técnica de la acción.

---

## 3. Catálogo Cerrado de Capacidades Válidas

El núcleo valida estrictamente las capacidades declaradas. Cualquier capacidad que no figure en este catálogo causará un `ValueError` inmediato al cargar el plugin y evitará su registro.

| Capacidad | `requires_confirmation` | Descripción |
|---|:---:|---|
| `system_info` | `False` | Lectura de métricas básicas del sistema, fecha, hora y estado. |
| `filesystem_read` | `False` | Lectura de archivos dentro del sandbox autorizado. |
| `filesystem_write` | `True` | Escritura, modificación o borrado de archivos dentro del sandbox. |
| `code_execution` | `True` | Ejecución de scripts o código arbitrario en entorno aislado. |
| `notify_user` | `False` | Envío de notificaciones a la interfaz local del usuario. |
| `telegram_send` | `False` | Envío de alertas y mensajes mediante el bot de Telegram. |

---

## 4. Namespacing de Acciones (`plugin_id.action`)

Para prevenir cualquier colisión entre plugins que declaren acciones con el mismo nombre, el motor registra e invoca las acciones exclusivamente bajo el formato:

$$\text{clave de invocación} = \text{plugin\_id}.\text{action\_name}$$

Ejemplos:
- `toy.get_time`
- `open_interpreter.write_file`
- `sensor_a.get_status` vs `sensor_b.get_status`

---

## 5. Sandboxing y Validación de Rutas (`is_safe_path`)

### Resolución de `sandbox_root`
Un plugin **nunca** puede definir su propia raíz arbitraria (ej. pasar `/etc` o `/root`). El núcleo resuelve la raíz del sandbox bajo una jerarquía estricta:
1. **Anulación programática explícita** (`set_default_sandbox_root(path)`).
2. **Variable de entorno** `JARVIS_SANDBOX_ROOT`.
3. **Fallback canónico** `_REPO_ROOT` (calculado a partir de `__file__`, **nunca** de `os.getcwd()`).

### Orden de Validación de `is_safe_path(target_path, sandbox_root, allowed_extensions)`:
1. **Confinamiento de ruta:** Se calcula la ruta canónica absoluta (`.resolve()`) y se valida que pertenezca a `sandbox_root` (sin escapes por `../`).
2. **Protección estructural (`_SENSITIVE_SUBDIRS` y patrones sensibles):** Se verifica por substring y prefijo en el nombre del archivo y en las partes del path que no coincida con `.ssh`, `.aws`, `.gnupg`, `.docker`, `.kube`, `.password-store`, perfiles de navegadores, `.git`, `.env*`, `*credentials*`, `id_rsa*`, etc.
3. **Allowlist de extensiones:**
   - Si el llamador especifica `allowed_extensions` (ej. `[".pptx"]`), se valida contra esa lista.
   - Si `allowed_extensions` es `None`, se aplica automáticamente `DEFAULT_ALLOWED_EXTENSIONS`:
     `{".txt", ".md", ".py", ".pptx", ".csv", ".log", ".png", ".jpg", ".jpeg", ".pdf"}`
   - **Nota crítica:** `DEFAULT_ALLOWED_EXTENSIONS` **NO incluye `.json`**. Si una acción necesita escribir un archivo estructurado `.json`, debe pasar explícitamente `allowed_extensions=[".json"]`.

---

## 6. Modelo de Confirmación de Usuario (`requires_confirmation`)

Las capacidades con `requires_confirmation=True` (`code_execution`, `filesystem_write`, `device_management`) requieren aprobación explícita del usuario:

- La confirmación se cachea **POR CAPACIDAD** para toda la sesión de proceso en memoria (`session_confirmed_capabilities`).
- **Implicación en la práctica:** Confirmar una vez `run_python` con `user_confirmed=True` autoriza la capacidad `code_execution` para todas las invocaciones subsiguientes dentro del mismo proceso sin volver a solicitar confirmación.
- Al reiniciar el proceso (o invocar `dispatcher.reset_session_confirmations()`), la caché se vacía y se exigirá nuevamente una confirmación explícita.

---

## 7. Formato de Respuesta Estructurado de `invoke()`

Cualquier llamada a `dispatcher.invoke()` retorna un diccionario estructurado:

### Invocación Exitosa:
```json
{
  "ok": true,
  "result": { ... },
  "action": "open_interpreter.write_file"
}
```

### Invocación Rechazada / Error:
```json
{
  "ok": false,
  "reason": "<código_de_razón>",
  "action": "open_interpreter.run_python"
}
```

### Lista Completa de Razones de Error (`reason`):
- `"action_not_declared"`: La acción solicitada no existe o no fue declarada en el manifiesto.
- `"capability_denied"`: La capacidad requerida por la acción no está autorizada en el perfil de versión activo (ej. `filesystem_write` en `core_lite`).
- `"needs_confirmation"`: La acción requiere confirmación del usuario y no fue confirmada (`user_confirmed=False`).
- `"rate_limit_exceeded"`: El hook de rate limit configurado bloqueó la llamada.
- `"execution_error"`: El código de la acción en `plugin.py` lanzó una excepción no controlada.

---

## 8. Ejemplo Completo y Funcional: Plugin `toy`

### `plugins/toy/manifest.json`
```json
{
  "schema_version": "1",
  "id": "toy",
  "name": "Toy Plugin",
  "version": "1.0.0",
  "capabilities": [
    "system_info"
  ],
  "actions": [
    {
      "name": "get_time",
      "capability": "system_info",
      "description": "Devuelve la fecha y hora actual del sistema en formato ISO UTC"
    }
  ]
}
```

### `plugins/toy/plugin.py`
```python
"""
Plugin de juguete (Fase 2).
Implementa la acción 'get_time' para devolver la hora del sistema.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def get_time(format_str: Optional[str] = None) -> Dict[str, Any]:
    """Devuelve la fecha y hora actual del sistema en UTC."""
    now = datetime.now(timezone.utc)
    if format_str:
        formatted = now.strftime(format_str)
    else:
        formatted = now.isoformat()

    return {
        "iso": now.isoformat(),
        "timestamp": now.timestamp(),
        "formatted": formatted,
    }


class Plugin:
    """Clase del plugin Toy."""

    def get_time(self, format_str: Optional[str] = None) -> Dict[str, Any]:
        return get_time(format_str=format_str)
```

---

## 9. Errores Comunes a Evitar

1. **No comparar nombres sensibles por igualdad exacta:**
   - ❌ *Incorrecto:* `filename == "credentials.json"`
   - ✔️ *Correcto:* Usar coincidencia por substring (`"credentials" in filename.lower()`), de modo que `credentials_prod.json`, `my_credentials.txt` y `.env.production` queden bloqueados.
2. **No derivar `sandbox_root` de `os.getcwd()`:**
   - ❌ *Incorrecto:* `DEFAULT_ROOT = Path(os.getcwd())` (cambiar de directorio de trabajo altera el sandbox).
   - ✔️ *Correcto:* Usar `JARVIS_SANDBOX_ROOT` o `Path(__file__).resolve().parent.parent`.
3. **No dejar conexiones SQLite abiertas en `audit_log`:**
   - ❌ *Incorrecto:* Usar `with conn:` creyendo que cierra la conexión (solo maneja transacciones).
   - ✔️ *Correcto:* Usar `try ... finally: conn.close()` para garantizar la liberación de descriptores de archivo.
4. **No olvidar que `.json` no está en la allowlist por defecto:**
   - Si su plugin escribe archivos JSON en el sandbox, debe pasar explícitamente `allowed_extensions=[".json"]`.
5. **No asumir aislamiento de sesión por acción:**
   - Confirmar una acción con capacidad de riesgo (ej. `run_python`) habilita dicha capacidad (`code_execution`) para el resto de la sesión de proceso.
6. **Requisito de sistema operativo para `code_execution` (`bwrap` obligatorio, fail-closed):**
   - Para ejecutar código Python con aislamiento de red en Linux, el binario del sistema `bwrap` (paquete `bubblewrap`) es un requisito de sistema obligatorio.
   - Si `bwrap` no está instalado en el sistema operativo, `run_python` opera bajo política **fail-closed**: rechaza inmediatamente la ejecución lanzando un `RuntimeError` y registrando un error en la auditoría, impidiendo cualquier ejecución degradada sin aislamiento.
