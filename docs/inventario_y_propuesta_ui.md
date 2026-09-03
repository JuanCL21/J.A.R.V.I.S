# JARVIS — Inventario Técnico de Funcionalidades y Propuesta Conceptual de Interfaz

Este documento consolida el estado del sistema tras el cierre de la Fase 4 de cimientos y formaliza el diseño conceptual para las interfaces de usuario de las diferentes versiones de JARVIS. El documento se divide en dos partes estrictamente diferenciadas y no contiene ninguna línea de código de implementación ni fragmentos ilustrativos.

---

# PARTE 1 — Totalidad de Funcionalidades (Inventario Real, No Aspiracional)

---

## BLOQUE A: Ya Construido y Probado

Este bloque detalla exclusivamente las capacidades, plugins, acciones, perfiles y mecanismos de auditoría que ya se encuentran implementados en el código fuente de las carpetas `core/`, `plugins/toy/`, `plugins/open_interpreter/` y `versions/core_lite/`, y que han sido verificados mediante la batería completa de pruebas automatizadas (unitarias, de integración y adversariales).

### 1. Capacidades del Catálogo Cerrado (`core/capability_catalog.py`)

El sistema cuenta con un catálogo cerrado de siete capacidades reconocidas. Cualquier acción o plugin que declare una capacidad ajena a este catálogo es rechazado inmediatamente durante la fase de carga con un error explícito. En la práctica, cada una habilita lo siguiente:

- **`system_info`**: Habilita la lectura de información básica del entorno, reloj del sistema en tiempo universal coordinado (UTC) y métricas elementales de estado operativo (no requiere confirmación previa).
- **`filesystem_read`**: Habilita la inspección y lectura del contenido de archivos de texto confinados estrictamente dentro de la raíz del sandbox autorizado (no requiere confirmación previa).
- **`filesystem_write`**: Habilita la creación, modificación y almacenamiento de archivos dentro del sandbox, aplicando validación previa de extensiones permitidas y exclusión estricta de nombres y rutas sensibles (requiere confirmación explícita del usuario).
- **`code_execution`**: Habilita la ejecución de scripts y fragmentos de código Python en procesos aislados del sistema operativo, con límites de tiempo (timeout) y aislamiento de red mediante contenedores ligeros si la plataforma lo soporta (requiere confirmación explícita del usuario).
- **`network_access`**: Habilita la realización de peticiones de red e integración con servicios y APIs remotas (no requiere confirmación previa).
- **`notify_user`**: Habilita el despacho de alertas y notificaciones locales directas a la interfaz de usuario activa o al entorno del sistema operativo (no requiere confirmación previa).
- **`telegram_send`**: Habilita el envío de mensajes, alertas y reportes a través del bot de mensajería de Telegram (no requiere confirmación previa).

### 2. Plugins Existentes y Acciones Disponibles

Actualmente existen dos plugins funcionales dentro de la carpeta `plugins/`:

#### Plugin de Juguete (`plugins/toy/`)
Creado como prueba de concepto del ciclo de vida de plugins y verificación del núcleo sin riesgos de seguridad:
- **`toy.get_time`**:
  - *Qué hace:* Devuelve la fecha y hora actual del sistema en formato estándar ISO en tiempo universal coordinado (UTC).
  - *Capacidad requerida:* `system_info`.
  - *Confirmación:* No pide confirmación.

#### Plugin Open Interpreter (`plugins/open_interpreter/`)
Implementa las cuatro operaciones centrales de asistencia técnica y automatización en el sistema:
- **`open_interpreter.run_python`**:
  - *Qué hace:* Ejecuta un fragmento de código Python en un subproceso aislado, aplicando aislamiento de red mediante Bubblewrap si está instalado en el sistema operativo y cancelando la ejecución si se supera el tiempo límite configurado.
  - *Capacidad requerida:* `code_execution`.
  - *Confirmación:* Sí pide confirmación previa del usuario (se solicita la primera vez en la sesión de proceso y se cachea en memoria).
