"""Agente de consulta temporal: ejecutar dentro de PowerFactory como ComPython."""
import json
import os
import sys
import time
import traceback
from pathlib import Path

import powerfactory
sys.path.insert(0, str(Path(__file__).resolve().parent))
from capturar_contexto import capturar, inventariar, analizar_lineas, configurar_opc_prueba, modificar_cargas, ejecutar_python_dinamico

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
        accion = solicitud.get('accion')
        if solicitud.get('id') != identificador or accion not in ('contexto', 'inventario', 'analizar_lineas', 'configurar_opc_prueba', 'modificar_cargas', 'ejecutar_python'):
            raise ValueError('Solicitud invalida o accion no permitida')
        if time.time() > float(solicitud['vence']):
            resultado = {'id': identificador, 'ok': False, 'error': 'Solicitud expirada.'}
        else:
            if accion == 'contexto':
                datos = capturar(app)
            elif accion == 'inventario':
                datos = inventariar(app)
            elif accion == 'configurar_opc_prueba':
                parametros = solicitud.get('parametros', {})
                ejecutar_enlace = parametros.get('ejecutar_enlace', True)
                if not isinstance(ejecutar_enlace, bool):
                    raise ValueError('ejecutar_enlace debe ser booleano.')
                datos = configurar_opc_prueba(app, ejecutar_enlace=ejecutar_enlace)
            elif accion == 'modificar_cargas':
                parametros = solicitud.get('parametros', {})
                datos = modificar_cargas(app, **parametros)
            elif accion == 'ejecutar_python':
                parametros = solicitud.get('parametros', {})
                datos = ejecutar_python_dinamico(
                    app,
                    parametros.get('codigo', ''),
                    permitir_fuera_de_prueba=bool(parametros.get('permitir_fuera_de_prueba', False)),
                )
            else:
                parametros = solicitud.get('parametros', {})
                ejecutar = parametros.get('ejecutar', False)
                if not isinstance(ejecutar, bool):
                    raise ValueError('ejecutar debe ser booleano.')
                mostrar_en_interfaz = bool(parametros.get('mostrar_en_interfaz', True))
                datos = analizar_lineas(app, parametros.get('umbral', 100.0), ejecutar, mostrar_en_interfaz=mostrar_en_interfaz)
            resultado = {'id': identificador, 'ok': True, 'resultado': datos}
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
