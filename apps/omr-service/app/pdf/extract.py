"""Extraction bas niveau : PDF typographié -> runs de texte positionnés.

Décode les chaînes des opérateurs Tj/TJ (littéraux ou hex) en Unicode grâce
aux CMaps ToUnicode embarquées, en suivant la police (Tf) et la position
(Tm / Td) courantes. Stdlib uniquement (re, zlib) : suffisant pour les PDF
sol-fa générés par ordinateur (pas d'image scannée).
"""
from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, replace
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

# Arbre des pages (PDF classique, objets « N 0 obj … endobj »). Sert à extraire
# les runs PAGE PAR PAGE puis à réempiler les pages superposées (cf. _stack_pages) :
# beaucoup de recueils sol-fa réutilisent le même repère y à chaque page, ce qui
# ferait tout tomber au même endroit si on superposait les flux à l'aveugle.
_CATALOG_RE = re.compile(rb"/Type\s*/Catalog\b")
_PAGES_REF_RE = re.compile(rb"/Pages\s+(\d+)\s+0\s+R")
_TYPE_PAGES_RE = re.compile(rb"/Type\s*/Pages\b")
_TYPE_PAGE_RE = re.compile(rb"/Type\s*/Page\b")
_KIDS_RE = re.compile(rb"/Kids\s*\[(.*?)\]", re.DOTALL)
_REF_RE = re.compile(rb"(\d+)\s+0\s+R")
_CONTENTS_RE = re.compile(rb"/Contents\s*(?:(\d+)\s+0\s+R|\[(.*?)\])", re.DOTALL)

# Empilement : écart vertical inséré entre deux pages réempilées (mêmes points
# que la convention scan, cf. ocr.py / paddle_ocr.py `gap=40.0`).
_STACK_GAP = 40.0


@dataclass
class Run:
    y: float
    x: float
    font: str
    text: str


@dataclass
class Barline:
    """Trait vertical (barre de mesure) tracé en vecteur. Repère aligné sur les
    ``Run`` (mêmes coordonnées, même empilement de pages)."""
    x: float
    y0: float
    y1: float


# Traits de dessin : « x y m x2 y2 l » (moveto+lineto) et « x y w h re » (rect).
_MLINE_RE = re.compile(rb"([-\d.]+)\s+([-\d.]+)\s+m\s+([-\d.]+)\s+([-\d.]+)\s+l\b")
_RECT_RE = re.compile(rb"([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+re\b")
# Hauteur mini d'un trait vertical pour être une barre de mesure ANCRE (≈ hauteur
# d'un système sol-fa ; écarte les micro-traits de ponctuation/ornement).
_BARLINE_MIN_HEIGHT = 40.0
# Hauteur mini d'un trait vertical COURT accepté comme barre interne SEULEMENT s'il
# s'aligne sur une colonne d'ancre. Dans la queue de certaines partitions (divisi,
# reprises) les barres internes ne sont dessinées que sur une fraction de la hauteur
# du système (h≈14-27) ; sans ça elles manquent et la mesure n'est pas scindée.
# La notation sol-fa n'a PAS de hampes de note → un vertical = toujours une barre.
_BARLINE_SHORT_MIN = 10.0
_BARLINE_COLUMN_TOL = 10.0


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


def _runs_from_content(content: bytes, name_to_cmap: Dict[str, Dict[int, str]]) -> List[Run]:
    """Runs d'UN flux de contenu (repère page-local). Le curseur police/position
    est réinitialisé au début du flux (un flux = une page, ou un flux isolé)."""
    runs: List[Run] = []
    if not content or b" Tf" not in content:
        return runs
    # Contenu page (opérateurs texte) — ignore les flux de glyphes binaires.
    if b"BT" not in content and b"Tm" not in content:
        return runs
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
                    Run(y=round(y, 1), x=round(x, 1), font=cur_font or "", text=text)
                )
    return runs


