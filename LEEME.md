# Servidor MCP de Control Total para DIgSILENT PowerFactory 2021 SP2 (`powerfactory_contexto`)

Este proyecto conecta agentes de IA (Codex, Antigravity, etc.) directamente con la **sesión gráfica activa** de DIgSILENT PowerFactory 2021 SP2 mediante MCP por `stdio`, permitiendo consultar toda la red, ejecutar flujos de carga (`ComLdf`), crear escenarios (`IntScenario`) y modificar cualquier elemento (`ElmLod`, `ElmPvsys`, `ElmLne`, `ElmTerm`, `ElmTr2`) en tiempo real.

---

## 1. Arquitectura y Archivos Principales

- **`servidor.py`**: Servidor MCP por `stdio` (sin dependencias externas, compatible con Python 3.8+). Gestiona la cola de solicitudes en `intercambio/` con sondeo de baja latencia (`15 ms`) y devuelve la respuesta automáticamente en una sola llamada cuando la sesión en vivo está activa.
- **`agente_puntual.py`**: Script vinculado al comando `ComPython` **`MCP Consulta Puntual`** dentro de PowerFactory. Al ejecutarse una vez, abre una **sesión de escucha continua** (4 horas por defecto) revisando `intercambio/peticion_*.json` cada `20 ms` y bombeando eventos gráficos de la interfaz mediante `QCoreApplication::processEvents` (`Qt5Core_pf.dll`) para que el diagrama unifilar se actualice en vivo.
- **`agente_temporal.py`**: Despachador de acciones (`contexto`, `inventario`, `analizar_lineas`, `modificar_cargas`, `ejecutar_python`, `configurar_opc_prueba`) invocado por `agente_puntual.py`.
- **`capturar_contexto.py`**: Implementación de todas las funciones sobre la API `powerfactory`:
  - `capturar(app)`: Lee proyecto activo, caso de estudio, variaciones, carpetas y selección actual (`~31 ms`).
  - `inventariar(app)`: Inventario completo de elementos `Elm*` en las redes activas (`ElmLne`, `ElmLod`, `ElmPvsys`, `ElmTr2`, `ElmTerm`, `ElmXnet`).
  - `analizar_lineas(app, umbral=100.0, ejecutar=False, mostrar_en_interfaz=True)`: Ejecuta opcionalmente `ComLdf`, reconstruye el diagrama unifilar (`app.Rebuild(1)`) y devuelve las líneas sobre el umbral ordenadas de mayor a menor cargabilidad (`c:loading`).
  - `modificar_cargas(app, ...)`: Escala o ajusta `plini`, `qlini` u `outserv` de cargas (`ElmLod`) por nombre, terminal o en toda la red, y recalcula el flujo.
  - `ejecutar_python_dinamico(app, codigo)`: Ejecuta cualquier bloque de código Python directamente sobre `app`, `proyecto` y `caso` en cualquier proyecto del usuario, devolviendo el contenido de la variable `resultado`.

---

## 2. Herramientas MCP Expuestas en `servidor.py`

**`crear_maquina_sincrona_sesion`**: crea una máquina síncrona en la sesión
gráfica activa, un tipo y cubículo, verifica su conexión y añade el símbolo al
diagrama abierto. Requiere rutas exactas del proyecto, terminal y diagrama,
nombre, potencia nominal en MVA y potencia activa en MW; admite potencia
reactiva en Mvar. El tipo usa parámetros predeterminados ilustrativos, no es
un modelo validado. No ejecuta flujo automáticamente. La disposición gráfica
puede incorporar otros elementos que falten en el diagrama. Si falla, informa
los objetos creados para su revisión; no reintente sin comprobarlos. Probada
en la copia con una máquina temporal, retirada posteriormente. Reinicie el
servidor MCP para que un cliente ya iniciado descubra la herramienta nueva.

1. **`ejecutar_python_sesion`** *(Herramienta principal de control total)*:
   - Recibe `{"codigo": "..."}`.
   - Tiene disponibles en el ámbito: `app`, `proyecto`, `caso`, `powerfactory`, `capturar`, `inventariar`, `analizar_lineas`, `modificar_cargas`.
   - Asigne a la variable `resultado` cualquier estructura serializable a JSON para recibirla de vuelta.
