"""Creación explícita de una máquina síncrona y su representación gráfica."""
import math


def crear(app, proyecto_ruta, terminal_ruta, diagrama_ruta, nombre, potencia_nominal_mva,
          potencia_activa_mw, potencia_reactiva_mvar=0.0):
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
    if not pagina or len(coincidencias) != 1 or pagina.loc_name != coincidencias[0].loc_name:
        raise ValueError('Abra el diagrama de red del proyecto antes de crear la máquina.')
    diagrama = coincidencias[0]

    creados = []
    try:
        tipo = biblioteca.CreateObject('TypSym', tipo_nombre)
        if not tipo:
            raise RuntimeError('No se pudo crear el tipo.')
        creados.append(tipo.GetFullName())
        tipo.SetAttribute('sgn', potencia_nominal_mva)
        tipo.SetAttribute('ugn', terminal.GetAttribute('uknom'))
        tipo.SetAttribute('cosn', 1.0)
        maquina = red.CreateObject('ElmSym', nombre)
        if not maquina:
            raise RuntimeError('No se pudo crear la máquina.')
        creados.append(maquina.GetFullName())
        maquina.SetAttribute('typ_id', tipo)
        maquina.SetAttribute('pgini', potencia_activa_mw)
        maquina.SetAttribute('qgini', potencia_reactiva_mvar)
        cubiculo = terminal.CreateObject('StaCubic', nombre + ' Cubiculo')
        if not cubiculo:
            raise RuntimeError('No se pudo crear el cubículo.')
        creados.append(cubiculo.GetFullName())
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
        representaciones = [o.GetFullName() for o in diagrama.GetContents('*.IntGrf', 1)
                            if o.GetAttribute('pDataObj') == maquina]
        if not representaciones:
            raise RuntimeError('No se encontró una representación gráfica de la máquina.')
        app.SetGraphicUpdate(1)
        app.Rebuild(1)
        return {'maquina': maquina.GetFullName(), 'terminal': terminal_ruta,
                'tipo': tipo.GetFullName(), 'cubiculo': cubiculo.GetFullName(),
                'diagramas': representaciones, 'potencia_nominal_mva': potencia_nominal_mva,
                'potencia_activa_mw': potencia_activa_mw,
                'potencia_reactiva_mvar': potencia_reactiva_mvar,
                'nota': 'Tipo con valores de prueba por defecto; no se ejecutó flujo. El layout puede añadir otros elementos ausentes.'}
    except Exception as exc:
        raise RuntimeError('Creación incompleta: %s. Objetos creados que requieren revisión: %s' % (exc, creados)) from exc
