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

The bot loads them from a `.env` file if it exists, so instead of exporting them
in the shell you can create e.g. `$HOME/.env` (or `./.env`, or
`$CONFIG_DIR/.env`):

```sh
ADDR=bot@midominio.com
PASSWORD=mi_password
API_ID=1234567
API_HASH=0123456789abcdef0123456789abcdef
ADMIN=yo@midominio.com
```

Variables already set in the environment always win over the `.env` file, and
the files are searched in this order: `$CONFIG_DIR/.env`, `./.env`, the `.env`
next to the code, `$HOME/.env` and `$HOME/.simplebot/.env`. `start.sh` loads the
same files, so you do not need to export anything when running it.

- API_HASH
  - Get from [Here](https://my.telegram.org).
- API_ID
  - Get from [Here](https://my.telegram.org). 
- ADDR
  - The email bot with imap enabled
- PASSWORD
  - The email bot password 
- ADMIN
  - Your own Delta Chat e-mail address (it must be a valid e-mail!), added as bot admin
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

Commands that are steps of another flow (`/sms`, `/pass`) or internal helpers
(`/c`, `/b`, `/inmore`, `/inclick`, `/indown`) keep working but are not listed in
`/help`, so the list only shows the commands you use directly.

Since Delta Chat/ArcaneChat no longer handle `mailto:` links, the bot sends the
commands of `/list` and of the inline results as plain text (for example
`/load 1234`), so you can copy them or send them as a normal message.
- `/list`, `/remove`, `/link2`: manage the linked chats.
- `/news`, `/search`, `/join`, `/preview`: list, search, join and preview chats.
- `/setting`, `/stats`, `/eval`, `/exec`, `/start`, `/stop`: bot administration (admins only).

## Run on GitHub Actions

The bot can be run on GitHub Actions (see `.github/workflows/bot.yml`), but keep in
mind that Actions is a CI service, not a hosting service:

- a job can run for 6 hours at most, and then the runner (and the bot account
  stored in it) is destroyed;
- that is why every run **restores** the bot account from the backup stored in
  Telegram, serves messages for `RUN_MINUTES` (320 by default) and uploads a
  fresh backup before stopping;
- the workflow is scheduled every 4 hours and a `concurrency` group prevents two
  instances from running at the same time (two instances sharing the same
  Telegram session would invalidate the session).

Configuration:

1. Add the repository secrets `ADDR`, `PASSWORD`, `API_ID`, `API_HASH`,
   `TGTOKEN` and `ADMIN` (settings → Secrets and variables → Actions).
   `TGTOKEN` is the session of a Telegram **user** account, used to keep the
   backup of the bot in its *Saved messages* (see `pip install telethon` +
   `python -c "from telethon.sync import TelegramClient; print(...)"` or just
   log in to the bot once with `/login` + `/token` and copy the token).
2. Scheduled workflows only run from the default branch, so merge this to
   `main` (or run it manually with `gh workflow run bot.yml --ref <branch>`).
3. For a private repository, check the Actions minutes of your plan.

It is fine for testing or for a bot with little traffic, but for a bot that must
be online 24/7 a small VPS (or any always-on host) running `./start.sh` as a
service is a much better option.

`start.sh` also honors `PORT` (starts the little health endpoint in `health.py`,
needed by hosting providers like Render) and `BACKUP_ON_EXIT` (store a backup in
Telegram when the process stops, for hosts with an ephemeral filesystem).

## Run on Render

The repository ships a `Dockerfile` and a `render.yaml` blueprint (Render sets
`PORT` for web services, and `health.py` is started automatically in that case so
the service is considered healthy).

1. In Render: **New + → Blueprint**, select this repository (merge it to the
   default branch first) and apply.
2. Fill the secrets it asks for (`ADDR`, `PASSWORD`, `ADMIN`, `API_ID`,
   `API_HASH`, `TGTOKEN`).
3. Done, the bot is reachable at `https://<service>.onrender.com/healthz`.

Two things you must know before choosing the plan:

| | Free web service ($0) | Background worker (~$7/month) |
| --- | --- | --- |
| Spins down | after 15 min **without HTTP traffic** | never |
| Filesystem | ephemeral | persistent disk available |
| Keeps the bot online | only with an external ping | yes |

- Render does **not** offer free instances for background workers, and a free web
  service sleeps after 15 minutes without inbound HTTP traffic (Delta Chat
  receiving an email does not count as traffic). So on the free plan:
  - point an uptime monitor (UptimeRobot, cron-job.org, …) to
    `https://<service>.onrender.com/healthz` every 5 minutes to keep it awake,
    and keep in mind the **750 free instance hours per month** limit of the
    workspace (an always-on service is ~744 hours, so there is little headroom);
  - the filesystem is ephemeral, so `BACKUP_ON_EXIT=1` makes `start.sh` store a
    backup of the bot account in Telegram when the service stops, and
    `restore.py` recovers it on the next start. That is why `TGTOKEN` is
    **required** in this mode.
- With a paid instance you can use the `worker` service variant that is
  commented at the bottom of `render.yaml`: it runs continuously, does not need
  HTTP traffic and mounts a 1 GB persistent disk in `/var/data`, so the account
  (and the Delta Chat / Telegram sessions) survive restarts and deploys.

## Deploy Now:
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Nenirey/simplebot_tg)
[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/Nenirey/simplebot_tg/tree/main)
