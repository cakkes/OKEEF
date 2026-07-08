from pathlib import Path

from okeef import extract


def test_strips_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "bom.txt"
    path.write_bytes(b"\xef\xbb\xbfHello world")

    text = extract.extract_text(path)

    assert text == "Hello world"
    assert "﻿" not in text
