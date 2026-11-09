"""Abre el panel experimental como proceso separado desde PowerFactory."""
import os
import subprocess
from pathlib import Path

import powerfactory


def main():
    app = powerfactory.GetApplication()
    panel = Path(__file__).resolve().with_name('panel_mcp_prueba.py')
    runtime = panel.parent / '.runtime-python' / 'cpython-3.9.25-windows-x86_64-none'
    pythonw = runtime / 'pythonw.exe'
    if not pythonw.is_file():
        raise RuntimeError('No se encontro el entorno de Python para abrir el panel.')
    registro = panel.with_name('panel_mcp_error.log')
    entorno = os.environ.copy()
    for clave in ('PYTHONHOME', 'PYTHONPATH', 'TCL_LIBRARY', 'TK_LIBRARY'):
        entorno.pop(clave, None)
    entorno['TCL_LIBRARY'] = str(runtime / 'tcl' / 'tcl8.6')
    entorno['TK_LIBRARY'] = str(runtime / 'tcl' / 'tk8.6')
    with registro.open('w', encoding='utf-8') as salida:
        subprocess.Popen([str(pythonw), str(panel)], close_fds=True,
                         stdout=salida, stderr=salida, env=entorno)
    if app:
        app.PrintInfo('MCP: panel de prueba iniciado.')


if __name__ == '__main__':
    main()
