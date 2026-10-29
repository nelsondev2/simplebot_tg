"""Compatibility layer for telebridge.

``telebridge.py`` was written against the old ``deltachat`` Python bindings
(the objects exposed by ``simplebot``: ``bot``, ``Chat``, ``Contact``,
``Message``, ``Replies``...).  Delta Chat bots are now developed with
``deltabot-cli`` + ``deltachat2``, which talk to ``deltachat-rpc-server``
through a JSON-RPC API where every call receives an account id and returns
plain data objects instead of live bindings.

This module re-implements the small subset of the old API that the bridge
uses, on top of ``deltachat2``.  That way the bridge logic is kept exactly as
it was, and the only thing that changed is the library underneath.
"""

from __future__ import annotations

import inspect
import logging
import os
import re
import sqlite3
import threading
from tempfile import NamedTemporaryFile
from typing import Any, List, Optional, Union

from deltachat2 import (
    ChatType,
    JsonRpcError,
    MessageData,
    MessageQuoteWithMessage,
    SpecialContactId,
    Viewtype,
)

CMD_PREFIX = "/"

#: a "simple" e-mail address check, the core does the real validation
ADDR_RE = re.compile(r"^[^@<>\s]+@[^@<>\s]+\.[^@<>\s]+$")


def is_valid_address(addr) -> bool:
    """Return True if ``addr`` looks like an e-mail address."""
    return bool(isinstance(addr, str) and ADDR_RE.match(addr.strip()))

# mapping of the old deltachat viewtype names to the new Viewtype enum
_VIEWTYPES = {
    "text": Viewtype.TEXT,
    "image": Viewtype.IMAGE,
    "gif": Viewtype.GIF,
    "sticker": Viewtype.STICKER,
    "audio": Viewtype.AUDIO,
    "voice": Viewtype.VOICE,
    "video": Viewtype.VIDEO,
    "file": Viewtype.FILE,
    "vcard": Viewtype.VCARD,
    "webxdc": Viewtype.WEBXDC,
}

# arguments a command/filter callback may ask for (same as simplebot)
CMD_ARGS = ("command", "replies", "bot", "payload", "args", "message")
FILTER_ARGS = ("message", "replies", "bot")


def _viewtype(value: Any) -> Optional[Viewtype]:
    if value is None or isinstance(value, Viewtype):
        return value
    try:
        return _VIEWTYPES[str(value).lower()]
    except KeyError:
        raise ValueError(f"unknown viewtype: {value!r}") from None


def _call(func, **kwargs):
    """Call ``func`` passing only the arguments it accepts."""
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):  # builtins, C functions, mocks, etc.
        return func(**kwargs)
    if any(p.kind is p.VAR_KEYWORD for p in params.values()):
        return func(**kwargs)
    return func(**{key: val for key, val in kwargs.items() if key in params})


class Contact:
    """A Delta Chat contact."""

    def __init__(self, rpc, accid: int, contact_id: int, data=None) -> None:
        self._rpc = rpc
        self._accid = accid
        self.id = int(contact_id)
        self._data = data

    @property
    def _contact(self):
        if self._data is None:
            self._data = self._rpc.get_contact(self._accid, self.id)
        return self._data

    @property
    def addr(self) -> str:
        return self._contact.address

    @property
    def address(self) -> str:
        return self.addr

    @property
    def display_name(self) -> str:
        return self._contact.display_name

    def is_blocked(self) -> bool:
        return bool(self._contact.is_blocked)

    def __eq__(self, other) -> bool:
        return isinstance(other, Contact) and other.id == self.id

    def __ne__(self, other) -> bool:
        return not self == other

    def __hash__(self) -> int:
        return hash(("Contact", self.id))

    def __repr__(self) -> str:
        return f"<Contact {self.addr!r}>"


