# Continuidad y Resultados: Conexión en Vivo y Control Total de PowerFactory 2021 SP2

## Actualización de la sesión: control manual y cursor

- Se comprobó que el puente leyó la tensión de la red externa a 0,98 p.u.
  después de un cambio manual del usuario en la copia de prueba.
- `agente_puntual.py` ahora restaura una vez el cursor de espera al iniciar;
  el usuario confirmó que el indicador de carga no reapareció al reiniciar.
  El ajuste usa funciones internas de Qt incluidas en PowerFactory 2021, por
  lo que su comportamiento puede variar en otras versiones.
- Con PowerFactory en primer plano, mantener **Ctrl+Alt+F12** cerca de un
  segundo detiene la escucha. El usuario probó el atajo y PowerFactory mostró
  que el script terminó. Una pulsación rápida puede no detectarse.
- La escucha quedó detenida tras esa prueba. Para reactivarla, ejecutar
  `MCP Consulta Puntual`. El archivo `detener_escucha.bat` sigue siendo una
  alternativa manual desde el Explorador de Windows.
- Una activación del proyecto dejó el diagrama en blanco; se recuperó al
  habilitar la actualización gráfica, redibujar y ajustar la vista. En otra
  activación apareció automáticamente; no se aisló la causa exacta.

## 1. Objetivo Logrado

El servidor MCP (`servidor.py`, registrado como `powerfactory_contexto`) ahora tiene **control bidireccional continuo y en tiempo real** sobre la sesión gráfica activa de DIgSILENT PowerFactory 2021 SP2:
- Lee contexto, topología, tensiones (`m:u`), cargabilidad de líneas y transformadores (`c:loading`), potencias de cargas (`ElmLod`) e inyecciones de generación distribuida (`ElmPvsys`) en **`~31 ms`**.
- Ejecuta flujos de carga (`ComLdf.Execute()` en **`54–62 ms`** de motor, **`~438 ms`** con redibujado del diagrama unifilar en pantalla y análisis completo de líneas).
- Crea, edita y escala cualquier elemento de red (`ElmLod`, `ElmPvsys`, `ElmLne`, `ElmTerm`, `IntScenario`, etc.) y cambia o activa cualquier proyecto (`app.ActivateProject(...)`) mediante ejecución dinámica de Python (`ejecutar_python_sesion`).
- Opera de forma continua durante 4 horas (`DURACION_SESION_SEGUNDOS = 14400` en `agente_puntual.py`) tras un único inicio de `MCP Consulta Puntual`, sin requerir que el usuario vuelva a presionar el botón para cada orden.

---

## 2. Hallazgos Técnicos Verificados (Guía para Codex / Agentes IA)

### 2.1. Prueba Empírica de OPC UA (`ComOpc`)
1. **Clase real en base de datos**: En PowerFactory 2021 SP2 (`datascheme.db`), el objeto *OPC UA Link* es de clase **`ComOpc`** (no `ComLOPC` como figura erróneamente en parte del PDF).
2. **Requisito obligatorio de configuración multihilo**:
   - Sin modo multihilo, `com_opc.Execute()` devuelve código `1` (`err - Link can only be established in multi-threading mode!`).
   - Se habilita en **`Tools -> Configuration... -> Advanced -> Advanced`** marcando:
     - `Unattended mode (engine mode)`
     - `Run simulation in separate thread`
3. **Ubicación de mediciones externas (`StaExtdatmea`)**:
   - Si existe una etapa de expansión activa (`System Stage`), `CreateObject('StaExtdatmea', ...)` falla dentro de `Summary Grid.ElmNet`. Debe crearse directamente dentro del `Study Case` (`IntCase`) o en la red `ElmNet` real y asociarse a `com_opc.SetAttribute('tagSet', mea)` con el bit de lectura `mea.SetStatusBit(536870912)`.
4. **Limitación real de OPC UA en modo `OSE`**:
   - Con `opc_local_servidor_prueba.py` corriendo en `127.0.0.1:4842`, PowerFactory establece sesión TCP (`IsConnected() == True`, `codigo_Execute == 0`).
   - Sin embargo, al escribir un valor nuevo (`42.5`) en el nodo OPC UA `MCP_Prueba`, el atributo `MCP_Prueba_Mea.Mea` permanece en su valor anterior hasta que un comando dentro de PowerFactory invoca explícitamente `com_opc.ReceiveData()`.
   - **Conclusión**: OPC UA sirve para intercambio de telemedidas escalares preconfiguradas, pero **no permite navegar arbitrariamente el modelo, ni crear escenarios, ni disparar flujos de carga por sí solo** sin un bucle o comando activo en PowerFactory.

