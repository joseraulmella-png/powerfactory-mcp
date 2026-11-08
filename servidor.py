"""Servidor MCP stdio minimo: lee una captura local, nunca modifica PowerFactory."""
import json
import os
import re
import sys
import time
import uuid
import subprocess
import threading
import queue
from pathlib import Path

ARCHIVO = Path(__file__).resolve().parent / 'contexto.json'
INTERCAMBIO = ARCHIVO.parent / 'intercambio'
MOTOR = None
RESPUESTAS_MOTOR = None


def consultar_motor(accion, **parametros):
    global MOTOR, RESPUESTAS_MOTOR
    if MOTOR is None or MOTOR.poll() is not None:
        if accion != 'iniciar':
            raise RuntimeError('Motor no iniciado. Use iniciar_motor primero.')
        python = os.environ.get('POWERFACTORY_PYTHON', str(ARCHIVO.parent / '.runtime-python' / 'cpython-3.9.25-windows-x86_64-none' / 'python.exe'))
        MOTOR = subprocess.Popen([python, '-u', str(ARCHIVO.parent / 'motor_persistente.py')],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr,
                                 text=True, encoding='utf-8')
        RESPUESTAS_MOTOR = queue.Queue()
        def leer(proc, destino):
            for linea in proc.stdout:
                destino.put(linea)
            destino.put(None)
        threading.Thread(target=leer, args=(MOTOR, RESPUESTAS_MOTOR), daemon=True).start()
    ident = uuid.uuid4().hex
    MOTOR.stdin.write(json.dumps(dict(id=ident, accion=accion, **parametros)) + '\n')
    MOTOR.stdin.flush()
    try:
        linea = RESPUESTAS_MOTOR.get(timeout=60)
    except queue.Empty:
        raise TimeoutError('El motor no respondio en 60 segundos. Si pidio una modificacion, puede haberse aplicado: revise el proyecto antes de reintentar y reinicie la sesion MCP.')
    if linea is None:
        raise RuntimeError('El proceso de PowerFactory termino inesperadamente.')
    respuesta = json.loads(linea)
    if respuesta.get('id') != ident:
        raise RuntimeError('Respuesta inesperada del motor; reinicie la sesion MCP.')
    if not respuesta.get('ok'):
        raise RuntimeError(respuesta.get('error', 'Error del motor'))
    return respuesta['resultado']


