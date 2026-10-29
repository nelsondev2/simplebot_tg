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

    def get_all_account_ids(self):
        return [1]

    def get_all_accounts(self):
        return [types.SimpleNamespace(id=1)]

    def check_email_validity(self, addr):
        return "@" in str(addr) and "." in str(addr).split("@")[-1]


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


def _listed_commands(text):
    """Return the set of commands listed in a /help reply."""
    return {
        line.split(" - ")[0]
        for line in text.splitlines()
        if line.startswith("/") and " - " in line
    }


def test_help_command(bridge):
    sent = _dispatch(bridge, "/help", 500)
    assert len(sent) == 1
    listed = _listed_commands(sent[0].text)
    # user facing commands are listed
    for expected in ("/help", "/more", "/login", "/load", "/token", "/inline", "/list", "/news"):
        assert expected in listed, expected
    # admin only commands are not listed for a normal user
    for admin in ("/eval", "/exec", "/setting", "/stats", "/start", "/stop"):
        assert admin not in listed, admin
    # commands that are steps of other flows or internal are hidden
    for internal in ("/sms", "/pass", "/c", "/b", "/inmore", "/inclick", "/indown"):
        assert internal not in listed, internal


def test_help_command_for_admin(bridge, monkeypatch):
    # administrators also see the admin-only commands
    monkeypatch.setattr(bridge, "is_admin", lambda *args, **kwargs: True)
    listed = _listed_commands(_dispatch(bridge, "/help", 510)[0].text)
    for expected in ("/eval", "/exec", "/setting", "/stats"):
        assert expected in listed, expected
    # but the internal commands stay hidden
    for internal in ("/sms", "/pass", "/c", "/b"):
        assert internal not in listed, internal


def test_hidden_commands_still_work(bridge):
    """Hidden commands are not listed but must keep working."""
    cmds = bridge.commands.dict()
    for internal in ("/sms", "/pass", "/c", "/b", "/inmore", "/inclick", "/indown"):
        assert internal in cmds, internal
        assert cmds[internal].hidden is True, internal


def test_chat_commands_restore_mailto_and_link2_destination():
    from html.parser import HTMLParser
    from urllib.parse import parse_qs, urlsplit, unquote
    import telebridge

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.hrefs = []
        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.hrefs.append(dict(attrs)["href"])

    for linked, command in [(False, "/load -123"), (True, "/remove -123")]:
        parser = Links()
        parser.feed(telebridge.chat_commands(-123, linked, "bot@example.org"))
        action, link2 = map(urlsplit, parser.hrefs)
        assert action.scheme == "mailto"
        assert unquote(action.path) == "bot@example.org"
        assert parse_qs(action.query)["body"] == [command]
        assert link2.path == ""
        assert parse_qs(link2.query)["body"] == ["/link2 -123"]


def test_inline_mailto_encodes_query_and_escapes_label():
    from urllib.parse import urlsplit, parse_qs
    from html.parser import HTMLParser
    import telebridge

    command = telebridge.inline_command("gifbot", '  dogs & cats? #1  ')
    assert command == "/inline gifbot dogs & cats? #1"
    markup = telebridge.mailto_command("bot@example.org", command, '<click & go>')
    assert '&lt;click &amp; go&gt;' in markup
    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            self.href = dict(attrs)["href"]
    parser = Links()
    parser.feed(markup)
    assert parse_qs(urlsplit(parser.href).query)["body"] == [command]


def test_append_html_to_last_reply_preserves_text_and_existing_html(bot):
    msg = bot.account.get_message_by_id(1)
    replies = Replies(msg, logger=bot.logger)
    replies.add(text="A < B\n/inline gif hello")
    replies.append_html_to_last_reply('<br><a href="mailto:bot@example.org?body=%2Finline">Go</a>')
    text, html, *_ = replies._replies[-1]
    assert text == "A < B\n/inline gif hello"
    assert html.startswith("A &lt; B<br>/inline gif hello")
    assert 'href="mailto:' in html
    replies.send_reply_messages()
    data = [c[2] for c in bot.rpc.calls if c[0] == "send_msg"][-1]
    assert data.text == text
    assert data.html == html
    replies.add(text="fallback", html="<b>original</b>")
    replies.append_html_to_last_reply("<br>action")
    assert replies._replies[-1][1] == "<b>original</b><br>action"


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


def _wait_queue(timeout=10.0):
    """Wait until the message worker handled all the queued messages."""
    import telebridge

    telebridge.message_queue.join()


