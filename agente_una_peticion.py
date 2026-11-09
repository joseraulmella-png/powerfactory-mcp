"""Atiende una solicitud MCP pendiente y devuelve el control a PowerFactory."""
import importlib
import sys
from pathlib import Path

import powerfactory

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agente_temporal

importlib.reload(agente_temporal)


def main():
    app = powerfactory.GetApplication()
    if app is None:
        raise RuntimeError('Ejecute este script dentro de PowerFactory.')

    carpeta = agente_temporal.CARPETA
    carpeta.mkdir(exist_ok=True)
    peticiones = sorted(carpeta.glob('peticion_*.json'), key=lambda ruta: ruta.stat().st_mtime)
    if not peticiones:
        app.PrintInfo('MCP: no hay peticiones pendientes.')
        return

    agente_temporal.atender(app, peticiones[0])
    app.PrintInfo('MCP: peticion atendida; comando finalizado.')


if __name__ == '__main__':
    main()
