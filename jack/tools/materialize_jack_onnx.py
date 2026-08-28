#!/usr/bin/env python3
from pathlib import Path
import base64
import hashlib

EXPECTED = "5602367fb172d7457c9cc7dc57e87e6aa765e8bc53cfbe8662468c5ad91d338b"
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
