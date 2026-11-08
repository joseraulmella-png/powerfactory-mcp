"""Representación de elementos existentes en el diagrama de red activo."""


def representar(app, proyecto_ruta, diagrama_ruta, elemento_ruta):
    proyecto = app.GetActiveProject()
    if not proyecto or proyecto.GetFullName() != proyecto_ruta:
        raise ValueError('El proyecto activo no coincide con la ruta indicada.')
    if not all(isinstance(x, str) and x for x in (diagrama_ruta, elemento_ruta)):
        raise ValueError('Se requieren las rutas exactas del diagrama y elemento.')
    carpeta = app.GetProjectFolder('dia')
    diagramas = [x for x in (carpeta.GetContents('*.IntGrfnet', 1) if carpeta else [])
                 if x.GetFullName() == diagrama_ruta]
    tablero = app.GetGraphicsBoard()
    pagina = tablero.GetActivePage()
    if len(diagramas) != 1 or not pagina or pagina.loc_name != diagramas[0].loc_name:
        raise ValueError('El diagrama indicado debe estar abierto y activo.')
    candidatos = [x for x in (proyecto.GetContents('*.Elm*', 1) or [])
                  if x.GetFullName() == elemento_ruta]
    if len(candidatos) != 1:
        raise ValueError('No se encontró el elemento eléctrico en el proyecto activo.')
    elemento, diagrama = candidatos[0], diagramas[0]

    def referencias():
        return [o.GetFullName() for o in diagrama.GetContents('*.IntGrf', 1)
                if o.GetAttribute('pDataObj') == elemento]

    existentes = referencias()
    if existentes:
        return {'elemento': elemento_ruta, 'clase': elemento.GetClassName(),
                'representaciones': existentes, 'ya_representado': True,
                'cambios': False}
    comando = app.GetFromStudyCase('ComSgllayout')
    if not comando:
        raise RuntimeError('No se encontró el comando de disposición gráfica.')
    antes = {o.GetFullName() for o in diagrama.GetContents('*.IntGrf', 1)}
    accion, modo = comando.GetAttribute('iAction'), comando.GetAttribute('insertionMode')
    try:
        tablero.Unfreeze()
        comando.SetAttribute('iAction', 1)
        comando.SetAttribute('insertionMode', 1)
        codigo = comando.Execute()
    finally:
        comando.SetAttribute('iAction', accion)
        comando.SetAttribute('insertionMode', modo)
    nuevos = [o.GetFullName() for o in diagrama.GetContents('*.IntGrf', 1)
              if o.GetFullName() not in antes]
    encontrados = referencias()
    app.SetGraphicUpdate(1)
    app.Rebuild(1)
    return {'elemento': elemento_ruta, 'clase': elemento.GetClassName(),
            'representaciones': encontrados, 'ya_representado': False,
            'representado': bool(encontrados), 'codigo_layout': codigo,
            'objetos_graficos_agregados': nuevos,
            'nota': 'El comando puede incorporar otros elementos ausentes; revise los gráficos agregados.'}