- **`open_interpreter.write_file`**:
  - *Qué hace:* Escribe contenido textual en un archivo dentro del directorio de sandbox, verificando que la ruta no escape de la raíz permitida, que no acceda a directorios protegidos de credenciales del sistema y que su extensión pertenezca a la lista autorizada.
  - *Capacidad requerida:* `filesystem_write`.
  - *Confirmación:* Sí pide confirmación previa del usuario (se solicita la primera vez en la sesión de proceso y se cachea en memoria).
- **`open_interpreter.read_file`**:
  - *Qué hace:* Lee el contenido de un archivo ubicado dentro del sandbox tras validar que la ruta no viole las reglas de confinamiento.
  - *Capacidad requerida:* `filesystem_read`.
  - *Confirmación:* No pide confirmación.
- **`open_interpreter.create_presentation`**:
  - *Qué hace:* Genera un archivo de presentación PowerPoint (.pptx) dentro del sandbox a partir de una lista declarativa de diapositivas con títulos y viñetas estructuradas, consumiendo datos directamente sin evaluar código dinámico.
  - *Capacidad requerida:* `filesystem_write`.
  - *Confirmación:* Sí pide confirmación previa del usuario (al estar asociada a `filesystem_write`, se solicita la primera vez en la sesión de proceso y se cachea en memoria).
- **`open_interpreter.search_local_files`**:
  - *Qué hace:* Busca archivos de forma recursiva por coincidencia de patrones dentro del sandbox autorizado, neutralizando intentos de navegación relativa que intenten salir del directorio raíz.
  - *Capacidad requerida:* `filesystem_read`.
  - *Confirmación:* No pide confirmación.

### 3. Alcance Real de un Usuario de `core-lite` Hoy

Un usuario que ejecute hoy la versión `core-lite` a través de su punto de entrada (`versions/core_lite/main.py`) opera bajo un perfil estricto compuesto únicamente por tres capacidades: `system_info`, `notify_user` y `telegram_send`. Su alcance práctico real se limita exactamente a lo siguiente:

- Puede inicializar el núcleo como un proceso silencioso en segundo plano que no levanta servidores HTTP, no abre puertos de red en el sistema operativo ni muestra ventanas de interfaz gráfica.
- Puede cargar y ejecutar con éxito el plugin `toy` para consultar la hora del sistema mediante `toy.get_time`.
- Si el usuario o el sistema intenta cargar el plugin `open_interpreter`, el cargador de plugins lo rechaza de forma inmediata y automática porque dicho plugin exige capacidades de ejecución de código y manipulación de archivos que no forman parte del perfil de `core-lite`.
- Si se intentara invocar manualmente cualquier acción de `open_interpreter`, el despachador detiene la solicitud antes de tocar el sistema operativo y registra un evento de rechazo por falta de capacidad o por acción no declarada.
- No puede leer archivos del disco, no puede escribir documentos, no puede crear presentaciones ni puede ejecutar código Python en su computadora.
- Puede utilizar las capacidades de notificación local o despacho de Telegram para recibir mensajes una vez que los emisores correspondientes sean invocados en el flujo de ejecución.

### 4. Registro y Consulta de Auditoría (`database/jarvis.db`)

Cada operación que atraviesa el despachador central genera una entrada inmutable en la tabla `audit_logs` de la base de datos SQLite del sistema.

#### Qué queda registrado:
- La marca de tiempo exacta del evento en formato ISO UTC.
- El identificador del plugin (`plugin_id`) y el nombre de la acción invocada (`action`).
- La capacidad del catálogo involucrada en la operación (`capability`).
- Un indicador booleano de autorización (`allowed`: 1 para operaciones permitidas, 0 para bloqueadas o rechazadas).
- El estado final del resultado (`result_status`), clasificado en:
  - Éxito operativo (`success`).
  - Denegado por falta de permisos en el perfil o exceso de tasa (`denied`).
  - Pausado a la espera de aprobación del usuario (`needs_confirmation`).
  - Fallo durante la ejecución interna (`error`).
- El motivo técnico estructurado del rechazo o error (`reason`), como por ejemplo `capability_denied`, `action_not_declared`, `requires_confirmation`, `rate_limit_exceeded` o `execution_error`.
- Los detalles contextuales del evento (`details`), almacenados como estructura JSON o texto legible, conteniendo los parámetros suministrados o el mensaje de error capturado.
- Los rechazos ocurridos durante el arranque cuando un plugin no cumple con el perfil de capacidades de la versión.