class Chat:
    """A Delta Chat chat."""

    def __init__(self, rpc, accid: int, chat_id: int, data=None) -> None:
        self._rpc = rpc
        self._accid = accid
        self.id = int(chat_id)
        self._data = data

    @property
    def _chat(self):
        if self._data is None:
            self._data = self._rpc.get_full_chat_by_id(self._accid, self.id)
        return self._data

    def get_full_chat(self):
        """Return the raw ``deltachat2`` FullChat object."""
        return self._chat

    def get_name(self) -> str:
        """Return the chat name."""
        return self._chat.name

    def get_profile_image(self) -> Optional[str]:
        """Return the chat profile image path, if any."""
        return self._chat.profile_image

    def is_multiuser(self) -> bool:
        """Return True if this is a group, broadcast list or mailing list."""
        return self._chat.chat_type != ChatType.SINGLE

    def is_group(self) -> bool:
        """Return True if this is a group chat."""
        return self._chat.chat_type == ChatType.GROUP

    def is_mailinglist(self) -> bool:
        """Return True if this is a mailing list."""
        return self._chat.chat_type == ChatType.MAILINGLIST

    def get_contacts(self) -> List[Contact]:
        """Return the contacts belonging to this chat."""
        return [
            Contact(self._rpc, self._accid, contact_id)
            for contact_id in self._rpc.get_chat_contacts(self._accid, self.id)
        ]

    def get_messages(self) -> List["Message"]:
        """Return all messages of this chat, oldest first."""
        return [
            Message.load(self._rpc, self._accid, msg_id)
            for msg_id in self._rpc.get_message_ids(self._accid, self.id, False, False)
        ]

    def send_text(self, text: str) -> "Message":
        """Send a text message to this chat."""
        msg_id = self._rpc.misc_send_text_message(self._accid, self.id, text)
        return Message.load(self._rpc, self._accid, msg_id)

    def send_msg(self, msg: "MessageData") -> "Message":
        """Send a pre-built ``deltachat2.MessageData`` to this chat."""
        msg_id = self._rpc.send_msg(self._accid, self.id, msg)
        return Message.load(self._rpc, self._accid, msg_id)

    def set_name(self, name: str) -> None:
        """Set the chat name."""
        self._rpc.set_chat_name(self._accid, self.id, name)
        self._data = None

    def set_profile_image(self, path: str) -> None:
        """Set the chat profile image."""
        self._rpc.set_chat_profile_image(self._accid, self.id, path)
        self._data = None

    def __eq__(self, other) -> bool:
        return isinstance(other, Chat) and other.id == self.id

    def __ne__(self, other) -> bool:
        return not self == other

    def __hash__(self) -> int:
        return hash(("Chat", self.id))

    def __repr__(self) -> str:
        return f"<Chat id={self.id}>"


class Message:
    """A Delta Chat message.

    The message data is loaded on demand, so creating a Message object from a
    message id is cheap (handy when listing all the messages of a chat).
    """

    def __init__(self, rpc, accid: int, data=None, msg_id: int = None) -> None:
        self._rpc = rpc
        self._accid = accid
        self._data = data
        self._msg_id = int(data.id if data is not None else msg_id)

    @classmethod
    def load(cls, rpc, accid: int, msg_id: int) -> "Message":
        """Return a (lazy) message object for the message with the given id."""
        return cls(rpc, accid, msg_id=msg_id)

    @property
    def data(self):
        if self._data is None:
            self._data = self._rpc.get_message(self._accid, self._msg_id)
        return self._data

    @property
    def id(self) -> int:
        return self._msg_id

    @property
    def text(self) -> str:
        return self.data.text

    @property
    def chat(self) -> Chat:
        return Chat(self._rpc, self._accid, self.data.chat_id)

    @property
    def filename(self) -> Optional[str]:
        """Path of the attached file, None if the message has no file."""
        return self.data.file or None

    @property
    def filemime(self) -> Optional[str]:
        return self.data.file_mime

    @property
    def quote(self) -> Optional["Message"]:
        """The quoted message, None if this message doesn't quote anything."""
        quote = self.data.quote
        if not isinstance(quote, MessageQuoteWithMessage):
            return None
        return Message.load(self._rpc, self._accid, quote.message_id)

    def get_sender_contact(self) -> Contact:
        """Return the contact that sent this message."""
        sender = self.data.sender
        return Contact(self._rpc, self._accid, sender.id, sender)

    def get_message_info(self) -> str:
        """Return an informational text about this message."""
        return self._rpc.get_message_info(self._accid, self.id)

    def get_filemime(self) -> Optional[str]:
        return self.filemime

    def is_system_message(self) -> bool:
        return bool(self.data.is_info)

    def is_audio(self) -> bool:
        return self.data.view_type in (Viewtype.AUDIO, Viewtype.VOICE)

    def is_gif(self) -> bool:
        return self.data.view_type == Viewtype.GIF

    def is_image(self) -> bool:
        return self.data.view_type == Viewtype.IMAGE

    def is_video(self) -> bool:
        return self.data.view_type == Viewtype.VIDEO

    def is_file(self) -> bool:
        return self.data.view_type == Viewtype.FILE

    def mark_seen(self) -> None:
        self._rpc.markseen_msgs(self._accid, [self.id])

    def __eq__(self, other) -> bool:
        return isinstance(other, Message) and other.id == self.id

    def __ne__(self, other) -> bool:
        return not self == other

    def __hash__(self) -> int:
        return hash(("Message", self.id))

    def __repr__(self) -> str:
        return f"<Message id={self.id}>"


