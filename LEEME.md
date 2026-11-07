# Prueba de consulta de PowerFactory

`capturar_contexto.py` se ejecuta como ComPython en la sesión gráfica y guarda
proyecto, caso, variaciones y selecciones en `contexto.json`. No modifica el
modelo. Cada consulta devuelve la última captura y su antigüedad; se debe
ejecutar nuevamente el ComPython para actualizarla. Los métodos de selección
no disponibles se informan en `errores`.

`servidor.py` expone la captura mediante MCP por stdio. No inicia PowerFactory
ni ejecuta comandos en él. Python 3.8 o posterior, sin dependencias externas.
El servidor se registró como `powerfactory_contexto` en Codex. Se verificó con
un app-server independiente de Codex que carga el servidor y descubre las
cuatro herramientas. La disponibilidad en un chat ya abierto puede diferir.

Para consulta bajo demanda, `solicitar_contexto` crea una solicitud local que
vence en 120 segundos. Ejecute el ComPython `MCP Consulta Puntual`, vinculado a
`agente_puntual.py`, y use `recoger_contexto` con el identificador recibido.
El comando consulta la sesión y termina; la interfaz se libera al terminar.
El servidor todavía no inicia por sí mismo el comando de PowerFactory: debe
ejecutarse desde la interfaz, por el usuario o mediante control de pantalla.
`consultar_contexto_vivo` permite la misma secuencia en una llamada que espera
30 segundos, pero requiere ejecutar el comando durante la espera. La respuesta
no usa silenciosamente una captura anterior cuando no hay respuesta.

Existe además `MCP Agente Temporal`, vinculado a `agente_temporal.py`: escucha
15 segundos y PowerFactory queda no interactivo durante ese tiempo. Es una
alternativa experimental, no una conexión permanente.

La selección disponible es la existente durante la ejecución; abrir el agente
desde el navegador puede seleccionar el propio ComPython. La integración no ha
sido validada para seleccionar otro elemento mientras el agente está activo.

En PowerFactory cree un ComPython con Script file apuntando a
`capturar_contexto.py` y ejecútelo con proyecto y caso activos. En Codex, el
servidor debe registrarse con el intérprete Python y la ruta de `servidor.py`.

## Llevarlo a otro computador

Copie o clone esta carpeta. Instale Python 3.8 o posterior y Codex; con ambos en
el PATH ejecute `powershell -ExecutionPolicy Bypass -File .\instalar_codex.ps1`.
El instalador no reemplaza un servidor del mismo nombre ya registrado. Cree un
ComPython `MCP Consulta Puntual` en PowerFactory y vincúlelo a la ruta local de
`agente_puntual.py`. La sesión gráfica de PowerFactory, sus permisos y el
intérprete compatible se necesitan en ese PC. La instalación no se hace en la
nube ni conecta una sesión de otro computador automáticamente.

No suba `contexto.json`, `intercambio/`, cachés ni archivos de proyectos
eléctricos al repositorio. `.gitignore` excluye los datos locales de este puente.
