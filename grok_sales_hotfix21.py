"""Boot the offline prompt-only app. No API or image/video generation endpoints."""
import base64,hashlib,io,zipfile,runpy
from pathlib import Path
payload=Path(__file__).with_name("prompt_studio_v3.b64").read_text().strip()
raw=base64.b64decode(payload,validate=True)
expected="0468f6586dd27e057b65535b6a9a50dbd0101366e9b138dfd79fbc99bdac2a32"
if hashlib.sha256(raw).hexdigest()!=expected:
    raise RuntimeError("Prompt Studio source checksum mismatch")
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    archive.extractall(Path(__file__).resolve().parent)
runpy.run_path(str(Path(__file__).with_name("server_v3.py")),run_name="__main__")
