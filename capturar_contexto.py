"""Ejecutar como ComPython dentro de PowerFactory. Solo consulta el contexto."""
import json
import os
import time
import math
from pathlib import Path

import powerfactory


DESTINO = Path(__file__).resolve().parent / "contexto.json"


def describir(obj):
    if obj is None:
        return None
    return {"nombre": str(obj.loc_name), "clase": str(obj.GetClassName()),
            "ruta": str(obj.GetFullName())}


ATRIBUTOS = {
    'ElmLne': ('outserv', 'dline', 'nlnum', 'typ_id', 'r:bus1:e:cBusBar', 'r:bus2:e:cBusBar'),
    'ElmTerm': ('outserv', 'uknom'),
    'ElmLod': ('outserv', 'plini', 'qlini', 'r:bus1:e:cBusBar'),
    'ElmPvsys': ('outserv', 'pgini', 'qgini', 'r:bus1:e:cBusBar'),
    'ElmTr2': ('outserv', 'typ_id', 'r:bushv:e:cBusBar', 'r:buslv:e:cBusBar'),
    'ElmXnet': ('outserv', 'r:bus1:e:cBusBar'),
}


def detalle(obj):
    datos = describir(obj)
    datos['atributos'] = {}
    datos['unidades'] = {}
    datos['errores_atributos'] = {}
    for atributo in ATRIBUTOS.get(datos['clase'], ('outserv',)):
        try:
            valor = obj.GetAttribute(atributo)
            if hasattr(valor, 'GetClassName'):
                valor = describir(valor)
            elif not isinstance(valor, (str, int, float, bool, type(None))):
                raise TypeError('Tipo de atributo no admitido')
            datos['atributos'][atributo] = valor
            if isinstance(valor, (int, float)) and not isinstance(valor, bool):
                try:
                    datos['unidades'][atributo] = str(obj.GetAttributeUnit(atributo))
                except Exception:
                    datos['unidades'][atributo] = None
        except Exception as exc:
            datos['errores_atributos'][atributo] = str(exc)
    return datos


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


def inventariar(app, limite=10000):
    """Lista redes y elementos contenidos en ellas, sin modificar el modelo."""
    proyecto = app.GetActiveProject()
    if proyecto is None:
        raise RuntimeError('No hay proyecto activo.')
    redes = proyecto.GetContents('*.ElmNet', 1) or []
    resultado = {'capturado_unix': time.time(), 'proyecto': describir(proyecto),
                 'alcance': 'redes del proyecto y elementos contenidos en ellas',
                 'redes': [], 'errores': [], 'limite_elementos': limite,
                 'elementos_devueltos': 0, 'truncado': False}
    for red in redes:
        entrada = {'red': describir(red), 'elementos': []}
        resultado['redes'].append(entrada)
        try:
            elementos = red.GetContents('*.Elm*', 1) or []
            entrada['total_elementos'] = len(elementos)
            for elemento in elementos:
                if resultado['elementos_devueltos'] >= limite:
                    resultado['truncado'] = True
                    break
                entrada['elementos'].append(detalle(elemento))
                resultado['elementos_devueltos'] += 1
        except Exception as exc:
            resultado['errores'].append({'red': entrada['red'], 'error': str(exc)})
    return resultado


