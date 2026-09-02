# JARVIS — Inventario de Funcionalidades y Propuesta Conceptual de Interfaz

Este documento consolida el estado real del sistema al cierre de la Fase 4 de cimientos y presenta la propuesta conceptual de diseño visual para las interfaces de usuario de las distintas versiones de JARVIS, sin incluir implementaciones ni fragmentos de código.

---

# PARTE 1 — Totalidad de Funcionalidades (Inventario Técnico)

---

## BLOQUE A: Ya Construido y Probado

Este bloque detalla exclusivamente los componentes, capacidades, acciones y flujos que ya se encuentran programados, probados con pruebas automatizadas unitarias/adversariales y confirmados en el repositorio.

### 1. Catálogo Cerrado de Capacidades del Sistema (`core/capability_catalog.py`)

- **`system_info`**: Habilita la lectura de información básica del entorno, reloj del sistema en tiempo universal coordinado y métricas elementales de estado operativo (no requiere confirmación).
- **`filesystem_read`**: Habilita la lectura de archivos de texto y documentos confinados estrictamente dentro de la raíz del sandbox autorizado (no requiere confirmación).
- **`filesystem_write`**: Habilita la creación, modificación y sobreescritura de archivos dentro del sandbox con validación previa de extensiones permitidas y exclusión de nombres sensibles (requiere confirmación del usuario).
- **`code_execution`**: Habilita la ejecución de scripts y fragmentos de código Python en procesos aislados del sistema operativo con control de timeout y aislamiento de red (requiere confirmación del usuario).
- **`network_access`**: Habilita la realización de peticiones de red e integración con servicios y APIs remotas (no requiere confirmación).
- **`device_management`**: Habilita el registro, vinculación, control y consulta de estado de dispositivos y nodos del ecosistema JARVIS (requiere confirmación del usuario).
- **`audio_synthesis`**: Habilita la conversión de texto a voz para respuestas audibles y síntesis de voz (no requiere confirmación).
- **`audio_capture`**: Habilita la captura de audio desde micrófonos y el procesamiento de reconocimiento de voz (no requiere confirmación).
- **`notify_user`**: Habilita el despacho de alertas y notificaciones locales directas a la interfaz de usuario activa (no requiere confirmación).
- **`telegram_send`**: Habilita el envío de mensajes, alertas y reportes a través del canal de bot de Telegram (no requiere confirmación).

### 2. Plugins Existentes y Acciones Disponibles

#### Plugin de Juguete (`plugins/toy/`)
- **`toy.get_time`**:
  - *Qué hace:* Obtiene la fecha, hora y marca temporal actual en formato universal coordinado, con opción de formateo personalizado.
  - *Capacidad requerida:* `system_info`.
  - *Confirmación:* No requiere confirmación previa.

#### Plugin Open Interpreter (`plugins/open_interpreter/`)
- **`open_interpreter.run_python`**:
  - *Qué hace:* Ejecuta código Python en un subproceso confinado mediante Bubblewrap (desconectando el acceso a la red externa) con límite de tiempo estricto por timeout.
  - *Capacidad requerida:* `code_execution`.
  - *Confirmación:* Requiere confirmación previa del usuario la primera vez en la sesión de proceso.
- **`open_interpreter.write_file`**:
  - *Qué hace:* Escribe contenido textual en un archivo dentro del sandbox, comprobando que la ruta no escape de la raíz permitida, que no coincida con nombres protegidos de credenciales y que su extensión pertenezca a la lista autorizada.
  - *Capacidad requerida:* `filesystem_write`.
  - *Confirmación:* Requiere confirmación previa del usuario la primera vez en la sesión de proceso.
- **`open_interpreter.read_file`**:
  - *Qué hace:* Lee el contenido de un archivo dentro del sandbox autorizado tras validar la seguridad de la ruta.
  - *Capacidad requerida:* `filesystem_read`.
  - *Confirmación:* No requiere confirmación previa.
- **`open_interpreter.create_presentation`**:
  - *Qué hace:* Genera un archivo de presentación PowerPoint (.pptx) a partir de una estructura de diapositivas con títulos y viñetas consumidas de forma puramente declarativa, sin evaluar código a partir del contenido.
  - *Capacidad requerida:* `filesystem_write`.
  - *Confirmación:* Requiere confirmación previa del usuario la primera vez en la sesión de proceso.
