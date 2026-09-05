"""
Pruebas para la Subfase B: Instalación de plugins (Catálogo Curado y Modo Avanzado).
Cubre:
1. TEST REQUERIDO 1: install_from_catalog preserva reviewed_at y reviewed_by EXACTAMENTE
   iguales a los del catálogo histórico original (comparación de igualdad estricta, no solo formato).
2. TEST REQUERIDO 2: install_from_url resuelve un hash de commit concreto (40 caracteres hexadecimales)
   sin importar si se solicita HEAD, rama o tag; nunca guarda referencias mutables.
3. TEST REQUERIDO 3: La función pública install_from_catalog de cara a la UI solo recibe plugin_id.
   Cualquier intento de pasar source_url, commit_hash o **kwargs falla de inmediato.
4. TEST REQUERIDO 4: Los plugins instalados por modo Avanzado quedan siempre con status='no_verificado',
   sin metadatos de auditoría (None), sin importar los parámetros pasados.
5. Carga y validación del archivo curated_catalog.json (incluyendo flag is_placeholder_data: true).
6. TEST ADVERSARIAL 1: test_resolve_git_ref_adversarial_rejects_source_url_starting_with_dash
   (rechazo fail-closed sin disparar subprocess).
7. TEST ADVERSARIAL 2: test_resolve_git_ref_adversarial_rejects_ref_starting_with_dash
   (rechazo fail-closed sin disparar subprocess).
8. TEST ADVERSARIAL 3: test_install_from_url_adversarial_propagates_rejection
   (sin efectos secundarios en base de datos tras rechazo).
"""

import inspect
import json
import os
from pathlib import Path
import re
import subprocess
import pytest

from core.plugin_installer import (
    PluginInstaller,
    install_from_catalog,
    install_from_url,
    load_curated_catalog,
    resolve_git_ref,
    resolve_catalog_path,
    CuratedPluginInfo,
    InstallResult,
    list_curated_plugins,
    validate_source_url,
)
from core.plugin_registry import PluginRegistry