class Replies:
    """Collects the replies that a bot plugin wants to send."""

    def __init__(self, bot, logger=None) -> None:
        if isinstance(bot, Message):
            self.bot = None
            self.incoming_message: Optional[Message] = bot
        else:
            self.bot = bot
            self.incoming_message = None
        self.logger = logger or getattr(bot, "logger", None) or logging.getLogger(__name__)
        self._replies: List[tuple] = []

    def has_replies(self) -> bool:
        return bool(self._replies)

    def add(
        self,
        text: str = None,
        *,
        html: str = None,
        viewtype: str = None,
        filename: str = None,
        bytefile=None,
        sender: str = None,
        quote: Message = None,
        chat: Chat = None,
    ) -> None:
        """Schedule a reply message."""
        if bytefile and not filename:
            raise ValueError("missing filename suggestion, needed with bytefile")
        if bytefile and os.path.basename(filename) != filename:
            raise ValueError(
                "if bytefile is specified, filename must be a basename, not a path"
            )
        self._replies.append(
            (text, html, viewtype, filename, bytefile, sender, quote, chat)
        )

    def append_html_to_last_reply(self, fragment: str) -> None:
        """Add HTML actions while retaining the plain-text reply as a fallback."""
        if not self._replies:
            raise ValueError("no reply to update")
        text, html, viewtype, filename, bytefile, sender, quote, chat = self._replies[-1]
        if html is None:
            from html import escape
            html = escape(text or "").replace("\n", "<br>")
        self._replies[-1] = (text, html + fragment, viewtype, filename, bytefile, sender, quote, chat)

    def send_reply_messages(self) -> List[Message]:
        """Send all the scheduled replies, returning the sent messages."""
        sent = []
        for (text, html, viewtype, filename, bytefile, sender, quote, chat) in self._replies:
            msg = self._create_message_data(
                text, html, viewtype, filename, bytefile, sender, quote
            )
            if chat is None:
                chat = self.incoming_message.chat
            msg_obj = chat.send_msg(msg)
            if self.logger:
                self.logger.debug(
                    "reply id=%s chat=%s sent with text: %r",
                    msg_obj.id,
                    chat.id,
                    (text or "")[:50],
                )
            sent.append(msg_obj)
        self._replies[:] = []
        return sent

    def _create_message_data(
        self,
        text: str = None,
        html: str = None,
        viewtype: str = None,
        filename: str = None,
        bytefile=None,
        sender: str = None,
        quote: Message = None,
    ) -> MessageData:
        accid = self._accid
        if bytefile:
            assert filename is not None, "bytefile given but filename not provided"
            blobdir = self._rpc.get_blob_dir(accid) or os.getcwd()
            parts = filename.split(".", maxsplit=1)
            if len(parts) == 2:
                prefix, suffix = parts
                prefix += "-"
                suffix = "." + suffix
            else:
                prefix = filename + "-"
                suffix = None
            with NamedTemporaryFile(
                dir=blobdir, prefix=prefix, suffix=suffix, delete=False
            ) as fp:
                filename = fp.name
            with open(filename, "wb") as f:
                with bytefile:
                    f.write(bytefile.read())

        if not viewtype:
            viewtype = "file" if filename else "text"

        return MessageData(
            text=text,
            html=html,
            file=filename,
            viewtype=_viewtype(viewtype),
            quoted_message_id=quote.id if quote is not None else None,
            override_sender_name=sender,
        )

    @property
    def _rpc(self):
        return self.bot.rpc if self.bot is not None else self.incoming_message._rpc

    @property
    def _accid(self) -> int:
        if self.bot is not None:
            return self.bot.accid
        return self.incoming_message._accid


