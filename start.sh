#!/bin/bash
#Folder where deltabot-cli stores the bot account (it can be overridden with CONFIG_DIR)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#the bot is run from its own folder: python3 -m telebridge must find the modules
cd "$SCRIPT_DIR" || exit 1
CONFIG_DIR="${CONFIG_DIR:-$HOME/.simplebot}"
export CONFIG_DIR

#load the variables from the .env files (the real environment always wins),
#using the same loader as the bot so values with spaces are handled correctly
if [ -f "$SCRIPT_DIR/env_loader.py" ]; then
   eval "$(PYTHONPATH="$SCRIPT_DIR" python3 "$SCRIPT_DIR/env_loader.py" --export)"
fi

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

HEALTH_PID=""
BOT_PID=""

stop_bot() {
   #forward the signal to the bot, so it can shutdown cleanly
   if [ -n "$BOT_PID" ] && kill -0 "$BOT_PID" 2>/dev/null; then
      kill -INT "$BOT_PID" 2>/dev/null
   fi
}
trap stop_bot TERM INT

#hosting providers (Render, Koyeb...) require web services to bind a port
if [ -n "$PORT" ]; then
   python3 ./health.py &
   HEALTH_PID=$!
fi

#RUN_MINUTES is used on CI environments (like GitHub Actions) where the bot can
#not run forever: serve for that time and then store a backup in Telegram
if [ -n "$RUN_MINUTES" ]; then
   echo "Sirviendo mensajes durante $RUN_MINUTES minutos..."
   timeout --signal=INT "${RUN_MINUTES}m" python3 -m telebridge --config-dir "$CONFIG_DIR" serve &
else
   python3 -m telebridge --config-dir "$CONFIG_DIR" serve &
fi
BOT_PID=$!

#wait for the bot, restarting the wait if a signal interrupts it
while kill -0 "$BOT_PID" 2>/dev/null; do
   wait "$BOT_PID" 2>/dev/null || true
done

#with an ephemeral filesystem (CI runners, free hosting plans) the account is
#lost when the process dies, so store a backup in Telegram before exiting
if [ -n "$BACKUP_ON_EXIT" ] || [ -n "$RUN_MINUTES" ]; then
   echo "Guardando copia de seguridad..."
   python3 -m telebridge --config-dir "$CONFIG_DIR" backup || true
fi

if [ -n "$HEALTH_PID" ]; then
   kill "$HEALTH_PID" 2>/dev/null
fi