#### Qué se puede consultar hoy:
- A través del componente programático del núcleo (`AuditLogger.query_logs`):
  - Se puede obtener la lista de los últimos registros ordenados cronológicamente de forma descendente.
  - Se puede filtrar opcionalmente por un plugin específico.
  - Se puede limitar la cantidad de registros devueltos (por defecto los últimos 100).
- A través de herramientas de base de datos directas sobre `database/jarvis.db`:
  - Se pueden ejecutar consultas SQL estándar sobre la tabla `audit_logs` para auditar el historial completo de ejecuciones, bloqueos de seguridad y autorizaciones otorgadas.

---

## BLOQUE B: Diseñado pero No Construido Todavía

Este bloque recopila todas las funcionalidades, componentes y subsistemas que forman parte de la arquitectura aprobada en los documentos de diseño (`DESGLOSE_PROYECTO_JARVIS.md`, `NUCLEO_PLUGINS_OPEN_INTERPRETER.md` y especificaciones previas de JARVIS-LOCAL/CORE), pero cuya implementación no existe aún en el código fuente.

- **Dashboard Web de Control y Administración (`core-full`) — Fases 5 y 6:**
  Interfaz web servida por FastAPI y accesible mediante cualquier navegador web remoto para supervisar la salud del servidor, visualizar métricas operativas, gestionar configuraciones de seguridad y monitorear tareas sin depender de un monitor físico conectado al equipo central.
- **Bot de Telegram 24/7 — Fases 5 y 6:**
  Canal de comunicación bidireccional continuo que permite al usuario enviar instrucciones al servidor desde su teléfono móvil y recibir confirmaciones y resúmenes estructurados en cualquier momento.
- **Capa de Inteligencia y LLM Multi-Proveedor con LiteLLM — Fase 5:**
  Módulo unificado de orquestación de modelos de lenguaje capaz de enrutar consultas de manera dinámica entre diferentes proveedores comerciales (Gemini, Anthropic, OpenAI) y modelos locales abiertos, optimizando costos, velocidad de respuesta y límites de cuota.
- **Sistema de Notificaciones Curadas — Fases 5 y 6:**
  Motor de filtrado contextual que evalúa la urgencia y relevancia de los sucesos del sistema antes de despachar una notificación al usuario, evitando la saturación con avisos intrascendentes y priorizando eventos críticos o decisiones pendientes.
- **Protocolo de Comunicación Remota CORE ↔ LOCAL — Fase 7:**
  Especificación y transporte seguro de mensajes en tiempo real para sincronizar el servidor central (`core-full`) con las terminales de escritorio (`local`/`asistente`), permitiendo la delegación de tareas y el intercambio distribuido de archivos y comandos.
- **Cola de Trabajos Persistente y Registro de Dispositivos — Fases 7 y 8:**
  Mecanismo transaccional basado en SQLite para registrar el estado de conexión de los diferentes dispositivos autorizados y coordinar la ejecución asíncrona de tareas de larga duración con reintentos y tolerancia a desconexiones.
- **Interfaz Gráfica de Escritorio Adaptada en PyQt6 (`asistente` y `local`) — Fase 8:**
  Adaptación y ampliación de la interfaz gráfica ya existente en el proyecto predecesor para incorporar la visualización de permisos por plugin, diálogos flotantes de autorización y consulta de auditoría, manteniendo el protagonismo de la interacción por voz.
- **Versión Móvil Ligera (`movil`) — Fase 9:**
  Cliente portátil (cuyo stack tecnológico aún no ha sido definido) enfocado en la consulta ágil del estado del servidor, recepción de alertas urgentes y aprobación de acciones sensibles mediante un solo toque táctil.
- **Gestión de Dispositivos (`device_management`) — Fase 7:**
  Capacidad diferida del catálogo para registro, emparejamiento, control y monitoreo de dispositivos satélite que se integrará al implementarse el protocolo remoto y registro de nodos en la Fase 7.
