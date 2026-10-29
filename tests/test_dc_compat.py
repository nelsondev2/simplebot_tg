"""Regression tests for the deltabot-cli migration.

The tests use a fake JSON-RPC client, so they run offline:

    python -m pytest tests
    # or simply:
    python tests/test_dc_compat.py
"""

import logging
import os
import shutil
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from deltachat2 import (  # noqa: E402
    ChatType,
    MessageQuoteWithMessage,
    Viewtype,
)
from deltachat2.types import Contact as DCContact  # noqa: E402
from deltachat2.types import FullChat  # noqa: E402
from deltachat2.types import Message as DCMessage  # noqa: E402

from dc_compat import DeltaBot, Replies  # noqa: E402

CONFIG_DIR = os.path.join(ROOT, ".test-config")


def make_contact(cid, addr):
    return DCContact(
        address=addr,
        auth_name="",
        color="",
        display_name=addr.split("@")[0],
        e2ee_avail=True,
        id=cid,
        is_blocked=False,
        is_bot=False,
        is_key_contact=False,
        is_verified=True,
        last_seen=0,
        name=str(cid),
        name_and_addr=str(cid),
        profile_image=None,
        status="",
        verifier_id=None,
        was_seen_recently=False,
    )


def make_chat(cid, name="chat", chat_type=ChatType.SINGLE):
    return FullChat(
        archived=False,
        can_send=True,
        chat_type=chat_type,
        color="",
        contact_ids=[1, 10],
        ephemeral_timer=0,
        fresh_message_counter=0,
        id=cid,
        is_contact_request=False,
        is_device_chat=False,
        is_encrypted=True,
        is_muted=False,
        is_self_talk=False,
        is_unpromoted=False,
        name=name,
        past_contact_ids=[],
        pinned=False,
        self_in_group=True,
        was_seen_recently=False,
    )


def make_msg(mid, chat_id, text="", sender_id=10, view_type=Viewtype.TEXT, file=None, quote=None):
    return DCMessage(
        chat_id=chat_id,
        dimensions_height=0,
        dimensions_width=0,
        download_state="Done",
        duration=0,
        file=file,
        file_bytes=0,
        file_mime=None,
        file_name=os.path.basename(file) if file else None,
        from_id=sender_id,
        has_deviating_timestamp=False,
        has_html=False,
        has_location=False,
        id=mid,
        is_bot=False,
        is_edited=False,
        is_forwarded=False,
        is_info=False,
        override_sender_name=None,
        parent_id=None,
        quote=quote,
        reactions=None,
        received_timestamp=0,
        saved_message_id=None,
        sender=make_contact(sender_id, "sender@example.org"),
        show_padlock=True,
        sort_timestamp=0,
        state=10,
        subject="",
        system_message_type="Unknown",
        text=text,
        timestamp=0,
        vcard_contact=None,
        view_type=view_type,
        webxdc_href=None,
    )


