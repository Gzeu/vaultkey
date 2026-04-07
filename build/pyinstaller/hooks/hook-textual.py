# PyInstaller hook for Textual
# Textual ships CSS theme files that must be included as data.
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas, binaries, hiddenimports = collect_all('textual')
datas += collect_data_files('textual')
hiddenimports += [
    'textual.app',
    'textual.screen',
    'textual.widget',
    'textual.widgets',
    'textual.containers',
    'textual.binding',
    'textual.reactive',
    'textual.message',
    'textual.events',
    'textual.css.query',
    'textual.css.scalar',
    'textual.geometry',
    'textual.color',
    'textual.strip',
    'textual.renderables',
    'textual._xterm_parser',
    'textual.driver',
    'textual.drivers',
    'textual.drivers._xterm_driver',
    'textual.drivers._win32_driver',
    'textual.drivers._headless_driver',
]