- **Captura y Síntesis de Audio (`audio_capture`, `audio_synthesis`) — Fase de Interfaz de Voz:**
  Capacidades diferidas del catálogo para grabación de micrófono, reconocimiento del habla (STT) y síntesis de voz (TTS) que se incorporarán al construir formalmente los plugins de voz en las interfaces de usuario correspondientes.

---

# PARTE 2 — Sugerencia de Interfaz Visual (Solo Diseño, Cero Código)

Esta propuesta visual define la experiencia de usuario y la arquitectura de pantallas para las diferentes variantes de JARVIS. Se adhiere a las restricciones acordadas: preserva el enfoque primario de JARVIS como asistente de voz con chat conversacional para las versiones de escritorio, diseña un panel web administrativo para el servidor remoto, mantiene la versión móvil como cliente ligero y no introduce ninguna línea de código ni etiquetas técnicas.

---

## 1. Versiones de Escritorio: `asistente` y `local` (Adaptación PyQt6)

Estas dos versiones reutilizan como cimiento la interfaz gráfica desarrollada en PyQt6 del asistente JARVIS_Custom. En ambas variantes, la experiencia gira alrededor del control por voz y la conversación fluida, evitando convertirse en una consola técnica o en un tablero de métricas. La diferencia entre ambas radica en sus capacidades: `asistente` es una versión de consulta, síntesis y lectura que no ejecuta código ni escribe en el disco; `local` es la estación de trabajo completa que dispone de ejecución en sandbox y manipulación de archivos.

### Pantalla Principal (Lo que ve el usuario apenas abre la aplicación)

El usuario se encuentra con una ventana de diseño limpio, estilizado y con predominio de tonos oscuros que transmiten calma y sofisticación. La disposición espacial se organiza de la siguiente manera:

- **Al centro superior: El Visualizador de Audio Reactivo:**
  Es el corazón visual de la interfaz. No es un gráfico estático ni una barra de volumen tradicional, sino un orbe u onda fluida y armónica que comunica de forma inmediata el estado del asistente sin emitir palabras:
  - *Estado de Reposo:* El orbe se mantiene en una oscilación suave y lenta, similar a una respiración pausada, con un resplandor tenue en tono azul o cian profundo.
  - *Estado Escuchando:* Al detectar la voz del usuario o pulsar el micrófono, las líneas del orbe se expanden y reaccionan de manera elástica y vibrante en tiempo real a la entonación y volumen del habla.
  - *Estado Hablando:* Mientras JARVIS responde mediante su motor de voz, el orbe pulsa en cadencia con el ritmo y las pausas de la locución sintética.
- **Al centro inferior: El Panel de Conversación Conversacional:**
  Ubicado justo por debajo del visualizador de audio, presenta el historial de diálogo en un formato de burbujas limpias con esquinas redondeadas. Las intervenciones del usuario aparecen alineadas a la derecha con un fondo oscuro diferenciado, mientras que las respuestas de JARVIS se ubican a la izquierda. Si un plugin produce un resultado enriquecido (como el resumen de un documento leído o la confirmación de una presentación generada), este se presenta como una tarjeta compacta y legible dentro del mismo flujo de burbujas, sin abrir ventanas externas.
- **En la parte inferior: Barra de Entrada Discreta:**
  Una línea de texto delgada para redactar mensajes manualmente cuando el usuario no desee hablar, acompañada de un botón de micrófono para activar la escucha por voz y un botón para enviar.
- **Arriba a la derecha: Barra de Estado No Invasiva:**
  Muestra únicamente un distintivo discreto de conectividad (indicando si el núcleo está activo) y un ícono sutil en forma de escudo translúcido. Este ícono es la puerta de entrada secundaria a las funciones de configuración, permisos y auditoría, manteniéndose completamente al margen de la atención durante el diálogo habitual.

### Representación Visual de Acciones con Confirmación (`requires_confirmation`)

Cuando el asistente, impulsado por una instrucción del usuario o un plan de trabajo, necesita invocar una acción sensible (como ejecutar código Python o guardar un archivo en la versión `local`), no se muestra una ventana emergente tradicional que bloquee toda la pantalla. En su lugar, se activa una **Cápsula Flotante de Autorización**:

- **Comportamiento y Ubicación:**
  La cápsula emerge mediante un deslizamiento suave desde el área superior, ubicándose entre el visualizador de audio y la última burbuja del chat. Utiliza un fondo translúcido con desenfoque de fondo que deja ver el contenido previo sin ocultarlo. El visualizador de audio pasa a un estado de atención expectante, reduciendo su movimiento y tiñéndose de un tono ámbar cálido.
- **Contenido Informativo:**
  La cápsula expone el motivo en lenguaje estrictamente natural y claro: indica qué plugin solicita el permiso, qué operación desea realizar y sobre qué elemento tendrá impacto. Por ejemplo: *"Open Interpreter necesita tu autorización para ejecutar un cálculo en Python dentro del entorno seguro"*.
- **Inspección sin Fricción:**
  Debajo del mensaje principal se incluye un control desplegable titulado *"Examinar detalles"*. Si el usuario desea verificar la operación, al tocar este control se expande dentro de la misma cápsula una vista de solo lectura que muestra las líneas de código o la ruta exacta del archivo a escribir. Si el usuario no desea inspeccionar el detalle técnico, no está obligado a hacerlo.
- **Decisión Rápida:**
  La cápsula ofrece dos botones de contraste definido: un botón destacado en verde suave para *"Autorizar para esta sesión"* y un botón neutro para *"Rechazar"*. Al tomar la decisión, la cápsula se contrae suavemente hacia el chat transformándose en un pequeño sello de confirmación que deja constancia visual en la conversación, y el visualizador de audio retoma su ciclo habitual para continuar respondiendo.

### Visualización del Estado de Permisos

Para comprender qué puede y qué no puede hacer la versión en uso sin necesidad de consultar código fuente ni perfiles técnicos:

- El usuario hace clic en el ícono de escudo de la esquina superior derecha, lo que despliega un **Panel Lateral de Capacidades** que se desliza desde el borde derecho sin tapar el visualizador ni la conversación principal.
- El panel organiza las capacidades mediante tarjetas ilustrativas con títulos cotidianos:
  - *"Acceso a Internet"* en lugar de términos de protocolo de red.
  - *"Ejecución de Código y Scripts"* en lugar de identificadores internos.
  - *"Escritura y Creación de Archivos"*.
  - *"Lectura de Documentos"*.
  - *"Voz y Micrófono"*.
- Cada tarjeta incluye un indicador visual inequívoco:
  - Un círculo verde con una tilde indica que la capacidad está concedida y opera de forma directa.
  - Un círculo ámbar con la silueta de una mano indica que la capacidad está permitida pero requerirá confirmación la primera vez que se use en la sesión.
  - Un círculo gris atenuado con un candado cerrado indica que la capacidad está estrictamente bloqueada por el perfil de la versión.
- En la versión `asistente`, el usuario observa inmediatamente que la ejecución de scripts y la escritura de archivos están en gris con el candado cerrado, entendiendo que esa versión fue concebida exclusivamente para asistencia de voz y consulta. En la versión `local`, esas mismas tarjetas aparecen en tono ámbar, reflejando que están disponibles pero bajo su supervisión.

### Navegación y Lectura del Log de Auditoría (`jarvis.db`)

Dentro del mismo panel lateral accesible desde el escudo de seguridad, una pestaña secundaria titulada *"Registro de Actividad"* ofrece la visualización de la base de datos de auditoría:

- **Diseño sin Apariencia de Consola:**
  Se destierra por completo la tabla de datos fría y el texto de terminal. La actividad se visualiza como una **Bitácora Cronológica de Eventos**:
  - Cada entrada se presenta como un bloque temporal con la hora relativa o exacta (*"Hace 10 minutos"*, *"Hoy a las 15:30"*).
  - Un ícono intuitivo clasifica el desenlace: una tilde verde para acciones exitosas, un escudo rojo para acciones bloqueadas por seguridad, una mano ámbar para acciones confirmadas por el usuario y un triángulo de advertencia para errores.
  - Una redacción orientada a personas no técnicas describe el evento: *"Se leyó el archivo notas.txt en la carpeta segura"*, *"Open Interpreter ejecutó un script tras tu autorización"* o *"Se bloqueó un intento de escritura no autorizado"*.
