# Herramientas y capacidades del puente

La sesión gráfica utiliza `MCP Consulta Puntual` para iniciar la escucha; el
servidor MCP se comunica con ella por archivos locales. Cuando `latido_timer.json`
confirma que la escucha está activa, todas las herramientas de sesión responden
en un solo paso bloqueante sin requerir una segunda llamada a `recoger_contexto`.
Si la escucha no está activa, devuelven un `id` sin borrar la solicitud pendiente
para poder recogerla tras iniciar el script.

## Sesión gráfica

- `solicitar_contexto`, `solicitar_inventario` y `solicitar_analisis_sesion`:
  cuando la escucha está activa devuelven directamente el contexto, inventario o
  análisis eléctrico (líneas, transformadores `ElmTr2` y tensiones en barras
  `ElmTerm` frente a `[v_min_pu, v_max_pu]`). Si no está activa, devuelven un `id`
  para `recoger_contexto`.
- `consultar_contexto_vivo`: espera hasta 30 segundos una respuesta en vivo.
- `modificar_cargas_sesion`: modifica las cargas seleccionadas y recalcula el flujo.
- `crear_maquina_sincrona_sesion`: crea una máquina síncrona (`ElmSym`), su tipo
  (`TypSym`) y cubículo (`StaCubic`), conecta al terminal y añade su símbolo al
  diagrama abierto. Incluye reversión automática (`revertir_en_error=true`) para
  eliminar objetos huérfanos si falla algún paso y filtrado opcional de gráficos
  adicionales (`limpiar_graficos_extra`).
- `crear_elemento_shunt_sesion`: crea de forma tipada y transaccional una carga
  (`ElmLod`) o un sistema fotovoltaico (`ElmPvsys`) junto con su cubículo y
  símbolo en el diagrama activo, revirtiendo automáticamente objetos parciales si
  ocurre un error.
- `representar_elemento_sesion`: agrega al diagrama activo la representación de
  un elemento eléctrico existente. Soporta `limpiar_graficos_extra=true` para
  retirar símbolos de otros elementos no relacionados agregados por `ComSgllayout`.
- `ejecutar_python_sesion`: operación general de Python con acceso al modelo.
- `detener_escucha_sesion`: solicita detener la escucha (también con Ctrl+Alt+F12).

## Motor externo y pruebas opcionales

Por defecto, `tools/list` expone únicamente las herramientas de la sesión gráfica
para evitar bloqueos de base de datos de instancia única y reducir ruido:
- Defina `MCP_INCLUIR_MOTOR_EXTERNO=1` para publicar `iniciar_motor`,
  `activar_proyecto_motor`, `consultar_motor`, `renombrar_elemento_motor` y
  `analizar_sobrecargas_lineas`.
- Defina `MCP_INCLUIR_OPC=1` para publicar `solicitar_prueba_opc`.

## Procedimientos comprobados y límites

Se confirmó lectura de un cambio manual en la tensión de una red externa,
activación de proyecto, flujo de carga, y conexión y representación gráfica de
una máquina síncrona en una copia. El redibujado al activar un proyecto se
probó una vez después de reiniciar PowerFactory. El símbolo se añadió mediante
el comando de disposición de PowerFactory, no mediante arrastre en la pantalla.
La herramienta de máquina no crea automáticamente otros tipos de elementos.
La representación general se probó únicamente con las clases indicadas arriba;
no se ha verificado en todas las clases ni proyectos. Las pruebas no demuestran estabilidad
prolongada ni cobertura completa de la API. Mantener explícitos el proyecto,
el caso, unidades y valores elegidos antes de modificar o calcular.