class FakeRpc:
    """Minimal JSON-RPC client, enough for the bridge objects."""

    def __init__(self):
        self.calls = []
        self.chats = {5: make_chat(5, "bridge chat")}
        self.msgs = {1: make_msg(1, 5, "hola"), 2: make_msg(2, 5, "mundo")}
        self.sent = 100

    def get_contact(self, accid, cid):
        return make_contact(
            cid, "bot@example.org" if cid == 1 else "other@example.org"
        )

    def get_message(self, accid, mid):
        self.calls.append(("get_message", mid))
        return self.msgs[int(mid)]

    def get_message_ids(self, accid, chat_id, info_only, add_daymarker):
        return [1, 2]

    def get_message_info(self, accid, mid):
        return "State: Seen"

    def get_full_chat_by_id(self, accid, chat_id):
        return self.chats[chat_id]

    def get_chat_contacts(self, accid, chat_id):
        return [1, 10]

    def misc_send_text_message(self, accid, chat_id, text):
        self.calls.append(("send_text", chat_id, text))
        self.sent += 1
        self.msgs[self.sent] = make_msg(self.sent, chat_id, text)
        return self.sent

    def send_msg(self, accid, chat_id, data):
        self.calls.append(("send_msg", chat_id, data))
        self.sent += 1
        self.msgs[self.sent] = make_msg(self.sent, chat_id, data.text or "")
        return self.sent

    def lookup_contact_id_by_addr(self, accid, addr):
        return 10 if addr == "other@example.org" else None

    def create_contact(self, accid, addr, name):
        return 11

    def create_chat_by_contact_id(self, accid, cid):
        return 5

    def create_group_chat(self, accid, name, protect):
        self.chats[7] = make_chat(7, name, ChatType.GROUP)
        return 7

    def add_contact_to_chat(self, accid, chat_id, cid):
        self.calls.append(("add_contact", chat_id, cid))

    def set_chat_name(self, accid, chat_id, name):
        self.calls.append(("set_name", chat_id, name))

    def set_chat_profile_image(self, accid, chat_id, path):
        self.calls.append(("set_profile_image", chat_id, path))

    def get_blob_dir(self, accid):
        return "/tmp"

    def get_config(self, accid, key):
        return "bot@example.org"

    def set_config(self, accid, key, value):
        self.calls.append(("set_config", key, value))

    def is_configured(self, accid):
        return True

    def get_chatlist_entries(self, accid, flags, query, contact_id):
        return [5]

    def get_connectivity_html(self):
        return "<html/>"


class FakeCli:
    def is_admin(self, rpc, accid, cid):
        return cid == 10

    def get_admin_chat(self, rpc, accid):
        return 42


@pytest.fixture()
def bot():
    shutil.rmtree(CONFIG_DIR, ignore_errors=True)
    rpc = FakeRpc()
    client = types.SimpleNamespace(rpc=rpc, logger=logging.getLogger("test"))
    yield DeltaBot(client, 1, CONFIG_DIR, cli=FakeCli(), admin_addr="admin@example.org")
    shutil.rmtree(CONFIG_DIR, ignore_errors=True)


def test_settings_are_persistent(bot):
    assert bot.get("FOO") is None
    bot.set("FOO", "bar")
    assert bot.get("FOO") == "bar"
    bot.set("FOO", None)
    assert bot.get("FOO", "default") == "default"
    bot.set("AUTOCHATSDB", "{}")
    assert ("AUTOCHATSDB", "{}") in bot.list_settings("global")
    # a new bot object (bot restart) sees the same settings
    other = DeltaBot(bot.client, 1, CONFIG_DIR, cli=bot.cli)
    assert other.get("AUTOCHATSDB") == "{}"
    other.close()


def test_admin(bot):
    assert bot.is_admin("admin@example.org")  # ADMIN environment variable
    assert bot.is_admin("other@example.org")  # member of the admins group
    assert not bot.is_admin("stranger@example.org")


def test_chats(bot):
    chat = bot.get_chat(5)
    assert chat.id == 5
    assert chat.get_name() == "bridge chat"
    assert not chat.is_multiuser()
    assert not chat.is_mailinglist()
    assert bot.get_chat("other@example.org").id == 5
    assert [m.id for m in chat.get_messages()] == [1, 2]
    assert chat.send_text("hey").text == "hey"
    group = bot.create_group("my group", [bot.get_contact("other@example.org")])
    assert group.id == 7
    assert group.is_multiuser()
    assert ("add_contact", 7, 10) in bot.rpc.calls


