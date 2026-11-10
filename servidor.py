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


def recoger_solicitud(identificador, timeout=0, cancelar_en_timeout=False):
    if not isinstance(identificador, str) or not re.fullmatch('[0-9a-f]{32}', identificador):
        raise ValueError('Identificador de solicitud invalido.')
    peticion = INTERCAMBIO / ('peticion_' + identificador + '.json')
    respuesta = INTERCAMBIO / ('respuesta_' + identificador + '.json')
    limite = time.monotonic() + timeout
    entregada = False
    cancelar = False

    def _leer_respuesta_si_existe(reintentos=3, pausa=0.02):
        nonlocal entregada
        for intento in range(reintentos):
            if respuesta.exists():
                try:
                    datos = json.loads(respuesta.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    if intento + 1 < reintentos:
                        time.sleep(pausa)
                        continue
                    raise
                entregada = True
                if datos.get('id') != identificador:
                    raise ValueError('La respuesta no coincide con la solicitud.')
                if not datos.get('ok'):
                    raise RuntimeError(datos.get('error', 'Error del agente'))
                return True, datos['resultado']
            if intento + 1 < reintentos:
                time.sleep(pausa)
        return False, None

    try:
        while True:
            if respuesta.exists():
                hay_resp, resultado = _leer_respuesta_si_existe()
                if hay_resp:
                    return resultado
            if time.monotonic() >= limite:
                hay_resp, resultado = _leer_respuesta_si_existe(reintentos=2, pausa=0.015)
                if hay_resp:
                    return resultado
                if timeout == 0 or not cancelar_en_timeout:
                    if not peticion.exists():
                        hay_resp, resultado = _leer_respuesta_si_existe(reintentos=4, pausa=0.02)
                        if hay_resp:
                            return resultado
                        raise ValueError('Solicitud inexistente o expirada.')
                    try:
                        solicitud = json.loads(peticion.read_text(encoding='utf-8'))
                    except FileNotFoundError:
                        hay_resp, resultado = _leer_respuesta_si_existe(reintentos=4, pausa=0.02)
                        if hay_resp:
                            return resultado
                        raise ValueError('Solicitud inexistente o expirada.')
                    # El vencimiento solo impide que el agente inicie la operación.
                    # Puede haberla iniciado antes de vencer y seguir ejecutándola.
                    raise TimeoutError('Respuesta pendiente o estado desconocido. Consulte con el mismo id antes de reintentar.')
                hay_resp, resultado = _leer_respuesta_si_existe(reintentos=3, pausa=0.02)
                if hay_resp:
                    return resultado
                cancelar = True
                raise TimeoutError('PowerFactory no respondio a tiempo. Inicie MCP Consulta Puntual mientras la solicitud esta pendiente.')
            time.sleep(0.015)
    finally:
        # Nunca eliminar una respuesta que no haya sido entregada al cliente.
        rutas_borrar = (peticion, respuesta) if entregada else ((peticion,) if cancelar else ())
        for ruta in rutas_borrar:
            try:
                ruta.unlink()
            except FileNotFoundError:
                pass


def _respuesta_timeout_pendiente(identificador, timeout_validez=120):
    return {
        'id': identificador,
        'estado': 'pendiente',
        'vence_en_segundos': timeout_validez,
        'escucha_activa': escucha_activa(),
        'advertencia': (
            'Tiempo de espera agotado; la operacion puede estar ejecutandose o haberse completado '
            'en PowerFactory. No reintente antes de verificar el resultado con recoger_contexto '
            'usando este mismo id.'
        ),
    }


def escucha_activa(max_antiguedad=3.5):
    latido = INTERCAMBIO / 'latido_timer.json'
    try:
        datos = json.loads(latido.read_text(encoding='utf-8'))
        return (time.time() - float(datos.get('latido_unix', 0))) <= max_antiguedad
    except Exception:
        return False


def despachar_solicitud(accion='contexto', parametros=None, timeout_espera=15, timeout_validez=120):
    ident = crear_solicitud(timeout=timeout_validez, accion=accion, parametros=parametros)
    espera = timeout_espera if escucha_activa() else min(1.5, timeout_espera)
    try:
        return recoger_solicitud(ident, timeout=espera, cancelar_en_timeout=False)
    except TimeoutError:
        return _respuesta_timeout_pendiente(ident, timeout_validez)


def consultar_en_vivo(timeout=30, timeout_validez=120):
    identificador = crear_solicitud(max(timeout, timeout_validez))
    try:
        return recoger_solicitud(identificador, timeout, cancelar_en_timeout=False)
    except TimeoutError:
        return _respuesta_timeout_pendiente(identificador, max(timeout, timeout_validez))


def atender(req):
    metodo = req.get('method')
    if metodo == 'initialize':
        version = req.get('params', {}).get('protocolVersion', '2024-11-05')
        return {'protocolVersion': version, 'capabilities': {'tools': {}},
                'serverInfo': {'name': 'powerfactory-contexto', 'version': '0.3.0'},
                'instructions': ('Cuando la escucha continua (MCP Consulta Puntual) esta activa, las herramientas de sesion responden directamente; si no, pueden devolver un id para recoger_contexto. '
                                 'Para interpretar estudios, consulte AGENTS.md en la carpeta del servidor. Identifique proyecto, caso, alimentador, escenarios, variaciones y etapas activas; verifique la validez del flujo y los limites aplicables antes de concluir. '
                                 'Determine por topologia si cada elemento pertenece al alimentador; una red o nombre por si solos no lo acreditan. Informe resultados con y sin obras por separado y no atribuya una causa unica a un flujo no convergente sin comprobarla.')}
    if metodo == 'ping':
        return {}
    if metodo == 'tools/list':
        herramientas = [
            {'name': 'anotar_elemento_sesion', 'description': 'Añade automáticamente en una zona libre del diagrama activo una etiqueta con flecha (nombre) y/o un cuadro con flecha mostrando las potencias (P, Q, S) del elemento indicado.', 'inputSchema': {'type': 'object', 'properties': {'nombre_o_ruta': {'type': 'string', 'minLength': 1}, 'incluir_etiqueta': {'type': 'boolean', 'default': True}, 'incluir_potencias': {'type': 'boolean', 'default': True}, 'diagrama_ruta': {'type': 'string'}}, 'required': ['nombre_o_ruta'], 'additionalProperties': False}},
            {'name': 'marcar_elemento_sesion', 'description': 'Selecciona y resalta en azul nativo (app.MarkInGraphics) uno o varios elementos en el diagrama activo por nombre o ruta, devolviendo además sus coordenadas (X, Y) en el diagrama activo.', 'inputSchema': {'type': 'object', 'properties': {'nombre_o_ruta': {'type': 'string'}, 'elementos': {'type': 'array', 'items': {'type': 'string'}}, 'escala': {'type': 'number', 'exclusiveMinimum': 0}, 'diagrama_ruta': {'type': 'string'}}, 'additionalProperties': False}},
            {'name': 'representar_elemento_sesion', 'description': 'Añade al diagrama activo la representación de un elemento eléctrico existente. No crea el elemento eléctrico. Requiere rutas exactas del proyecto, diagrama y elemento. Si limpiar_graficos_extra=true, elimina símbolos de otros elementos no relacionados que el comando gráfico haya agregado.', 'inputSchema': {'type': 'object', 'properties': {'proyecto_ruta': {'type': 'string', 'minLength': 1}, 'diagrama_ruta': {'type': 'string', 'minLength': 1}, 'elemento_ruta': {'type': 'string', 'minLength': 1}, 'limpiar_graficos_extra': {'type': 'boolean', 'default': False}}, 'required': ['proyecto_ruta', 'diagrama_ruta', 'elemento_ruta'], 'additionalProperties': False}},
            {'name': 'crear_maquina_sincrona_sesion', 'description': 'Crea una máquina síncrona, tipo de prueba y cubículo en el proyecto activo, la conecta al terminal indicado y añade su representación gráfica al diagrama abierto. Si falla, revierte automáticamente los objetos creados para no dejar huérfanos.', 'inputSchema': {'type': 'object', 'properties': {'proyecto_ruta': {'type': 'string'}, 'terminal_ruta': {'type': 'string'}, 'diagrama_ruta': {'type': 'string'}, 'nombre': {'type': 'string'}, 'potencia_nominal_mva': {'type': 'number', 'exclusiveMinimum': 0}, 'potencia_activa_mw': {'type': 'number'}, 'potencia_reactiva_mvar': {'type': 'number', 'default': 0}, 'revertir_en_error': {'type': 'boolean', 'default': True}, 'limpiar_graficos_extra': {'type': 'boolean', 'default': False}}, 'required': ['proyecto_ruta', 'terminal_ruta', 'diagrama_ruta', 'nombre', 'potencia_nominal_mva', 'potencia_activa_mw'], 'additionalProperties': False}},
            {'name': 'crear_elemento_shunt_sesion', 'description': 'Crea una carga (ElmLod) o sistema fotovoltaico (ElmPvsys) y su cubículo en el proyecto activo, lo conecta al terminal indicado y lo representa en el diagrama abierto con reversión automática en caso de error.', 'inputSchema': {'type': 'object', 'properties': {'proyecto_ruta': {'type': 'string'}, 'terminal_ruta': {'type': 'string'}, 'diagrama_ruta': {'type': 'string'}, 'clase': {'type': 'string', 'enum': ['ElmLod', 'ElmPvsys']}, 'nombre': {'type': 'string'}, 'potencia_activa_mw': {'type': 'number'}, 'potencia_reactiva_mvar': {'type': 'number', 'default': 0}, 'potencia_nominal_kva': {'type': 'number', 'exclusiveMinimum': 0}, 'revertir_en_error': {'type': 'boolean', 'default': True}, 'limpiar_graficos_extra': {'type': 'boolean', 'default': False}}, 'required': ['proyecto_ruta', 'terminal_ruta', 'diagrama_ruta', 'clase', 'nombre', 'potencia_activa_mw'], 'additionalProperties': False}},
            {'name': 'detener_escucha_sesion', 'description': 'Detiene el bucle de escucha continua (MCP Consulta Puntual / agente_puntual.py) en PowerFactory para liberar inmediatamente la barra de herramientas y el canal ComPython.', 'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
            {'name': 'ejecutar_python_sesion', 'description': 'Ejecuta codigo Python arbitrario sobre la sesion activa de PowerFactory (app, proyecto, caso) en cualquier proyecto (o para activar/cambiar proyectos), permitiendo crear/editar elementos y ejecutar calculos.', 'inputSchema': {'type': 'object', 'properties': {'codigo': {'type': 'string', 'minLength': 1}}, 'required': ['codigo'], 'additionalProperties': False}},
            {'name': 'modificar_cargas_sesion', 'description': 'Modifica cargas (ElmLod) por nombres, terminales o todas en el proyecto activo y recalcula el flujo.', 'inputSchema': {'type': 'object', 'properties': {'nombres': {'type': 'array', 'items': {'type': 'string'}}, 'terminales': {'type': 'array', 'items': {'type': 'string'}}, 'factor_escala': {'type': 'number', 'minimum': 0}, 'plini': {'type': 'number'}, 'qlini': {'type': 'number'}, 'outserv': {'type': 'integer', 'enum': [0, 1]}, 'todas': {'type': 'boolean'}, 'ejecutar_flujo': {'type': 'boolean', 'default': True}, 'umbral': {'type': 'number', 'minimum': 0, 'default': 80}}, 'additionalProperties': False}},
            {'name': 'solicitar_analisis_sesion', 'description': 'Analiza cargabilidad de líneas y transformadores y perfil de tensión en barras en la sesión gráfica. Si la escucha está activa responde directamente; ejecutar=true calcula el flujo de carga.', 'inputSchema': {'type': 'object', 'properties': {'umbral': {'type': 'number', 'minimum': 0, 'default': 100}, 'ejecutar': {'type': 'boolean', 'default': False}, 'incluir_transformadores': {'type': 'boolean', 'default': True}, 'v_min_pu': {'type': 'number', 'exclusiveMinimum': 0, 'default': 0.95}, 'v_max_pu': {'type': 'number', 'exclusiveMinimum': 0, 'default': 1.05}}, 'additionalProperties': False}},
            {'name': 'solicitar_inventario', 'description': 'Obtiene el inventario de redes y elementos del proyecto activo. Si la escucha está activa responde directamente; si no, devuelve un id para recoger_contexto.', 'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
            {'name': 'solicitar_contexto', 'description': 'Obtiene el contexto actual (proyecto, caso, selección). Si la escucha está activa responde directamente; si no, devuelve un id válido por 120 segundos para recoger_contexto.', 'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
            {'name': 'recoger_contexto', 'description': 'Recoge la respuesta pendiente de una solicitud por id.', 'inputSchema': {'type': 'object', 'properties': {'id': {'type': 'string'}}, 'required': ['id'], 'additionalProperties': False}},
            {'name': 'consultar_contexto_vivo', 'description': 'Solicita contexto nuevo esperando hasta 30 segundos.', 'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
            {'name': 'consultar_contexto', 'description': 'Lee la ultima captura manual guardada en disco; no es una consulta en tiempo real.', 'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
        ]
        if os.environ.get('MCP_INCLUIR_OPC') == '1':
            herramientas.append({'name': 'solicitar_prueba_opc', 'description': 'Crea y configura automaticamente ComOpc (OPC UA Link) y un punto de medicion MCP_Prueba_Mea en la copia de prueba activa.', 'inputSchema': {'type': 'object', 'properties': {'ejecutar_enlace': {'type': 'boolean', 'default': True}}, 'additionalProperties': False}})
        if os.environ.get('MCP_INCLUIR_MOTOR_EXTERNO') == '1':
            herramientas.extend([
                {'name': 'analizar_sobrecargas_lineas', 'description': 'Analiza lineas sobre un umbral usando resultados validos del flujo en el motor externo.', 'inputSchema': {'type': 'object', 'properties': {'umbral': {'type': 'number', 'minimum': 0, 'default': 100}, 'ejecutar': {'type': 'boolean', 'default': False}}, 'additionalProperties': False}},
                {'name': 'renombrar_elemento_motor', 'description': 'MODIFICA un elemento del proyecto activo en el motor externo.', 'inputSchema': {'type': 'object', 'properties': {k: {'type': 'string', 'minLength': 1} for k in ('proyecto_ruta', 'objeto_ruta', 'nombre_actual', 'nombre_nuevo')}, 'required': ['proyecto_ruta', 'objeto_ruta', 'nombre_actual', 'nombre_nuevo'], 'additionalProperties': False}},
                {'name': 'iniciar_motor', 'description': 'Inicia una sesion externa persistente de PowerFactory; la base local no puede estar abierta en otra instancia.', 'inputSchema': {'type': 'object', 'properties': {'mostrar': {'type': 'boolean'}}, 'additionalProperties': False}},
                {'name': 'activar_proyecto_motor', 'description': 'Activa un proyecto por nombre en la sesion externa persistente.', 'inputSchema': {'type': 'object', 'properties': {'proyecto': {'type': 'string'}}, 'required': ['proyecto'], 'additionalProperties': False}},
                {'name': 'consultar_motor', 'description': 'Lee contexto o inventario actual directamente de la sesion externa persistente.', 'inputSchema': {'type': 'object', 'properties': {'tipo': {'type': 'string', 'enum': ['contexto', 'inventario']}}, 'required': ['tipo'], 'additionalProperties': False}},
            ])
        return {'tools': herramientas}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'anotar_elemento_sesion':
        args = req.get('params', {}).get('arguments', {})
        if not isinstance(args, dict) or not isinstance(args.get('nombre_o_ruta'), str) or not args['nombre_o_ruta'].strip() or set(args) - {'nombre_o_ruta', 'incluir_etiqueta', 'incluir_potencias', 'diagrama_ruta'}:
            return {'isError': True, 'content': [{'type': 'text', 'text': 'Argumentos inválidos.'}]}
        codigo = 'import importlib, diagramas\nimportlib.reload(diagramas)\nresultado = diagramas.anotar(app, **%r)' % args
        ident = crear_solicitud(timeout=120, accion='ejecutar_python', parametros={'codigo': codigo})
        try:
            return {'content': [{'type': 'text', 'text': json.dumps(recoger_solicitud(ident, timeout=30, cancelar_en_timeout=False), ensure_ascii=False)}]}
        except TimeoutError:
            return {'content': [{'type': 'text', 'text': json.dumps(_respuesta_timeout_pendiente(ident, 120), ensure_ascii=False)}]}
        except Exception as exc:
            return {'isError': True, 'content': [{'type': 'text', 'text': 'No se pudo anotar el elemento: %s' % exc}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'marcar_elemento_sesion':
        args = req.get('params', {}).get('arguments', {})
        if not isinstance(args, dict) or set(args) - {'nombre_o_ruta', 'elementos', 'escala', 'diagrama_ruta'}:
            return {'isError': True, 'content': [{'type': 'text', 'text': 'Argumentos inválidos.'}]}
        codigo = 'import importlib, diagramas\nimportlib.reload(diagramas)\nresultado = diagramas.marcar(app, **%r)' % args
        ident = crear_solicitud(timeout=120, accion='ejecutar_python', parametros={'codigo': codigo})
        try:
            return {'content': [{'type': 'text', 'text': json.dumps(recoger_solicitud(ident, timeout=30, cancelar_en_timeout=False), ensure_ascii=False)}]}
        except TimeoutError:
            return {'content': [{'type': 'text', 'text': json.dumps(_respuesta_timeout_pendiente(ident, 120), ensure_ascii=False)}]}
        except Exception as exc:
            return {'isError': True, 'content': [{'type': 'text', 'text': 'No se pudo marcar el elemento: %s' % exc}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'representar_elemento_sesion':
        args = req.get('params', {}).get('arguments', {})
        requeridos = {'proyecto_ruta', 'diagrama_ruta', 'elemento_ruta'}
        if not isinstance(args, dict) or not requeridos.issubset(args) or set(args) - (requeridos | {'limpiar_graficos_extra'}) or not all(isinstance(args[k], str) and args[k] for k in requeridos):
            return {'isError': True, 'content': [{'type': 'text', 'text': 'Se requieren las tres rutas exactas.'}]}
        codigo = 'import importlib, diagramas\nimportlib.reload(diagramas)\nresultado = diagramas.representar(app, **%r)' % args
        ident = crear_solicitud(timeout=120, accion='ejecutar_python', parametros={'codigo': codigo})
        try:
            return {'content': [{'type': 'text', 'text': json.dumps(recoger_solicitud(ident, timeout=30, cancelar_en_timeout=False), ensure_ascii=False)}]}
        except TimeoutError:
            return {'content': [{'type': 'text', 'text': json.dumps(_respuesta_timeout_pendiente(ident, 120), ensure_ascii=False)}]}
        except Exception as exc:
            return {'isError': True, 'content': [{'type': 'text', 'text': 'No se confirmó la representación: %s. Revise el diagrama antes de reintentar.' % exc}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'crear_maquina_sincrona_sesion':
        args = req.get('params', {}).get('arguments', {})
        requeridos = {'proyecto_ruta', 'terminal_ruta', 'diagrama_ruta', 'nombre', 'potencia_nominal_mva', 'potencia_activa_mw'}
        opcionales = {'potencia_reactiva_mvar', 'revertir_en_error', 'limpiar_graficos_extra'}
        if not isinstance(args, dict) or not requeridos.issubset(args) or set(args) - (requeridos | opcionales):
            return {'isError': True, 'content': [{'type': 'text', 'text': 'Argumentos inválidos.'}]}
        codigo = 'import importlib, maquina_sincrona\nimportlib.reload(maquina_sincrona)\nresultado = maquina_sincrona.crear(app, **%r)' % args
        ident = crear_solicitud(timeout=120, accion='ejecutar_python', parametros={'codigo': codigo})
        try:
            return {'content': [{'type': 'text', 'text': json.dumps(recoger_solicitud(ident, timeout=30, cancelar_en_timeout=False), ensure_ascii=False)}]}
        except TimeoutError:
            return {'content': [{'type': 'text', 'text': json.dumps(_respuesta_timeout_pendiente(ident, 120), ensure_ascii=False)}]}
        except Exception as exc:
            return {'isError': True, 'content': [{'type': 'text', 'text': 'No se confirmó la creación: %s. Revise el proyecto antes de reintentar.' % exc}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'crear_elemento_shunt_sesion':
        args = req.get('params', {}).get('arguments', {})
        requeridos = {'proyecto_ruta', 'terminal_ruta', 'diagrama_ruta', 'clase', 'nombre', 'potencia_activa_mw'}
        opcionales = {'potencia_reactiva_mvar', 'potencia_nominal_kva', 'revertir_en_error', 'limpiar_graficos_extra'}
        if not isinstance(args, dict) or not requeridos.issubset(args) or set(args) - (requeridos | opcionales):
            return {'isError': True, 'content': [{'type': 'text', 'text': 'Argumentos inválidos.'}]}
        codigo = 'import importlib, elementos_shunt\nimportlib.reload(elementos_shunt)\nresultado = elementos_shunt.crear(app, **%r)' % args
        ident = crear_solicitud(timeout=120, accion='ejecutar_python', parametros={'codigo': codigo})
        try:
            return {'content': [{'type': 'text', 'text': json.dumps(recoger_solicitud(ident, timeout=30, cancelar_en_timeout=False), ensure_ascii=False)}]}
        except TimeoutError:
            return {'content': [{'type': 'text', 'text': json.dumps(_respuesta_timeout_pendiente(ident, 120), ensure_ascii=False)}]}
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
        try:
            return {'content': [{'type': 'text', 'text': json.dumps(despachar_solicitud('ejecutar_python', {'codigo': args['codigo']}), ensure_ascii=False)}]}
        except Exception as exc:
            return {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'modificar_cargas_sesion':
        args = req.get('params', {}).get('arguments', {})
        if not isinstance(args, dict):
            return {'isError': True, 'content': [{'type': 'text', 'text': 'Argumentos invalidos.'}]}
        try:
            return {'content': [{'type': 'text', 'text': json.dumps(despachar_solicitud('modificar_cargas', args), ensure_ascii=False)}]}
        except Exception as exc:
            return {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'solicitar_prueba_opc':
        args = req.get('params', {}).get('arguments', {})
        if not isinstance(args, dict) or set(args) - {'ejecutar_enlace'} or not isinstance(args.get('ejecutar_enlace', True), bool):
            return {'isError': True, 'content': [{'type': 'text', 'text': 'Argumentos invalidos.'}]}
        try:
            return {'content': [{'type': 'text', 'text': json.dumps(despachar_solicitud('configurar_opc_prueba', args), ensure_ascii=False)}]}
        except Exception as exc:
            return {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'solicitar_analisis_sesion':
        args = req.get('params', {}).get('arguments', {})
        permitidos = {'umbral', 'ejecutar', 'incluir_transformadores', 'v_min_pu', 'v_max_pu'}
        if not isinstance(args, dict) or set(args) - permitidos or not isinstance(args.get('ejecutar', False), bool):
            return {'isError': True, 'content': [{'type': 'text', 'text': 'Argumentos invalidos.'}]}
        try:
            return {'content': [{'type': 'text', 'text': json.dumps(despachar_solicitud('analizar_lineas', args), ensure_ascii=False)}]}
        except Exception as exc:
            return {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}
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
        try:
            return {'content': [{'type': 'text', 'text': json.dumps(despachar_solicitud('inventario'), ensure_ascii=False)}]}
        except Exception as exc:
            return {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}
    if metodo == 'tools/call' and req.get('params', {}).get('name') == 'solicitar_contexto':
        try:
            return {'content': [{'type': 'text', 'text': json.dumps(despachar_solicitud('contexto'), ensure_ascii=False)}]}
        except Exception as exc:
            return {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}
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