def _barlines_from_content(content: bytes) -> List[Barline]:
    """Traits VERTICAUX d'un flux (repère page-local) = barres de mesure.
    Ignore le CTM (comme l'extraction texte) : barres et runs restent alignés.

    Deux passes : (1) les traits HAUTS (≥ ``_BARLINE_MIN_HEIGHT``) sont des barres
    ancres et définissent les COLONNES de barres de la page ; (2) les traits COURTS
    (≥ ``_BARLINE_SHORT_MIN``) ne sont retenus que s'ils tombent sur une colonne
    d'ancre — récupère les barres internes de la queue (divisi/reprises) dessinées
    sur une fraction de hauteur, sans laisser passer d'éventuel micro-trait isolé."""
    if not content:
        return []
    tall: List[Barline] = []
    short: List[Barline] = []
    for mm in _MLINE_RE.finditer(content):
        x0, y0, x1, y1 = (float(g) for g in mm.groups())
        if abs(x1 - x0) >= 1.5:
            continue
        h = abs(y1 - y0)
        bar = Barline(round((x0 + x1) / 2, 1), min(y0, y1), max(y0, y1))
        if h >= _BARLINE_MIN_HEIGHT:
            tall.append(bar)
        elif h >= _BARLINE_SHORT_MIN:
            short.append(bar)
    for mm in _RECT_RE.finditer(content):
        x, y, w, h_raw = (float(g) for g in mm.groups())
        if abs(w) >= 1.5:
            continue
        h = abs(h_raw)
        bar = Barline(round(x, 1), min(y, y + h_raw), max(y, y + h_raw))
        if h >= _BARLINE_MIN_HEIGHT:
            tall.append(bar)
        elif h >= _BARLINE_SHORT_MIN:
            short.append(bar)
    if not short:
        return tall
    anchors = sorted({b.x for b in tall})
    kept_short = [
        b for b in short
        if any(abs(b.x - a) <= _BARLINE_COLUMN_TOL for a in anchors)
    ]
    return tall + kept_short


def _page_contents_objs(page_obj: bytes) -> List[int]:
    """Numéros d'objet /Contents d'une page (référence unique ou tableau)."""
    m = _CONTENTS_RE.search(page_obj)
    if not m:
        return []
    if m.group(1):
        return [int(m.group(1))]
    return [int(r) for r in _REF_RE.findall(m.group(2) or b"")]


def _pages_in_order(objs: Dict[int, bytes]) -> List[List[int]]:
    """Pages dans l'ordre de lecture -> numéros d'objet /Contents de chacune.
    Parcourt l'arbre /Type/Pages via /Kids (nœuds Pages imbriqués gérés). Renvoie
    [] si l'arbre n'est pas parsable (PDF à flux d'objets, etc.) -> l'appelant
    retombe alors sur la superposition historique."""
    root = None
    # 1) Catalogue → /Pages (indépendant de l'ordre des clés dans le dict).
    for ob in objs.values():
        if _CATALOG_RE.search(ob):
            m = _PAGES_REF_RE.search(ob)
            if m:
                root = int(m.group(1))
                break
    # 2) Repli : le nœud /Type/Pages racine = celui qui n'est le kid d'aucun autre.
    if root is None:
        pages_objs = {num for num, ob in objs.items() if _TYPE_PAGES_RE.search(ob)}
        kids: set = set()
        for num in pages_objs:
            km = _KIDS_RE.search(objs[num])
            if km:
                kids.update(int(k) for k in _REF_RE.findall(km.group(1)))
        roots = pages_objs - kids
        if len(roots) == 1:
            root = next(iter(roots))
    if root is None:
        return []
    order: List[List[int]] = []
    seen: set = set()

    def walk(num: int) -> None:
        if num in seen or num not in objs:  # garde-fou cycles / réfs cassées
            return
        seen.add(num)
        ob = objs[num]
        if _TYPE_PAGES_RE.search(ob):
            km = _KIDS_RE.search(ob)
            if km:
                for kid in _REF_RE.findall(km.group(1)):
                    walk(int(kid))
        elif _TYPE_PAGE_RE.search(ob):
            order.append(_page_contents_objs(ob))

    walk(root)
    return order


