"""Creación transaccional de cargas (ElmLod) y sistemas fotovoltaicos (ElmPvsys) con representación gráfica."""
import math


def crear(app, proyecto_ruta, terminal_ruta, diagrama_ruta, clase, nombre,
          potencia_activa_mw, potencia_reactiva_mvar=0.0, potencia_nominal_kva=None,
          revertir_en_error=True, limpiar_graficos_extra=False):
    if clase not in ('ElmLod', 'ElmPvsys'):
        raise ValueError("La clase debe ser 'ElmLod' o 'ElmPvsys'.")
    proyecto = app.GetActiveProject()
    if not proyecto or proyecto.GetFullName() != proyecto_ruta:
        raise ValueError('El proyecto activo no coincide con la ruta indicada.')
    if not nombre or any(c in nombre for c in '\\/*?'):
        raise ValueError('Nombre inválido para el elemento.')
    for v in (potencia_activa_mw, potencia_reactiva_mvar):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError('Las potencias deben ser números finitos.')
    if potencia_nominal_kva is not None:
        if isinstance(potencia_nominal_kva, bool) or not isinstance(potencia_nominal_kva, (int, float)) or not math.isfinite(potencia_nominal_kva) or potencia_nominal_kva <= 0:
            raise ValueError('La potencia nominal en kVA debe ser un número finito positivo.')

    terminales = [t for t in (app.GetCalcRelevantObjects('*.ElmTerm') or [])
                  if t.GetFullName() == terminal_ruta]
    if len(terminales) != 1:
        raise ValueError('No se encontró un terminal relevante con la ruta exacta.')
    terminal = terminales[0]
    red = terminal.GetParent()
    if red.GetClassName() != 'ElmNet':
        raise ValueError('El terminal debe pertenecer directamente a una red.')
    if any(o.loc_name == nombre for o in (red.GetContents('*.%s' % clase, 0) or [])):
        raise ValueError('Ya existe un elemento %s con ese nombre en la red.' % clase)

    tablero = app.GetGraphicsBoard()
    pagina = tablero.GetActivePage()
    diagramas = app.GetProjectFolder('dia')
    coincidencias = [d for d in (diagramas.GetContents('*.IntGrfnet', 1) if diagramas else [])
                     if d.GetFullName() == diagrama_ruta]
    actual_dia = app.GetCurrentDiagram() if hasattr(app, 'GetCurrentDiagram') else None
    if not pagina or len(coincidencias) != 1 or (pagina.loc_name != coincidencias[0].loc_name and actual_dia != coincidencias[0]):
        raise ValueError('Abra el diagrama de red del proyecto antes de crear el elemento.')
    diagrama = coincidencias[0]

    objetos_creados = []
    antes_graficos = {o.GetFullName() for o in (diagrama.GetContents('*.IntGrf', 1) or [])}
    try:
        elemento = red.CreateObject(clase, nombre)
        if not elemento:
            raise RuntimeError('No se pudo crear el elemento %s.' % clase)
        objetos_creados.append(elemento)
        if clase == 'ElmLod':
            elemento.SetAttribute('plini', float(potencia_activa_mw))
            elemento.SetAttribute('qlini', float(potencia_reactiva_mvar))
        else:
            s_aparente_kva = math.hypot(potencia_activa_mw, potencia_reactiva_mvar) * 1000.0
            sgn_kva = float(potencia_nominal_kva) if potencia_nominal_kva is not None else max(100.0, round(s_aparente_kva * 1.1, 2))
            if sgn_kva < s_aparente_kva:
                raise ValueError('La potencia nominal kVA del sistema FV debe cubrir la potencia aparente.')
            try:
                elemento.SetAttribute('sgn', sgn_kva)
            except Exception:
                pass
            elemento.SetAttribute('pgini', float(potencia_activa_mw * 1000.0))
            elemento.SetAttribute('qgini', float(potencia_reactiva_mvar * 1000.0))

        cubiculo = terminal.CreateObject('StaCubic', nombre + ' Cubiculo')
        if not cubiculo:
            raise RuntimeError('No se pudo crear el cubículo.')
        objetos_creados.append(cubiculo)
        elemento.SetAttribute('bus1', cubiculo)
        if elemento.GetAttribute('bus1').GetAttribute('cterm').GetFullName() != terminal_ruta:
            raise RuntimeError('No se pudo verificar la conexión al terminal.')

        comando = app.GetFromStudyCase('ComSgllayout')
        if not comando:
            raise RuntimeError('No se encontró el comando de disposición gráfica.')
        accion, modo = comando.GetAttribute('iAction'), comando.GetAttribute('insertionMode')
        try:
            tablero.Unfreeze()
            comando.SetAttribute('iAction', 1)
            comando.SetAttribute('insertionMode', 1)
            codigo = comando.Execute()
        finally:
            comando.SetAttribute('iAction', accion)
            comando.SetAttribute('insertionMode', modo)
        if codigo != 0:
            raise RuntimeError('Falló el comando de disposición gráfica: %s' % codigo)
        todos_graficos = diagrama.GetContents('*.IntGrf', 1) or []
        representaciones = [o.GetFullName() for o in todos_graficos
                            if o.GetAttribute('pDataObj') == elemento]
        if not representaciones:
            raise RuntimeError('No se encontró representación gráfica del elemento creado.')
        graficos_extra_eliminados = []
        if limpiar_graficos_extra:
            for g in todos_graficos:
                ruta_g = g.GetFullName()
                if ruta_g not in antes_graficos and g.GetAttribute('pDataObj') not in (elemento, terminal):
                    try:
                        if g.Delete() == 0:
                            graficos_extra_eliminados.append(ruta_g)
                    except Exception:
                        pass
        app.SetGraphicUpdate(1)
        app.Rebuild(1)
        return {
            'elemento': elemento.GetFullName(),
            'clase': clase,
            'terminal': terminal_ruta,
            'cubiculo': cubiculo.GetFullName(),
            'diagramas': representaciones,
            'potencia_activa_mw': potencia_activa_mw,
            'potencia_reactiva_mvar': potencia_reactiva_mvar,
            'graficos_extra_eliminados': graficos_extra_eliminados,
        }
    except Exception as exc:
        revertidos, pendientes = [], []
        if revertir_en_error:
            for g in (diagrama.GetContents('*.IntGrf', 1) or []):
                ruta_g = g.GetFullName()
                if ruta_g not in antes_graficos:
                    try:
                        if g.Delete() == 0:
                            revertidos.append(ruta_g)
                    except Exception:
                        pass
            for obj in reversed(objetos_creados):
                ruta_obj = obj.GetFullName()
                try:
                    if obj.Delete() == 0:
                        revertidos.append(ruta_obj)
                    else:
                        pendientes.append(ruta_obj)
                except Exception:
                    pendientes.append(ruta_obj)
            try:
                app.SetGraphicUpdate(1)
                app.Rebuild(1)
            except Exception:
                pass
        else:
            pendientes = [o.GetFullName() for o in objetos_creados]
        raise RuntimeError(
            'Creación incompleta: %s. Objetos revertidos: %s. Objetos pendientes de revisión: %s'
            % (exc, revertidos, pendientes)
        ) from exc