class SettingsStore:
    """Persistent key/value settings, compatible with simplebot's ``bot.db``."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()
        dirname = os.path.dirname(path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        with self._lock, self.db:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS config"
                " (keyname TEXT PRIMARY KEY,value TEXT)"
            )

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            row = self.db.execute(
                "SELECT value FROM config WHERE keyname=?", (key,)
            ).fetchone()
        return row and row["value"]

    def set(self, key: str, value: Optional[str]) -> Optional[str]:
        old = self.get(key)
        with self._lock, self.db:
            if value is None:
                self.db.execute("DELETE FROM config WHERE keyname=?", (key,))
            else:
                self.db.execute("REPLACE INTO config VALUES (?,?)", (key, str(value)))
        return old

    def list(self) -> List[tuple]:
        with self._lock:
            rows = self.db.execute("SELECT * FROM config").fetchall()
        return [(row["keyname"], row["value"]) for row in rows]

    def close(self) -> None:
        with self._lock:
            self.db.close()


class CommandDef:
    """Definition of a '/COMMAND'."""

    def __init__(self, cmd: str, func, admin=False, hidden=False, help=None) -> None:
        self.cmd = cmd
        self.func = func
        self.admin = admin
        self.hidden = hidden
        self.help = help if help is not None else (func.__doc__ or "")
        self.short = self.help.strip().split("\n", maxsplit=1)[0]

    def __call__(self, **kwargs):
        return _call(self.func, **kwargs)


class IncomingCommand:
    """An incoming command request."""

    def __init__(self, bot, cmd_def: CommandDef, args, payload, message: Message) -> None:
        self.bot = bot
        self.cmd_def = cmd_def
        self.args = args
        self.payload = payload
        self.message = message

    def __repr__(self) -> str:
        return f"<IncomingCommand {self.cmd_def.cmd!r} payload={self.payload!r}>"


class Commands:
    """Registry and dispatcher of bot commands."""

    def __init__(self, bot) -> None:
        self.bot = bot
        self.logger = bot.logger
        self._cmd_defs = {}

    def register(
        self, func, name: str = None, help: str = None, admin: bool = False, hidden: bool = False
    ) -> CommandDef:
        """Register a command function."""
        name = name or CMD_PREFIX + func.__name__
        cmd_def = CommandDef(name, func, admin=admin, hidden=hidden, help=help)
        self._cmd_defs[name.lower()] = cmd_def
        self.logger.debug("registered new command %r", name)
        return cmd_def

    def unregister(self, name: str) -> CommandDef:
        return self._cmd_defs.pop(name.lower())

    def dict(self) -> dict:
        return self._cmd_defs.copy()

    def handle(self, message: Message, replies: Replies) -> bool:
        """Process the given message as a command, return True if it was one."""
        text = message.text or ""
        if not text.startswith(CMD_PREFIX):
            return False
        args = text.split()
        payload = text.split(maxsplit=1)[1] if len(args) > 1 else ""
        orig_cmd_name = args.pop(0)

        if "@" in orig_cmd_name:
            suffix = "@" + self.bot.self_contact.addr
            if orig_cmd_name.endswith(suffix):
                orig_cmd_name = orig_cmd_name[: -len(suffix)]
            else:
                return True

        parts = orig_cmd_name.split("_")
        cmd_def = None
        while parts:
            cmd_def = self._cmd_defs.get("_".join(parts).lower())
            if cmd_def is not None:
                break
            newarg = parts.pop()
            args.insert(0, newarg)
            payload = (newarg + " " + payload).rstrip()

        if not cmd_def or (
            cmd_def.admin and not self.bot.is_admin(message.get_sender_contact().addr)
        ):
            reply = f"unknown command {orig_cmd_name!r}"
            self.logger.warning(reply)
            if not message.chat.is_multiuser():
                replies.add(text=reply)
            return True

        cmd = IncomingCommand(
            bot=self.bot, cmd_def=cmd_def, message=message, args=args, payload=payload
        )
        self.logger.debug("processing command %s", cmd)
        try:
            cmd_def(
                command=cmd,
                replies=replies,
                bot=self.bot,
                payload=cmd.payload,
                args=cmd.args,
                message=cmd.message,
            )
        except Exception as ex:  # noqa: BLE001
            self.logger.exception(ex)
        return True


class FilterDef:
    """Definition of a message filter."""

    def __init__(self, name: str, func, admin=False, hidden=False, priority=0) -> None:
        self.name = name
        self.func = func
        self.admin = admin
        self.hidden = hidden
        self.priority = priority
        self.help = func.__doc__ or ""
        self.short = self.help.strip().split("\n", maxsplit=1)[0]

    def __call__(self, **kwargs):
        return _call(self.func, **kwargs)


class Filters:
    """Registry and dispatcher of message filters."""

    def __init__(self, bot) -> None:
        self.bot = bot
        self.logger = bot.logger
        self._filter_defs = {}

    def register(
        self,
        func,
        name: str = None,
        help: str = None,  # noqa: A002
        tryfirst: bool = False,
        trylast: bool = False,
        admin: bool = False,
        hidden: bool = False,
    ) -> FilterDef:
        name = name or f"{func.__module__}.{func.__name__}"
        filter_def = FilterDef(
            name, func, admin=admin, hidden=hidden, priority=0 - tryfirst + trylast
        )
        if help is not None:
            filter_def.help = help
            filter_def.short = help.strip().split("\n", maxsplit=1)[0]
        self._filter_defs[name] = filter_def
        self.logger.debug("registered new filter %r", name)
        return filter_def

    def unregister(self, name: str) -> FilterDef:
        return self._filter_defs.pop(name)

    def dict(self) -> dict:
        return self._filter_defs.copy()

    def apply(self, message: Message, replies: Replies) -> None:
        """Run all the filters over the given message."""
        is_admin = self.bot.is_admin(message.get_sender_contact().addr)
        for _, filter_def in sorted(
            self._filter_defs.items(), key=lambda e: e[1].priority
        ):
            if filter_def.admin and not is_admin:
                continue
            self.logger.debug("calling filter %r on message id=%s", filter_def.name, message.id)
            if filter_def(message=message, replies=replies, bot=self.bot):
                return


class Account:
    """The bot's Delta Chat account."""

    def __init__(self, bot: "DeltaBot") -> None:
        self._bot = bot

    @property
    def rpc(self):
        return self._bot.rpc

    @property
    def accid(self) -> int:
        return self._bot.accid

    def get_config(self, key: str) -> Optional[str]:
        """Get an account configuration value."""
        return self.rpc.get_config(self.accid, key)

    def set_config(self, key: str, value: str) -> None:
        """Set an account configuration value."""
        self.rpc.set_config(self.accid, key, value)

    def set_avatar(self, path: str) -> None:
        """Set the account avatar from the given image path."""
        self.rpc.set_config(self.accid, "selfavatar", path)

    def get_chats(self) -> List[Chat]:
        """Return all chats of the account."""
        chat_ids = self.rpc.get_chatlist_entries(self.accid, None, None, None)
        return [Chat(self.rpc, self.accid, chat_id) for chat_id in chat_ids]

    def get_self_contact(self) -> Contact:
        """Return the account's own contact."""
        return self._bot.self_contact

    def get_message_by_id(self, msg_id: int) -> Message:
        """Load the message with the given id."""
        return Message.load(self.rpc, self.accid, msg_id)

    def get_connectivity_html(self) -> str:
        """Return an HTML overview of the account connectivity."""
        return self.rpc.get_connectivity_html(self.accid)

    def get_blobdir(self) -> Optional[str]:
        """Return the account blob directory."""
        return self.rpc.get_blob_dir(self.accid)

    def add_account_plugin(self, plugin) -> None:
        """Kept for API compatibility, account plugins no longer exist."""