- **`open_interpreter.search_local_files`**:
  - *Qué hace:* Realiza búsquedas de archivos mediante patrones dentro del sandbox autorizado de manera recursiva, neutralizando intentos de navegación hacia directorios superiores mediante rutas relativas.
  - *Capacidad requerida:* `filesystem_read`.
  - *Confirmación:* No requiere confirmación previa.

### 3. Alcance Real de un Usuario de `core-lite` Hoy

Un usuario que inicie la versión `core-lite` (`versions/core_lite/main.py`) cuenta con un perfil restringido compuesto exclusivamente por `system_info`, `notify_user` y `telegram_send`. En la práctica actual, esto significa que:
- Puede arrancar el núcleo como un proceso silencioso en segundo plano sin abrir ningún puerto de red ni levantar servidores web o ventanas de interfaz gráfica.
- Puede cargar y ejecutar el plugin `toy` para consultar la hora del sistema.
- El sistema rechazará de manera inmediata cualquier intento de cargar o invocar las acciones del plugin `open_interpreter` (tanto ejecución de código como lectura/escritura en el disco), registrando el rechazo en la base de datos de auditoría.

### 4. Registro y Consulta de Auditoría (`database/jarvis.db`)

Cada invocación que pasa por el motor central —sea aprobada, denegada por permisos de versión, rechazada por falta de confirmación o fallida por error interno— genera una fila persistente en la tabla `audit_logs` de SQLite con:
- Marca de tiempo precisa en formato ISO UTC.
- Identificador del plugin y nombre de la acción invocada.
- Capacidad asociada y valor booleano de si fue permitida o rechazada.
- Estado del resultado (éxito, denegado, requiere confirmación o error de ejecución).
- Motivo estructurado del rechazo o fallo.
- Detalles contextuales en formato serializado (parámetros y perfiles involucrados).

Actualmente, estos registros pueden consultarse programáticamente mediante el método de consulta de auditoría del núcleo o mediante sentencias directas sobre la base de datos para verificar el historial completo de eventos del sistema.

---

## BLOQUE B: Diseñado pero No Construido Todavía

Este bloque reúne todas las características y módulos que han sido especificados en los documentos de diseño arquitectónico pero cuya construcción corresponde a fases posteriores.

- **Dashboard Web Administrativo y de Control (`core-full`) — Fases 5 y 6:**
  Interfaz web servida por FastAPI accesible desde navegadores locales y remotos para monitorear el estado del servidor, gestionar configuraciones, revisar colas de trabajo y administrar permisos sin requerir una pantalla física conectada al servidor.
- **Bot de Telegram 24/7 y Sistema de Notificaciones Curadas — Fases 5 y 6:**
  Canal de mensajería bidireccional continuo que permite al servidor enviar avisos proactivos filtrados por relevancia y recibir comandos remotos autenticados desde teléfonos móviles.
- **Capa de Inteligencia y LLM Multi-Proveedor con LiteLLM — Fase 5:**
  Módulo de orquestación de modelos de lenguaje capaz de alternar dinámicamente entre Gemini, Anthropic, OpenAI y modelos locales según costo, latencia y disponibilidad de cuota.
- **Protocolo de Comunicación Remota CORE ↔ LOCAL — Fase 7:**
  Canal seguro de sincronización y transporte de mensajes en tiempo real entre el servidor central y las terminales locales o de escritorio para delegación de tareas y distribución de carga.
- **Cola de Trabajos Persistente y Registro de Dispositivos — Fases 7 y 8:**
  Mecanismo transaccional en SQLite para encolar tareas asíncronas de larga duración, registrar el estado de conexión de nodos satélite y coordinar la entrega de resultados entre dispositivos.
- **Interfaz Gráfica de Escritorio Adaptada en PyQt6 (`asistente` y `local`) — Fase 8:**
  Extensión visual de la interfaz de escritorio existente para integrar paneles de control de permisos por plugin, diálogos claros de confirmación de seguridad y visor de auditoría para el usuario final.
- **Versión Móvil del Asistente (`movil`) — Fase 9:**
  Aplicación o cliente ligero diseñado para teléfonos inteligentes enfocado en recepción de notificaciones push, confirmaciones de seguridad en un toque y consultas rápidas de estado.

