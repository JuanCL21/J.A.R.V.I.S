"""
Dispatcher central de JARVIS — Único punto de entrada para invocar acciones.
Revisión de auditor:
- Acciones invocadas como plugin_id.action.
- Validación de capacidades contra el perfil de versión activo (capability_denied).
- Confirmación por sesión de proceso cacheada en memoria (needs_confirmation).
- Hook extensible para rate limiting por plugin/minuto (diferido a Fase 7).
- Auditoría obligatoria en SQLite para TODO invoke() (permitido o denegado).
- Formato de respuesta estructurado: {"ok": bool, "reason": str, ...}.
"""

from typing import Any, Callable, Dict, Optional, Set

from .audit_log import AuditLogger, default_audit_logger
from .capability_catalog import capability_requires_confirmation
from .plugin_loader import ActionDefinition, PluginLoader
from .version_profiles import is_capability_allowed


class Dispatcher:
    def __init__(
        self,
        plugin_loader: PluginLoader,
        version_profile: str = "core_lite",
        audit_logger: Optional[AuditLogger] = None,
        rate_limit_hook: Optional[Callable[[str, str], bool]] = None,
    ):
        self.plugin_loader = plugin_loader
        self.version_profile = version_profile
        self.audit_logger = audit_logger or default_audit_logger
        self.rate_limit_hook = rate_limit_hook

        # Caché de confirmaciones de usuario por sesión de proceso en memoria (Revisión de auditor #6)
        self.session_confirmed_capabilities: Set[str] = set()

    def reset_session_confirmations(self) -> None:
        """Reinicia la caché de confirmaciones de sesión (útil en reinicios o pruebas)."""
        self.session_confirmed_capabilities.clear()

    def set_rate_limit_hook(self, hook: Optional[Callable[[str, str], bool]]) -> None:
        """Configura el hook de rate limiting (Revisión de auditor #4)."""
        self.rate_limit_hook = hook

    def invoke(
        self,
        action_full_name: str,
        params: Optional[Dict[str, Any]] = None,
        user_confirmed: bool = False,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Punto único de entrada para invocar cualquier acción de plugin.
        Retorna siempre un diccionario estructurado {"ok": bool, ...}.
        """
        params = params or {}

        # 1. Separar plugin_id y action_name (Formato: plugin_id.action_name)
        if "." not in action_full_name:
            plugin_id = "unknown"
            action_name = action_full_name
        else:
            plugin_id, action_name = action_full_name.split(".", 1)

        # 2. Hook de Rate Limiting si está configurado (Revisión de auditor #4)
        if self.rate_limit_hook is not None:
            if not self.rate_limit_hook(plugin_id, action_name):
                self.audit_logger.log_invocation(
                    plugin_id=plugin_id,
                    action=action_name,
                    capability=None,
                    allowed=False,
                    result_status="denied",
                    reason="rate_limit_exceeded",
                    details={"params": params},
                )
                return {
                    "ok": False,
                    "reason": "rate_limit_exceeded",
                    "plugin_id": plugin_id,
                    "action": action_name,
                }

        # 3. Comprobar si la acción existe en el registro de plugins
        action_def: Optional[ActionDefinition] = self.plugin_loader.registered_actions.get(
            action_full_name
        )
        if not action_def:
            self.audit_logger.log_invocation(
                plugin_id=plugin_id,
                action=action_name,
                capability=None,
                allowed=False,
                result_status="denied",
                reason="action_not_declared",
                details={"params": params},
            )
            return {
                "ok": False,
                "reason": "action_not_declared",
                "action": action_full_name,
            }

        capability = action_def.capability

        # 4. Comprobar si la capacidad está autorizada en el perfil de versión (NUC-02)
        if not is_capability_allowed(self.version_profile, capability):
            self.audit_logger.log_invocation(
                plugin_id=plugin_id,
                action=action_name,
                capability=capability,
                allowed=False,
                result_status="denied",
                reason="capability_denied",
                details={"profile": self.version_profile, "params": params},
            )
            return {
                "ok": False,
                "reason": "capability_denied",
                "capability": capability,
                "profile": self.version_profile,
            }

        # 5. Comprobar si requiere confirmación del usuario (Auditor #6, NUC-03)
        if capability_requires_confirmation(capability):
            # ¿Ya fue confirmada en esta sesión de proceso?
            if capability not in self.session_confirmed_capabilities:
                if user_confirmed:
                    # El usuario confirma en esta llamada: cachear para el resto de la sesión
                    self.session_confirmed_capabilities.add(capability)
                else:
                    self.audit_logger.log_invocation(
                        plugin_id=plugin_id,
                        action=action_name,
                        capability=capability,
                        allowed=False,
                        result_status="needs_confirmation",
                        reason="needs_confirmation",
                        details={"params": params},
                    )
                    return {
                        "ok": False,
                        "reason": "needs_confirmation",
                        "capability": capability,
                    }

        # 6. Ejecución del handler
        handler = action_def.handler
        if handler is None:
            # Acción declarada sin handler ejecutable
            self.audit_logger.log_invocation(
                plugin_id=plugin_id,
                action=action_name,
                capability=capability,
                allowed=True,
                result_status="success",
                reason="no_handler_defined",
                details={"params": params},
            )
            return {
                "ok": True,
                "result": None,
                "action": action_full_name,
            }

        try:
            # Invocar handler
            try:
                # Intentar pasar como kwargs o como único argumento params
                result = handler(**params)
            except TypeError:
                result = handler(params)

            # 7. Registro de auditoría exitoso (NUC-05)
            self.audit_logger.log_invocation(
                plugin_id=plugin_id,
                action=action_name,
                capability=capability,
                allowed=True,
                result_status="success",
                details={"params": params},
            )
            return {
                "ok": True,
                "result": result,
                "action": action_full_name,
            }

        except Exception as e:
            # Registro de auditoría en error de ejecución
            self.audit_logger.log_invocation(
                plugin_id=plugin_id,
                action=action_name,
                capability=capability,
                allowed=True,
                result_status="error",
                reason="execution_error",
                details={"error": str(e), "params": params},
            )
            return {
                "ok": False,
                "reason": "execution_error",
                "error": str(e),
                "action": action_full_name,
            }
