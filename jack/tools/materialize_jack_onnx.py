#!/usr/bin/env python3
from pathlib import Path
import base64, hashlib

EXPECTED = "a30920efe9e9cf930d90ce120511ef9b30547dbaaf624bc3fe1628aade1e1618"
here = Path(__file__).resolve().parents[1]
src = here / "models" / "jack_relentless_gate.onnx.b64"
dst = here / "models" / "jack_relentless_gate.onnx"
data = base64.b64decode(src.read_text(encoding="utf-8").strip(), validate=True)
actual = hashlib.sha256(data).hexdigest()
if actual != EXPECTED:
    raise SystemExit(f"ONNX hash mismatch: {actual} != {EXPECTED}")
dst.write_bytes(data)
print(dst)
print(actual)