def test_message_api(bot):
    msg = bot.account.get_message_by_id(1)
    assert msg.text == "hola"
    assert msg.chat.id == 5
    assert msg.get_sender_contact().addr == "sender@example.org"
    assert msg.quote is None
    assert msg.filename is None
    assert not msg.is_system_message()
    assert not msg.is_audio() and not msg.is_image() and not msg.is_file()
    assert msg.get_message_info() == "State: Seen"

    bot.rpc.msgs[3] = make_msg(
        3,
        5,
        "reply",
        quote=MessageQuoteWithMessage(
            author_display_color="",
            author_display_name="me",
            chat_id=5,
            is_forwarded=False,
            message_id=1,
            text="hola",
            view_type=Viewtype.TEXT,
        ),
    )
    reply = bot.account.get_message_by_id(3)
    assert reply.quote.id == 1
    assert reply.quote.text == "hola"

    bot.rpc.msgs[4] = make_msg(4, 5, "", view_type=Viewtype.AUDIO, file="/tmp/a.aac")
    audio = bot.account.get_message_by_id(4)
    assert audio.is_audio()
    assert audio.filename == "/tmp/a.aac"


def test_replies(bot):
    msg = bot.account.get_message_by_id(1)
    replies = Replies(msg, logger=bot.logger)
    replies.add(text="hola", quote=msg, sender="Me")
    replies.add(text="con html", html="<b>con html</b>")
    replies.add(text="sticker", filename="/tmp/a.aac", viewtype="sticker")
    sent = replies.send_reply_messages()
    assert [m.text for m in sent] == ["hola", "con html", "sticker"]
    data = [c[2] for c in bot.rpc.calls if c[0] == "send_msg"]
    assert data[0].quoted_message_id == 1
    assert data[0].override_sender_name == "Me"
    assert data[0].viewtype == Viewtype.TEXT
    assert data[1].html == "<b>con html</b>"
    assert data[2].viewtype == Viewtype.STICKER

    # replies with an explicit target chat (the bridge sends to other chats)
    internal = Replies(bot, logger=bot.logger)
    internal.add(text="to chat", chat=bot.get_chat(5))
    assert internal.send_reply_messages()[0].id > 100


def test_commands(bot):
    @bot.commands.register
    def test(bot, payload, replies, message):
        """a test command"""
        replies.add(text="payload=" + payload)

    def reply_for(text):
        bot.rpc.sent += 1
        msg_id = bot.rpc.sent
        bot.rpc.msgs[msg_id] = make_msg(msg_id, 5, text)
        msg = bot.account.get_message_by_id(msg_id)
        out = Replies(msg, logger=bot.logger)
        assert bot.commands.handle(msg, out) is True
        return [m.text for m in out.send_reply_messages()]

    assert bot.commands.handle(bot.account.get_message_by_id(1), Replies(
        bot.account.get_message_by_id(1), logger=bot.logger)) is False
    assert reply_for("/test hello") == ["payload=hello"]
    # multi-part commands: /test_-10
    assert reply_for("/test_-10") == ["payload=-10"]
    # command addressed to the bot
    assert reply_for("/test@bot@example.org hi") == ["payload=hi"]
    # unknown commands are only answered in 1:1 chats
    assert reply_for("/nope") == ["unknown command '/nope'"]


def test_filters(bot):
    seen = []

    @bot.filters.register
    def my_filter(bot, message, replies):
        """a filter"""
        seen.append(message.id)

    msg = bot.account.get_message_by_id(2)
    bot.filters.apply(msg, Replies(msg, logger=bot.logger))
    assert seen == [2]


def test_telebridge_wiring():
    """The bridge registers all its commands and filters on deltabot-cli."""
    import telebridge

    args = types.SimpleNamespace(config_dir=CONFIG_DIR, account=1)
    client = types.SimpleNamespace(rpc=FakeRpc(), logger=logging.getLogger("test"))
    for hook in telebridge.cli._init_hooks:
        hook(client, args)
    cmds = set(telebridge.bot.commands.dict())
    for expected in ("/more", "/down", "/pdown", "/comment", "/load", "/list", "/remove",
                     "/link2", "/alias", "/login", "/sms", "/pass", "/token", "/logout",
                     "/search", "/join", "/preview", "/auto", "/inline", "/inmore",
                     "/inclick", "/indown", "/forward", "/pin", "/news", "/info",
                     "/react", "/chat", "/b", "/c", "/eval", "/exec", "/start", "/stop",
                     "/setting", "/stats", "/help"):
        assert expected in cmds, expected
    assert telebridge.bot.filters.dict()
    assert telebridge.cli._start_hooks


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


