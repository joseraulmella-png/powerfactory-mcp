"""Representación de elementos existentes en el diagrama de red activo."""


def _terminales_conectados(elemento):
    terminales = set()
    for attr in ('r:bus1:e:cBusBar', 'r:bus2:e:cBusBar', 'r:bushv:e:cBusBar', 'r:buslv:e:cBusBar'):
        try:
            bus = elemento.GetAttribute(attr)
            if bus is not None:
                terminales.add(bus)
        except Exception:
            pass
    return terminales


def representar(app, proyecto_ruta, diagrama_ruta, elemento_ruta, limpiar_graficos_extra=False):
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
    actual_dia = app.GetCurrentDiagram() if hasattr(app, 'GetCurrentDiagram') else None
    if len(diagramas) != 1 or not pagina or (pagina.loc_name != diagramas[0].loc_name and actual_dia != diagramas[0]):
        raise ValueError('El diagrama indicado debe estar abierto y activo.')
    candidatos = [x for x in (proyecto.GetContents('*.Elm*', 1) or [])
                  if x.GetFullName() == elemento_ruta]
    if len(candidatos) != 1:
        raise ValueError('No se encontró el elemento eléctrico en el proyecto activo.')
    elemento, diagrama = candidatos[0], diagramas[0]

    def referencias():
        return [o.GetFullName() for o in (diagrama.GetContents('*.IntGrf', 1) or [])
                if o.GetAttribute('pDataObj') == elemento]

    existentes = referencias()
    if existentes:
        return {'elemento': elemento_ruta, 'clase': elemento.GetClassName(),
                'representaciones': existentes, 'ya_representado': True,
                'cambios': False}
    comando = app.GetFromStudyCase('ComSgllayout')
    if not comando:
        raise RuntimeError('No se encontró el comando de disposición gráfica.')
    antes = {o.GetFullName() for o in (diagrama.GetContents('*.IntGrf', 1) or [])}
    accion, modo = comando.GetAttribute('iAction'), comando.GetAttribute('insertionMode')
    try:
        tablero.Unfreeze()
        comando.SetAttribute('iAction', 1)
        comando.SetAttribute('insertionMode', 1)
        codigo = comando.Execute()
    finally:
        comando.SetAttribute('iAction', accion)
        comando.SetAttribute('insertionMode', modo)
    permitidos = {elemento} | _terminales_conectados(elemento)
    eliminados = []
    if limpiar_graficos_extra:
        for o in (diagrama.GetContents('*.IntGrf', 1) or []):
            ruta_o = o.GetFullName()
            if ruta_o not in antes and o.GetAttribute('pDataObj') not in permitidos:
                try:
                    if o.Delete() == 0:
                        eliminados.append(ruta_o)
                except Exception:
                    pass
    nuevos = [o.GetFullName() for o in (diagrama.GetContents('*.IntGrf', 1) or [])
              if o.GetFullName() not in antes]
    encontrados = referencias()
    app.SetGraphicUpdate(1)
    app.Rebuild(1)
    return {'elemento': elemento_ruta, 'clase': elemento.GetClassName(),
            'representaciones': encontrados, 'ya_representado': False,
            'representado': bool(encontrados), 'codigo_layout': codigo,
            'objetos_graficos_agregados': nuevos,
            'graficos_extra_eliminados': eliminados,
            'nota': 'El comando puede incorporar otros elementos ausentes; revise los gráficos agregados.'}


def _obtener_diagrama_activo(app, diagrama_ruta=None):
    carpeta = app.GetProjectFolder('dia')
    todos = carpeta.GetContents('*.IntGrfnet', 1) if carpeta else []
    tablero = app.GetGraphicsBoard()
    pagina = tablero.GetActivePage() if tablero else None
    actual_dia = app.GetCurrentDiagram() if hasattr(app, 'GetCurrentDiagram') else None
    if actual_dia and actual_dia.GetClassName() == 'IntGrfnet':
        activo = actual_dia
    elif pagina:
        coincidencias = [d for d in todos if d.loc_name == pagina.loc_name]
        activo = coincidencias[0] if len(coincidencias) == 1 else None
    else:
        activo = None
    if not activo:
        raise ValueError('No hay un diagrama de red abierto y activo.')
    if diagrama_ruta and activo.GetFullName() != diagrama_ruta:
        raise ValueError('El diagrama indicado debe estar abierto y activo.')
    return activo


