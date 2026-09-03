"""
Plugin Open Interpreter (Fase 4).
Implementa las 4 acciones centrales:
1. run_python (con timeout y aislamiento Bubblewrap bwrap si disponible)
2. write_file / read_file (con validación de sandbox y allowlist de extensiones)
3. create_presentation (generación estructurada con python-pptx)
4. search_local_files (búsqueda acotada al sandbox root)
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.sandbox import is_safe_path, resolve_sandbox_root

DEFAULT_RUN_TIMEOUT = 10.0


def run_python(
    code: str,
    timeout: float = DEFAULT_RUN_TIMEOUT,
    network_isolated: bool = True,
) -> Dict[str, Any]:
    """
    Ejecuta un script Python en un subproceso aislado con timeout.
    Utiliza Bubblewrap (bwrap) para aislamiento de red si está disponible en el SO.
    """
    workspace_root = resolve_sandbox_root().resolve()
    bwrap_path = shutil.which("bwrap")

    if network_isolated:
        if not bwrap_path:
            raise RuntimeError(
                "Aislamiento de red no disponible: 'bwrap' (Bubblewrap) no está instalado en el sistema. "
                "Ejecución de código rechazada por política de seguridad fail-closed."
            )

        venv_root = Path(sys.executable).parent.parent
        base_prefix = Path(sys.base_prefix)

        cmd = [
            bwrap_path,
            "--unshare-net",
            "--ro-bind", "/usr", "/usr",
            "--ro-bind-try", "/lib", "/lib",
            "--ro-bind-try", "/lib64", "/lib64",
            "--ro-bind-try", "/bin", "/bin",
            "--ro-bind-try", "/etc", "/etc",
            "--proc", "/proc",
            "--dev", "/dev",
            "--ro-bind", str(venv_root), str(venv_root),
            "--ro-bind-try", str(base_prefix), str(base_prefix),
            "--bind", str(workspace_root), str(workspace_root),
            sys.executable,
            "-c",
            code,
        ]
        backend = "bwrap"
    else:
        cmd = [sys.executable, "-c", code]
        backend = "subprocess"

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(workspace_root),
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "backend": backend,
            "timeout_seconds": timeout,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "reason": "timeout",
            "error": f"Ejecución cancelada por timeout de {timeout}s",
            "stdout": e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or ""),
            "stderr": e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or ""),
            "backend": backend,
            "timeout_seconds": timeout,
        }


def write_file(
    path: str,
    content: str,
    allowed_extensions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Escribe un archivo de forma segura dentro del sandbox autorizado.
    Valida confinamiento, subdirectorios/archivos sensibles y allowlist de extensiones.
    """
    if not is_safe_path(path, allowed_extensions=allowed_extensions):
        raise PermissionError(
            f"Escritura rechazada por el sandbox: la ruta o extensión '{path}' no está autorizada."
        )

    root = resolve_sandbox_root()
    target = Path(path)
    if not target.is_absolute():
        target = root / target
    resolved_target = target.resolve()

    resolved_target.parent.mkdir(parents=True, exist_ok=True)
    resolved_target.write_text(content, encoding="utf-8")

    return {
        "ok": True,
        "path": str(resolved_target),
        "bytes_written": len(content.encode("utf-8")),
    }


