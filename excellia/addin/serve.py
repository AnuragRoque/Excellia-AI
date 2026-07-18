"""HTTPS server for the Excel add-in: `excellia-addin`.

Office add-in panes must load over HTTPS, but the core API is plain
HTTP. Instead of the classic Node proxy, this serves the SAME FastAPI
app (API + web app + add-in files) over TLS on https://localhost:8443
with a self-signed localhost certificate — pure Python, no toolchain.

The certificate must be trusted by the OS or Excel's webview will
refuse to load the pane. Trusting is a system change, so it only ever
happens with explicit consent (interactive Y/n), and the manual
commands are always printed for both Windows and macOS.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from excellia.core import store

DEFAULT_PORT = 8443
CERT_DAYS = 365


def _cert_paths() -> tuple[Path, Path]:
    base = store.home() / "addin"
    base.mkdir(exist_ok=True)
    return base / "localhost-cert.pem", base / "localhost-key.pem"


def ensure_cert() -> tuple[Path, Path]:
    """Create (or reuse) a self-signed cert for localhost/127.0.0.1."""
    cert_path, key_path = _cert_paths()
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path
    try:
        import ipaddress

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        sys.exit(
            "The add-in server needs the 'cryptography' package to mint its "
            "localhost certificate. Install it with:  pip install excellia[addin]"
        )

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Excellia localhost")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=CERT_DAYS))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"Created a localhost certificate ({CERT_DAYS} days): {cert_path}")
    return cert_path, key_path


def offer_trust(cert_path: Path) -> None:
    """Print the trust commands; on Windows offer to run certutil (with consent)."""
    print(
        "\nExcel loads add-ins over HTTPS and must TRUST this certificate once.\n"
        "  Windows:  certutil -user -addstore Root \"" + str(cert_path) + "\"\n"
        "  macOS:    sudo security add-trusted-cert -d -r trustRoot "
        "-k /Library/Keychains/System.keychain \"" + str(cert_path) + "\"\n"
    )
    if os.name == "nt" and sys.stdin.isatty():
        try:
            answer = input(
                "Add it to YOUR user's trusted roots now via certutil? [y/N] "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):  # non-interactive despite isatty()
            answer = "n"
        if answer == "y":
            result = subprocess.run(
                ["certutil", "-user", "-addstore", "Root", str(cert_path)],
                capture_output=True, text=True)
            if result.returncode == 0:
                print("Trusted. (Remove later with: certutil -user -delstore Root \"Excellia localhost\")")
            else:
                print(f"certutil failed:\n{result.stdout or result.stderr}\n"
                      "Run the command above manually in an elevated prompt.")


def sideload_help() -> str:
    manifest = Path(__file__).parent / "static" / "manifest.xml"
    return f"""
SIDELOAD THE ADD-IN (one time)
  Manifest: {manifest}

  Windows (shared-folder catalog):
    1. Pick/create a folder, e.g. C:\\ExcelAddins, and copy manifest.xml into it.
    2. Right-click the folder > Properties > Sharing > Share (with yourself) and
       note the network path (\\\\YOURPC\\ExcelAddins).
    3. Excel > File > Options > Trust Center > Trust Center Settings >
       Trusted Add-in Catalogs > add that network path, tick "Show in Menu", OK.
    4. Restart Excel > Insert (Home tab: Add-ins) > My Add-ins > SHARED FOLDER > Excellia.

  macOS:
    1. Copy manifest.xml to:
       ~/Library/Containers/com.microsoft.Excel/Data/Documents/wef/
       (create the wef folder if missing)
    2. Restart Excel > Insert > My Add-ins (dropdown arrow) > Excellia.

  Then try:  =XAI.VALIDATE(A2,"pan")   or the Excellia button on the Home tab.
"""


def main() -> None:
    cert, key = ensure_cert()
    offer_trust(cert)
    print(sideload_help())
    port = int(os.environ.get("EXCELLIA_ADDIN_PORT", str(DEFAULT_PORT)))
    print(f"Serving API + web app + add-in at https://localhost:{port}  (Ctrl+C to stop)")

    import uvicorn

    from excellia.api.main import app

    uvicorn.run(app, host="127.0.0.1", port=port,
                ssl_certfile=str(cert), ssl_keyfile=str(key))


if __name__ == "__main__":
    main()
