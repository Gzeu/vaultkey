# PyInstaller hook for CustomTkinter
# CTk ships themes (JSON) and fonts that must travel with the binary.
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas, binaries, hiddenimports = collect_all('customtkinter')
datas += collect_data_files('customtkinter', include_py_files=False)
hiddenimports += [
    'customtkinter',
    'customtkinter.windows',
    'customtkinter.windows.widgets',
    'customtkinter.windows.widgets.core_rendering',
    'customtkinter.windows.widgets.core_widget_classes',
    'customtkinter.windows.widgets.theme',
    'customtkinter.windows.widgets.font',
    'customtkinter.windows.widgets.utility',
]