@pytest.fixture
def test_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Configura base de datos y catálogo aislados para pruebas de instalación."""
    db_file = tmp_path / "test_installer.db"
    catalog_file = tmp_path / "test_curated_catalog.json"

    catalog_data = {
        "schema_version": "1",
        "catalog_updated_at": "2026-08-30T00:00:00Z",
        "is_placeholder_data": True,
        "plugins": [
            {
                "plugin_id": "toy",
                "name": "Toy Plugin",
                "description": "Plugin de diagnóstico básico",
                "icon": "clock-outline",
                "source_url": "https://github.com/jarvis-plugins/toy-plugin.git",
                "commit_hash": "e2a4b6c8d0e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9",
                "reviewed_by": "auditor_seguridad_principal",
                "reviewed_at": "2026-08-15T14:30:00Z",
            },
            {
                "plugin_id": "open_interpreter",
                "name": "Open Interpreter",
                "description": "Ejecución de código aislado",
                "icon": "code-braces",
                "source_url": "https://github.com/jarvis-plugins/open-interpreter.git",
                "commit_hash": "f1d3b5a7c9e1f3a5b7c9d1e3f5a7b9c1d3e5f7b0",
                "reviewed_by": "comite_seguridad_fase4",
                "reviewed_at": "2026-08-20T18:00:00Z",
            },
        ],
    }
    with open(catalog_file, "w", encoding="utf-8") as f:
        json.dump(catalog_data, f, indent=2)

    monkeypatch.setenv("JARVIS_DB_PATH", str(db_file))
    monkeypatch.setenv("JARVIS_CURATED_CATALOG_PATH", str(catalog_file))

    registry = PluginRegistry(db_path=db_file)
    installer = PluginInstaller(registry=registry, catalog_path=catalog_file)

    return {
        "db_file": db_file,
        "catalog_file": catalog_file,
        "registry": registry,
        "installer": installer,
        "catalog_data": catalog_data,
    }


@pytest.fixture
def local_git_repo(tmp_path: Path) -> Path:
    """Crea un repositorio Git local real con ramas y tags para verificar resolución de commits."""
    repo_dir = tmp_path / "mock_git_remote_repo"
    repo_dir.mkdir()

    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@jarvis.local"], cwd=repo_dir, check=True, capture_output=True)

    manifest_file = repo_dir / "manifest.json"
    manifest_file.write_text('{"schema_version": "1", "id": "local_plugin"}')

    subprocess.run(["git", "add", "manifest.json"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)

    # Renombrar rama a main y crear tag
    subprocess.run(["git", "branch", "-M", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "tag", "-a", "v1.0.0", "-m", "Release v1.0.0"], cwd=repo_dir, check=True, capture_output=True)

    return repo_dir


# ============================================================================
# TEST 1: install_from_catalog preserva reviewed_at del catálogo histórico
# ============================================================================
def test_install_from_catalog_preserves_original_reviewed_at(test_env):
    """
    TEST REQUERIDO 1:
    Verifica que reviewed_at en el registro final es EXACTAMENTE el del catálogo,
    no un timestamp generado durante el test (comparación de igualdad exacta contra el valor fijo).
    """
    installer: PluginInstaller = test_env["installer"]
    registry: PluginRegistry = test_env["registry"]

    fixed_historical_date = "2026-08-15T14:30:00Z"
    fixed_historical_auditor = "auditor_seguridad_principal"
    fixed_commit_hash = "e2a4b6c8d0e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9"

    # Instalar mediante catálogo curado
    result = installer.install_from_catalog("toy")
    assert result["plugin_id"] == "toy"

    # Consultar registro final en la base de datos
    stored = registry.get_plugin("toy")
    assert stored is not None
    assert stored["active_commit_hash"] == fixed_commit_hash
    assert stored["status"] == "curado"

    # REGLA CRÍTICA DE AUDITORÍA: El reviewed_at DEBE coincidir de forma idéntica
    assert stored["reviewed_at"] == fixed_historical_date, (
        f"reviewed_at ({stored['reviewed_at']}) debe ser idéntico al del catálogo ({fixed_historical_date})"
    )
    assert stored["reviewed_by"] == fixed_historical_auditor, (
        f"reviewed_by ({stored['reviewed_by']}) debe ser idéntico al del catálogo ({fixed_historical_auditor})"
    )

    # promoted_at sí se genera al momento de la instalación y es distinto de la fecha de revisión histórica
    assert stored["promoted_at"] is not None
    assert stored["promoted_at"] != fixed_historical_date


# ============================================================================
# TEST 2: install_from_url resuelve commit concreto, nunca guarda ref mutable
# ============================================================================
def test_install_from_url_resolves_concrete_commit_hash_never_mutable_ref(test_env, local_git_repo):
    """
    TEST REQUERIDO 2:
    Verifica que sin importar qué ref se pida (rama, tag, HEAD), el valor guardado
    en active_commit_hash es un hash de commit concreto (40 hex), nunca el string
    de la rama o tag original.
    """
    installer: PluginInstaller = test_env["installer"]
    registry: PluginRegistry = test_env["registry"]
    repo_url = str(local_git_repo)

    # Obtener el hash real del HEAD del repositorio
    expected_sha = subprocess.run(
        ["git", "-C", repo_url, "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()

    assert len(expected_sha) == 40
    assert re.match(r"^[0-9a-f]{40}$", expected_sha)

    # 1. Probar instalación especificando ref="HEAD"
    installer.install_from_url(source_url=repo_url, plugin_id="p_head", ref="HEAD")
    stored_head = registry.get_plugin("p_head")
    assert stored_head is not None
    assert stored_head["active_commit_hash"] == expected_sha
    assert stored_head["active_commit_hash"] != "HEAD"

    # 2. Probar instalación especificando ref="main" (rama mutable)
    installer.install_from_url(source_url=repo_url, plugin_id="p_branch", ref="main")
    stored_branch = registry.get_plugin("p_branch")
    assert stored_branch is not None
    assert stored_branch["active_commit_hash"] == expected_sha
    assert stored_branch["active_commit_hash"] != "main"

    # 3. Probar instalación especificando ref="v1.0.0" (tag)
    installer.install_from_url(source_url=repo_url, plugin_id="p_tag", ref="v1.0.0")
    stored_tag = registry.get_plugin("p_tag")
    assert stored_tag is not None
    assert stored_tag["active_commit_hash"] == expected_sha
    assert stored_tag["active_commit_hash"] != "v1.0.0"


# ============================================================================
# TEST 3: install_from_catalog de cara a la UI solo recibe plugin_id
# ============================================================================
def test_install_from_catalog_signature_strictly_accepts_only_plugin_id(test_env):
    """
    TEST REQUERIDO 3:
    Verifica que la función de cara al usuario final para catálogo (install_from_catalog)
    SOLO recibe plugin_id. No admite source_url, commit_hash, ni **kwargs arbitrarios.
    """
    # 1. Inspección estricta de signatura mediante inspect
    sig = inspect.signature(install_from_catalog)
    params = list(sig.parameters.values())

    assert len(params) == 1, (
        f"install_from_catalog debe recibir exactamente 1 parámetro, tiene {len(params)}: {params}"
    )
    assert params[0].name == "plugin_id", "El único parámetro debe llamarse 'plugin_id'"
    assert params[0].kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.POSITIONAL_ONLY,
    )

    # Verificar que NO tenga var_keyword (**kwargs)
    for p in params:
        assert p.kind != inspect.Parameter.VAR_KEYWORD, "No se permiten **kwargs en install_from_catalog"
        assert p.default == inspect.Parameter.empty, "plugin_id no debe tener valor por defecto"

    # 2. Intentos de inyectar source_url o commit_hash deben fallar con TypeError
    with pytest.raises(TypeError):
        install_from_catalog("toy", source_url="https://malicious.com/repo.git")  # type: ignore

    with pytest.raises(TypeError):
        install_from_catalog("toy", commit_hash="1111222233334444555566667777888899990000")  # type: ignore

    with pytest.raises(TypeError):
        install_from_catalog("toy", status="curado")  # type: ignore

    # 3. Invocación legítima exitosa
    res = install_from_catalog("toy")
    assert isinstance(res, InstallResult)
    assert res.success is True
    assert res.plugin_id == "toy"
    assert "instaló correctamente" in res.message.lower()

    # REGLA DE SEGURIDAD ESTRICTA: La UI no recibe commit_hash, source_url, reviewed_by ni status
    assert not hasattr(res, "status")
    assert not hasattr(res, "commit_hash")
    assert not hasattr(res, "source_url")
    assert not hasattr(res, "reviewed_by")

    # En el backend, la base de datos sí fue actualizada a status='curado'
    installed = test_env["registry"].get_plugin("toy")
    assert installed is not None
    assert installed["status"] == "curado"



# ============================================================================
# TEST 4: Modo Avanzado (install_from_url) queda SIEMPRE en status='no_verificado'
# ============================================================================
def test_install_from_url_always_leaves_status_no_verificado(test_env, local_git_repo):
    """
    TEST REQUERIDO 4:
    Un plugin instalado por modo Avanzado queda con status='no_verificado'
    sin importar qué parámetros se le pasen a install_from_url.
    """
    installer: PluginInstaller = test_env["installer"]
    registry: PluginRegistry = test_env["registry"]
    repo_url = str(local_git_repo)

    res = installer.install_from_url(source_url=repo_url, plugin_id="adv_plugin", ref="HEAD")
    assert res["plugin_id"] == "adv_plugin"

    stored = registry.get_plugin("adv_plugin")
    assert stored is not None
    assert stored["status"] == "no_verificado", (
        "Cualquier instalación por URL DEBE quedar en status 'no_verificado'"
    )
    assert stored["reviewed_by"] is None, "reviewed_by debe ser None"
    assert stored["reviewed_at"] is None, "reviewed_at debe ser None"
    assert stored["promoted_at"] is None, "promoted_at debe ser None"
    assert registry.is_curated("adv_plugin") is False


# ============================================================================
# TEST 5: Carga y validación del archivo de catálogo real (curated_catalog.json)
# ============================================================================
def test_curated_catalog_json_file_valid_schema():
    """Verifica que el archivo real database/curated_catalog.json contenga las entradas requeridas y el flag placeholder."""
    catalog_path = resolve_catalog_path()
    with open(catalog_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    assert raw_data.get("is_placeholder_data") is True, (
        "database/curated_catalog.json debe contener 'is_placeholder_data': true"
    )

    catalog = load_curated_catalog()
    assert "toy" in catalog
    assert "open_interpreter" in catalog
    assert "system_monitor" in catalog

    for p_id, entry in catalog.items():
        assert entry["plugin_id"] == p_id
        assert len(entry["commit_hash"]) == 40
        assert entry["source_url"].startswith("http")
        assert entry["name"]
        assert entry["reviewed_by"]
        assert entry["reviewed_at"]


# ============================================================================
# TESTS ADVERSARIALES: Protección contra inyección de argumentos hacia git
# ============================================================================

def test_resolve_git_ref_adversarial_rejects_source_url_starting_with_dash(monkeypatch: pytest.MonkeyPatch):
    """
    TEST ADVERSARIAL 1:
    Llamar a resolve_git_ref con un source_url que empiece con '-' y verificar que levanta
    ValueError ANTES de ejecutar ningún subprocess.run (garantizado con mock que explota si se llama).
    """
    def mock_subprocess_run(*args, **kwargs):
        raise AssertionError(
            "VULNERABILIDAD DETECTADA: subprocess.run fue invocado con source_url que inicia con '-'!"
        )

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    # Intentos de inyección de argumentos como switches de git (ej. --upload-pack, -c, etc.)
    malicious_urls = [
        "--upload-pack=touch /tmp/pwned",
        "-c core.gitproxy=evil",
        "--version",
        "-v",
        "  -leading-spaces-with-dash",
    ]

    for bad_url in malicious_urls:
        with pytest.raises(ValueError, match="source_url inválido"):
            resolve_git_ref(source_url=bad_url, ref="HEAD")


def test_resolve_git_ref_adversarial_rejects_ref_starting_with_dash(monkeypatch: pytest.MonkeyPatch):
    """
    TEST ADVERSARIAL 2:
    Llamar a resolve_git_ref con un ref que empiece con '-' y verificar que levanta
    ValueError ANTES de ejecutar ningún subprocess.run.
    """
    def mock_subprocess_run(*args, **kwargs):
        raise AssertionError(
            "VULNERABILIDAD DETECTADA: subprocess.run fue invocado con ref que inicia con '-'!"
        )

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    malicious_refs = [
        "--output=/tmp/pwned",
        "-o",
        "--end-of-options",
        "--tags",
        "  -leading-dash-ref",
    ]

    for bad_ref in malicious_refs:
        with pytest.raises(ValueError, match="ref inválido"):
            resolve_git_ref(source_url="https://github.com/org/repo.git", ref=bad_ref)


def test_install_from_url_adversarial_propagates_rejection(test_env):
    """
    TEST ADVERSARIAL 3:
    Confirmar que install_from_url() no registra nada en plugin_registry si resolve_git_ref
    levantó ValueError (rechazo total, cero side effects en la base de datos).
    También valida que plugin_id comenzando con '-' sea rechazado fail-closed.
    """
    installer: PluginInstaller = test_env["installer"]
    registry: PluginRegistry = test_env["registry"]

    # 1. Intento con ref malicioso
    with pytest.raises(ValueError, match="ref inválido"):
        installer.install_from_url(
            source_url="https://github.com/org/valid_repo.git",
            plugin_id="plugin_reject_ref",
            ref="--config=pwned",
        )
    assert registry.get_plugin("plugin_reject_ref") is None, (
        "No debe existir ningún registro en plugin_registry si ref fue rechazado"
    )

    # 2. Intento con source_url malicioso
    with pytest.raises(ValueError, match="source_url inválido"):
        installer.install_from_url(
            source_url="--upload-pack=pwned",
            plugin_id="plugin_reject_url",
            ref="HEAD",
        )
    assert registry.get_plugin("plugin_reject_url") is None, (
        "No debe existir ningún registro en plugin_registry si source_url fue rechazado"
    )

    # 3. Intento con plugin_id malicioso (empezando con '-')
    with pytest.raises(ValueError, match="plugin_id inválido"):
        installer.install_from_url(
            source_url="https://github.com/org/valid_repo.git",
            plugin_id="-flag_as_plugin_id",
            ref="HEAD",
        )
    assert registry.get_plugin("-flag_as_plugin_id") is None, (
        "No debe existir ningún registro en plugin_registry si plugin_id fue rechazado"
    )

    # 4. Intento con plugin_id malicioso en install_from_catalog
    with pytest.raises(ValueError, match="plugin_id inválido"):
        installer.install_from_catalog("-malicious_catalog_id")
    assert registry.get_plugin("-malicious_catalog_id") is None


def test_resolve_git_ref_adversarial_rejects_ext_scheme_and_non_https(monkeypatch: pytest.MonkeyPatch):
    """
    TEST ADVERSARIAL REQUERIDO 1:
    Verifica que resolve_git_ref() rechace esquemas distintos de 'https://' o directorios
    locales existentes (ej. ext::, ssh://, git://, file://, http://, etc.) levantando
    ValueError ANTES de ejecutar ningún subprocess.run.
    """
    def mock_subprocess_run(*args, **kwargs):
        raise AssertionError(
            f"VULNERABILIDAD CRÍTICA DETECTADA: subprocess.run fue invocado con transporte no seguro: {args} {kwargs}!"
        )

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    disallowed_urls = [
        "ext::sh -c touch /tmp/pwned",
        "ext::cat /etc/passwd",
        "ssh://git@github.com/org/repo.git",
        "ssh://-oProxyCommand=sh/repo.git",
        "ssh://user@host:port/repo.git",
        "git://github.com/org/repo.git",
        "file:///tmp/repo.git",
        "file:///etc/passwd",
        "http://github.com/org/repo.git",
        "ftp://github.com/org/repo.git",
        "HTTPS://github.com/org/repo.git",
        "https:github.com/org/repo.git",
        "https://evil-untrusted-host.com/org/repo.git",
        "git::https://github.com/org/repo.git",
        "https://github.com/org/repo.git::ext",
        "/nonexistent/local/dir/that/does/not/exist",
    ]

    for bad_url in disallowed_urls:
        with pytest.raises(ValueError):
            resolve_git_ref(source_url=bad_url, ref="HEAD")
        with pytest.raises(ValueError):
            validate_source_url(bad_url)


def test_validate_source_url_accepts_authorized_hosts_and_local_dirs(local_git_repo: Path):
    """Verifica que validate_source_url acepte dominios autorizados y directorios locales absolutos."""
    validate_source_url("https://github.com/jarvis-plugins/toy-plugin.git")
    validate_source_url("https://gitlab.com/jarvis-plugins/sample-plugin.git")
    validate_source_url(str(local_git_repo.resolve()))



def test_resolve_git_ref_adversarial_still_allows_local_test_repo(local_git_repo: Path):
    """
    TEST ADVERSARIAL REQUERIDO 2:
    Verifica que resolve_git_ref() mantenga soporte para repositorios locales existentes
    (utilizados por fixtures de tests y entornos aislados) resolviendo su commit hash concreto.
    """
    resolved_commit = resolve_git_ref(source_url=str(local_git_repo), ref="HEAD")
    assert re.match(r"^[0-9a-f]{40}$", resolved_commit)


# ============================================================================
# TESTS: Funciones Públicas del Catálogo Curado para la UI
# ============================================================================

def test_list_curated_plugins_returns_clean_objects_and_reflects_installation(test_env):
    """
    Verifica que list_curated_plugins():
    1. Devuelve una lista de CuratedPluginInfo con solo los campos permitidos para la UI.
    2. No filtra datos técnicos ni de auditoría (commit_hash, source_url, reviewed_by, status).
    3. Refleja fielmente el estado de instalación (is_installed: False -> True tras instalar).
    """
    # Antes de instalar: ningún plugin curado está instalado en test_env
    plugins_before = list_curated_plugins()
    assert len(plugins_before) == 2
    ids_before = {p.plugin_id: p for p in plugins_before}

    assert "toy" in ids_before
    assert "open_interpreter" in ids_before

    toy_info = ids_before["toy"]
    assert isinstance(toy_info, CuratedPluginInfo)
    assert toy_info.name == "Toy Plugin"
    assert toy_info.icon == "clock-outline"
    assert toy_info.description == "Plugin de diagnóstico básico"
    assert toy_info.is_installed is False

    # REGLA NO NEGOCIABLE: No debe contener commit_hash, source_url, reviewed_by ni status
    for p in plugins_before:
        assert not hasattr(p, "commit_hash")
        assert not hasattr(p, "source_url")
        assert not hasattr(p, "reviewed_by")
        assert not hasattr(p, "status")
        # Tampoco vía dict / getitem
        assert "commit_hash" not in p.to_dict()
        assert "source_url" not in p.to_dict()
        assert "reviewed_by" not in p.to_dict()
        assert "status" not in p.to_dict()

    # Instalar toy desde el catálogo
    install_res = install_from_catalog("toy")
    assert install_res.success is True

    # Después de instalar: toy debe figurar como is_installed=True y open_interpreter como False
    plugins_after = list_curated_plugins()
    ids_after = {p.plugin_id: p for p in plugins_after}

    assert ids_after["toy"].is_installed is True
    assert ids_after["open_interpreter"].is_installed is False


def test_install_from_catalog_already_installed_handled_gracefully(test_env):
    """
    Verifica que si un plugin ya está instalado:
    1. install_from_catalog() lo maneja con gracia (sin excepciones ni re-instalación silenciosa).
    2. Devuelve un InstallResult claro con mensaje legible para el usuario.
    """
    # Primera instalación exitosa
    res1 = install_from_catalog("toy")
    assert res1.success is True
    assert res1.plugin_id == "toy"

    # Segunda instalación (ya instalado)
    res2 = install_from_catalog("toy")
    assert res2.success is False
    assert res2.plugin_id == "toy"
    assert "ya se encuentra instalado" in res2.message.lower()

    # Verificar que no hubo excepción y no se alteró la auditoría original
    reg_entry = test_env["registry"].get_plugin("toy")
    assert reg_entry["reviewed_by"] == "auditor_seguridad_principal"


def test_install_from_catalog_error_handling_user_friendly(test_env):
    """
    Verifica el manejo de errores con mensajes comprensibles para el usuario final.
    """
    # Plugin no existente en el catálogo
    res_unknown = install_from_catalog("non_existent_plugin")
    assert res_unknown.success is False
    assert "no existe" in res_unknown.message.lower()

    # Plugin id con guión inicial (rechazo fail-closed)
    res_dash = install_from_catalog("-malicious_id")
    assert res_dash.success is False
    assert "inválido" in res_dash.message.lower()