### 2.2. Comportamiento del Intérprete Python Embebido (`digcal.dll`) y Solución con `Qt5Core_pf.dll`
1. **Por qué mueren los hilos y `SetTimer` al terminar `ComPython`**:
   - Al inspeccionar la tabla de importaciones de `C:\Program Files\DIgSILENT\PowerFactory 2021 SP2\digcal.dll`, se comprobó que importa `Py_Initialize`, `PyGILState_Ensure`, `PyGILState_Release` y `PyRun_String`, pero **jamás llama a `PyEval_SaveThread()`** al finalizar `ComPython.Execute()`.
   - Como consecuencia, apenas termina el script `ComPython`, el hilo nativo retiene el GIL de Python bloqueado; cualquier `threading.Thread` en segundo plano o callback `ctypes.WINFUNCTYPE` de `user32.SetTimer` queda congelado hasta la siguiente ejecución de `ComPython`.
2. **Solución de Escucha Continua con Bombeo de Eventos Qt (`agente_puntual.py`)**:
   - En lugar de salir tras la primera petición, `agente_puntual.py` permanece en un bucle de escucha de baja latencia (`20 ms` por ciclo) revisando `intercambio/peticion_*.json`.
   - En cada iteración carga `Qt5Core_pf.dll` e invoca el símbolo C++ exportado:
     `?processEvents@QCoreApplication@pf@@SAXV?$QFlags@W4ProcessEventsFlag@QEventLoop@pf@@@2@H@Z`
   - Esto permite que la interfaz Qt de PowerFactory (diagrama unifilar, colores de sobrecarga, cajas de resultados y ventana de salida) se redibuje en tiempo real después de cada cálculo (`app.SetGraphicUpdate(1)` + `app.Rebuild(1)` + `processEvents(0, 40)`).
   - Para liberar manualmente la barra de herramientas de PowerFactory en cualquier momento, basta crear el archivo vacío `proyecto/intercambio/detener_timer`.

---

## 3. Optimización para Operaciones Multi-Escenario (Modo Silencioso + Refresco Final Único)

- Cada llamada a `app.Rebuild(1)` + refresco gráfico del diagrama unifilar toma **`~350–600 ms`**, mientras que el cálculo puro del flujo de carga (`ComLdf.Execute()`) en una red BT de 140 elementos toma solo **`~55–62 ms`**.
- **Regla de oro para agentes IA (Codex)**:
  - Cuando el usuario pida configurar o simular múltiples escenarios seguidos, desactivar el eco y el refresco gráfico durante los pasos intermedios:
    ```python
    app.EchoOff()
    app.SetGraphicUpdate(0)
    ```
  - Al finalizar el **último escenario** (o el escenario que deba quedar en pantalla), reactivar y reconstruir una sola vez:
    ```python
    app.EchoOn()
    app.SetGraphicUpdate(1)
    app.Rebuild(1)
    if pe:
        pe(0, 40)
    ```

---

## 4. Resultados Obtenidos en `MCP PRUEBA 20261107 172945` (`RED_BT.ElmNet`)

Se crearon, calibraron, simularon y guardaron tres escenarios de operación (`IntScenario` en la carpeta `Operation Scenarios`) en **`3.00 segundos`**:

| Escenario (`IntScenario`) | Tiempo (`ms`) | EGs Activos (`ElmPvsys`) | Escala Cargas (`83 ElmLod`) | Carga Trafo (`2-Winding Transformer`) | Línea Más Cargada | Líneas `> 100 %` | Tensión Mín / Máx (`p.u.`) |
| :--- | :---: | :--- | :---: | :---: | :--- | :---: | :---: |
| **1. `Escenario 1 - Trafo 30 Sin EG`** | `1241.26 ms` | Ninguno (`0 kW`) | Factor `0.998143` (`379.74 kW`) | **`30.00 %`** (`29.9989 %`) | `172316_CU 13/13 MM2 4C` (`59.63 %`) | `0` | `0.9699` / `1.0000` |
| **2. `Escenario 2 - Dos EGs Izquierda`** | `840.77 ms` | `EG 371848 kW` (`8 kW`) + `EG 10198 2.5 kW` (`2.5 kW`) | Factor `0.998143` (`379.74 kW`) | **`28.02 %`** (`28.0163 %`) | `172316_CU 13/13 MM2 4C` (`59.70 %`) | `0` | `0.9718` / `1.0000` |
| **3. `Escenario 3 - Tres EGs Activos`** | `757.39 ms` | Los 3 EGs (`8 kW` + `2.5 kW` + `150 kW` en `PP.5-073793`) | Factor `0.998143` (`379.74 kW`) | **`83.88 %`** (`83.8781 %`) | `434012_CU 13/13 MM2 4C` (**`215.10 %`**) | **`3`** (`215.10 %`, `187.65 %`, `187.65 %`) | `0.9933` / **`1.0717`** |
