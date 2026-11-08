"""Proceso de PowerFactory: una instancia externa, consultas JSON por stdin."""
import json
import os
import sys
import traceback

raiz = os.environ.get('POWERFACTORY_DIR', r'C:\Program Files\DIgSILENT\PowerFactory 2021 SP2')
if hasattr(os, 'add_dll_directory'):
    os.add_dll_directory(raiz)
sys.path.insert(0, os.path.join(raiz, 'Python', '%s.%s' % sys.version_info[:2]))
import powerfactory
from capturar_contexto import capturar, inventariar, renombrar_elemento, analizar_lineas


def main():
    app = None
    for linea in sys.stdin:
        ident = None
        try:
            req = json.loads(linea)
            ident = req['id']
            accion = req['accion']
            if accion == 'iniciar':
                if app is None:
                    app = powerfactory.GetApplicationExt()
                    if req.get('mostrar', False):
                        app.Show()
                valor = {'usuario': str(app.GetCurrentUser().loc_name), 'contexto': capturar(app)}
            elif app is None:
                raise RuntimeError('Primero inicie la sesion de PowerFactory.')
            elif accion == 'activar_proyecto':
                nombre = req.get('proyecto')
                if not isinstance(nombre, str) or not nombre.strip():
                    raise ValueError('Nombre de proyecto requerido.')
                codigo = app.ActivateProject(nombre)
                if codigo != 0:
                    raise RuntimeError('No se pudo activar el proyecto; codigo %s.' % codigo)
                valor = capturar(app)
            elif accion == 'contexto':
                valor = capturar(app)
            elif accion == 'inventario':
                valor = inventariar(app)
            elif accion == 'analizar_lineas':
                ejecutar = req.get('ejecutar', False)
                if not isinstance(ejecutar, bool):
                    raise ValueError('ejecutar debe ser booleano.')
                valor = analizar_lineas(app, req.get('umbral', 100.0), ejecutar)
            elif accion == 'renombrar':
                valor = renombrar_elemento(app, req.get('proyecto_ruta'), req.get('objeto_ruta'),
                                           req.get('nombre_actual'), req.get('nombre_nuevo'))
                coincidencias = [x for x in (app.GetActiveProject().GetContents('*.Elm*', 1) or [])
                                 if str(x.GetFullName()) == valor['despues']['ruta']]
                if len(coincidencias) != 1 or str(coincidencias[0].loc_name) != req['nombre_nuevo']:
                    raise RuntimeError('Cambio aplicado, pero no se pudo verificar en una nueva consulta. Revise el proyecto antes de reintentar.')
                valor['verificado_en_nueva_consulta'] = True
            else:
                raise ValueError('Accion no permitida.')
            respuesta = {'id': ident, 'ok': True, 'resultado': valor}
        except Exception as exc:
            respuesta = {'id': ident, 'ok': False, 'error': str(exc), 'tipo': type(exc).__name__}
            traceback.print_exc(file=sys.stderr)
        print(json.dumps(respuesta, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
