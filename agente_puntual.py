"""Agente MCP en sesion grafica: atiende solicitudes de inmediato y mantiene escucha en vivo con refresco Qt."""
import ctypes
import importlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import powerfactory
import capturar_contexto
import agente_temporal

# PowerFactory mantiene modulos importados entre ejecuciones del ComPython.
importlib.reload(capturar_contexto)
importlib.reload(agente_temporal)
from agente_temporal import CARPETA, atender

DURACION_SESION_SEGUNDOS = 14400  # 4 horas de escucha continua


def solicitar_parada_por_teclado():
    """Ctrl+Alt+F12 detiene la escucha solo con PowerFactory en primer plano."""
    try:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        ventana = user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ventana, ctypes.byref(pid))
        if pid.value != os.getpid():
            return False
        return all(user32.GetAsyncKeyState(tecla) & 0x8000 for tecla in (0x11, 0x12, 0x7B))
    except (AttributeError, OSError):
        return False


def cargar_process_events():
    """Obtiene QCoreApplication::processEvents de Qt5Core_pf.dll para refrescar la GUI en vivo."""
    try:
        qt = ctypes.CDLL('Qt5Core_pf.dll')
        simbolo = '?processEvents@QCoreApplication@pf@@SAXV?$QFlags@W4ProcessEventsFlag@QEventLoop@pf@@@2@H@Z'
        fn = getattr(qt, simbolo)
        fn.argtypes = [ctypes.c_int, ctypes.c_int]
        fn.restype = None
        return fn
    except Exception:
        return None


def restaurar_cursor_ocupado():
    """Quita una sola vez el cursor de espera de Qt al iniciar la escucha."""
    try:
        qt = ctypes.CDLL('Qt5Gui_pf.dll')
        obtener = getattr(qt, '?overrideCursor@QGuiApplication@pf@@SAPEAVQCursor@2@XZ')
        obtener.restype = ctypes.c_void_p
        cursor = obtener()
        if not cursor:
            return False
        forma = getattr(qt, '?shape@QCursor@pf@@QEBA?AW4CursorShape@Qt@2@XZ')
        forma.argtypes = [ctypes.c_void_p]
        forma.restype = ctypes.c_int
        if forma(cursor) not in (3, 16):  # Qt::WaitCursor y Qt::BusyCursor
            return False
        restaurar = getattr(qt, '?restoreOverrideCursor@QGuiApplication@pf@@SAXXZ')
        restaurar.argtypes = []
        restaurar.restype = None
        restaurar()
        return True
    except (AttributeError, OSError):
        return False


def refrescar_diagrama_al_activar(app):
    """Redibuja la página activa o abre el único diagrama disponible."""
    try:
        tablero = app.GetGraphicsBoard()
        pagina = tablero.GetActivePage()
        if not pagina:
            carpeta = app.GetProjectFolder('dia')
            diagramas = carpeta.GetContents('*.IntGrfnet', 1) if carpeta else []
            if len(diagramas) == 1:
                pagina = tablero.AddPage(diagramas[0])
        if pagina:
            app.SetGraphicUpdate(1)
            app.Rebuild(1)
            tablero.ZoomAll()
    except Exception as exc:
        app.PrintWarn('MCP: no se pudo refrescar el diagrama: %s' % exc)


def ruta_proyecto_activo(app):
    proyecto = app.GetActiveProject()
    return proyecto.GetFullName() if proyecto else None


def main():
    app = powerfactory.GetApplication()
    if app is None:
        raise RuntimeError('Ejecute el agente dentro de PowerFactory.')
    CARPETA.mkdir(exist_ok=True)
    bandera_parar = CARPETA / 'detener_timer'
    if bandera_parar.exists():
        try:
            bandera_parar.unlink()
        except OSError:
            pass

    process_events = cargar_process_events()
    app.PrintInfo('MCP: sesion de control en vivo activa (procesando eventos graficos en tiempo real).')
    restaurar_cursor_ocupado()
    # Reactiva el redibujado antes de iniciar la escucha continua.
    app.SetGraphicUpdate(1)
    app.Rebuild(1)
    proyecto_anterior = ruta_proyecto_activo(app)

    limite = time.monotonic() + DURACION_SESION_SEGUNDOS
    ultimo_latido = 0.0
    try:
        while time.monotonic() < limite:
            if solicitar_parada_por_teclado():
                app.PrintInfo('MCP: parada manual solicitada con Ctrl+Alt+F12.')
                break
            if bandera_parar.exists():
                try:
                    bandera_parar.unlink()
                except OSError:
                    pass
                break

            peticiones = sorted(CARPETA.glob('peticion_*.json'), key=lambda p: p.stat().st_mtime)
            if peticiones:
                for peticion in peticiones[:10]:
                    atender(app, peticion)
                    if process_events is not None:
                        try:
                            process_events(0, 50)
                        except Exception:
                            pass

            proyecto_actual = ruta_proyecto_activo(app)
            if proyecto_actual != proyecto_anterior:
                proyecto_anterior = proyecto_actual
                if proyecto_actual:
                    refrescar_diagrama_al_activar(app)

            ahora = time.time()
            if ahora - ultimo_latido >= 1.0:
                ultimo_latido = ahora
                try:
                    (CARPETA / 'latido_timer.json').write_text(
                        json.dumps({'latido_unix': ahora, 'pid': os.getpid(), 'qt_events': process_events is not None}),
                        encoding='utf-8'
                    )
                except OSError:
                    pass

            if process_events is not None:
                try:
                    process_events(0, 30)
                except Exception:
                    pass
            time.sleep(0.02)
    finally:
        app.PrintInfo('MCP: sesion de control en vivo finalizada; interfaz liberada.')


if __name__ == '__main__':
    main()
