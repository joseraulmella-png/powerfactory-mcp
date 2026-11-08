# Opciones y Arquitectura Definitiva para Conectar con la Sesión Gráfica Activa

Objetivo: que cualquier consulta, edición del modelo, creación de escenarios o cálculo solicitado desde el MCP (`servidor.py`) opere sobre la **misma sesión gráfica de PowerFactory 2021 SP2** que usa la persona, sin accionar manualmente un `ComPython` para cada petición.

---

## 1. Resumen de Alternativas Evaluadas y Veredicto Empírico

| Vía Evaluada | Resultado Empírico en este Equipo | Veredicto |
| :--- | :--- | :--- |
| **1. Bucle en vivo dentro de `ComPython` + `Qt5Core_pf.dll` (`agente_puntual.py`)** | Mantiene `ComPython` abierto escuchando `intercambio/peticion_*.json` cada `20 ms` e invoca `QCoreApplication::processEvents` de `Qt5Core_pf.dll`. Latencia de lectura: **`31 ms`**; flujo de carga puro: **`55–62 ms`**; flujo con redibujado visual: **`438 ms`**. | **SOLUCIÓN DEFINITIVA ADOPTADA** |
| **2. Hilos Python (`threading.Thread`) o `user32.SetTimer` post-`ComPython`** | `digcal.dll` no llama a `PyEval_SaveThread()` al terminar `ComPython`. El GIL queda bloqueado al salir del comando y detiene cualquier hilo o timer posterior. | Descartado tras prueba binaria en `digcal.dll` |
| **3. OPC UA (`ComOpc` en modo `OSE`)** | Conecta en `127.0.0.1:4842` tras activar modo multihilo (`Unattended mode` + `Run simulation in separate thread`), pero exige invocar `com_opc.ReceiveData()` para refrescar mediciones (`StaExtdatmea`) y no permite navegar ni editar el modelo libremente. | Útil solo para telemedidas; insuficiente para control total |
| **4. Motor externo (`GetApplicationExt` en `motor_persistente.py`)** | Funciona en segundo plano si PowerFactory está cerrado, pero arroja **Error 4002** (base de datos monopuesto bloqueada) si la ventana gráfica del usuario está abierta. | Útil solo en modo batch sin GUI abierta |

---

## 2. Cómo Funciona la Arquitectura Activa (`agente_puntual.py` + `servidor.py`)

1. **Inicio único**:
   - El usuario ejecuta una sola vez el objeto `ComPython` **`MCP Consulta Puntual`** (vinculado a `proyecto/agente_puntual.py`).
   - El script recarga en caliente `capturar_contexto.py` y `agente_temporal.py` (`importlib.reload`) y entra en un bucle de escucha continua por 4 horas (`DURACION_SESION_SEGUNDOS = 14400`).
2. **Latido de salud (`latido_timer.json`)**:
   - Cada `1.0 s`, `agente_puntual.py` actualiza `proyecto/intercambio/latido_timer.json` con `{"latido_unix": ..., "pid": ..., "qt_events": true}`.
   - Cualquier agente (Codex, Antigravity, etc.) puede verificar si la sesión en vivo sigue activa comprobando que `time.time() - latido_unix < 3.0`.
3. **Ejecución dinámica sin restricciones (`ejecutar_python_sesion`)**:
   - Envía código Python arbitrario a `ejecutar_python_dinamico(app, codigo)` en `capturar_contexto.py`.
   - Expone en el entorno local: `app`, `proyecto`, `caso`, `powerfactory`, `describir`, `detalle`, `capturar`, `inventariar`, `analizar_lineas`, `modificar_cargas` y recoge cualquier diccionario/valor asignado a la variable `resultado`.
   - Permite operar sobre **cualquier proyecto** del usuario (o cambiar de proyecto con `app.ActivateProject("Nombre")`).
4. **Liberación limpia del canal**:
   - Mientras el bucle está activo, el indicador de comando de PowerFactory permanece encendido (lo que impide lanzar otro `ComPython` manualmente desde la botonera, aunque el agente puede ejecutar cualquier script internamente).
   - Para terminar el bucle y liberar la botonera al instante, basta crear el archivo `proyecto/intercambio/detener_timer`.