def analizar_lineas(app, umbral=100.0, ejecutar=False, mostrar_en_interfaz=True,
                    incluir_transformadores=True, v_min_pu=0.95, v_max_pu=1.05):
    """Consulta carga de lineas, transformadores y perfil de tensiones con resultados de flujo validos."""
    if isinstance(umbral, bool) or not isinstance(umbral, (int, float)) or not math.isfinite(umbral) or umbral < 0:
        raise ValueError('El umbral debe ser un numero finito no negativo.')
    for v in (v_min_pu, v_max_pu):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise ValueError('Los limites de tension deben ser numeros finitos positivos.')
    if v_min_pu > v_max_pu:
        raise ValueError('v_min_pu no puede superar a v_max_pu.')
    proyecto, caso = app.GetActiveProject(), app.GetActiveStudyCase()
    if proyecto is None or caso is None:
        raise RuntimeError('Se requiere proyecto y caso de estudio activos.')
    if ejecutar:
        comando = app.GetFromStudyCase('ComLdf')
        if comando is None:
            raise RuntimeError('No se encontro un comando de flujo de carga.')
        if mostrar_en_interfaz:
            for m in ('EchoOn',):
                if hasattr(app, m):
                    try:
                        getattr(app, m)()
                    except Exception:
                        pass
        else:
            for m in ('EchoOff',):
                if hasattr(app, m):
                    try:
                        getattr(app, m)()
                    except Exception:
                        pass
        t0_ldf = time.perf_counter()
        codigo = comando.Execute()
        duracion_flujo_ms = round((time.perf_counter() - t0_ldf) * 1000.0, 2)
        if mostrar_en_interfaz:
            for m, a in (('SetGraphicUpdate', (1,)), ('Rebuild', (1,))):
                if hasattr(app, m):
                    try:
                        getattr(app, m)(*a)
                    except Exception:
                        pass
        if codigo != 0:
            raise RuntimeError('El flujo de carga fallo (codigo %s); no se analizaron resultados.' % codigo)
    if not app.IsLdfValid():
        raise RuntimeError('No hay resultados validos de flujo de carga. Ejecute el calculo explicitamente antes de analizar.')
    lineas = app.GetCalcRelevantObjects('*.ElmLne') or []
    salida = {'capturado_unix': time.time(), 'proyecto': describir(proyecto), 'caso_estudio': describir(caso),
              'flujo_ejecutado': ejecutar, 'umbral_porcentaje': umbral, 'total_lineas_relevantes': len(lineas),
              'fuera_de_servicio': 0, 'lineas_analizadas': 0, 'lineas_sobre_umbral': [],
              'transformadores_analizados': 0, 'transformadores_sobre_umbral': [],
              'rango_tension_pu': [v_min_pu, v_max_pu], 'terminales_analizados': 0,
              'terminales_fuera_rango_tension': [], 'errores': []}
    for linea in lineas:
        try:
            if linea.GetAttribute('outserv'):
                salida['fuera_de_servicio'] += 1
                continue
            carga = float(linea.GetAttribute('c:loading'))
            if not math.isfinite(carga):
                raise ValueError('Resultado de carga no finito.')
            salida['lineas_analizadas'] += 1
            if carga > umbral:
                registro = detalle(linea)
                registro['carga_porcentaje'] = carga
                salida['lineas_sobre_umbral'].append(registro)
        except Exception as exc:
            salida['errores'].append({'linea': describir(linea), 'error': str(exc)})
    salida['lineas_sobre_umbral'].sort(key=lambda x: x['carga_porcentaje'], reverse=True)

    if incluir_transformadores:
        for trafo in (app.GetCalcRelevantObjects('*.ElmTr2') or []):
            try:
                if trafo.GetAttribute('outserv'):
                    continue
                carga_tr = float(trafo.GetAttribute('c:loading'))
                if not math.isfinite(carga_tr):
                    continue
                salida['transformadores_analizados'] += 1
                if carga_tr > umbral:
                    reg_tr = detalle(trafo)
                    reg_tr['carga_porcentaje'] = carga_tr
                    salida['transformadores_sobre_umbral'].append(reg_tr)
            except Exception as exc:
                salida['errores'].append({'transformador': describir(trafo), 'error': str(exc)})
        salida['transformadores_sobre_umbral'].sort(key=lambda x: x['carga_porcentaje'], reverse=True)

    for term in (app.GetCalcRelevantObjects('*.ElmTerm') or []):
        try:
            if term.GetAttribute('outserv'):
                continue
            u_pu = float(term.GetAttribute('m:u'))
            if not math.isfinite(u_pu):
                raise ValueError('Resultado de tension no finito.')
            salida['terminales_analizados'] += 1
            if u_pu < v_min_pu or u_pu > v_max_pu:
                reg_term = detalle(term)
                reg_term['tension_pu'] = round(u_pu, 5)
                reg_term['desviacion'] = 'subtension' if u_pu < v_min_pu else 'sobretension'
                salida['terminales_fuera_rango_tension'].append(reg_term)
        except Exception as exc:
            salida['errores'].append({'terminal': describir(term), 'error': str(exc)})
    salida['terminales_fuera_rango_tension'].sort(key=lambda x: abs(x['tension_pu'] - 1.0), reverse=True)

    if ejecutar:
        salida['duracion_flujo_ms'] = duracion_flujo_ms
        salida['mostrar_en_interfaz'] = mostrar_en_interfaz
        if mostrar_en_interfaz:
            try:
                app.PrintInfo(
                    'MCP Flujo en vivo: %s ms | %d lineas (%d > %.1f%%) | %d trafos (%d > %.1f%%) | %d barras fuera de [%.2f, %.2f] p.u.'
                    % (duracion_flujo_ms, salida['lineas_analizadas'], len(salida['lineas_sobre_umbral']), umbral,
                       salida['transformadores_analizados'], len(salida['transformadores_sobre_umbral']), umbral,
                       len(salida['terminales_fuera_rango_tension']), v_min_pu, v_max_pu)
                )
                for item in salida['lineas_sobre_umbral'][:10]:
                    app.PrintWarn('  Sobrecarga linea: %s -> %.2f%%' % (item['nombre'], item['carga_porcentaje']))
                for item in salida['transformadores_sobre_umbral'][:10]:
                    app.PrintWarn('  Sobrecarga trafo: %s -> %.2f%%' % (item['nombre'], item['carga_porcentaje']))
            except Exception:
                pass
    return salida