---

# PARTE 2 — Propuesta Conceptual de Interfaz Visual (Cero Código)

---

## 1. `core-full`: Dashboard Web de Control Remoto 24/7

### Pantalla Principal (Vista de Estado del Servidor)
Al acceder desde un navegador web de escritorio o móvil, el usuario encuentra un panel limpio y oscuro de alta legibilidad organizado en tres áreas:
- **Cabecera superior:** Muestra el nombre de la instancia, el tiempo de actividad continuo, el perfil de permisos activo y un indicador general de salud del sistema.
- **Zona central:** Tarjetas visuales de estado que representan los componentes clave: estado del motor, plugins cargados, cola de tareas pendientes y gráfico de eventos de auditoría de las últimas horas.
- **Barra lateral o menú inferior móvil:** Acceso directo a Monitoreo en Vivo, Gestor de Plugins, Historial de Auditoría y Configuración de Conectividad (Telegram y Nodos).

### Representación Visual de Acciones que Requieren Confirmación
Cuando un proceso en segundo plano o una petición remota requiere ejecutar una acción sensible (como ejecución de código o escritura de archivos):
- Se despliega una **Tarjeta de Intervención Requerida** destacada con un tono ámbar tenue en la parte superior de la pantalla.
- La tarjeta detalla en lenguaje natural qué plugin solicita la acción, la capacidad técnica invocada y una vista previa del impacto (por ejemplo, el script que se pretende correr o la ruta del archivo que se va a modificar).
- Se presentan dos alternativas de aprobación explícitas: "Autorizar para esta sesión" o "Rechazar acción", acompañadas de una explicación clara de que autorizar habilitará la capacidad correspondiente mientras el servidor permanezca encendido.

### Visualización del Estado de Permisos
- En la sección de configuración y en la cabecera principal, las capacidades del catálogo se representan como una matriz de credenciales visuales:
  - Las capacidades autorizadas para la versión actual se muestran con un distintivo verde y una breve descripción de su función.
  - Las capacidades bloqueadas por el perfil se muestran en tono atenuado con un ícono de candado cerrado, indicando claramente que la versión actual tiene restringido ese acceso por diseño.

### Navegación y Lectura del Log de Auditoría
- La sección de auditoría abandona el aspecto de tabla de base de datos técnica y se presenta como una **Línea de Tiempo de Actividad Humana**.
- Cada evento se muestra como un bloque cronológico: un ícono indica el resultado (tilde verde para éxito, escudo rojo para denegado, mano en alto para confirmación requerida), seguido de una frase explicativa en lenguaje cotidiano (por ejemplo: "El plugin Open Interpreter ejecutó un script Python de forma segura" o "El plugin Open Interpreter intentó escribir en una ruta protegida y fue bloqueado").
- Filtros rápidos por estado (Todo, Solo Bloqueados, Solo Aprobados) permiten inspeccionar incidentes de seguridad sin necesidad de conocer SQL ni la estructura interna de tablas.

### Comunicación Remota y Notificaciones Móviles 24/7
- Al abrir el dashboard desde el navegador de un celular, la interfaz se reorganiza como un centro de control vertical:
  - Un carrusel superior resume eventos críticos que ocurrieron mientras el usuario no estaba mirando (por ejemplo, "3 tareas completadas durante la noche, 0 alertas de seguridad").
  - Si hay un evento que requiere decisión, aparece fijado como una notificación prioritaria con botones de acción táctiles grandes para responder en un solo toque.

---

## 2. `asistente` y `local`: Adaptación de la Interfaz de Escritorio en PyQt6

### Pantalla Principal (Extensión del Asistente Existente)
Conservando la estructura general de ventana y chat que ya tiene la interfaz de JARVIS_Custom, se incorporan mejoras visuales integradas:
- **Barra de estado contextual superior:** Indica de forma discreta que el núcleo está operando bajo el perfil local, mostrando el estado del sandbox y el número de plugins activos.
- **Área central de interacción:** El flujo de conversación habitual se complementa con tarjetas enriquecidas cuando un plugin genera un entregable (por ejemplo, una vista previa interactiva al crear una presentación o un visor de texto cuando se lee un documento).
- **Acceso a seguridad:** Un botón con forma de escudo en la barra superior abre el panel de control de permisos y auditoría sin abandonar la conversación principal.