def crear_solicitud(timeout=120, accion='contexto', parametros=None):
    if accion not in ('contexto', 'inventario', 'analizar_lineas', 'configurar_opc_prueba', 'modificar_cargas', 'ejecutar_python'):
        raise ValueError('Accion no permitida.')
    INTERCAMBIO.mkdir(exist_ok=True)
    identificador = uuid.uuid4().hex
    peticion = INTERCAMBIO / ('peticion_' + identificador + '.json')
    temporal = peticion.with_suffix('.tmp')
    temporal.write_text(json.dumps({'id': identificador, 'accion': accion, 'parametros': parametros or {},
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
            time.sleep(0.015)
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
        return {'tools': [{'name': 'representar_elemento_sesion', 'description': 'Añade al diagrama activo la representación de un elemento eléctrico existente. No crea el elemento eléctrico. Requiere rutas exactas del proyecto, diagrama y elemento. El comando gráfico puede añadir también otros elementos ausentes; devuelve todos los gráficos agregados. Verifique representado y codigo_layout.', 'inputSchema': {'type': 'object', 'properties': {k: {'type': 'string', 'minLength': 1} for k in ('proyecto_ruta', 'diagrama_ruta', 'elemento_ruta')}, 'required': ['proyecto_ruta', 'diagrama_ruta', 'elemento_ruta'], 'additionalProperties': False}},
                {'name': 'crear_maquina_sincrona_sesion', 'description': 'Crea una máquina síncrona, tipo de prueba y cubículo en el proyecto activo, la conecta al terminal indicado y añade su representación gráfica al diagrama abierto. Modifica el proyecto; requiere petición del usuario. El tipo usa valores predeterminados ilustrativos. No ejecuta flujo. El comando de disposición también puede añadir otros objetos ausentes al diagrama. Si falla, informa los objetos creados para revisión.', 'inputSchema': {'type': 'object', 'properties': {'proyecto_ruta': {'type': 'string'}, 'terminal_ruta': {'type': 'string'}, 'diagrama_ruta': {'type': 'string'}, 'nombre': {'type': 'string'}, 'potencia_nominal_mva': {'type': 'number', 'exclusiveMinimum': 0}, 'potencia_activa_mw': {'type': 'number'}, 'potencia_reactiva_mvar': {'type': 'number', 'default': 0}}, 'required': ['proyecto_ruta', 'terminal_ruta', 'diagrama_ruta', 'nombre', 'potencia_nominal_mva', 'potencia_activa_mw'], 'additionalProperties': False}},
                {'name': 'detener_escucha_sesion', 'description': 'Detiene el bucle de escucha continua (MCP Consulta Puntual / agente_puntual.py) en PowerFactory para liberar inmediatamente la barra de herramientas y el canal ComPython.', 'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
                {'name': 'ejecutar_python_sesion', 'description': 'Ejecuta codigo Python arbitrario sobre la sesion activa de PowerFactory (app, proyecto, caso) en cualquier proyecto (o para activar/cambiar proyectos), permitiendo crear/editar elementos y ejecutar calculos.', 'inputSchema': {'type': 'object', 'properties': {'codigo': {'type': 'string', 'minLength': 1}}, 'required': ['codigo'], 'additionalProperties': False}},
                {'name': 'modificar_cargas_sesion', 'description': 'Modifica cargas (ElmLod) por nombres, terminales o todas en el proyecto activo y recalcula el flujo.', 'inputSchema': {'type': 'object', 'properties': {'nombres': {'type': 'array', 'items': {'type': 'string'}}, 'terminales': {'type': 'array', 'items': {'type': 'string'}}, 'factor_escala': {'type': 'number', 'minimum': 0}, 'plini': {'type': 'number'}, 'qlini': {'type': 'number'}, 'outserv': {'type': 'integer', 'enum': [0, 1]}, 'todas': {'type': 'boolean'}, 'ejecutar_flujo': {'type': 'boolean', 'default': True}, 'umbral': {'type': 'number', 'minimum': 0, 'default': 80}}, 'additionalProperties': False}},
                {'name': 'solicitar_prueba_opc', 'description': 'Crea y configura automaticamente ComOpc (OPC UA Link) y un punto de medicion MCP_Prueba_Mea en la copia de prueba activa. Ejecutar MCP Consulta Puntual y recoger_contexto con el id.', 'inputSchema': {'type': 'object', 'properties': {'ejecutar_enlace': {'type': 'boolean', 'default': True}}, 'additionalProperties': False}},
                {'name': 'solicitar_analisis_sesion', 'description': 'Solicita analisis de lineas en la sesion grafica existente. Ejecutar MCP Consulta Puntual y recoger_contexto con el id. ejecutar=true calcula el flujo con ajustes actuales; requiere solicitud explicita.', 'inputSchema': {'type': 'object', 'properties': {'umbral': {'type': 'number', 'minimum': 0, 'default': 100}, 'ejecutar': {'type': 'boolean', 'default': False}}, 'additionalProperties': False}},
                {'name': 'analizar_sobrecargas_lineas', 'description': 'Analiza lineas sobre un umbral usando resultados validos del flujo en el motor externo. ejecutar=true ejecuta el flujo con sus ajustes actuales; usar solo cuando el usuario lo solicite.', 'inputSchema': {'type': 'object', 'properties': {'umbral': {'type': 'number', 'minimum': 0, 'default': 100}, 'ejecutar': {'type': 'boolean', 'default': False}}, 'additionalProperties': False}},
                {'name': 'renombrar_elemento_motor', 'description': 'MODIFICA un elemento del proyecto activo. Solo ante solicitud expresa del usuario; exige ruta y nombre actuales y verifica el resultado con una nueva consulta.', 'inputSchema': {'type': 'object', 'properties': {k: {'type': 'string', 'minLength': 1} for k in ('proyecto_ruta', 'objeto_ruta', 'nombre_actual', 'nombre_nuevo')}, 'required': ['proyecto_ruta', 'objeto_ruta', 'nombre_actual', 'nombre_nuevo'], 'additionalProperties': False}},
                {'name': 'iniciar_motor', 'description': 'Inicia una sesion externa persistente de PowerFactory; la base local no puede estar abierta en otra instancia.', 'inputSchema': {'type': 'object', 'properties': {'mostrar': {'type': 'boolean'}}, 'additionalProperties': False}},
                {'name': 'activar_proyecto_motor', 'description': 'Activa un proyecto por nombre en la sesion externa persistente.', 'inputSchema': {'type': 'object', 'properties': {'proyecto': {'type': 'string'}}, 'required': ['proyecto'], 'additionalProperties': False}},
                {'name': 'consultar_motor', 'description': 'Lee contexto o inventario actual directamente de la sesion externa persistente.', 'inputSchema': {'type': 'object', 'properties': {'tipo': {'type': 'string', 'enum': ['contexto', 'inventario']}}, 'required': ['tipo'], 'additionalProperties': False}},
                {'name': 'solicitar_inventario',
                'description': 'Solicita inventario de redes y elementos del proyecto activo; ejecutar MCP Consulta Puntual y recoger_contexto con el id.',
                'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
                {'name': 'solicitar_contexto',
                'description': 'Crea solicitud de lectura valida por 120 segundos; ejecutar MCP Consulta Puntual y despues recoger_contexto.',
                'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
                {'name': 'recoger_contexto', 'description': 'Recoge la respuesta de una solicitud de contexto puntual.',
                'inputSchema': {'type': 'object', 'properties': {'id': {'type': 'string'}}, 'required': ['id'], 'additionalProperties': False}},
                {'name': 'consultar_contexto_vivo',
                'description': 'Solicita contexto nuevo; requiere ejecutar MCP Consulta Puntual en PowerFactory mientras espera hasta 30 segundos.',
                'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}, {'name': 'consultar_contexto',
                'description': 'Lee la ultima captura manual de la sesion grafica PowerFactory; no es una consulta en tiempo real.',
                'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'representar_elemento_sesion':
        args = req.get('params', {}).get('arguments', {})
        claves = {'proyecto_ruta', 'diagrama_ruta', 'elemento_ruta'}
        if not isinstance(args, dict) or set(args) != claves or not all(isinstance(args[k], str) and args[k] for k in claves):
            return {'isError': True, 'content': [{'type': 'text', 'text': 'Se requieren las tres rutas exactas.'}]}
        codigo = 'import importlib, diagramas\nimportlib.reload(diagramas)\nresultado = diagramas.representar(app, **%r)' % args
        ident = crear_solicitud(timeout=40, accion='ejecutar_python', parametros={'codigo': codigo})
        try:
            return {'content': [{'type': 'text', 'text': json.dumps(recoger_solicitud(ident, timeout=30), ensure_ascii=False)}]}
        except Exception as exc:
            return {'isError': True, 'content': [{'type': 'text', 'text': 'No se confirmó la representación: %s. Revise el diagrama antes de reintentar.' % exc}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'crear_maquina_sincrona_sesion':
        args = req.get('params', {}).get('arguments', {})
        requeridos = {'proyecto_ruta', 'terminal_ruta', 'diagrama_ruta', 'nombre', 'potencia_nominal_mva', 'potencia_activa_mw'}
        if not isinstance(args, dict) or not requeridos.issubset(args) or set(args) - (requeridos | {'potencia_reactiva_mvar'}):
            return {'isError': True, 'content': [{'type': 'text', 'text': 'Argumentos inválidos.'}]}
        codigo = 'import importlib, maquina_sincrona\nimportlib.reload(maquina_sincrona)\nresultado = maquina_sincrona.crear(app, **%r)' % args
        ident = crear_solicitud(timeout=40, accion='ejecutar_python', parametros={'codigo': codigo})
        try:
            return {'content': [{'type': 'text', 'text': json.dumps(recoger_solicitud(ident, timeout=30), ensure_ascii=False)}]}
        except Exception as exc:
            return {'isError': True, 'content': [{'type': 'text', 'text': 'No se confirmó la creación: %s. Revise el proyecto antes de reintentar.' % exc}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'detener_escucha_sesion':
        INTERCAMBIO.mkdir(exist_ok=True)
        bandera = INTERCAMBIO / 'detener_timer'
        bandera.write_text('', encoding='utf-8')
        t0 = time.monotonic()
        while bandera.exists() and (time.monotonic() - t0) < 1.5:
            time.sleep(0.02)
        detenido = not bandera.exists()
        return {'content': [{'type': 'text', 'text': json.dumps({'escucha_detenida': detenido}, ensure_ascii=False)}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'ejecutar_python_sesion':
        args = req.get('params', {}).get('arguments', {})
        if not isinstance(args, dict) or not isinstance(args.get('codigo'), str) or not args['codigo'].strip():
            return {'isError': True, 'content': [{'type': 'text', 'text': 'Se requiere codigo Python valido.'}]}
        ident = crear_solicitud(accion='ejecutar_python', parametros={'codigo': args['codigo']})
        try:
            return {'content': [{'type': 'text', 'text': json.dumps(recoger_solicitud(ident, timeout=15), ensure_ascii=False)}]}
        except TimeoutError:
            return {'content': [{'type': 'text', 'text': json.dumps({'id': ident, 'vence_en_segundos': 120})}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'modificar_cargas_sesion':
        args = req.get('params', {}).get('arguments', {})
        if not isinstance(args, dict):
            return {'isError': True, 'content': [{'type': 'text', 'text': 'Argumentos invalidos.'}]}
        ident = crear_solicitud(accion='modificar_cargas', parametros=args)
        try:
            return {'content': [{'type': 'text', 'text': json.dumps(recoger_solicitud(ident, timeout=15), ensure_ascii=False)}]}
        except TimeoutError:
            return {'content': [{'type': 'text', 'text': json.dumps({'id': ident, 'vence_en_segundos': 120})}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'solicitar_prueba_opc':
        args = req.get('params', {}).get('arguments', {})
        if not isinstance(args, dict) or set(args) - {'ejecutar_enlace'} or not isinstance(args.get('ejecutar_enlace', True), bool):
            return {'isError': True, 'content': [{'type': 'text', 'text': 'Argumentos invalidos.'}]}
        return {'content': [{'type': 'text', 'text': json.dumps({'id': crear_solicitud(accion='configurar_opc_prueba', parametros=args), 'vence_en_segundos': 120})}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'solicitar_analisis_sesion':
        args = req.get('params', {}).get('arguments', {})
        if not isinstance(args, dict) or set(args) - {'umbral', 'ejecutar'} or not isinstance(args.get('ejecutar', False), bool):
            return {'isError': True, 'content': [{'type': 'text', 'text': 'Argumentos invalidos.'}]}
        return {'content': [{'type': 'text', 'text': json.dumps({'id': crear_solicitud(accion='analizar_lineas', parametros=args), 'vence_en_segundos': 120})}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') in ('iniciar_motor', 'activar_proyecto_motor', 'consultar_motor', 'renombrar_elemento_motor', 'analizar_sobrecargas_lineas'):
        try:
            nombre = req['params']['name']
            args = req['params'].get('arguments', {})
            if not isinstance(args, dict):
                raise ValueError('Argumentos invalidos.')
            if nombre == 'iniciar_motor':
                mostrar = args.get('mostrar', False)
                if not isinstance(mostrar, bool):
                    raise ValueError('mostrar debe ser booleano.')
                resultado = consultar_motor('iniciar', mostrar=mostrar)
            elif nombre == 'activar_proyecto_motor':
                resultado = consultar_motor('activar_proyecto', proyecto=args.get('proyecto'))
            elif nombre == 'analizar_sobrecargas_lineas':
                if set(args) - {'umbral', 'ejecutar'}:
                    raise ValueError('Argumentos desconocidos.')
                resultado = consultar_motor('analizar_lineas', umbral=args.get('umbral', 100.0), ejecutar=args.get('ejecutar', False))
            elif nombre == 'renombrar_elemento_motor':
                claves = ('proyecto_ruta', 'objeto_ruta', 'nombre_actual', 'nombre_nuevo')
                if set(args) != set(claves) or not all(isinstance(args[k], str) and args[k].strip() for k in claves):
                    raise ValueError('Se requieren proyecto, ruta del elemento y nombres actual y nuevo.')
                resultado = consultar_motor('renombrar', **args)
            else:
                tipo = args.get('tipo')
                if tipo not in ('contexto', 'inventario'):
                    raise ValueError('Tipo de consulta invalido.')
                resultado = consultar_motor(tipo)
            return {'content': [{'type': 'text', 'text': json.dumps(resultado, ensure_ascii=False)}]}
        except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
            return {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'solicitar_inventario':
        return {'content': [{'type': 'text', 'text': json.dumps({'id': crear_solicitud(accion='inventario'), 'vence_en_segundos': 120})}]}
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
