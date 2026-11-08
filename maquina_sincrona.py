"""Creación explícita de una máquina síncrona y su representación gráfica."""
import math


def crear(app, proyecto_ruta, terminal_ruta, diagrama_ruta, nombre, potencia_nominal_mva,
          potencia_activa_mw, potencia_reactiva_mvar=0.0, revertir_en_error=True,
          limpiar_graficos_extra=False):
    proyecto = app.GetActiveProject()
    if not proyecto or proyecto.GetFullName() != proyecto_ruta:
        raise ValueError('El proyecto activo no coincide con la ruta indicada.')
    if not nombre or any(c in nombre for c in '\\/*?'):
        raise ValueError('Nombre inválido para el generador.')
    valores = (potencia_nominal_mva, potencia_activa_mw, potencia_reactiva_mvar)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in valores):
        raise ValueError('Las potencias deben ser números finitos.')
    if potencia_nominal_mva <= 0 or math.hypot(potencia_activa_mw, potencia_reactiva_mvar) > potencia_nominal_mva:
        raise ValueError('La potencia nominal debe cubrir las potencias activa y reactiva.')
    terminales = [t for t in (app.GetCalcRelevantObjects('*.ElmTerm') or [])
                  if t.GetFullName() == terminal_ruta]
    if len(terminales) != 1:
        raise ValueError('No se encontró un terminal relevante con la ruta exacta.')
    terminal = terminales[0]
    red = terminal.GetParent()
    if red.GetClassName() != 'ElmNet':
        raise ValueError('El terminal debe pertenecer directamente a una red.')
    if any(o.loc_name == nombre for o in red.GetContents('*.ElmSym', 0)):
        raise ValueError('Ya existe una máquina con ese nombre en la red.')
    biblioteca = app.GetProjectFolder('equip')
    if not biblioteca:
        raise ValueError('No se encontró la biblioteca de tipos del proyecto.')
    tipo_nombre = nombre + ' Tipo'
    if any(o.loc_name == tipo_nombre for o in biblioteca.GetContents('*.TypSym', 0)):
        raise ValueError('Ya existe un tipo con ese nombre.')
    # El diagrama activo debe pertenecer a este proyecto; no se elige uno al azar.
    tablero = app.GetGraphicsBoard()
    pagina = tablero.GetActivePage()
    diagramas = app.GetProjectFolder('dia')
    coincidencias = [d for d in (diagramas.GetContents('*.IntGrfnet', 1) if diagramas else [])
                     if d.GetFullName() == diagrama_ruta]
    actual_dia = app.GetCurrentDiagram() if hasattr(app, 'GetCurrentDiagram') else None
    if not pagina or len(coincidencias) != 1 or (pagina.loc_name != coincidencias[0].loc_name and actual_dia != coincidencias[0]):
        raise ValueError('Abra el diagrama de red del proyecto antes de crear la máquina.')
    diagrama = coincidencias[0]

    objetos_creados = []
    antes_graficos = {o.GetFullName() for o in (diagrama.GetContents('*.IntGrf', 1) or [])}
    try:
        tipo = biblioteca.CreateObject('TypSym', tipo_nombre)
        if not tipo:
            raise RuntimeError('No se pudo crear el tipo.')
        objetos_creados.append(tipo)
        tipo.SetAttribute('sgn', potencia_nominal_mva)
        tipo.SetAttribute('ugn', terminal.GetAttribute('uknom'))
        tipo.SetAttribute('cosn', 1.0)
        for attr_din, val_din in (
            ('xd', 1.8), ('xq', 1.7), ('xds', 0.25), ('xqs', 0.25),
            ('xdss', 0.18), ('xqss', 0.18), ('xl', 0.1),
            ('td0s', 5.0), ('tq0s', 1.0), ('td0ss', 0.03), ('tq0ss', 0.05),
            ('tag', 4.0), ('rstr', 0.005), ('x0', 0.1), ('x2', 0.18),
        ):
            if tipo.HasAttribute(attr_din):
                try:
                    tipo.SetAttribute(attr_din, val_din)
                except Exception:
                    pass
        maquina = red.CreateObject('ElmSym', nombre)
        if not maquina:
            raise RuntimeError('No se pudo crear la máquina.')
        objetos_creados.append(maquina)
        maquina.SetAttribute('typ_id', tipo)
        maquina.SetAttribute('pgini', potencia_activa_mw)
        maquina.SetAttribute('qgini', potencia_reactiva_mvar)
        cubiculo = terminal.CreateObject('StaCubic', nombre + ' Cubiculo')
        if not cubiculo:
            raise RuntimeError('No se pudo crear el cubículo.')
        objetos_creados.append(cubiculo)
        maquina.SetAttribute('bus1', cubiculo)
        if maquina.GetAttribute('bus1').GetAttribute('cterm').GetFullName() != terminal_ruta:
            raise RuntimeError('No se pudo verificar la conexión.')
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
                            if o.GetAttribute('pDataObj') == maquina]
        if not representaciones:
            raise RuntimeError('No se encontró una representación gráfica de la máquina.')
        graficos_extra_eliminados = []
        if limpiar_graficos_extra:
            for g in todos_graficos:
                ruta_g = g.GetFullName()
                if ruta_g not in antes_graficos and g.GetAttribute('pDataObj') not in (maquina, terminal):
                    try:
                        if g.Delete() == 0:
                            graficos_extra_eliminados.append(ruta_g)
                    except Exception:
                        pass
        app.SetGraphicUpdate(1)
        app.Rebuild(1)
        return {'maquina': maquina.GetFullName(), 'terminal': terminal_ruta,
                'tipo': tipo.GetFullName(), 'cubiculo': cubiculo.GetFullName(),
                'diagramas': representaciones, 'potencia_nominal_mva': potencia_nominal_mva,
                'potencia_activa_mw': potencia_activa_mw,
                'potencia_reactiva_mvar': potencia_reactiva_mvar,
                'graficos_extra_eliminados': graficos_extra_eliminados,
                'nota': 'Tipo con valores de prueba por defecto; no se ejecutó flujo. El layout puede añadir otros elementos ausentes.'}
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
