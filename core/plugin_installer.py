"""
Instalador de plugins para JARVIS (Subfase B).
Implementa dos flujos de instalación con aislamiento estricto y auditoría:
1. B.1 - Catálogo Curado (para usuario final):
   Instala únicamente mediante plugin_id, leyendo commit_hash y source_url del catálogo curado.
   Registra primero en status='no_verificado' y promueve inmediatamente a 'curado' PRESERVANDO
   el reviewed_by y reviewed_at ORIGINALES de la auditoría histórica previa.
   La interfaz de usuario final NO expone parámetros de URL ni commit.
2. B.2 - Modo Avanzado (instalación por URL):
   Resuelve el hash de commit concreto (40 hex) de la referencia dada (HEAD, rama, tag),
   registrándolo en status='no_verificado' sin excepción.
3. B.3 - Integración con sandbox y dispatcher común.

SEGURIDAD Y SANITIZACIÓN:
- Rechazo explícito (fail-closed) de source_url, ref y plugin_id que comiencen con '-' para prevenir
  inyección de argumentos hacia binarios de git o almacenamiento.
- Uso del separador '--' en git ls-remote y '--end-of-options' en git rev-parse como defensa en profundidad.

CATÁLOGO CURADO DE DESARROLLO:
- El archivo database/curated_catalog.json contiene el flag 'is_placeholder_data: true'.
  Sus entradas (toy, open_interpreter, system_monitor) utilizan commit hashes sintéticos y URLs
  de prueba; son únicamente de ejemplo de desarrollo y DEBEN ser reemplazadas por revisiones reales
  de auditoría humana antes de cualquier despliegue en producción.
"""

import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Dict, List, Optional, Union

from .plugin_registry import PluginRegistry, _REPO_ROOT

# Ruta por defecto del catálogo curado independiente de os.getcwd()
_DEFAULT_CATALOG_PATH = _REPO_ROOT / "database" / "curated_catalog.json"

# TODO (PENDIENTE 1): Control de acceso a quién puede ejecutar install_from_url (se resuelve en Fase 5 con autenticación).
# TODO (PENDIENTE 2): Estado de revocación/bloqueo para un plugin YA curado que después se descubre problemático.
# TODO (PENDIENTE 3): Criterio que gatilla que una cuenta vea el modo Avanzado, más allá de estar oculto por defecto.


def resolve_catalog_path(catalog_path: Optional[Union[str, Path]] = None) -> Path:
    """
    Resuelve la ruta absoluta del archivo de catálogo curado:
    1. Anulación explícita vía parámetro catalog_path.
    2. Variable de entorno JARVIS_CURATED_CATALOG_PATH.
    3. Raíz canónica del proyecto (_REPO_ROOT / database / curated_catalog.json).
    NUNCA depende de os.getcwd().
    """
    if catalog_path is not None:
        return Path(catalog_path).resolve()

    env_path = os.environ.get("JARVIS_CURATED_CATALOG_PATH")
    if env_path:
        return Path(env_path).resolve()

    return _DEFAULT_CATALOG_PATH.resolve()