def _pages_overlap_in_y(extents: List[Tuple[float, float]]) -> bool:
    """Vrai si deux pages partagent une plage y (superposées -> à réempiler).
    Faux quand elles sont déjà disjointes (multi-pages pré-décalé, ex. the-lord)."""
    for i in range(len(extents)):
        a0, a1 = extents[i]
        for j in range(i + 1, len(extents)):
            b0, b1 = extents[j]
            overlap = min(a1, b1) - max(a0, b0)
            if overlap > 0:
                smaller = min(a1 - a0, b1 - b0)
                if smaller <= 0 or overlap > 0.3 * smaller:
                    return True
    return False


def _stack_pages(page_runs: List[List[Run]], gap: float = _STACK_GAP) -> List[Run]:
    """Réempile verticalement des pages superposées, dans l'ordre de lecture.
    Ne touche à rien si ≤1 page réelle ou si les pages sont déjà disjointes en y."""
    pages = [p for p in page_runs if p]
    flat = [r for p in pages for r in p]
    if len(pages) <= 1:
        return flat
    extents = [(min(r.y for r in p), max(r.y for r in p)) for p in pages]
    if not _pages_overlap_in_y(extents):
        return flat  # déjà mises en page les unes sous les autres -> inchangé
    out: List[Run] = []
    running_bottom: Optional[float] = None
    for (ymin, ymax), p in zip(extents, pages):
        shift = 0.0 if running_bottom is None else ymax - (running_bottom - gap)
        out.extend(replace(r, y=round(r.y - shift, 1)) for r in p)
        running_bottom = ymin - shift
    return out


def _stack_page_data(
    page_runs: List[List[Run]],
    page_bars: List[List[Barline]],
    gap: float = _STACK_GAP,
) -> Tuple[List[Run], List[Barline]]:
    """Réempile runs ET barres avec les MÊMES décalages (repère cohérent).
    L'empilement est décidé sur les runs (texte) ; les barres suivent."""
    pairs = [(pr, pb) for pr, pb in zip(page_runs, page_bars) if pr]
    runs_flat = [r for pr, _ in pairs for r in pr]
    bars_flat = [b for _, pb in pairs for b in pb]
    if len(pairs) <= 1:
        return runs_flat, bars_flat
    extents = [(min(r.y for r in pr), max(r.y for r in pr)) for pr, _ in pairs]
    if not _pages_overlap_in_y(extents):
        return runs_flat, bars_flat
    out_runs: List[Run] = []
    out_bars: List[Barline] = []
    running_bottom: Optional[float] = None
    for (ymin, ymax), (pr, pb) in zip(extents, pairs):
        shift = 0.0 if running_bottom is None else ymax - (running_bottom - gap)
        out_runs.extend(replace(r, y=round(r.y - shift, 1)) for r in pr)
        out_bars.extend(
            replace(b, y0=round(b.y0 - shift, 1), y1=round(b.y1 - shift, 1)) for b in pb
        )
        running_bottom = ymin - shift
    return out_runs, out_bars


# Marqueurs d'ENTÊTE (tonique/mètre/tonalité) : toujours en HAUT d'une partition.
# Sert à trancher le sens de l'axe Y (certains PDF ont l'origine en haut-gauche →
# y croît vers le BAS → titre au y minimal). ``Do dia X`` / ``Key F Majeur``.
_HEADER_MARK_RE = re.compile(r"do\s*dia|doh|key|maj[eo]r|min[eo]r", re.I)


