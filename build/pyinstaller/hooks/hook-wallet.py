# PyInstaller hook for the wallet package itself
# Makes sure all submodules are discovered even when __init__ doesn't import them.

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = collect_submodules('wallet')
datas = collect_data_files('wallet')