def renombrar_elemento(app, proyecto_ruta, objeto_ruta, nombre_actual, nombre_nuevo):
    """Renombra un elemento tras validar proyecto, identidad y nombre anterior."""
    if not all(isinstance(x, str) and x.strip() for x in
               (proyecto_ruta, objeto_ruta, nombre_actual, nombre_nuevo)):
        raise ValueError('Se requieren rutas y nombres no vacios.')
    if any(x in nombre_nuevo for x in ('\\', '/', '.')):
        raise ValueError('El nuevo nombre no puede incluir barras ni puntos.')
    proyecto = app.GetActiveProject()
    if proyecto is None or str(proyecto.GetFullName()) != proyecto_ruta:
        raise ValueError('El proyecto activo no coincide con el solicitado.')
    encontrados = [x for x in (proyecto.GetContents('*.Elm*', 1) or [])
                   if str(x.GetFullName()) == objeto_ruta]
    if len(encontrados) != 1:
        raise ValueError('No se encontro un unico elemento con esa ruta.')
    objeto = encontrados[0]
    if str(objeto.loc_name) != nombre_actual:
        raise ValueError('El nombre actual cambio; vuelva a consultar.')
    padre = objeto.GetParent()
    for hermano in padre.GetContents('*.%s' % objeto.GetClassName(), 0) or []:
        if str(hermano.loc_name).casefold() == nombre_nuevo.casefold() and hermano != objeto:
            raise ValueError('Ya existe un elemento de la misma clase con ese nombre.')
    objeto.SetAttribute('loc_name', nombre_nuevo)
    if str(objeto.loc_name) != nombre_nuevo:
        raise RuntimeError('PowerFactory no confirmo el nuevo nombre; revise el objeto.')
    return {'antes': {'ruta': objeto_ruta, 'nombre': nombre_actual},
            'despues': describir(objeto)}


