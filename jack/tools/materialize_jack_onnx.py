#!/usr/bin/env python3
from pathlib import Path
import base64, hashlib

EXPECTED = "380b07116262de02b9951028e495daf3cbffea7354b1006c133d5c0444c96dec"
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