- **Profundidad Opcional:**
  Al hacer clic sobre cualquier evento, la tarjeta se expande hacia abajo mostrando una ficha de comprobación con el identificador del plugin y los parámetros involucrados, permitiendo una verificación rigurosa si un usuario avanzado lo requiere, pero manteniendo la vista general siempre limpia y comprensible.

---

## 2. Versión de Servidor: `core-full` (Dashboard Web Remoto 24/7)

A diferencia de las versiones de escritorio, `core-full` está destinado a operar de forma ininterrumpida en un servidor que carece de pantalla física y de periféricos de audio directos. Por este motivo, su interfaz adopta la forma de un **Dashboard Web Responsivo** accesible desde cualquier navegador web moderno, optimizado tanto para pantallas grandes de computadora como para la pantalla vertical de un teléfono celular.

### Pantalla Principal (Vista General de Supervisión)

Al ingresar a la dirección web del servidor, el usuario visualiza un centro de control estructurado en tres zonas:

- **Barra Superior de Control:**
  Arriba a la izquierda se visualiza el nombre del nodo y una insignia viva de estado (*"Servidor Operativo 24/7"*). Arriba al centro se muestra el tiempo continuo que lleva encendido el sistema (uptime). Arriba a la derecha se ubica un selector de entorno, una campana de alertas activas con contador de pendientes y un acceso a la configuración general.
- **Barra de Navegación Lateral (o Menú Inferior en Móvil):**
  Proporciona acceso directo a cuatro secciones: *"Vista General"*, *"Cola de Tareas y Procesos"*, *"Plugins y Permisos"* e *"Historial de Auditoría"*.
- **Zona Central de Módulos Operativos:**
  Organizada en cuadrícula de tarjetas de información clave:
  - *Estado del Núcleo:* Gráficos limpios de uso de memoria, estado de los plugins cargados y modo de aislamiento del sandbox.
  - *Cola de Trabajos en Curso:* Lista de tareas de fondo activas, tareas programadas en espera y procesos concluidos recientemente.
  - *Conectividad y Nodos:* Estado del canal de Telegram y lista de dispositivos emparejados (computadoras con versión local o teléfonos móviles sincronizados).

### Representación Visual de Acciones con Confirmación (`requires_confirmation`)

Dado que el servidor ejecuta procesos desatendidos que pueden originarse a deshora o a través de tareas programadas, las confirmaciones de seguridad se gestionan como **Alertas de Intervención Prioritaria**:

- En la parte superior del dashboard se fija una franja destacada con fondo ámbar suave que persiste en todas las vistas mientras exista una solicitud esperando respuesta.
- La franja exhibe la leyenda: *"Acción sensible en espera de autorización"*, indicando el plugin que la solicita y el tiempo transcurrido desde la petición.
- Al pulsar sobre la franja, se despliega una tarjeta de decisión que presenta:
  - El origen exacto de la petición (por ejemplo, una tarea encolada por Telegram o un script nocturno).
  - La descripción del impacto (código que se ejecutará o archivo que se modificará).
  - Una vista previa del contenido relevante.
  - Dos botones de acción: *"Aprobar ejecución para esta sesión"* y *"Denegar y cancelar tarea"*.
- Si la solicitud no es atendida en el navegador, el sistema despacha simultáneamente una notificación interactiva a través del bot de Telegram para que el usuario pueda autorizarla directamente desde la mensajería móvil.

### Visualización del Estado de Permisos

Dentro de la sección *"Plugins y Permisos"*, el administrador encuentra un mapa completo de seguridad del servidor:

- Cada plugin instalado se representa mediante una tarjeta de perfil que detalla su versión, estado de carga y las capacidades que tiene declaradas en su manifiesto.
- Junto a cada capacidad se muestra una etiqueta de estado:
  - *"Autorizada de forma directa"* (en verde).
  - *"Autorizada con confirmación de sesión"* (en ámbar).
  - *"Bloqueada por directiva de seguridad"* (en gris con candado).