def marcar(app, nombre_o_ruta=None, elementos=None, escala=None, diagrama_ruta=None):
    """Selecciona uno o varios elementos en el diagrama activo con el resaltado azul nativo (app.MarkInGraphics)."""
    proyecto = app.GetActiveProject()
    if not proyecto:
        raise RuntimeError('No hay proyecto activo.')
    objetivos = []
    if isinstance(nombre_o_ruta, str) and nombre_o_ruta.strip():
        objetivos.append(nombre_o_ruta.strip())
    if isinstance(elementos, list):
        objetivos.extend(x.strip() for x in elementos if isinstance(x, str) and x.strip())
    if not objetivos:
        raise ValueError('Indique nombre_o_ruta o una lista de elementos para marcar en el diagrama.')
    objetivos_set = set(objetivos)
    todos = proyecto.GetContents('*.Elm*', 1) or []
    encontrados = [x for x in todos if x.GetFullName() in objetivos_set or x.loc_name in objetivos_set]
    if not encontrados:
        raise ValueError('No se encontraron los elementos indicados en el proyecto activo.')
    dia_activo = _obtener_diagrama_activo(app, diagrama_ruta)
    simbolos = []
    encontrados_set = set(encontrados)
    for g in (dia_activo.GetContents('*.IntGrf', 1) or []):
        obj = g.GetAttribute('pDataObj')
        if obj in encontrados_set:
            if escala is not None:
                g.SetAttribute('rSizeX', float(escala))
                g.SetAttribute('rSizeY', float(escala))
            simbolos.append({
                'elemento': obj.loc_name,
                'simbolo': g.GetFullName(),
                'x': round(float(g.GetAttribute('rCenterX')), 2),
                'y': round(float(g.GetAttribute('rCenterY')), 2),
            })
    if escala is not None:
        app.SetGraphicUpdate(1)
        app.Rebuild(1)
    app.MarkInGraphics(encontrados, 1)
    return {
        'diagrama': dia_activo.GetFullName(),
        'elementos_marcados': [o.GetFullName() for o in encontrados],
        'seleccion_diagrama': [o.GetFullName() for o in (app.GetDiagramSelection() or [])],
        'simbolos_y_coordenadas': simbolos,
    }


def _buscar_espacio_libre(dia, cx, cy, ancho=22.0, alto=10.0, ignorar_nombres=(), extra_ocupados=()):
    import math
    ocupados = list(extra_ocupados)
    for g in (dia.GetContents('*.IntGrf', 0) or []):
        if g.loc_name in ignorar_nombres:
            continue
        gx, gy = float(g.GetAttribute('rCenterX')), float(g.GetAttribute('rCenterY'))
        if gx > 1.0 or gy > 1.0:
            ocupados.append((gx, gy))
        for con in (g.GetContents('*.IntGrfcon', 0) or []):
            try:
                for vx, vy in zip(con.GetAttribute('rX') or [], con.GetAttribute('rY') or []):
                    if vx > 1.0 or vy > 1.0:
                        ocupados.append((float(vx), float(vy)))
            except Exception:
                pass
    mejor = (-9999.0, 0.0, cx - 18.0, cy + 8.0)
    for dist in range(12, 45, 3):
        for ang_deg in range(0, 360, 15):
            ang = math.radians(ang_deg)
            tx = cx + dist * math.cos(ang)
            ty = cy + dist * math.sin(ang)
            d_min = 9999.0
            for ox, oy in ocupados:
                dx = max(0.0, abs(tx - ox) - ancho / 2.0)
                dy = max(0.0, abs(ty - oy) - alto / 2.0)
                d = math.hypot(dx, dy)
                if d < d_min:
                    d_min = d
            score = d_min * 3.0 - dist * 0.25
            if score > mejor[0]:
                mejor = (score, d_min, round(tx, 2), round(ty, 2))
    return mejor[2], mejor[3], round(mejor[1], 2)


