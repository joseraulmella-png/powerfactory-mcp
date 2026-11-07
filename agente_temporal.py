"""Agente de consulta temporal: ejecutar dentro de PowerFactory como ComPython."""
import json
import os
import sys
import time
import traceback
from pathlib import Path

import powerfactory
sys.path.insert(0, str(Path(__file__).resolve().parent))
from capturar_contexto import capturar

CARPETA = Path(__file__).resolve().parent / 'intercambio'
DURACION_SEGUNDOS = 15


def guardar(ruta, datos):
    temporal = ruta.with_suffix('.tmp')
    temporal.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    os.replace(str(temporal), str(ruta))


def atender(app, ruta):
    identificador = ruta.stem[len('peticion_'):]
    if len(identificador) != 32 or any(c not in '0123456789abcdef' for c in identificador):
        return
    try:
        solicitud = json.loads(ruta.read_text(encoding='utf-8'))
        if solicitud.get('id') != identificador or solicitud.get('accion') != 'contexto':
            raise ValueError('Solicitud invalida o accion no permitida')
        if time.time() > float(solicitud['vence']):
            resultado = {'id': identificador, 'ok': False, 'error': 'Solicitud expirada.'}
        else:
            resultado = {'id': identificador, 'ok': True, 'resultado': capturar(app)}
    except Exception as exc:
        resultado = {'id': identificador, 'ok': False, 'error': str(exc), 'detalle': traceback.format_exc()}
    try:
        guardar(CARPETA / ('respuesta_' + identificador + '.json'), resultado)
    finally:
        try:
            ruta.unlink()
        except OSError:
            pass


def main():
    app = powerfactory.GetApplication()
    if app is None:
        raise RuntimeError('Ejecute el agente dentro de PowerFactory.')
    CARPETA.mkdir(exist_ok=True)
    app.PrintPlain('MCP: agente temporal de lectura iniciado por %s segundos.' % DURACION_SEGUNDOS)
    limite = time.monotonic() + DURACION_SEGUNDOS
    try:
        while time.monotonic() < limite:
            for ruta in CARPETA.glob('peticion_*.json'):
                atender(app, ruta)
            time.sleep(0.15)
    finally:
        app.PrintPlain('MCP: agente temporal finalizado.')


if __name__ == '__main__':
    main()
