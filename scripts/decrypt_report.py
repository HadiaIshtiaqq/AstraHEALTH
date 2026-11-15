"""Decrypt an ASTRAHEALTH encrypted export (.astra.enc) for the receiving medical professional.

Usage:  backend\\.venv\\Scripts\\python.exe scripts\\decrypt_report.py report.pdf.astra.enc [output-file]
The passphrase is prompted for (never passed on the command line).
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.exporting import decrypt  # noqa: E402

src = Path(sys.argv[1])
dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_name(src.name.removesuffix(".astra.enc"))
dst.write_bytes(decrypt(src.read_bytes(), getpass.getpass("Passphrase: ")))
print(f"Decrypted to {dst}")
