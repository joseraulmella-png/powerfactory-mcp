# Herramientas y capacidades del puente

La sesión gráfica utiliza `MCP Consulta Puntual` para iniciar la escucha; el
servidor MCP se comunica con ella por archivos locales. Las herramientas se
descubren mediante `tools/list`. Reiniciar el servidor MCP cuando se agregan
herramientas para que los clientes ya iniciados puedan descubrirlas.

## Sesión gráfica

- `consultar_contexto_vivo`: lee el proyecto, caso y contexto de la sesión.
- `solicitar_inventario` y `recoger_contexto`: solicitan y recogen inventario;
  cuando la escucha está activa atiende la solicitud sin reiniciar el script.
- `solicitar_analisis_sesion` y `recoger_contexto`: analizan líneas; el
  parámetro `ejecutar` permite solicitar un flujo de carga.
- `modificar_cargas_sesion`: modifica las cargas seleccionadas; comprobar sus
  argumentos antes de llamar, ya que puede ejecutar un flujo.
- `crear_maquina_sincrona_sesion`: crea una máquina síncrona, tipo y cubículo,
  conecta al terminal y añade su símbolo. Es específica de esa clase; el tipo
  tiene parámetros de ejemplo. No ejecuta flujo. La disposición gráfica puede
  añadir otros objetos que falten. Una prueba real en la copia creó y retiró
  una máquina temporal, dejando intacta la máquina solicitada por el usuario.
- `representar_elemento_sesion`: agrega al diagrama activo la representación de
  un elemento eléctrico que ya existe, identificado por su ruta exacta. No
  crea el elemento eléctrico. Probada con carga, sistema fotovoltaico, máquina
  síncrona y red externa en la copia; las pruebas retiraron sus objetos
  temporales. Una segunda llamada detectó cada símbolo sin duplicarlo. El
  comando de PowerFactory puede agregar otros elementos ausentes: devuelve las
  rutas de los objetos gráficos nuevos para que se revisen. La disponibilidad
  y aspecto de otras clases o proyectos todavía deben verificarse.
- `ejecutar_python_sesion`: operación general de Python con acceso al modelo.
  Es potente, pero exige que la IA prepare y verifique la operación; no equivale
  a herramientas específicas para todos los tipos de elemento.
- `detener_escucha_sesion`: solicita detener la escucha. El usuario también
  puede detenerla manteniendo Ctrl+Alt+F12 con PowerFactory en primer plano.
- `solicitar_prueba_opc`: experimento OPC para una copia, no es necesario para
  el funcionamiento actual del puente.

## Captura y motor externo

- `solicitar_contexto` y `recoger_contexto`: par de solicitud y respuesta.
- `consultar_contexto`: lee la última captura guardada, que puede estar vieja.
- `iniciar_motor`, `activar_proyecto_motor`, `consultar_motor`,
  `renombrar_elemento_motor` y `analizar_sobrecargas_lineas` corresponden al
  motor externo, separado de la sesión gráfica; puede fallar si la base local
  de usuario único ya está ocupada.

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