def configurar_opc_prueba(app, ejecutar_enlace=True):
    """Crea y configura ComOpc (OPC UA Link) y un punto StaExtdatmea en la copia de prueba."""
    proyecto = app.GetActiveProject()
    caso = app.GetActiveStudyCase()
    if proyecto is None or caso is None:
        raise RuntimeError('Se requiere proyecto y caso de estudio activos.')

    existentes = caso.GetContents('*.ComOpc') or []
    creado_opc = False
    if existentes:
        com_opc = existentes[0]
    else:
        com_opc = caso.CreateObject('ComOpc', 'OPC UA Link')
        creado_opc = True
    if com_opc is None:
        raise RuntimeError('No se pudo obtener ni crear el objeto ComOpc en el Study Case.')

    ajustes_opc = {
        'iopt_type': 0,
        'sComputerUrl': 'opc.tcp://127.0.0.1',
        'sServerName': 'freeopcua/server/',
        'iPort': 4842,
        'rootPath': 'Objects',
        'iopt_auth': 0,
    }
    aplicados = {}
    errores_ajustes = {}
    for attr, val in ajustes_opc.items():
        try:
            com_opc.SetAttribute(attr, val)
            aplicados[attr] = com_opc.GetAttribute(attr)
        except Exception as exc:
            errores_ajustes[attr] = str(exc)

    redes = app.GetCalcRelevantObjects('*.ElmNet') or proyecto.GetContents('*.ElmNet', 1) or []
    medicion_info = None
    contenedor_mea = caso
    meas_existentes = [m for m in (proyecto.GetContents('*.StaExtdatmea', 1) or [])
                       if str(m.loc_name) == 'MCP_Prueba_Mea']
    creada_mea = False
    mea = meas_existentes[0] if meas_existentes else None
    if mea is None:
        for candidato in [caso] + [r for r in (proyecto.GetContents('*.ElmNet', 1) or [])
                                   if 'Summary Grid' not in str(r.GetFullName())]:
            try:
                mea = candidato.CreateObject('StaExtdatmea', 'MCP_Prueba_Mea')
            except Exception:
                mea = None
            if mea is not None:
                creada_mea = True
                break
    if mea is not None:
        try:
            mea.SetAttribute('sTagID', 'MCP_Prueba')
            mea.SetAttribute('for_name', 'MCP_Prueba')
            mea.SetAttribute('i_dat', 3)  # REAL
            mea.SetAttribute('deadband', 0.0)
            if hasattr(mea, 'SetStatusBit'):
                mea.SetStatusBit(536870912)  # Read flag (OPC -> PF)
            try:
                com_opc.SetAttribute('tagSet', mea)
            except Exception:
                pass
            medicion_info = {
                'objeto': describir(mea),
                'creado': creada_mea,
                'sTagID': str(mea.GetAttribute('sTagID')),
                'raw_value': mea.GetAttribute('val_raw') if hasattr(mea, 'val_raw') else None,
            }
        except Exception as exc:
            medicion_info = {'objeto': describir(mea), 'creado': creada_mea, 'error': str(exc)}

    pruebas = {}
    if mea is not None:
        try:
            pruebas['valor_Mea_antes_ReceiveData'] = mea.GetAttribute('Mea')
        except Exception as exc:
            pruebas['error_Mea_antes'] = str(exc)

    if hasattr(com_opc, 'IsConnected'):
        try:
            pruebas['estaba_conectado'] = bool(com_opc.IsConnected())
        except Exception as exc:
            pruebas['error_estaba_conectado'] = str(exc)

    if ejecutar_enlace and not pruebas.get('estaba_conectado'):
        try:
            pruebas['codigo_Execute'] = com_opc.Execute()
        except Exception as exc:
            pruebas['error_Execute'] = str(exc)

    if hasattr(com_opc, 'ReceiveData'):
        try:
            pruebas['codigo_ReceiveData'] = com_opc.ReceiveData()
        except Exception as exc:
            pruebas['error_ReceiveData'] = str(exc)

    if mea is not None:
        try:
            pruebas['valor_Mea_despues_ReceiveData'] = mea.GetAttribute('Mea')
        except Exception as exc:
            pruebas['error_Mea_despues'] = str(exc)

    # Ejecutar flujo de carga de prueba y resumir lineas
    try:
        pruebas['flujo_lineas'] = analizar_lineas(app, umbral=80.0, ejecutar=True)
    except Exception as exc:
        pruebas['error_flujo'] = str(exc)

    if hasattr(com_opc, 'IsConnected'):
        try:
            pruebas['IsConnected'] = bool(com_opc.IsConnected())
        except Exception as exc:
            pruebas['error_IsConnected'] = str(exc)

    app.PrintPlain('MCP: ComOpc configurado y probado en %s.' % caso.GetFullName())
    return {
        'capturado_unix': time.time(),
        'proyecto': describir(proyecto),
        'caso_estudio': describir(caso),
        'com_opc': describir(com_opc),
        'creado_com_opc': creado_opc,
        'ajustes_aplicados': aplicados,
        'errores_ajustes': errores_ajustes,
        'medicion_prueba': medicion_info,
        'pruebas_conexion': pruebas,
    }


