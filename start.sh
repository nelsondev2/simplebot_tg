#!/bin/bash
#Folder where deltabot-cli stores the bot account (it can be overridden with CONFIG_DIR)
CONFIG_DIR="${CONFIG_DIR:-$HOME/.simplebot}"
BOTZIPDB="./${ADDR/@/%40}.zip"
echo "CONFIG_DIR = $CONFIG_DIR"
echo "BOTZIPDB = $BOTZIPDB"

#true if the bot account is already configured
is_configured() {
   python3 -m telebridge --config-dir "$CONFIG_DIR" list 2>/dev/null | grep "^#" | grep -qv "not configured"
}

if is_configured; then
   echo "Bot ya inicializado!"
else
   echo "Restaurando..."
   python3 ./restore.py
   rm -f "$BOTZIPDB"
   if is_configured; then
      echo "Bot restaurado!"
   else
      echo "No existen restauras, configurando..."
      python3 -m telebridge --config-dir "$CONFIG_DIR" init "$ADDR" "$PASSWORD"
   fi
fi
if [ -n "$ADMIN" ]; then
   echo "Administrador del bot: $ADMIN"
fi

#RUN_MINUTES is set by CI environments (like GitHub Actions) where the bot can
#not run forever: serve for that time and then store a backup in Telegram
if [ -n "$RUN_MINUTES" ]; then
   echo "Sirviendo mensajes durante $RUN_MINUTES minutos..."
   timeout --signal=INT "${RUN_MINUTES}m" python3 -m telebridge --config-dir "$CONFIG_DIR" serve
   echo "Guardando copia de seguridad..."
   python3 -m telebridge --config-dir "$CONFIG_DIR" backup
else
   python3 -m telebridge --config-dir "$CONFIG_DIR" serve
fi