#
# regressions: /help must answer and /login must report real errors
#
@pytest.fixture()
def bridge():
    """A bot with all the bridge commands registered (like a running bot)."""
    import telebridge

    shutil.rmtree(CONFIG_DIR, ignore_errors=True)
    client = types.SimpleNamespace(rpc=FakeRpc(), logger=logging.getLogger("test"))
    for hook in telebridge.cli._init_hooks:
        hook(client, types.SimpleNamespace(config_dir=CONFIG_DIR, account=1))
    yield telebridge.bot
    shutil.rmtree(CONFIG_DIR, ignore_errors=True)


def _dispatch(bot, text, mid):
    """Run a command through the bridge like on_new_message() does."""
    bot.rpc.msgs[mid] = make_msg(mid, 5, text)
    msg = bot.account.get_message_by_id(mid)
    replies = Replies(msg, logger=bot.logger)
    assert bot.commands.handle(msg, replies) is True
    return replies.send_reply_messages()


def test_help_command(bridge):
    sent = _dispatch(bridge, "/help", 500)
    assert len(sent) == 1
    text = sent[0].text
    # all the public commands are listed, admin-only ones are not
    for expected in ("/help", "/more", "/login", "/load", "/token", "/inline"):
        assert expected in text, expected
    for hidden in ("/eval", "/exec", "/setting", "/stats", "/start", "/stop"):
        assert hidden not in text, hidden


def test_help_command_for_admin(bridge, monkeypatch):
    # administrators also see the admin-only commands
    monkeypatch.setattr(bridge, "is_admin", lambda *args, **kwargs: True)
    sent = _dispatch(bridge, "/help", 510)
    text = sent[0].text
    for expected in ("/eval", "/exec", "/setting", "/stats"):
        assert expected in text, expected


def test_login_reports_missing_api_credentials(bridge, monkeypatch):
    import telebridge

    monkeypatch.setattr(telebridge, "api_id", None)
    monkeypatch.setattr(telebridge, "api_hash", None)
    for mid, msg_text in enumerate(("/login +5355555555", "/login +53 5555 5555"), 501):
        sent = _dispatch(bridge, msg_text, mid)
        assert "API_ID" in sent[0].text, sent[0].text
        assert "codigo del pais" not in sent[0].text


def test_login_rejects_invalid_number(bridge, monkeypatch):
    import telebridge

    monkeypatch.setattr(telebridge, "api_id", 1234)
    monkeypatch.setattr(telebridge, "api_hash", "0123456789abcdef0123456789abcdef")
    sent = _dispatch(bridge, "/login hola", 502)
    assert "invalido" in sent[0].text, sent[0].text


def test_login_accepts_separators_and_sms_flag(bridge, monkeypatch):
    import telebridge

    calls = []

    class FakeClient:
        def __init__(self, session, api_id, api_hash):
            self.session = session

        async def connect(self):
            pass

        async def send_code_request(self, phone, force_sms=False):
            calls.append((phone, force_sms))
            return types.SimpleNamespace(phone_code_hash="hash")

    monkeypatch.setattr(telebridge, "api_id", 1234)
    monkeypatch.setattr(telebridge, "api_hash", "0123456789abcdef0123456789abcdef")
    monkeypatch.setattr(telebridge, "TC", FakeClient)

    _dispatch(bridge, "/login +53 5555-5555", 503)
    _dispatch(bridge, "/login +5355555555 sms", 504)
    assert calls[0] == ("+5355555555", False)
    assert calls[1] == ("+5355555555", True)