def read_file(
    path: str,
    allowed_extensions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Lee un archivo de forma segura dentro del sandbox autorizado.
    """
    if not is_safe_path(path, allowed_extensions=allowed_extensions):
        raise PermissionError(
            f"Lectura rechazada por el sandbox: la ruta '{path}' no está autorizada."
        )

    root = resolve_sandbox_root()
    target = Path(path)
    if not target.is_absolute():
        target = root / target
    resolved_target = target.resolve()

    if not resolved_target.is_file():
        raise FileNotFoundError(f"Archivo no encontrado: '{resolved_target}'")

    content = resolved_target.read_text(encoding="utf-8")
    return {
        "ok": True,
        "path": str(resolved_target),
        "content": content,
    }


def create_presentation(
    path: str,
    slides: List[Dict[str, Any]],
    title: str = "Presentación",
) -> Dict[str, Any]:
    """
    Crea una presentación PPTX estructurada con python-pptx dentro del sandbox.
    Solo consume estructuras de datos; nunca ejecuta código dinámico a partir del contenido.
    Pasa explícitamente allowed_extensions=['.pptx'].
    """
    # Validación explícita con extensión .pptx
    if not is_safe_path(path, allowed_extensions=[".pptx"]):
        raise PermissionError(
            f"Creación de presentación rechazada: la ruta '{path}' debe terminar en .pptx y ser segura."
        )

    from pptx import Presentation

    prs = Presentation()

    # Diapositiva de portada
    title_slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_slide_layout)
    slide.shapes.title.text = title
    if slide.placeholders and len(slide.placeholders) > 1:
        slide.placeholders[1].text = "Generado automáticamente por JARVIS"

    # Diapositivas de contenido estructurado
    bullet_slide_layout = prs.slide_layouts[1]
    for slide_data in slides:
        slide_title = str(slide_data.get("title", ""))
        bullets = slide_data.get("bullets", [])
        content_text = str(slide_data.get("content", ""))

        s = prs.slides.add_slide(bullet_slide_layout)
        if s.shapes.title:
            s.shapes.title.text = slide_title

        body_shape = s.shapes.placeholders[1]
        tf = body_shape.text_frame
        tf.clear()

        if bullets:
            for idx, bullet in enumerate(bullets):
                p = tf.add_paragraph() if idx > 0 else tf.paragraphs[0]
                p.text = str(bullet)
        elif content_text:
            p = tf.paragraphs[0]
            p.text = content_text

    root = resolve_sandbox_root()
    target = Path(path)
    if not target.is_absolute():
        target = root / target
    resolved_target = target.resolve()

    resolved_target.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(resolved_target))

    return {
        "ok": True,
        "path": str(resolved_target),
        "slides_count": len(slides) + 1,
    }


def search_local_files(
    pattern: str = "*",
    subfolder: str = "",
) -> Dict[str, Any]:
    """
    Busca archivos dentro del sandbox acotado al root autorizado.
    Si el llamador intenta escapar mediante '..' en subfolder o en el patrón,
    la búsqueda permanece estrictamente confinada a sandbox_root.
    """
    root = resolve_sandbox_root().resolve()
    target_dir = root

    if subfolder:
        candidate = (root / subfolder).resolve()
        try:
            candidate.relative_to(root)
            if candidate.is_dir():
                target_dir = candidate
        except ValueError:
            target_dir = root

    clean_pattern = pattern.replace("../", "").replace("..\\", "")
    if not clean_pattern:
        clean_pattern = "*"

    matches: List[str] = []
    # Buscar de forma recursiva si clean_pattern es '*' o incluye subdirectorios
    finder = target_dir.rglob(clean_pattern) if clean_pattern == "*" or "**" in clean_pattern else target_dir.glob(clean_pattern)

    for item in finder:
        if item.is_file():
            if is_safe_path(item, sandbox_root=root):
                try:
                    rel = item.relative_to(root)
                    matches.append(str(rel))
                except ValueError:
                    pass
        elif item.is_dir():
            if is_safe_path(item / "probe.txt", sandbox_root=root):
                try:
                    rel = item.relative_to(root)
                    matches.append(str(rel))
                except ValueError:
                    pass

    return {
        "ok": True,
        "base_directory": str(root),
        "matches": sorted(list(set(matches))),
    }


class Plugin:
    """Clase del plugin Open Interpreter."""

    def run_python(self, code: str, timeout: float = DEFAULT_RUN_TIMEOUT, network_isolated: bool = True) -> Dict[str, Any]:
        return run_python(code=code, timeout=timeout, network_isolated=network_isolated)

    def write_file(self, path: str, content: str, allowed_extensions: Optional[List[str]] = None) -> Dict[str, Any]:
        return write_file(path=path, content=content, allowed_extensions=allowed_extensions)

    def read_file(self, path: str, allowed_extensions: Optional[List[str]] = None) -> Dict[str, Any]:
        return read_file(path=path, allowed_extensions=allowed_extensions)

    def create_presentation(self, path: str, slides: List[Dict[str, Any]], title: str = "Presentación") -> Dict[str, Any]:
        return create_presentation(path=path, slides=slides, title=title)

    def search_local_files(self, pattern: str = "*", subfolder: str = "") -> Dict[str, Any]:
        return search_local_files(pattern=pattern, subfolder=subfolder)