class DeltaBot:
    """The bot object handed over to the bridge's commands and filters."""

    def __init__(
        self,
        client,
        accid: int = 0,
        config_dir: str = "",
        cli=None,
        admin_addr: Optional[str] = None,
    ) -> None:
        self.client = client
        self.rpc = client.rpc
        self.logger = client.logger
        self.config_dir = config_dir
        self.cli = cli
        self.admin_addr = admin_addr
        self.commands = Commands(self)
        self.filters = Filters(self)
        self.account = Account(self)
        self.accid = 0
        self._settings: Optional[SettingsStore] = None
        self.use_account(accid)

    def use_account(self, accid: int) -> None:
        """Set the account this bot works with."""
        self.accid = int(accid or 0)
        if self._settings is not None:
            self._settings.close()
            self._settings = None
        if self.accid > 0:
            path = os.path.join(
                self.config_dir, "accounts", str(self.accid), "bot.db"
            )
            self._settings = SettingsStore(path)

    #
    # persistent key/value settings API
    #
    def get(self, name: str, default: str = None, scope: str = "global") -> Optional[str]:
        """Get a bot setting from the given scope."""
        if self._settings is None:
            return default
        value = self._settings.get(scope + "/" + name)
        return value if value is not None else default

    def set(self, name: str, value: str, scope: str = "global") -> Optional[str]:
        """Store a bot setting with the given scope."""
        if self._settings is None:
            return None
        return self._settings.set(scope + "/" + name, value)

    def delete(self, name: str, scope: str = "global") -> None:
        """Delete a bot setting with the given scope."""
        if self._settings is not None:
            self._settings.set(scope + "/" + name, None)

    def list_settings(self, scope: str = None) -> List[tuple]:
        """List bot settings for the given scope."""
        if self._settings is None:
            return []
        items = self._settings.list()
        if scope is None:
            return items
        prefix = scope + "/"
        return [(key[len(prefix):], value) for key, value in items if key.startswith(prefix)]

    #
    # bot administration API
    #
    def is_admin(self, contact: Union[Contact, int, str]) -> bool:
        """Return True if the given contact is a bot administrator."""
        addr = self._addr(contact)
        if not addr:
            return False
        if self.admin_addr and addr == self.admin_addr:
            return True
        if not is_valid_address(addr):
            return False
        if not self.accid or self.cli is None:
            return False
        try:
            contact_id = self.rpc.lookup_contact_id_by_addr(self.accid, addr)
            if not contact_id:
                return False
            return bool(self.cli.is_admin(self.rpc, self.accid, contact_id))
        except Exception:  # noqa: BLE001
            return False

    def add_admin(self, contact: Union[Contact, int, str]) -> None:
        """Add the given contact to the bot administration group."""
        contact_id = self.get_contact(contact).id
        chat_id = self.cli.get_admin_chat(self.rpc, self.accid)
        if contact_id not in self.rpc.get_chat_contacts(self.accid, chat_id):
            self.rpc.add_contact_to_chat(self.accid, chat_id, contact_id)

    def del_admin(self, contact: Union[Contact, int, str]) -> None:
        """Remove the given contact from the bot administration group."""
        contact_id = self.get_contact(contact).id
        chat_id = self.cli.get_admin_chat(self.rpc, self.accid)
        if contact_id in self.rpc.get_chat_contacts(self.accid, chat_id):
            self.rpc.remove_contact_from_chat(self.accid, chat_id, contact_id)

    def _addr(self, contact: Union[Contact, int, str, None]) -> Optional[str]:
        if contact is None:
            return None
        if isinstance(contact, str):
            return contact
        if isinstance(contact, Contact):
            return contact.addr
        try:
            return self.rpc.get_contact(self.accid, int(contact)).address
        except (JsonRpcError, ValueError):
            return None

    #
    # contacts and chats API
    #
    @property
    def self_contact(self) -> Contact:
        """This bot's own contact."""
        contact = self.rpc.get_contact(self.accid, SpecialContactId.SELF)
        return Contact(self.rpc, self.accid, contact.id, contact)

    def get_contact(self, ref: Union[str, int, Contact]) -> Contact:
        """Return the Contact for the given address, contact id or Contact."""
        if isinstance(ref, Contact):
            return ref
        if isinstance(ref, int):
            return Contact(self.rpc, self.accid, ref)
        if not is_valid_address(ref):
            raise ValueError(
                f"invalid e-mail address: {ref!r}, "
                "check the ADMIN/ADDR values of your configuration"
            )
        ref = ref.strip()
        contact_id = self.rpc.lookup_contact_id_by_addr(self.accid, ref)
        if not contact_id:
            contact_id = self.rpc.create_contact(self.accid, ref, None)
        return Contact(self.rpc, self.accid, contact_id)

    def get_chat(self, ref: Union[Message, Contact, str, int]) -> Optional[Chat]:
        """Return the 1:1 chat (created if needed) for the given reference."""
        if isinstance(ref, Message):
            return ref.chat
        if isinstance(ref, (Contact, str)):
            contact = self.get_contact(ref)
            chat_id = self.rpc.create_chat_by_contact_id(self.accid, contact.id)
            return Chat(self.rpc, self.accid, chat_id)
        try:
            data = self.rpc.get_full_chat_by_id(self.accid, int(ref))
        except (JsonRpcError, ValueError):
            return None
        return Chat(self.rpc, self.accid, int(ref), data)

    def create_group(self, name: str, contacts: list = None) -> Chat:
        """Create a new group chat."""
        chat_id = self.rpc.create_group_chat(self.accid, name, False)
        for contact in contacts or []:
            self.rpc.add_contact_to_chat(
                self.accid, chat_id, self.get_contact(contact).id
            )
        return Chat(self.rpc, self.accid, chat_id)

    def is_configured(self) -> bool:
        """Return True if the bot account is successfully configured."""
        return bool(self.accid and self.rpc.is_configured(self.accid))

    def __repr__(self) -> str:
        return f"<DeltaBot accid={self.accid}>"

    def close(self) -> None:
        if self._settings is not None:
            self._settings.close()
            self._settings = None
