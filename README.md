# powerfactory-mcp

Puente MCP para consultar y operar una sesión de DIgSILENT PowerFactory.
Consulte [LEEME.md](LEEME.md) para la instalación y [HERRAMIENTAS_MCP.md](HERRAMIENTAS_MCP.md) para las herramientas disponibles.

El panel flotante y el agente de una petición son experimentales: la reactivación
de la escucha desde el panel aún no está implementada ni validada. La escucha
continua existente se sigue iniciando desde PowerFactory.

## Validación

Las pruebas de regresión sin PowerFactory se ejecutan con `python -m unittest -v test_regresiones`.
Comprueban respuestas tardías y conservación de anotaciones mediante objetos simulados; no sustituyen pruebas funcionales en una copia de PowerFactory.

Si una solicitud no responde a tiempo, conserve su identificador y consulte `recoger_contexto` antes de reintentar. El vencimiento no detiene una operación que ya comenzó; si el agente se interrumpe, el resultado puede permanecer desconocido y debe revisarse el proyecto antes de repetirla.