def anotar(app, nombre_o_ruta, incluir_etiqueta=True, incluir_potencias=True, diagrama_ruta=None):
    """Agrega etiqueta con flecha y/o cuadro de potencias en zona despejada del diagrama activo para el elemento indicado."""
    import math
    if not isinstance(incluir_etiqueta, bool) or not isinstance(incluir_potencias, bool):
        raise ValueError('incluir_etiqueta e incluir_potencias deben ser booleanos.')
    proyecto = app.GetActiveProject()
    if not proyecto:
        raise RuntimeError('No hay proyecto activo.')
    candidatos = [x for x in (proyecto.GetContents('*.Elm*', 1) or [])
                  if x.GetFullName() == nombre_o_ruta or x.loc_name == nombre_o_ruta]
    if not candidatos:
        raise ValueError('No se encontró el elemento en el proyecto activo.')
    elemento = candidatos[0]
    clase = elemento.GetClassName()
    dia = _obtener_diagrama_activo(app, diagrama_ruta)
    simbolos = [g for g in (dia.GetContents('*.IntGrf', 1) or [])
                if g.GetAttribute('pDataObj') == elemento and g.GetAttribute('sSymNam') != 'TBDummy']
    if not simbolos:
        raise ValueError('El elemento no tiene símbolo gráfico en el diagrama activo.')
    grf = simbolos[0]
    cx, cy = float(grf.GetAttribute('rCenterX')), float(grf.GetAttribute('rCenterY'))
    if not incluir_etiqueta and not incluir_potencias:
        return {
            'elemento': elemento.GetFullName(),
            'elemento_xy': [round(cx, 2), round(cy, 2)],
            'anotaciones': {},
            'cambios': False,
        }
    plantillas = [g for g in (dia.GetContents('*.IntGrf', 0) or [])
                  if g.GetAttribute('sSymNam') == 'TBDummy' and g.GetContents('*.IntFormsel', 0)]
    if not plantillas:
        raise RuntimeError('No se encontró plantilla TBDummy en el diagrama.')
    plantilla = plantillas[0]
    sn = chr(36) + 'N'
    nom_lbl = 'TB_Nombre_' + elemento.loc_name
    nom_pot = 'TB_Potencias_' + elemento.loc_name
    a_reemplazar = tuple(
        ([nom_pot] if incluir_potencias else []) +
        ([nom_lbl] if incluir_etiqueta else [])
    )
    for viejo in a_reemplazar:
        for g in (dia.GetContents(viejo + '.IntGrf', 0) or []):
            g.Delete()

    def crear_tb(nombre_tb, tx, ty, lineas_lstr, mostrar_marco, chars_ancho):
        tb = dia.AddCopy(plantilla, nombre_tb)
        tb.SetAttribute('pDataObj', elemento)
        tb.SetAttribute('rCenterX', tx)
        tb.SetAttribute('rCenterY', ty)
        tb.SetAttribute('iCol', 0)
        v = tb.GetContents('*.SetVitxt', 0)[0]
        v.SetAttribute('glvl', 3)
        v.SetAttribute('zlvl', 1)
        v.SetAttribute('iArrowVis', 1)
        v.SetAttribute('iBoxRefPt', -1)
        v.SetAttribute('sh_frame', 1 if mostrar_marco else 0)
        v.SetAttribute('iLines', len(lineas_lstr))
        v.SetAttribute('chars', chars_ancho)
        v.SetAttribute('rX1', cx)
        v.SetAttribute('rY1', cy)
        ux, uy = cx - tx, cy - ty
        norm = math.hypot(ux, uy) or 1.0
        v.SetAttribute('rX2', round(tx + (ux / norm) * 6.0, 2))
        v.SetAttribute('rY2', round(ty + (uy / norm) * 3.5, 2))
        fm = tb.GetContents('*.IntFormsel', 0)[0]
        for f in (fm.GetContents('*.IntForm', 0) or []):
            if f.GetAttribute('otarget') not in ('ElmNet', ''):
                f.SetAttribute('otarget', clase)
            if f.GetAttribute('subtar') not in ('ElmNet', ''):
                f.SetAttribute('subtar', clase)
            f.SetAttribute('extLstr', 0)
            f.SetAttribute('lstr', lineas_lstr)
        return tb.GetFullName()

    creados = {}
    extra = []
    if incluir_potencias:
        px, py, clr_p = _buscar_espacio_libre(dia, cx, cy, 24.0, 11.0, a_reemplazar)
        bus_attr = 'bushv' if clase == 'ElmTr2' else 'bus1'
        lineas_p = [
            '# ' + sn + ',@:loc_name',
            '#=#.#### # ' + sn + (',@:~m:P:%s,@:m:P:%s,@:[m:P:%s' % (bus_attr, bus_attr, bus_attr)),
            '#=#.#### # ' + sn + (',@:~m:Q:%s,@:m:Q:%s,@:[m:Q:%s' % (bus_attr, bus_attr, bus_attr)),
            '#=#.#### # ' + sn + (',@:~m:S:%s,@:m:S:%s,@:[m:S:%s' % (bus_attr, bus_attr, bus_attr)),
        ]
        creados['cuadro_potencias'] = {'ruta': crear_tb(nom_pot, px, py, lineas_p, True, 22), 'xy': [px, py], 'despeje': clr_p}
        extra.extend([(px, py), (px - 8, py), (px + 8, py), (px, py - 4), (px, py + 4)])
    if incluir_etiqueta:
        nx, ny, clr_n = _buscar_espacio_libre(dia, cx, cy, 18.0, 7.0, a_reemplazar, extra)
        creados['etiqueta_nombre'] = {'ruta': crear_tb(nom_lbl, nx, ny, ['# ' + sn + ',@:loc_name'], False, 18), 'xy': [nx, ny], 'despeje': clr_n}

    app.SetGraphicUpdate(1)
    app.Rebuild(1)
    return {'elemento': elemento.GetFullName(), 'elemento_xy': [round(cx, 2), round(cy, 2)], 'anotaciones': creados, 'cambios': True}