- Esto permite auditar de un solo vistazo qué grado de autonomía tiene concedido el servidor en cada área funcional sin necesidad de inspeccionar archivos JSON de configuración en el disco.

### Navegación y Lectura del Log de Auditoría (`jarvis.db`)

La sección *"Historial de Auditoría"* transforma los registros técnicos de la base de datos en una **Línea de Vida Operativa**:

- **Filtros Rápidos en la Cabecera:**
  Botones de selección inmediata permiten segmentar los eventos en: *"Todos los eventos"*, *"Solo bloqueos de seguridad"*, *"Solo autorizaciones manuales"* y *"Errores de ejecución"*.
- **Visualización en Lista Inteligente:**
  Cada suceso se describe con una frase autoexplicativa acompañada del identificador de la máquina o usuario que lo provocó. El usuario puede buscar por términos cotidianos (como el nombre de un archivo o una fecha) sin necesidad de construir sentencias de base de datos.
- **Panel Desplegable de Diagnóstico:**
  Al seleccionar cualquier registro, se abre una división lateral que separa la explicación en lenguaje común de los datos crudos del sistema (parámetros exactos, valores de retorno y marcas de tiempo precisas), ofreciendo transparencia total tanto para el usuario común como para auditorías técnicas profundas.

### Comunicación Remota 24/7 (Recordatorios y Notificaciones en Pantalla de Celular)

Cuando el usuario abre el dashboard web de `core-full` desde el navegador de su teléfono celular, la interfaz se adapta automáticamente a un formato táctil vertical enfocado en la supervisión remota continua:

- **Bandeja Superior de Atención Inmediata:**
  Si el servidor ejecutó recordatorios programados, completó procesos de fondo o requiere una confirmación de seguridad mientras el usuario estaba lejos, estos elementos aparecen agrupados en la parte superior como tarjetas interactivas de lectura rápida.
- **Diseño Orientado al Pulgar:**
  Las acciones de confirmación, postergación de recordatorios o descarte de notificaciones cuentan con botones táctiles generosos ubicados en la mitad inferior de la pantalla, permitiendo operar el servidor con una sola mano.
- **Sincronización Transparente con Canales Externos:**
  Cada notificación indica si ya fue notificada al teléfono mediante el bot de Telegram o si permanece únicamente registrada en el servidor web, garantizando que el usuario nunca reciba alertas duplicadas innecesarias.

---

## 3. Versión Móvil Ligera: `movil` (Cliente de Acompañamiento)

La versión móvil está concebida como un satélite portátil del ecosistema. Su propósito no es sustituir la estación de trabajo ni albergar paneles de métricas densos, sino brindar al usuario un canal inmediato para consultar el estado del asistente, dar órdenes breves por voz o texto y autorizar acciones sensibles sobre la marcha.

### Pantalla Principal

Al abrir la aplicación móvil, el usuario encuentra una pantalla vertical dividida en tres áreas de interacción directa:

- **Zona Superior (Estado del Ecosistema):**
  Una cabecera compacta que muestra el estado de enlace con el servidor central `core-full` (un punto verde brillante con el texto *"Conectado a JARVIS"*), la hora actual y un acceso al menú de configuración personal.
- **Zona Central (Voz y Asistencia Inmediata):**
  Un orbe reactivo táctil similar al de las versiones de escritorio, adaptado a la escala de la pantalla móvil. Al tocar el orbe, se activa el micrófono del teléfono para formular una consulta rápida por voz. Debajo del orbe, un campo de texto estilizado permite escribir si la situación ambiental no permite hablar.
- **Zona Inferior (Resumen del Día y Acciones Rápidas):**
  Una sección deslizable verticalmente que contiene pequeñas tarjetas informativas:
  - Resumen de recordatorios del día.
  - Estado de las tareas delegadas al servidor central.
  - Botones rápidos para solicitar el reporte del día o pausar las notificaciones temporalmente.

### Representación Visual de Acciones con Confirmación (`requires_confirmation`)

En un dispositivo móvil, las solicitudes de confirmación representan el punto más crítico de seguridad y ergonomía, ya que deben evitar aprobaciones involuntarias causadas por roces en el bolsillo o toques accidentales en la pantalla:

- **Pantalla de Autorización Protegida:**
  Al recibir una solicitud de confirmación proveniente del servidor o de un plugin local, la aplicación abre una tarjeta flotante de pantalla completa con vibración háptica característica.
- **Explicación Clara y Riesgo:**
  La pantalla detalla en letras grandes la acción requerida: *"JARVIS solicita autorización para ejecutar un script en el servidor"*, mostrando el origen de la orden y un extracto de lo que se va a procesar.
- **Mecanismo de Deslizador de Seguridad:**
  En lugar de un botón estándar de pulsar, la autorización se concede mediante un **Control Deslizante de Aprobación** (con la leyenda *"Desliza para autorizar"*). Este gesto exige una acción física deliberada que previene toques en falso.
- **Rechazo Inmediato:**
  Debajo del deslizador se sitúa un botón simple en tono rojo suave para *"Rechazar y cancelar"*, el cual cancela la solicitud con un solo toque y devuelve el foco a la pantalla de inicio.

### Visualización del Estado de Permisos

- En el menú de opciones de la aplicación, una pantalla titulada *"Privacidad y Permisos de este Dispositivo"* muestra claramente qué facultades tiene habilitadas la aplicación en el teléfono (acceso a micrófono para órdenes de voz, notificaciones en pantalla y conectividad de red).
- Una pestaña complementaria permite consultar qué nivel de delegación tiene concedido este dispositivo respecto al servidor central, permitiendo revocar el enlace de confianza con un solo toque si el dispositivo se extravía.

### Navegación y Lectura del Log de Auditoría

- La sección de historial en el móvil se presenta como un **Feed de Actividad Reciente**:
  - Organizado por días (*"Hoy"*, *"Ayer"*, *"Esta semana"*).
  - Enfocado en mostrar las acciones que el usuario autorizó desde el propio teléfono y los avisos críticos enviados por el servidor.
  - Cada elemento cuenta con un ícono claro, hora y descripción en lenguaje accesible. Al pulsar sobre cualquier elemento se despliega una ficha con el resultado y el tiempo de respuesta.

---

## 4. Preguntas Abiertas de Diseño

Antes de emprender la construcción técnica de cualquiera de estas interfaces, es necesario debatir y resolver las siguientes decisiones de experiencia de usuario y seguridad:

1. **Persistencia y visibilidad del estado de confirmación en la interfaz principal:**
   Dado que el núcleo cachea las confirmaciones de seguridad durante toda la sesión de ejecución del proceso, ¿debe la interfaz de usuario de escritorio y móvil mantener un indicador visible continuo (por ejemplo, un pequeño distintivo o cambio de color en el marco del visualizador) que recuerde al usuario que una capacidad como `code_execution` ya fue autorizada y no volverá a pedir confirmación hasta que se reinicie el programa, o es preferible que la interfaz no agregue elementos persistentes y confíe en la bitácora de auditoría?
2. **Modalidad de confirmación en entornos de voz pura:**
   Considerando que `asistente` y `local` son prioritariamente asistentes de voz, cuando el sistema requiera una confirmación para una acción sensible de `requires_confirmation`, ¿se debe admitir que el usuario autorice la acción pronunciando una frase de voz explícita (como por ejemplo *"Sí, autorizo la ejecución"*), o debe exigirse de manera obligatoria una interacción física en pantalla (un clic con el ratón o un toque en el deslizador) para evitar que ruidos ambientales o interpretaciones erróneas del micrófono autoricen operaciones de riesgo?
3. **Comportamiento ante la expiración de confirmaciones remotas en `core-full`:**
   En el servidor web 24/7 y en el cliente móvil, cuando una tarea en segundo plano requiere confirmación y el usuario no se encuentra frente al navegador ni responde a la notificación en su teléfono tras un tiempo prudencial (por ejemplo, 15 minutos), ¿debe el despachador cancelar automáticamente la tarea registrándola como expirada en la auditoría, o debe congelar el proceso indefinidamente en la cola de trabajos hasta que el usuario se conecte y decida?
