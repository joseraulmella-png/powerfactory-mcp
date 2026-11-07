"""Ejecutar como ComPython dentro de PowerFactory. Solo consulta el contexto."""
import json
import os
import time
from pathlib import Path

import powerfactory


DESTINO = Path(__file__).resolve().parent / "contexto.json"


def describir(obj):
    if obj is None:
        return None
    return {"nombre": str(obj.loc_name), "clase": str(obj.GetClassName()),
            "ruta": str(obj.GetFullName())}


def capturar(app):
    resultado = {"capturado_unix": time.time(), "errores": {}}
    for clave, metodo, lista in (
        ("proyecto", "GetActiveProject", False),
        ("caso_estudio", "GetActiveStudyCase", False),
        ("variaciones", "GetActiveNetworkVariations", True),
        ("seleccion_diagrama", "GetDiagramSelection", True),
        ("seleccion_navegador", "GetBrowserSelection", True),
        ("seleccion_actual", "GetCurrentSelection", True),
    ):
        try:
            valor = getattr(app, metodo)()
            resultado[clave] = [describir(x) for x in (valor or [])] if lista else describir(valor)
        except Exception as exc:
            resultado[clave] = None
            resultado["errores"][clave] = str(exc)
    return resultado


def main():
    app = powerfactory.GetApplication()
    if app is None:
        raise RuntimeError("Ejecute este script dentro de PowerFactory.")
    datos = capturar(app)
    temporal = DESTINO.with_suffix('.tmp')
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(str(temporal), str(DESTINO))
    app.PrintPlain("MCP PowerFactory: contexto capturado en " + str(DESTINO))


if __name__ == '__main__':
    main()
