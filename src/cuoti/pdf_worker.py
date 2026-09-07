"""Small isolated WeasyPrint worker used by the bounded-memory PDF exporter."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def configure_macos_libraries() -> None:
    if sys.platform != "darwin" or not Path("/opt/homebrew/lib").exists():
        return
    fallback = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    paths = [item for item in fallback.split(":") if item]
    if "/opt/homebrew/lib" not in paths:
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(["/opt/homebrew/lib", *paths])


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: python -m cuoti.pdf_worker INPUT.html OUTPUT.pdf BASE_URL")
    input_html, output_pdf, base_url = sys.argv[1:]
    configure_macos_libraries()
    from weasyprint import HTML

    HTML(filename=input_html, base_url=base_url).write_pdf(output_pdf)


if __name__ == "__main__":
    main()