def _page_ydown(runs: List[Run]) -> bool:
    """Vrai si la page a l'axe Y vers le BAS (origine haut-gauche) : l'entête est
    alors au Y MINIMAL (= haut visuel). Règle musicale appliquée : le titre/entête
    est TOUJOURS en haut, jamais en bas → sa position tranche le sens de lecture.
    Ne regarde QUE les lignes proches d'un extrême (une parole « dia » au milieu ne
    doit pas piéger la détection)."""
    if not runs:
        return False
    ys = [r.y for r in runs]
    lo, hi = min(ys), max(ys)
    span = hi - lo
    if span < 1:
        return False
    rows: Dict[float, List[Run]] = {}
    for r in runs:
        rows.setdefault(round(r.y / 6.0) * 6.0, []).append(r)
    for rr in rows.values():
        y = sum(x.y for x in rr) / len(rr)
        if min(abs(y - lo), abs(y - hi)) > 0.25 * span:
            continue  # que les extrêmes (haut/bas de page)
        text = "".join(x.text for x in sorted(rr, key=lambda t: t.x))
        if _HEADER_MARK_RE.search(text):
            return abs(y - lo) < abs(y - hi)  # entête près du min-y → axe y vers le bas
    return False


def _extract_document(data: bytes) -> Tuple[List[Run], List[Barline]]:
    """Runs texte + barres vectorielles, page par page, empilés dans un repère commun."""
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

    # Chemin PAGE PAR PAGE : chaque flux /Contents est décodé dans son repère
    # local, puis les pages superposées sont réempilées (cf. _stack_page_data). Les
    # flux d'une même page (tableau /Contents) sont concaténés = un seul flux
    # logique (spec PDF : état graphique reporté). Runs (texte) ET barres (vecteur)
    # sont extraits ensemble pour rester dans le même repère.
    pages = _pages_in_order(objs)
    page_runs: List[List[Run]] = []
    page_bars: List[List[Barline]] = []
    for cobjs in pages:
        content = b"\n".join(
            s for c in cobjs if (s := _stream_of(objs.get(c, b""))) is not None
        )
        page_runs.append(_runs_from_content(content, name_to_cmap))
        page_bars.append(_barlines_from_content(content))

    # Normaliser l'orientation : si le PDF a l'axe Y vers le bas (entête au y min,
    # ex. MPANJAKAN « Key F Majeur »), on NÉGATIVE tous les Y → titre au y max (haut),
    # notation dessous. L'empilement (qui suppose y-up) et ``_orient_rows`` lisent
    # alors correctement (page 1 → 2 → …, chaque page de haut en bas).
    first = next((p for p in page_runs if p), None)
    if first is not None and _page_ydown(first):
        page_runs = [[replace(r, y=-r.y) for r in p] for p in page_runs]
        # NÉGATIVER en préservant y0 ≤ y1 (échanger) : l'aval suppose y0=min, y1=max.
        page_bars = [[replace(b, y0=-b.y1, y1=-b.y0) for b in p] for p in page_bars]

    if any(page_runs):
        runs, bars = _stack_page_data(page_runs, page_bars)
    else:
        # Repli (arbre de pages absent/non parsable) : comportement historique —
        # chaque flux de contenu décodé séparément (repère local), superposés.
        runs, bars = [], []
        for ob in objs.values():
            content = _stream_of(ob) or b""
            runs.extend(_runs_from_content(content, name_to_cmap))
            bars.extend(_barlines_from_content(content))

    if not runs:
        raise ExtractError(
            "aucun texte extrait — le PDF est probablement scanné (image) "
            "et nécessite l'OCR"
        )
    return runs, bars


def extract_runs(data: bytes) -> List[Run]:
    """Renvoie tous les runs de texte positionnés, texte décodé en Unicode."""
    return _extract_document(data)[0]


def extract_runs_and_barlines(data: bytes) -> Tuple[List[Run], List[Barline]]:
    """Runs texte + barres de mesure vectorielles, dans le même repère (empilées)."""
    return _extract_document(data)
