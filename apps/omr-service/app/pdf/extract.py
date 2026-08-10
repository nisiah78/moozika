"""Extraction bas niveau : PDF typographié -> runs de texte positionnés.

Décode les chaînes des opérateurs Tj/TJ (littéraux ou hex) en Unicode grâce
aux CMaps ToUnicode embarquées, en suivant la police (Tf) et la position
(Tm / Td) courantes. Stdlib uniquement (re, zlib) : suffisant pour les PDF
sol-fa générés par ordinateur (pas d'image scannée).
"""
from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

_OBJ_RE = re.compile(rb"(\d+) 0 obj(.*?)endobj", re.DOTALL)
_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
_TOUNICODE_RE = re.compile(rb"/ToUnicode (\d+) 0 R")
# Ressource police : /TT2, /F4, /g2A…
_FONT_NAME_RE = re.compile(rb"/([A-Za-z][A-Za-z0-9_+,#\-]*)\s+(\d+) 0 R")

_BFRANGE_RE = re.compile(rb"beginbfrange(.*?)endbfrange", re.DOTALL)
_BFCHAR_RE = re.compile(rb"beginbfchar(.*?)endbfchar", re.DOTALL)
_RANGE_ENTRY_RE = re.compile(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>")
_CHAR_ENTRY_RE = re.compile(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>")

# Un token de contenu : police, positionnement, ou texte (littéral / hex).
# NB : les séparateurs peuvent être n'importe quel blanc (espace OU retour
# ligne), d'où \s+ — sinon un « 1094\nTm » n'est pas capturé et le run
# hériterait d'une position périmée.
_TOKEN_RE = re.compile(
    rb"/([A-Za-z][A-Za-z0-9_+,#\-]*)\s+[\d.]+\s+Tf"  # /FontName s Tf
    rb"|([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+Tm"
    rb"|([-\d.]+)\s+([-\d.]+)\s+Td"                     # tx ty Td
    rb"|<([0-9A-Fa-f]+)>\s*Tj"                          # <hex> Tj
    rb"|\[(.*?)\]\s*TJ"                                 # [ ... ] TJ
    rb"|\((?:[^()\\]|\\.)*\)\s*Tj",                     # ( ... ) Tj
    re.DOTALL,
)
_PAREN_RE = re.compile(rb"\((?:[^()\\]|\\.)*\)")
_HEX_IN_TJ_RE = re.compile(rb"<([0-9A-Fa-f]+)>")


@dataclass
class Run:
    y: float
    x: float
    font: str
    text: str


class ExtractError(ValueError):
    pass


def _decompress(raw: bytes) -> bytes:
    try:
        return zlib.decompress(raw)
    except zlib.error:
        return raw


def _stream_of(obj_bytes: bytes) -> bytes | None:
    m = _STREAM_RE.search(obj_bytes)
    return _decompress(m.group(1)) if m else None


def _parse_cmap(txt: bytes) -> Dict[int, str]:
    mapping: Dict[int, str] = {}
    for block in _BFRANGE_RE.finditer(txt):
        for lo, hi, dst in _RANGE_ENTRY_RE.findall(block.group(1)):
            a, b, d = int(lo, 16), int(hi, 16), int(dst, 16)
            for i in range(a, b + 1):
                mapping[i] = chr(d + (i - a))
    for block in _BFCHAR_RE.finditer(txt):
        for src, dst in _CHAR_ENTRY_RE.findall(block.group(1)):
            mapping[int(src, 16)] = chr(int(dst, 16))
    return mapping


def _cmap_bytes_per_char(cmap: Dict[int, str]) -> int:
    """CID multi-octets si la CMap adresse au-delà de 255."""
    if cmap and max(cmap) > 255:
        return 2
    return 1


def _map_code(code: int, cmap: Dict[int, str]) -> str:
    if cmap:
        if code in cmap:
            return cmap[code]
        # Identité ASCII si la CMap est partielle (polices sol-fa simples).
        if 0x20 <= code < 0x7F:
            return chr(code)
        return ""
    if 0x20 <= code < 0x7F:
        return chr(code)
    return ""


def _decode_literal(body: bytes, cmap: Dict[int, str]) -> str:
    s = body.decode("latin1")
    out: List[str] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            nxt = s[i + 1]
            if nxt.isdigit():
                octal = s[i + 1 : i + 4]
                code = int(octal, 8)
                i += 1 + len(octal)
            else:
                code = ord(nxt)
                i += 2
        else:
            code = ord(c)
            i += 1
        out.append(_map_code(code, cmap))
    return "".join(out)


def _decode_hex(hex_digits: bytes, cmap: Dict[int, str]) -> str:
    raw = bytes.fromhex(hex_digits.decode("ascii"))
    bpc = _cmap_bytes_per_char(cmap)
    # Hex court impair ou 1 octet explicite → forcer 1.
    if len(raw) % bpc != 0:
        bpc = 1
    out: List[str] = []
    for i in range(0, len(raw), bpc):
        code = int.from_bytes(raw[i : i + bpc], "big")
        out.append(_map_code(code, cmap))
    return "".join(out)


def _decode_tj_array(payload: bytes, cmap: Dict[int, str]) -> str:
    """Décode un opérande TJ : littéraux (…), hex <…>, nombres ignorés."""
    parts: List[str] = []
    for m in _PAREN_RE.finditer(payload):
        parts.append(_decode_literal(m.group(0)[1:-1], cmap))
    for m in _HEX_IN_TJ_RE.finditer(payload):
        parts.append(_decode_hex(m.group(1), cmap))
    if parts:
        return "".join(parts)
    return ""


def extract_runs(data: bytes) -> List[Run]:
    """Renvoie tous les runs de texte positionnés, texte décodé en Unicode."""
    objs = {int(m.group(1)): m.group(2) for m in _OBJ_RE.finditer(data)}

    # numéro d'objet ToUnicode -> table {code -> caractère}
    tounicode_cmap: Dict[int, Dict[int, str]] = {}
    for num, ob in objs.items():
        m = _TOUNICODE_RE.search(ob)
        if not m:
            continue
        cm_num = int(m.group(1))
        stream = _stream_of(objs.get(cm_num, b""))
        if stream is not None:
            tounicode_cmap[cm_num] = _parse_cmap(stream)

    # nom de ressource -> table, via l'objet police qui référence son ToUnicode
    name_to_cmap: Dict[str, Dict[int, str]] = {}
    for m in _FONT_NAME_RE.finditer(data):
        name, font_num = m.group(1).decode(), int(m.group(2))
        font_obj = objs.get(font_num)
        if not font_obj:
            continue
        tm = _TOUNICODE_RE.search(font_obj)
        if tm and int(tm.group(1)) in tounicode_cmap:
            name_to_cmap[name] = tounicode_cmap[int(tm.group(1))]

    runs: List[Run] = []
    for ob in objs.values():
        content = _stream_of(ob)
        if not content or b" Tf" not in content:
            continue
        # Contenu page (opérateurs texte) — ignore les flux de glyphes binaires.
        if b"BT" not in content and b"Tm" not in content:
            continue
        cur_font: Optional[str] = None
        x = y = 0.0
        for tok in _TOKEN_RE.finditer(content):
            g = tok.group(0)
            if g.endswith(b"Tf"):
                cur_font = tok.group(1).decode()
            elif g.endswith(b"Tm"):
                x = float(tok.group(6))
                y = float(tok.group(7))
            elif g.endswith(b"Td"):
                x += float(tok.group(8))
                y += float(tok.group(9))
            else:
                cmap = name_to_cmap.get(cur_font or "", {})
                if g.endswith(b"TJ"):
                    text = _decode_tj_array(tok.group(11), cmap)
                elif g.lstrip().startswith(b"<"):
                    text = _decode_hex(tok.group(10), cmap)
                else:
                    inner = re.search(rb"\((.*)\)\s*Tj", g, re.DOTALL)
                    text = _decode_literal(inner.group(1), cmap) if inner else ""
                if text.strip():
                    runs.append(
                        Run(
                            y=round(y, 1),
                            x=round(x, 1),
                            font=cur_font or "",
                            text=text,
                        )
                    )
    if not runs:
        raise ExtractError(
            "aucun texte extrait — le PDF est probablement scanné (image) "
            "et nécessite l'OCR"
        )
    return runs