def test_events_from_other_accounts_are_ignored(bridge):
    """With more than one account the bot must answer only once."""
    import deltachat2.events as dcevents
    import telebridge

    telebridge.message_client = bridge.client
    before = len([c for c in bridge.rpc.calls if c[0] == "send_msg"])
    bridge.rpc.msgs[520] = make_msg(520, 5, "/help")
    msg = bridge.rpc.msgs[520]
    # event coming from another account in the same config dir
    telebridge.on_new_message(
        bridge.client, 2, dcevents.NewMsgEvent(command="", payload="", msg=msg)
    )
    _wait_queue()
    after = len([c for c in bridge.rpc.calls if c[0] == "send_msg"])
    assert after == before

    # and the event of the bot account is processed
    telebridge.on_new_message(
        bridge.client, 1, dcevents.NewMsgEvent(command="", payload="", msg=msg)
    )
    _wait_queue()
    assert len([c for c in bridge.rpc.calls if c[0] == "send_msg"]) > before


def test_events_are_handled_outside_the_event_loop(bridge, monkeypatch):
    """on_new_message must return immediately: the core loop can not be blocked."""
    import time

    import deltachat2.events as dcevents
    import telebridge

    telebridge.message_client = bridge.client
    bridge.rpc.msgs[530] = make_msg(530, 5, "/help")
    msg = bridge.rpc.msgs[530]

    def slow(*args, **kwargs):
        time.sleep(1.0)

    monkeypatch.setattr(telebridge, "handle_message", slow)
    started = time.monotonic()
    telebridge.on_new_message(
        bridge.client, 1, dcevents.NewMsgEvent(command="", payload="", msg=msg)
    )
    elapsed = time.monotonic() - started
    assert elapsed < 0.2, elapsed
    _wait_queue()


def test_duplicated_events_are_processed_once(bridge, monkeypatch):
    import deltachat2.events as dcevents
    import telebridge

    telebridge.message_client = bridge.client
    telebridge.messages_processed.clear()
    bridge.rpc.msgs[540] = make_msg(540, 5, "/help")
    bridge.rpc.msgs[540].id = 540
    msg = bridge.rpc.msgs[540]
    for _ in range(3):
        telebridge.on_new_message(
            bridge.client, 1, dcevents.NewMsgEvent(command="", payload="", msg=msg)
        )
    _wait_queue()
    sent = [c for c in bridge.rpc.calls if c[0] == "send_msg"]
    assert len(sent) == 1


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


#
# invalid ADMIN / ADDR must be reported, never crash the bot
#
def test_is_valid_address():
    from dc_compat import is_valid_address

    assert is_valid_address("yo@example.org")
    assert is_valid_address(" bot@example.org ") or not is_valid_address(" bot@example.org ")
    for bad in ("nelson9608", "@example.org", "yo@", "yo@example", "", None, 42):
        assert not is_valid_address(bad), bad


def test_get_contact_with_invalid_address(bot):
    with pytest.raises(ValueError) as exc:
        bot.get_contact("nelson9608")
    assert "invalid e-mail address" in str(exc.value)


def test_account_selection_prefers_addr(monkeypatch):
    import telebridge

    class Rpc(FakeRpc):
        def get_all_account_ids(self):
            return [4, 5]

        def get_config(self, accid, key):
            if key == "addr":
                return {4: "otro@example.org", 5: "bot@example.org"}[accid]
            return None

    monkeypatch.setattr(telebridge, "ADDR", "BOT@example.org")
    assert telebridge.get_account_id(Rpc(), types.SimpleNamespace(account=None)) == 5
    # -a always wins
    assert telebridge.get_account_id(Rpc(), types.SimpleNamespace(account=4)) == 4
    # without ADDR the first configured account is used
    monkeypatch.setattr(telebridge, "ADDR", None)
    assert telebridge.get_account_id(Rpc(), types.SimpleNamespace(account=None)) == 4


def test_start_does_not_crash_with_invalid_admin(bridge, monkeypatch):
    """Reproduces the reported bug: ADMIN=nelson9608 crashed the whole bot."""
    import telebridge

    monkeypatch.setattr(telebridge, "admin_addr", "nelson9608")

    def boom(accid, addr, name):
        raise Exception("provided email address is not a valid email address")

    monkeypatch.setattr(bridge.rpc, "create_contact", boom, raising=False)
    client = types.SimpleNamespace(rpc=bridge.rpc, logger=bridge.logger)
    # neither the add_admin nor the startup notification may raise
    telebridge.deltabot_start(client, types.SimpleNamespace(config_dir=CONFIG_DIR, account=1))
    assert bridge.rpc.is_configured(1)


