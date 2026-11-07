"""Servidor MCP stdio minimo: lee una captura local, nunca modifica PowerFactory."""
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

ARCHIVO = Path(__file__).resolve().parent / 'contexto.json'
INTERCAMBIO = ARCHIVO.parent / 'intercambio'


def crear_solicitud(timeout=120):
    INTERCAMBIO.mkdir(exist_ok=True)
    identificador = uuid.uuid4().hex
    peticion = INTERCAMBIO / ('peticion_' + identificador + '.json')
    temporal = peticion.with_suffix('.tmp')
    temporal.write_text(json.dumps({'id': identificador, 'accion': 'contexto',
                                    'vence': time.time() + timeout}), encoding='utf-8')
    os.replace(str(temporal), str(peticion))
    return identificador


def recoger_solicitud(identificador, timeout=0):
    if not isinstance(identificador, str) or not re.fullmatch('[0-9a-f]{32}', identificador):
        raise ValueError('Identificador de solicitud invalido.')
    peticion = INTERCAMBIO / ('peticion_' + identificador + '.json')
    respuesta = INTERCAMBIO / ('respuesta_' + identificador + '.json')
    limite = time.monotonic() + timeout
    try:
        while True:
            if respuesta.exists():
                datos = json.loads(respuesta.read_text(encoding='utf-8'))
                if datos.get('id') != identificador:
                    raise ValueError('La respuesta no coincide con la solicitud.')
                if not datos.get('ok'):
                    raise RuntimeError(datos.get('error', 'Error del agente'))
                return datos['resultado']
            if time.monotonic() >= limite:
                if timeout == 0:
                    if not peticion.exists():
                        raise ValueError('Solicitud inexistente o expirada.')
                    solicitud = json.loads(peticion.read_text(encoding='utf-8'))
                    if time.time() > float(solicitud['vence']):
                        peticion.unlink()
                        raise ValueError('Solicitud expirada; cree una nueva.')
                    raise TimeoutError('Respuesta pendiente. Ejecute MCP Consulta Puntual en PowerFactory.')
                raise TimeoutError('PowerFactory no respondio a tiempo. Inicie MCP Consulta Puntual mientras la solicitud esta pendiente.')
            time.sleep(0.1)
    finally:
        # Una consulta no bloqueante pendiente no debe cancelar la solicitud.
        for ruta in ((peticion, respuesta) if respuesta.exists() or timeout else ()):
            try:
                ruta.unlink()
            except FileNotFoundError:
                pass


def consultar_en_vivo(timeout=30):
    identificador = crear_solicitud(timeout)
    try:
        return recoger_solicitud(identificador, timeout)
    finally:
        try:
            (INTERCAMBIO / ('peticion_' + identificador + '.json')).unlink()
        except FileNotFoundError:
            pass


def atender(req):
    metodo = req.get('method')
    if metodo == 'initialize':
        version = req.get('params', {}).get('protocolVersion', '2024-11-05')
        return {'protocolVersion': version, 'capabilities': {'tools': {}},
                'serverInfo': {'name': 'powerfactory-contexto', 'version': '0.2.0'},
                'instructions': 'Para una consulta actual: llamar solicitar_contexto, ejecutar MCP Consulta Puntual en la interfaz de PowerFactory y llamar recoger_contexto con el id. El comando puntual no se dispara automaticamente desde el servidor. La captura manual puede estar desactualizada.'}
    if metodo == 'ping':
        return {}
    if metodo == 'tools/list':
        return {'tools': [{'name': 'solicitar_contexto',
                'description': 'Crea solicitud de lectura valida por 120 segundos; ejecutar MCP Consulta Puntual y despues recoger_contexto.',
                'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
                {'name': 'recoger_contexto', 'description': 'Recoge la respuesta de una solicitud de contexto puntual.',
                'inputSchema': {'type': 'object', 'properties': {'id': {'type': 'string'}}, 'required': ['id'], 'additionalProperties': False}},
                {'name': 'consultar_contexto_vivo',
                'description': 'Solicita contexto nuevo; requiere ejecutar MCP Consulta Puntual en PowerFactory mientras espera hasta 30 segundos.',
                'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}, {'name': 'consultar_contexto',
                'description': 'Lee la ultima captura manual de la sesion grafica PowerFactory; no es una consulta en tiempo real.',
                'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'solicitar_contexto':
        return {'content': [{'type': 'text', 'text': json.dumps({'id': crear_solicitud(), 'vence_en_segundos': 120})}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'recoger_contexto':
        try:
            ident = req.get('params', {}).get('arguments', {}).get('id')
            return {'content': [{'type': 'text', 'text': json.dumps(recoger_solicitud(ident), ensure_ascii=False)}]}
        except (OSError, ValueError, KeyError, RuntimeError, TimeoutError) as exc:
            return {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'consultar_contexto_vivo':
        try:
            texto = json.dumps(consultar_en_vivo(), ensure_ascii=False, indent=2)
            return {'content': [{'type': 'text', 'text': texto}]}
        except (OSError, ValueError, KeyError, RuntimeError, TimeoutError) as exc:
            return {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'consultar_contexto':
        try:
            datos = json.loads(ARCHIVO.read_text(encoding='utf-8'))
            datos['antiguedad_segundos'] = max(0, round(time.time() - datos['capturado_unix']))
            texto = json.dumps(datos, ensure_ascii=False, indent=2)
            return {'content': [{'type': 'text', 'text': texto}]}
        except (OSError, ValueError, KeyError) as exc:
            return {'isError': True, 'content': [{'type': 'text', 'text': 'No hay captura valida. Ejecute capturar_contexto.py dentro de PowerFactory. Detalle: ' + str(exc)}]}
    raise ValueError('Metodo o herramienta desconocida: ' + str(metodo))


def main():
    for linea in sys.stdin:
        try:
            req = json.loads(linea)
            if 'id' not in req:
                continue
            try:
                respuesta = {'jsonrpc': '2.0', 'id': req['id'], 'result': atender(req)}
            except Exception as exc:
                respuesta = {'jsonrpc': '2.0', 'id': req['id'], 'error': {'code': -32601, 'message': str(exc)}}
            print(json.dumps(respuesta, ensure_ascii=True), flush=True)
        except Exception as exc:
            print('Error procesando solicitud: ' + str(exc), file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
