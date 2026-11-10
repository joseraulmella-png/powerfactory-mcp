# powerfactory-mcp

## Overview and scope

PowerFactory MCP connects an MCP client to a DIgSILENT PowerFactory graphical session through a local Python bridge. It was developed for PowerFactory 2021 SP2 on Windows. The MCP server communicates with a ComPython agent through local request and response files; the continuous listener must be started in PowerFactory.

The available tools can:

- Inspect the active project, study case, selection and network inventory.
- Run a load flow and report line and transformer loading and bus voltages.
- Modify loads and create connected loads, photovoltaic systems or synchronous machines, including their graphical representation.
- Represent, highlight or annotate elements in the active diagram.
- Execute Python in the active PowerFactory session for operations beyond the dedicated tools. This can modify the project, so review the code and work on a copy when appropriate.

Optional tools for an external engine and an OPC experiment are disabled by default. The floating panel and one-request agent are experimental; restarting the listener from the panel is not implemented. If the listener is inactive, session requests may need to be collected later by ID. A timeout does not cancel an operation already in progress.

Validation has covered selected workflows, not every PowerFactory version, model or API operation. Check the active project, study case, scenarios, variations, calculation validity and applicable limits before interpreting results. See [AGENTS.md](AGENTS.md) for study guidance, [LEEME.md](LEEME.md) for setup and [HERRAMIENTAS_MCP.md](HERRAMIENTAS_MCP.md) for tool details (Spanish).

## Descripción en español

Puente MCP para consultar y operar una sesión de DIgSILENT PowerFactory.
Consulte [LEEME.md](LEEME.md) para la instalación y [HERRAMIENTAS_MCP.md](HERRAMIENTAS_MCP.md) para las herramientas disponibles.

La guía [AGENTS.md](AGENTS.md) reúne criterios para interpretar estudios y debe acompañar al servidor al compartirlo. El servidor también anuncia un resumen durante la conexión MCP, sujeto a que el cliente lo procese.

El panel flotante y el agente de una petición son experimentales: la reactivación
de la escucha desde el panel aún no está implementada ni validada. La escucha
continua existente se sigue iniciando desde PowerFactory.

## Validación

Las pruebas de regresión sin PowerFactory se ejecutan con `python -m unittest -v test_regresiones`.
Comprueban respuestas tardías y conservación de anotaciones mediante objetos simulados; no sustituyen pruebas funcionales en una copia de PowerFactory.

Si una solicitud no responde a tiempo, conserve su identificador y consulte `recoger_contexto` antes de reintentar. El vencimiento no detiene una operación que ya comenzó; si el agente se interrumpe, el resultado puede permanecer desconocido y debe revisarse el proyecto antes de repetirla.
