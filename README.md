# simplebot_tg
Telegram/DeltaChat Bridge, made with [deltabot-cli](https://github.com/deltachat-bot/deltabot-cli-py),
the library to develop Delta Chat bots.

## Demo Bot
<a href="mailto:dc.telebridge@gmail.com">dc.telebridge@gmail.com</a>

## Install
To install the bot dependencies run the following command (preferably in a
[virtual environment](https://packaging.python.org/tutorials/installing-packages/#creating-and-using-virtual-environments)):

```sh
pip install -r requirements.txt
```

## Configs enviroments variables
- API_HASH
  - Get from [Here](https://my.telegram.org).
- API_ID
  - Get from [Here](https://my.telegram.org). 
- ADDR
  - The email bot with imap enabled
- PASSWORD
  - The email bot password 
- ADMIN
  - Your own email as bot admin
- TGTOKEN
  - (Optional) Telegram session token, used to store a backup of the bot db in Telegram.
- CONFIG_DIR
  - (Optional) Folder where the bot account is stored, default: `$HOME/.simplebot`
- WHITE_LIST / BLACK_LIST
  - (Optional) space separated list of email addresses allowed/blocked to use the bot.
- APP_KEY
  - (Optional) Get from [Here](https://www.dropbox.com/developers/apps/create).
- DBXTOKEN
  - (Optional) Get from [Here](https://www.dropbox.com/developers/apps/create).

## Run local

```sh
./start.sh
```

The script restores the account backup (if any), configures the bot account and
then starts serving messages. It is a shortcut for:

```sh
# configure the bot account
python3 -m telebridge --config-dir ~/.simplebot init "$ADDR" "$PASSWORD"
# start serving messages
python3 -m telebridge --config-dir ~/.simplebot serve
```

`deltabot-cli` also offers some other useful subcommands, run
`python3 -m telebridge --help` to see them all, for example:

```sh
# show the invitation link of the bot administration group
python3 -m telebridge --config-dir ~/.simplebot admin
# backup the account in a tarball
python3 -m telebridge --config-dir ~/.simplebot export ./backups
```

The administrators of the bot are the members of the *Bot Admins* group (the
address set in the `ADMIN` environment variable is added automatically).

## Commands

Send `/help` to the bot to get the list of available commands. Some examples:

- `/login +5355555555` then `/sms 12345` or `/token <session>`: log in to Telegram.
- `/load`, `/load #privates`: link Telegram chats to Delta Chat chats.
- `/more`, `/down`, `/comment`, `/inline`: load messages, files, comments and inline bot results.
- `/list`, `/remove`, `/link2`: manage the linked chats.
- `/news`, `/search`, `/join`, `/preview`: list, search, join and preview chats.
- `/setting`, `/stats`, `/eval`, `/exec`, `/start`, `/stop`: bot administration (admins only).

## Deploy Now:
[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/Nenirey/simplebot_tg/tree/main)