def test_events_from_other_accounts_are_ignored(bridge):
    """With more than one account the bot must answer only once."""
    import deltachat2.events as dcevents
    import telebridge

    before = len([c for c in bridge.rpc.calls if c[0] == "send_msg"])
    bridge.rpc.msgs[520] = make_msg(520, 5, "/help")
    msg = bridge.rpc.msgs[520]
    # event coming from another account in the same config dir
    telebridge.on_new_message(
        bridge.client, 2, dcevents.NewMsgEvent(command="", payload="", msg=msg)
    )
    after = len([c for c in bridge.rpc.calls if c[0] == "send_msg"])
    assert after == before

    # and the event of the bot account is processed
    telebridge.on_new_message(
        bridge.client, 1, dcevents.NewMsgEvent(command="", payload="", msg=msg)
    )
    assert len([c for c in bridge.rpc.calls if c[0] == "send_msg"]) > before


#
# .env loading
#
def test_parse_env_file(tmp_path):
    from env_loader import parse_env_file

    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "\n"
        "ADDR=bot@example.org\n"
        "PASSWORD='my secret pass'\n"
        'API_HASH="0123456789abcdef"\n'
        "export API_ID=1234567\n"
        "TGTOKEN=abc # trailing comment\n"
        "CON_ADMIN=yo@example.org\n"
        "basura sin igual\n"
        "  ESPACIOS = valor  \n"
    )
    values = parse_env_file(env)
    assert values["ADDR"] == "bot@example.org"
    assert values["PASSWORD"] == "my secret pass"
    assert values["API_HASH"] == "0123456789abcdef"
    assert values["API_ID"] == "1234567"
    assert values["TGTOKEN"] == "abc"
    assert values["ESPACIOS"] == "valor"
    assert "basura sin igual" not in values


def test_load_env_does_not_override_real_env(tmp_path, monkeypatch):
    import env_loader

    env = tmp_path / ".env"
    env.write_text("API_ID=111\nFROM_ENV_FILE=hola\n")
    monkeypatch.setenv("API_ID", "222")  # real environment wins
    monkeypatch.delenv("FROM_ENV_FILE", raising=False)

    assert env_loader.load_env_files([env]) == [str(env)]
    assert os.environ["API_ID"] == "222"
    assert os.environ["FROM_ENV_FILE"] == "hola"
    monkeypatch.delenv("FROM_ENV_FILE", raising=False)


def test_export_shell_is_quoted_safely(tmp_path, monkeypatch):
    import subprocess

    env = tmp_path / ".env"
    env.write_text("PASSWORD='pa ss $word'\n")
    monkeypatch.delenv("PASSWORD", raising=False)
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); import env_loader;"
         "print(env_loader.export_shell([%r]))" % (ROOT, str(env))],
        capture_output=True, text=True, check=True,
    ).stdout
    assert out.startswith("export PASSWORD=")
    # the generated statement must not break the shell
    check = subprocess.run(["bash", "-c", out + '\nprintf "%s" "$PASSWORD"'],
                           capture_output=True, text=True, check=True)
    assert check.stdout == "pa ss $word"


def test_bot_reads_api_credentials_from_home_env(tmp_path):
    """telebridge must load ~/.env (the reported problem)."""
    import subprocess

    home = tmp_path / "home"
    home.mkdir()
    (home / ".env").write_text("API_ID=1234567\nAPI_HASH=0123456789abcdef\nADDR=bot@example.org\n")
    code = (
        "import sys; sys.path.insert(0, %r); import telebridge;"
        "print(telebridge.api_id, telebridge.api_hash, telebridge.ADDR, telebridge.env_files_loaded)"
        % ROOT
    )
    env = {k: v for k, v in os.environ.items()
           if k not in ("API_ID", "API_HASH", "ADDR", "CONFIG_DIR")}
    env["HOME"] = str(home)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env=env, cwd=str(tmp_path)).stdout.strip()
    assert out.startswith("1234567 0123456789abcdef bot@example.org"), out
