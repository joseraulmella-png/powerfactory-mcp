"""Prueba interactiva de conexion externa, sin modificar datos de proyecto."""
import os
import sys
import json

raiz = r'C:\Program Files\DIgSILENT\PowerFactory 2021 SP2'
os.add_dll_directory(raiz)
sys.path.insert(0, os.path.join(raiz, 'Python', '3.9'))
import powerfactory

try:
    app = powerfactory.GetApplicationExt()
    print('Conexion establecida; usuario:', app.GetCurrentUser().loc_name, flush=True)
    app.Show()
    print('Comandos disponibles: activar, contexto, salir', flush=True)
    for comando in sys.stdin:
        comando = comando.strip()
        if comando == 'salir':
            break
        if comando == 'activar':
            print('Activacion:', app.ActivateProject('EG 39063'), flush=True)
        elif comando == 'contexto':
            proyecto = app.GetActiveProject()
            caso = app.GetActiveStudyCase()
            print(json.dumps({'proyecto': proyecto.loc_name if proyecto else None,
                              'caso': caso.loc_name if caso else None}), flush=True)
        else:
            print('Comando desconocido', flush=True)
except Exception as exc:
    print('Error:', type(exc).__name__, str(exc), flush=True)
    sys.exit(1)