def modificar_cargas(app, nombres=None, terminales=None, factor_escala=None,
                     plini=None, qlini=None, outserv=None, todas=False,
                     ejecutar_flujo=True, umbral=80.0):
    """Modifica cargas (ElmLod) en la copia MCP PRUEBA* y opcionalmente recalcula el flujo."""
    proyecto = app.GetActiveProject()
    caso = app.GetActiveStudyCase()
    if proyecto is None or caso is None:
        raise RuntimeError('Se requiere proyecto y caso de estudio activos.')
    cargas = app.GetCalcRelevantObjects('*.ElmLod') or []
    nombres_set = set(nombres or [])
    terminales_set = set(terminales or [])
    if not nombres_set and not terminales_set and not todas:
        raise ValueError('Especifique nombres, terminales o todas=True para seleccionar cargas.')

    modificadas = []
    for carga in cargas:
        nom = str(carga.loc_name)
        ruta = str(carga.GetFullName())
        try:
            bus = carga.GetAttribute('r:bus1:e:cBusBar')
            nom_bus = str(bus.loc_name) if bus is not None else None
        except Exception:
            nom_bus = None
        if not todas:
            if not ((nom in nombres_set) or (ruta in nombres_set) or (nom_bus and nom_bus in terminales_set)):
                continue
        antes = {
            'nombre': nom,
            'ruta': ruta,
            'terminal': nom_bus,
            'plini': float(carga.GetAttribute('plini')),
            'qlini': float(carga.GetAttribute('qlini')),
            'outserv': int(carga.GetAttribute('outserv')),
        }
        if factor_escala is not None:
            carga.SetAttribute('plini', float(antes['plini']) * float(factor_escala))
            carga.SetAttribute('qlini', float(antes['qlini']) * float(factor_escala))
        if plini is not None:
            carga.SetAttribute('plini', float(plini))
        if qlini is not None:
            carga.SetAttribute('qlini', float(qlini))
        if outserv is not None:
            carga.SetAttribute('outserv', int(outserv))
        despues = {
            'nombre': str(carga.loc_name),
            'ruta': str(carga.GetFullName()),
            'terminal': nom_bus,
            'plini': float(carga.GetAttribute('plini')),
            'qlini': float(carga.GetAttribute('qlini')),
            'outserv': int(carga.GetAttribute('outserv')),
        }
        modificadas.append({'antes': antes, 'despues': despues})

    resultado = {
        'capturado_unix': time.time(),
        'proyecto': describir(proyecto),
        'caso_estudio': describir(caso),
        'total_cargas_modificadas': len(modificadas),
        'cargas_modificadas': modificadas,
    }
    if ejecutar_flujo:
        resultado['flujo_lineas'] = analizar_lineas(app, umbral=umbral, ejecutar=True)
    return resultado


def ejecutar_python_dinamico(app, codigo, permitir_fuera_de_prueba=True):
    """Ejecuta codigo Python arbitrario sobre la sesion activa de PowerFactory en cualquier proyecto."""
    if not isinstance(codigo, str) or not codigo.strip():
        raise ValueError('Se requiere codigo Python no vacio.')
    proyecto = app.GetActiveProject()
    caso = app.GetActiveStudyCase()
    entorno = {
        '__builtins__': __builtins__,
        'powerfactory': powerfactory,
        'app': app,
        'proyecto': proyecto,
        'caso': caso,
        'describir': describir,
        'detalle': detalle,
        'capturar': capturar,
        'inventariar': inventariar,
        'analizar_lineas': analizar_lineas,
        'modificar_cargas': modificar_cargas,
        'resultado': None,
    }
    exec(codigo, entorno, entorno)
    proyecto_post = app.GetActiveProject()
    caso_post = app.GetActiveStudyCase()
    return {
        'capturado_unix': time.time(),
        'proyecto': describir(proyecto_post),
        'caso_estudio': describir(caso_post),
        'resultado': entorno.get('resultado'),
    }


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