2. **`modificar_cargas_sesion`**:
   - Permite escalar (`factor_escala`) o fijar potencia (`plini`, `qlini`, `outserv`) en cargas específicas (`nombres`, `terminales`) o en todas (`todas=True`), recalculando el flujo automáticamente.
3. **`solicitar_analisis_sesion`**:
   - Analiza sobrecargas de líneas (`umbral`, `ejecutar=True/False`, `mostrar_en_interfaz=True/False`). Cuando la escucha continua está activa, devuelve el resultado directamente sin requerir un segundo paso.
4. **`solicitar_contexto` / `solicitar_inventario` / `recoger_contexto`**:
   - Consultas de contexto e inventario de la sesión gráfica.
5. **`iniciar_motor` / `activar_proyecto_motor` / `consultar_motor` / `analizar_sobrecargas_lineas` / `renombrar_elemento_motor`**:
   - Herramientas para el motor externo persistente (`motor_persistente.py`), útiles únicamente cuando la ventana gráfica de PowerFactory está cerrada (debido al bloqueo monopuesto de la base de datos de PowerFactory).

---

## 3. Cómo Conectarse y Operar desde Codex o Antigravity

### Paso 1: Verificar si la escucha continua ya está activa
Revise el archivo `proyecto/intercambio/latido_timer.json`:
- Si la diferencia entre `time.time()` y `latido_unix` es menor a `3 segundos`, la sesión en vivo en PowerFactory **ya está activa** y responderá en `30–450 ms` sin intervención del usuario.
- Si no está activa, deje creada una solicitud (por ejemplo llamando a `ejecutar_python_sesion` o `solicitar_contexto`) y pídale al usuario que haga clic **una sola vez** en el comando `MCP Consulta Puntual` en PowerFactory. A partir de ese momento la sesión quedará abierta por 4 horas.

### Paso 2: Buenas prácticas de velocidad y refresco visual
- **Cuando se ejecuta un único flujo o cambio que el usuario quiere ver en vivo**:
  ```python
  app.EchoOn()
  app.SetGraphicUpdate(1)
  ldf = app.GetFromStudyCase('ComLdf')
  ldf.Execute()
  app.Rebuild(1)
  ```
- **Cuando se configuran o simulan varios escenarios seguidos (batch)**:
  Desactive la actualización gráfica en los pasos intermedios (`app.EchoOff()`, `app.SetGraphicUpdate(0)`) y ejecute `app.SetGraphicUpdate(1)` + `app.Rebuild(1)` **únicamente al final del último escenario**. Así cada flujo intermedio tarda solo `~55 ms` en lugar de `~800 ms`.

### Paso 3: Cómo detener la escucha continua para usar botones manuales
Con PowerFactory en primer plano, mantenga **Ctrl + Alt + F12** durante un segundo. La ventana de salida confirma la parada. Probado en la sesión gráfica; una pulsación muy rápida puede no detectarse. Para reanudar, ejecute de nuevo `MCP Consulta Puntual`.

Mientras `agente_puntual.py` está activo manteniendo abierto el canal `ComPython`, PowerFactory muestra el indicador de comando en ejecución. Si el usuario desea ejecutar otro `ComPython` manualmente desde la interfaz, basta crear el archivo vacío `proyecto/intercambio/detener_timer` (o ejecutar `New-Item proyecto\intercambio\detener_timer`) y el bucle se cerrará limpiamente en `< 25 ms`.

---

## 4. Llevarlo a otro computador

1. Copie o clone esta carpeta.
2. Con Python 3.8+ y Codex en el `PATH`, ejecute:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\instalar_codex.ps1
   ```
3. En PowerFactory, vaya a **`Tools -> Configuration... -> Advanced -> Advanced`** y marque:
   - `Unattended mode (engine mode)`
   - `Run simulation in separate thread`
4. Cree un objeto `ComPython` llamado `MCP Consulta Puntual` dentro de su caso de estudio y apunte su *Script file* a la ruta local de `agente_puntual.py`.
