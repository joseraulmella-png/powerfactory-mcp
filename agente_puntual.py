"""Procesa una solicitud pendiente y termina; ejecutar en PowerFactory."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import powerfactory
from agente_temporal import CARPETA, atender


def main():
    app = powerfactory.GetApplication()
    if app is None:
        raise RuntimeError('Ejecute el agente dentro de PowerFactory.')
    CARPETA.mkdir(exist_ok=True)
    peticiones = sorted(CARPETA.glob('peticion_*.json'), key=lambda p: p.stat().st_mtime)
    if not peticiones:
        app.PrintPlain('MCP: no hay solicitudes pendientes.')
        return
    for peticion in peticiones[:25]:
        atender(app, peticion)
    app.PrintPlain('MCP: consulta puntual procesada.')


if __name__ == '__main__':
    main()