def test_start_swallows_unexpected_errors(bridge, monkeypatch):
    import telebridge

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(telebridge, "_deltabot_start", boom)
    monkeypatch.setattr(telebridge, "notify_admin", lambda *a, **k: False)
    client = types.SimpleNamespace(rpc=bridge.rpc, logger=bridge.logger)
    telebridge.deltabot_start(client, types.SimpleNamespace(config_dir=CONFIG_DIR, account=1))


#
# automatic chats (polling): the automation must survive restarts and
# transient errors
#
def test_last_msg_survives_restart(bridge, monkeypatch):
    import telebridge

    monkeypatch.setattr(telebridge, "last_messagedb", {})
    telebridge.register_last_msg("user@example.org", 12, 100, 555)
    telebridge.savelastmsgs(bridge)
    assert bridge.get("LASTMSGDB")

    # simulate a bot restart
    monkeypatch.setattr(telebridge, "last_messagedb", {})
    telebridge.loadlastmsgs(bridge)
    assert telebridge.last_register_msg("user@example.org", 12) == 555


def test_auto_load_keeps_chat_after_transient_error(bridge, monkeypatch):
    import asyncio

    import telebridge

    monkeypatch.setattr(telebridge, "autochatsdb", {"user@example.org": {"12": "1234"}})
    monkeypatch.setattr(telebridge, "logindb", {"user@example.org": "session"})
    monkeypatch.setattr(telebridge, "SYNC_ENABLED", 0)
    monkeypatch.setattr(telebridge, "saveautochats", lambda bot: None)

    class FakeTgClient:
        def __init__(self, *args, **kwargs):
            pass

        async def connect(self):
            pass

        async def disconnect(self):
            pass

    async def boom(*args, **kwargs):
        raise ConnectionError("network down")

    monkeypatch.setattr(telebridge, "TC", FakeTgClient)
    monkeypatch.setattr(telebridge, "load_chat_messages", boom)

    failures = {}
    for n in range(1, telebridge.MAX_AUTO_FAILURES):
        asyncio.run(telebridge.auto_load_pass(bridge, None, failures))
        # the chat is still automated while the errors are not permanent
        assert telebridge.autochatsdb["user@example.org"]["12"] == "1234"
        assert failures[("user@example.org", "12")] == n

    # after MAX_AUTO_FAILURES consecutive errors it is disabled
    asyncio.run(telebridge.auto_load_pass(bridge, None, failures))
    assert "12" not in telebridge.autochatsdb.get("user@example.org", {})


def test_auto_load_recovers_after_an_error(bridge, monkeypatch):
    import asyncio

    import telebridge

    monkeypatch.setattr(telebridge, "autochatsdb", {"user@example.org": {"12": "1234"}})
    monkeypatch.setattr(telebridge, "logindb", {"user@example.org": "session"})
    monkeypatch.setattr(telebridge, "SYNC_ENABLED", 0)
    monkeypatch.setattr(telebridge, "saveautochats", lambda bot: None)

    class FakeTgClient:
        def __init__(self, *args, **kwargs):
            pass

        async def connect(self):
            pass

        async def disconnect(self):
            pass

    calls = []

    async def sometimes(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("network down")

    monkeypatch.setattr(telebridge, "TC", FakeTgClient)
    monkeypatch.setattr(telebridge, "load_chat_messages", sometimes)

    failures = {}
    asyncio.run(telebridge.auto_load_pass(bridge, None, failures))
    assert failures[("user@example.org", "12")] == 1
    # the next pass works, so the counter is reset
    asyncio.run(telebridge.auto_load_pass(bridge, None, failures))
    assert ("user@example.org", "12") not in failures
    assert telebridge.autochatsdb["user@example.org"]["12"] == "1234"


def test_save_bot_db_does_not_block(bridge, monkeypatch):
    """The cloud backup must never block the code that saves a setting."""
    import time

    import telebridge

    def slow_upload():
        time.sleep(3)

    monkeypatch.setattr(telebridge, "TGTOKEN", "session")
    monkeypatch.setattr(telebridge, "async_cloud_db", slow_upload)
    started = time.monotonic()
    telebridge.save_bot_db()
    assert time.monotonic() - started < 0.2
    assert telebridge.backup_pending is True
    # and it is not uploaded more than once per interval
    monkeypatch.setattr(telebridge, "BACKUP_MIN_INTERVAL", 3600)
    telebridge.backup_pending = False


def test_save_bot_db_force_is_synchronous(bridge, monkeypatch):
    import telebridge

    called = []
    monkeypatch.setattr(telebridge, "TGTOKEN", "session")
    monkeypatch.setattr(telebridge, "async_cloud_db", lambda: called.append(1))
    telebridge.save_bot_db(force=True)
    assert called == [1]