def load_curated_catalog(catalog_path: Optional[Union[str, Path]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Carga el catálogo curado desde el archivo JSON y lo devuelve indexado por plugin_id.
    Nota: Verifica y parsea el archivo database/curated_catalog.json (el cual incluye
    el flag 'is_placeholder_data: true' para indicar entradas sintéticas de desarrollo).
    """
    target_path = resolve_catalog_path(catalog_path)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"No se encontró el catálogo curado en la ruta especificada: {target_path}"
        )

    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    plugins_list = data.get("plugins", [])
    catalog_by_id: Dict[str, Dict[str, Any]] = {}

    for item in plugins_list:
        p_id = item.get("plugin_id")
        if not p_id:
            continue
        required_fields = [
            "commit_hash",
            "source_url",
            "name",
            "description",
            "icon",
            "reviewed_by",
            "reviewed_at",
        ]
        for req in required_fields:
            if req not in item:
                raise ValueError(
                    f"Entrada inválida en catálogo curado para '{p_id}': falta campo '{req}'."
                )
        catalog_by_id[p_id] = item

    return catalog_by_id


def resolve_git_ref(source_url: str, ref: str = "HEAD") -> str:
    """
    Resuelve el hash de commit concreto (40 caracteres hexadecimales) para una ref dada
    (HEAD, rama, tag o hash directo) en el repositorio remoto o local especificado por source_url.
    NUNCA devuelve ni persiste la referencia mutable.

    REGLAS DE SEGURIDAD (ANTI-INYECCIÓN DE ARGUMENTOS):
    1. Rechazo explícito (fail-closed) ANTES de invocar procesos si source_url o ref empiezan con '-'.
    2. Defensa en profundidad mediante '--' en git ls-remote y '--end-of-options' en git rev-parse.
    """
    # 1. Validación estricta y fail-closed de source_url
    if not source_url or not isinstance(source_url, str) or source_url.strip().startswith("-"):
        raise ValueError(
            f"source_url inválido: no puede estar vacío ni comenzar con '-' ('{source_url}')."
        )

    # 2. Validación estricta y fail-closed de ref
    clean_ref = ref.strip() if isinstance(ref, str) else ""
    if not clean_ref or clean_ref.startswith("-"):
        raise ValueError(
            f"ref inválido: no puede estar vacío ni comenzar con '-' ('{ref}')."
        )

    # Si ya es un hash SHA-1 de 40 caracteres hexadecimales, es directamente el commit
    if re.match(r"^[0-9a-fA-F]{40}$", clean_ref):
        return clean_ref.lower()

    # Si es un directorio local con repositorio git, resolver con git rev-parse localmente
    # usando --verify y --end-of-options como terminador de opciones estándar de git
    local_path = Path(source_url)
    if local_path.is_dir() and ((local_path / ".git").exists() or (local_path / "HEAD").exists()):
        for target in [f"{clean_ref}^{{commit}}", clean_ref]:
            cmd = ["git", "-C", str(local_path), "rev-parse", "--verify", "--end-of-options", target]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10.0,
                check=False,
            )
            if proc.returncode == 0:
                commit_out = proc.stdout.strip().lower()
                if re.match(r"^[0-9a-fA-F]{40}$", commit_out):
                    return commit_out

    # Resolver mediante git ls-remote sin necesidad de clonar todo el árbol
    # Separador '--' incluido obligatoriamente antes de source_url (defensa en profundidad)
    cmd = ["git", "ls-remote", "--", source_url, clean_ref]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20.0,
            check=False,
        )
    except Exception as e:
        raise RuntimeError(
            f"Error al ejecutar git ls-remote para '{source_url}': {str(e)}"
        ) from e

    output = proc.stdout.strip() if proc.returncode == 0 else ""
    if not output:
        # Intentar buscar en refs/heads/ y refs/tags/ explícitamente con '--'
        cmd_fallback = [
            "git",
            "ls-remote",
            "--",
            source_url,
            f"refs/heads/{clean_ref}",
            f"refs/tags/{clean_ref}",
            f"refs/tags/{clean_ref}^{{}}",
        ]
        try:
            proc_fallback = subprocess.run(
                cmd_fallback,
                capture_output=True,
                text=True,
                timeout=20.0,
                check=False,
            )
            if proc_fallback.returncode == 0:
                output = proc_fallback.stdout.strip()
        except Exception:
            pass

    if not output:
        raise ValueError(
            f"No se pudo resolver la referencia '{clean_ref}' en el repositorio '{source_url}'."
        )

    # Parsear salida: pares <commit_hash>\t<ref_name>
    # Si hay una referencia desreferenciada ^{} (tag anotado), preferir ese commit
    candidate_hash: Optional[str] = None
    dereferenced_hash: Optional[str] = None

    for line in output.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            sha, ref_name = parts[0], parts[1]
            if re.match(r"^[0-9a-fA-F]{40}$", sha):
                if ref_name.endswith("^{}"):
                    dereferenced_hash = sha.lower()
                elif candidate_hash is None:
                    candidate_hash = sha.lower()

    resolved = dereferenced_hash or candidate_hash
    if not resolved:
        raise ValueError(
            f"Respuesta inválida de git ls-remote para '{clean_ref}' en '{source_url}': {output}"
        )

    return resolved


class PluginInstaller:
    """
    Controlador de instalación de plugins desde el catálogo curado o mediante modo Avanzado (URL).
    """

    def __init__(
        self,
        registry: Optional[PluginRegistry] = None,
        catalog_path: Optional[Union[str, Path]] = None,
    ):
        self.registry = registry or PluginRegistry()
        self.catalog_path = resolve_catalog_path(catalog_path)

    def install_from_catalog(self, plugin_id: str) -> Dict[str, Any]:
        """
        Instala un plugin del catálogo curado.
        La UI de cara al usuario final SOLO envía plugin_id; commit_hash y source_url viven encapsulados.
        1. Obtiene la entrada del catálogo.
        2. Registra en plugin_registry (lo deja en status='no_verificado').
        3. Promueve inmediatamente a 'curado' con el reviewed_by y reviewed_at ORIGINALES del catálogo.
        """
        # NOTA DE AUDITORÍA: plugin_id no es validado contra prefijos '-' en plugin_registry.py (solo se inserta
        # parametrizado en SQLite), por lo que se valida explícitamente aquí en la capa de instalación (fail-closed).
        if not plugin_id or not isinstance(plugin_id, str) or plugin_id.strip().startswith("-"):
            raise ValueError(
                f"plugin_id inválido: no puede estar vacío ni comenzar con '-' ('{plugin_id}')."
            )

        catalog = load_curated_catalog(self.catalog_path)
        if plugin_id not in catalog:
            raise KeyError(
                f"El plugin '{plugin_id}' no existe en el catálogo curado."
            )

        entry = catalog[plugin_id]
        commit_hash = entry["commit_hash"]
        source_url = entry["source_url"]
        orig_reviewed_by = entry["reviewed_by"]
        orig_reviewed_at = entry["reviewed_at"]

        # 1. Registrar (fuerza siempre status='no_verificado')
        self.registry.register_plugin(
            plugin_id=plugin_id,
            active_commit_hash=commit_hash,
            source_url=source_url,
        )

        # 2. Promover con los datos de auditoría histórica ORIGINALES del catálogo
        promoted = self.registry.promote_to_curated(
            plugin_id=plugin_id,
            reviewed_by=orig_reviewed_by,
            reviewed_at=orig_reviewed_at,
        )
        if not promoted:
            raise RuntimeError(
                f"Fallo al promover a 'curado' el plugin '{plugin_id}' desde el catálogo."
            )

        installed = self.registry.get_plugin(plugin_id)
        if not installed:
            raise RuntimeError(f"Error al recuperar plugin instalado '{plugin_id}'.")
        return installed

    def install_from_url(
        self,
        source_url: str,
        plugin_id: str,
        ref: str = "HEAD",
    ) -> Dict[str, Any]:
        """
        Modo Avanzado: instala un plugin a partir de su URL de repositorio Git.
        1. Resuelve la referencia (rama, tag, HEAD) a un hash de commit concreto.
        2. Registra en plugin_registry con status='no_verificado'.
        NUNCA persiste una referencia mutable.
        """
        # TODO (PENDIENTE 1): Control de acceso por rol/cuenta para modo Avanzado.

        # NOTA DE AUDITORÍA: plugin_id no es validado contra prefijos '-' en plugin_registry.py (solo se inserta
        # parametrizado en SQLite), por lo que se valida explícitamente aquí en la capa de instalación (fail-closed).
        if not plugin_id or not isinstance(plugin_id, str) or plugin_id.strip().startswith("-"):
            raise ValueError(
                f"plugin_id inválido: no puede estar vacío ni comenzar con '-' ('{plugin_id}')."
            )

        # resolve_git_ref valida fail-closed source_url y ref antes de cualquier subproceso
        commit_hash = resolve_git_ref(source_url=source_url, ref=ref)

        self.registry.register_plugin(
            plugin_id=plugin_id,
            active_commit_hash=commit_hash,
            source_url=source_url,
        )

        installed = self.registry.get_plugin(plugin_id)
        if not installed:
            raise RuntimeError(f"Error al recuperar plugin instalado '{plugin_id}'.")
        return installed


# ---------------------------------------------------------------------------
# Funciones públicas de nivel de módulo para la UI y la API de JARVIS
# ---------------------------------------------------------------------------

def install_from_catalog(plugin_id: str) -> Dict[str, Any]:
    """
    Función de cara al usuario final para instalación desde el catálogo curado.
    REGLA DE SEGURIDAD ESTRICTA: SOLO recibe plugin_id. No expone parámetros opcionales,
    valores por defecto ni **kwargs para commit_hash o source_url.
    """
    installer = PluginInstaller()
    return installer.install_from_catalog(plugin_id)


def install_from_url(
    source_url: str,
    plugin_id: str,
    ref: str = "HEAD",
) -> Dict[str, Any]:
    """
    Función para modo Avanzado: instala desde URL git resolviendo commit concreto.
    Queda siempre registrado en status='no_verificado'.
    """
    installer = PluginInstaller()
    return installer.install_from_url(source_url=source_url, plugin_id=plugin_id, ref=ref)