### Representación Visual de Acciones que Requieren Confirmación
- La solicitud de confirmación no interrumpe al usuario con un diálogo modal bloqueante y agresivo, sino que se inserta directamente en el flujo de la conversación como una **Cápsula de Autorización de Seguridad**:
  - La cápsula resalta visualmente con un borde de advertencia estilizado y muestra el motivo de la solicitud, el plugin responsable y un botón expandible de "Ver detalles técnicos" que permite examinar el código o archivo involucrado.
  - Incluye botones claros de decisión: "Permitir durante esta ejecución" y "Denegar". La conversación se pausa suavemente hasta que el usuario toma una decisión o hasta que expira el tiempo de espera.

### Visualización del Estado de Permisos
- Dentro del panel de configuración de la interfaz, una pestaña titulada "Privacidad y Capacidades" muestra la lista de plugins instalados.
- Al seleccionar cualquier plugin, se despliega una tarjeta descriptiva que lista qué capacidades tiene concedidas según el perfil local y cuáles requerirán confirmación manual durante el uso diario.

### Navegación y Lectura del Log de Auditoría
- Dentro del mismo panel de escritorio, la pestaña "Registro de Seguridad" ofrece un visor ordenado de eventos recientes:
  - Cada fila presenta la hora exacta, el nombre del plugin, la acción y un resumen legible para el usuario final.
  - Al hacer clic en cualquier fila, se abre un panel lateral con información detallada (parámetros y respuesta del motor), permitiendo verificar exactamente qué ocurrió en caso de comportamiento inesperado.

---

## 3. `movil`: Interfaz Ligera de Acompañamiento y Control

### Pantalla Principal
Una experiencia enfocada en la consulta rápida y la toma de decisiones sobre la marcha:
- **Pantalla de inicio dividida en dos bloques:**
  - *Bloque superior (Resumen Activo):* Estado de conexión con el servidor central (`core-full`), tareas que se encuentran en ejecución y último mensaje relevante recibido.
  - *Bloque inferior (Acciones Rápidas):* Botones para consultar la hora/estado, solicitar reportes o enviar una instrucción rápida al servidor.

### Representación Visual de Confirmaciones Remotas
- Al recibir una solicitud de confirmación generada por el servidor, la aplicación móvil presenta una **Notificación Interactiva a Pantalla Completa**:
  - Muestra un encabezado claro: "JARVIS requiere tu autorización".
  - Detalla la acción solicitada, el nivel de riesgo y la opción de aprobar mediante un deslizador de confirmación (previniendo toques accidentales) o rechazar con un toque simple.

### Visualización de Permisos y Auditoría
- Un menú lateral simplificado permite revisar el estado de sincronización con el servidor y un historial condensado de las últimas autorizaciones concedidas de forma remota.

---

## 4. Preguntas Abiertas de Diseño para Definición Previa

Antes de iniciar la construcción de cualquiera de las interfaces visuales, se identifican las siguientes decisiones conceptuales de diseño que deben acordarse:

1. **Persistencia visual de autorizaciones en sesión:**
   Dado que el núcleo cachea las confirmaciones por capacidad durante toda la sesión de proceso, ¿la interfaz debe mostrar un indicador permanente y visible (por ejemplo, una insignia de "Modo ejecución de código activo") en la pantalla principal para recordar al usuario que dicha capacidad ya no volverá a pedir permiso hasta reiniciar el programa?

2. **Mecanismo de respuesta ante expiración de confirmaciones remotas:**
   En el dashboard web y la versión móvil, si una acción sensible queda en espera de confirmación y el usuario no responde tras un periodo prudencial, ¿la interfaz debe cancelar automáticamente la solicitud por tiempo límite y registrar el evento como expirado, o debe mantener la tarjeta en espera indefinida hasta que el usuario abra la aplicación?

3. **Nivel de detalle técnico predeterminado en el visor de auditoría:**
   ¿Es preferible que el visor de auditoría para usuarios de escritorio muestre por defecto únicamente descripciones en lenguaje simple ocultando los identificadores técnicos bajo un botón de "Detalles avanzados", o debe ofrecer desde el primer vistazo una vista técnica compacta orientada a usuarios avanzados?
