# PyInstaller hook for pydantic v2 (pydantic-core is a Rust extension)
from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs

hiddenimports = collect_submodules("pydantic") + collect_submodules("pydantic_core")
binaries = collect_dynamic_libs("pydantic_core")
