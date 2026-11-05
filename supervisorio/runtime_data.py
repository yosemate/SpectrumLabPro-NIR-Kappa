"""Criação dos arquivos ausentes, sem substituir dados já existentes."""
import json
import os
from pathlib import Path
import sys
import tempfile


def data_directory():
    override = os.environ.get("SPECTRUM_LAB_DATA_DIR")
    if override:
        return Path(override).resolve()
    if getattr(sys, "frozen", False):
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SpectrumLabPro"
    return Path(__file__).resolve().parent


def create_json_if_missing(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = path.open("x", encoding="utf-8")
    except FileExistsError:
        return False
    try:
        with handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return True


def directory_writable(path):
    try:
        with tempfile.TemporaryFile(dir=path):
            pass
        return True
    except OSError:
        return False


def resolve_database_path(name="usuarios.db"):
    if os.environ.get("SPECTRUM_LAB_DATA_DIR") or not getattr(sys, "frozen", False):
        return str(data_directory() / name)
    portable = Path(sys.executable).resolve().parent / name
    fallback = data_directory() / name
    # Banco já existente permanece no local de origem; nunca é trocado por um vazio.
    if portable.exists():
        return str(portable)
    if fallback.exists():
        return str(fallback)
    return str(portable if directory_writable(portable.parent) else fallback)


def prepare_data_files():
    from appearance import preferences_path

    base = data_directory()
    base.mkdir(parents=True, exist_ok=True)
    material_path = base / "banco_materiais.json"
    if not material_path.exists():
        bundled = Path(__file__).resolve().parent / "banco_materiais.json"
        seed = bundled
        if getattr(sys, "frozen", False):
            portable = Path(sys.executable).resolve().parent / "banco_materiais.json"
            if portable.exists():
                seed = portable
        with seed.open(encoding="utf-8-sig") as handle:
            materials = json.load(handle)
        if not isinstance(materials, dict):
            raise ValueError("A base inicial de materiais precisa ser um objeto JSON.")
        create_json_if_missing(material_path, materials)
    preference_path = preferences_path()
    create_json_if_missing(preference_path, {"theme": "light"})
    return {"database": resolve_database_path(), "materials": str(material_path),
            "preferences": str(preference_path)}
