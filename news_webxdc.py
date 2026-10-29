"""Build a self-contained /news webxdc with a snapshot of Telegram chats."""
import io
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def build_news_webxdc(chats):
    """Return an in-memory .xdc; data is private to the message recipients."""
    output = io.BytesIO()
    template = Path(__file__).resolve().parent / "webxdc" / "news" / "index.html"
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("index.html", template.read_bytes())
        archive.writestr("manifest.toml", 'name = "Chats de Telegram"\nsource_code_url = "https://github.com/nelsondev2/simplebot_tg"\n')
        archive.writestr("chats.json", json.dumps(chats, ensure_ascii=False))
    output.seek(0)
    return output
