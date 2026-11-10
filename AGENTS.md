# Guía para estudios con PowerFactory

Antes de interpretar resultados, consulte el proyecto, caso de estudio, escenario, tiempo de estudio, variaciones y etapas activas, red y alimentador objeto del pedido. Indique si las obras están activas. Identifique los elementos del alimentador por su conectividad o pertenencia comprobada, no solo por el nombre de la red o del objeto.

Verifique si el flujo es válido y describa las condiciones de cálculo antes de usar resultados. No presente un flujo no convergente como evidencia de una sobrecarga o causa concreta. Si se cambian temporalmente variaciones o escenarios para comparar, registre el estado inicial, restablézcalo incluso ante errores y compruebe la restauración y el flujo. No consolide variaciones sin una instrucción específica.

Para tensiones, identifique el nivel, criterio y clasificación rural o urbana aplicables al estudio. Distinga nodos desenergizados o resultados cero de tensiones válidas. Informe el alcance del análisis y los elementos fuera del alimentador. En estudios desequilibrados considere las fases pertinentes, no solo un valor agregado.

Para obras y generación, considere conjuntamente la configuración de la red, etapas de refuerzo, escenario de demanda y generación, estado de cada EG o PMGD, P, Q y controles. Diferencie datos configurados de resultados del flujo y compruebe unidades y convenciones de signos. Un resultado conforme con obras activas no describe la red sin obras.

Al seleccionar un elemento gráfico, verifique identidad y ruta. Si usa `objeto.MarkInGraphics()`, compruebe el diagrama y la selección después de ejecutarlo. Una llamada sin error no prueba por sí sola que el usuario vea el elemento.

Estos criterios orientan la investigación y no sustituyen la información vigente del proyecto ni las instrucciones del usuario. Los nombres, límites y estados concretos de un proyecto no se trasladan automáticamente a otro.
