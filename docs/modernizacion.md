# Investigación de modernización

## Implementado

- El evento nativo `events.NewMessage` sigue usando el filtro de deltachat2 y
  delega el trabajo a un hilo, sin bloquear el bucle de eventos de Delta Chat.
- Las operaciones lentas indican procesamiento con la reacción ⏳. Se retira
  al acabar. Algunos manejadores capturan y comunican sus propios errores, por
  lo que retirar ⏳ **no significa éxito**; no se envía un ✅ engañoso. Un
  error no controlado produce ❌ si el cliente admite reacciones.
- `/news`, `/list` y `/search` ofrecen vistas webxdc. En `/list` y `/search`
  se conservan las respuestas en texto existentes. Las acciones emplean
  `sendToChat`: la persona elige el chat y confirma el envío; el webxdc no
  ejecuta operaciones directamente. Los datos del webxdc son una instantánea
  visible para todas las personas que reciban ese mensaje.
- `/stats` informa de cola, errores no controlados, tarea automática y estado
  de copia de seguridad sin incluir sesiones ni nombres de usuarios. El último
  backup correcto se registra solo durante la ejecución actual. Los fallos de
  backup quedan pendientes para reintento, con separación mínima de 30 segundos.

## Investigado; no activado por seguridad y compatibilidad

- **Paralelismo por usuario:** los manejadores utilizan `loop.run_until_complete`
  sobre un único bucle global y comparten diccionarios, estados de inicio de
  sesión y clientes Telethon con la tarea automática. Ejecutarlos en hilos
  paralelos sin rediseñar la propiedad de bucles, sesiones y datos puede causar
  carreras, pérdida de cambios y errores de sesión. Se necesita aislar por
  usuario, coordinar `/auto` con comandos y probar orden, cancelación y reinicio.
- **Reacciones entre plataformas:** deltachat2 expone `EventTypeIncomingReaction`,
  `EventTypeReactionsChanged`, `get_message_reactions` y `send_reaction`.
  La asociación de mensajes del puente (`messagedb`) está en memoria y se
  pierde al reiniciar; en grupos también debe verificarse qué usuario de
  Telegram tiene autorización para actuar. La sincronización automática necesita
  persistencia, manejo de eliminación/cambios, emojis no compatibles y prevención
  de bucles. `/react` permanece disponible.
- **Botones de Telegram:** el puente ya distingue consultas inline, URL y otros
  botones; `/c` acciona botones mediante Telegram. No todos los botones son
  equivalentes: algunos solicitan información o abren apps. Convertirlos todos
  en botones webxdc sin comprobar tipo, contexto y consentimiento cambiaría su
  comportamiento. Siguen disponibles los mecanismos existentes.
- **Migración completa de `dc_compat.py`:** requiere sustituir gradualmente
  comandos, filtros, respuestas, chats y almacenamiento con pruebas de regresión.
  Eliminar la capa ahora implicaría una reescritura extensa, sin garantía de
  conservar el comportamiento del puente. No se ha eliminado.
- No se ha automatizado una alerta al administrador por cada error: antes hacen
  falta límites de frecuencia y una política de redacción para evitar spam o
  filtrar información sensible.

Las pruebas de este repositorio funcionan sin credenciales y no sustituyen una
prueba real con Delta Chat, IMAP y Telegram. En particular, compruebe la apertura
webxdc, el selector de destino y las reacciones en su cliente.
