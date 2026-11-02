"""Boot the offline prompt-only app. No API or image/video generation endpoints."""
import base64,hashlib,io,zipfile,runpy
from pathlib import Path
payload=Path(__file__).with_name("prompt_studio_v3.b64").read_text().strip()
raw=base64.b64decode(payload,validate=True)
expected="b31b70a6c96a86a42490123b9a02acb843db03ac31fc283e38c42b0cdaaa10ba"
if hashlib.sha256(raw).hexdigest()!=expected:
    raise RuntimeError("Prompt Studio source checksum mismatch")
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    archive.extractall(Path(__file__).resolve().parent)
runpy.run_path(str(Path(__file__).with_name("server_v3.py")),run_name="__main__")
