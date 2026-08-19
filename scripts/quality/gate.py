#!/usr/bin/env python3
"""Porte de qualité pré-commit — 100 % déterministe, AUCUN appel à un modèle.

Lit l'INDEX git (`git diff --cached`), en déduit les stacks touchés, et n'exécute
que ce qui concerne ces stacks. Deux niveaux :

  Niveau 1 (BLOQUANT, zéro tolérance) : tests du stack, tsc --noEmit, php -l,
      syntaxe Python. Du code qui ne compile pas ou dont les tests échouent ne passe
      jamais.
  Niveau 2 (SCORÉ) : style / conventions / analyse statique. Note sur 10 selon
      la formule pylint, comparée au seuil de scripts/quality/thresholds.json.
      Tant que ce seuil vaut `null`, le Niveau 2 est INFORMATIF (il n'échoue pas)
      — c'est le mode de mesure de la Phase 0.

Utilisable seul, hors Claude Code :

    python3 scripts/quality/gate.py                 # porte complète
    python3 scripts/quality/gate.py --report-only   # mesure, retourne toujours 0
    python3 scripts/quality/gate.py --stack frontend --stack omr
    python3 scripts/quality/gate.py --json          # rapport JSON sur stdout
    python3 scripts/quality/gate.py --all-files     # ignore l'index, prend tout

Rapport machine : .git/pr-gate-report.json
Stdlib pure (pip est cassé sur cette machine, cf. CLAUDE.md).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REPORT_PATH = REPO / ".git" / "pr-gate-report.json"
THRESHOLDS_PATH = REPO / "scripts" / "quality" / "thresholds.json"

# Fichiers qui ne doivent jamais entrer dans un commit.
FORBIDDEN_GLOBS = ("_debug_*.ndjson", "*.orig", "*.rej", "*.pyc", "*.log")

# Extensions commentaire → préfixe de commentaire ligne, pour le comptage de N.
COMMENT_PREFIX = {".py": "#", ".php": "//", ".ts": "//", ".tsx": "//", ".mjs": "//", ".js": "//"}


# --------------------------------------------------------------------------- #
# Mapping chemin → stack. Table figée : aucune heuristique, aucune devinette.
# --------------------------------------------------------------------------- #

@dataclass
class Stack:
    name: str
    prefix: str
    label: str
    # Extensions dont la modification déclenche le stack (None = toutes).
    source_ext: tuple[str, ...] = ()
    tests_note: str = ""


STACKS: tuple[Stack, ...] = (
    Stack("omr", "apps/omr-service/", "omr-service (Python)", (".py",)),
    Stack("audiveris", "apps/audiveris-service/", "audiveris-service (Python)", (".py",)),
    Stack("api", "apps/api/", "api (Symfony/PHP)", (".php",),
          tests_note="aucun test PHP dans le repo : Niveau 1 limité à `php -l`"),
    Stack("frontend", "apps/frontend/", "frontend (Next.js/TS)", (".ts", ".tsx", ".mjs", ".js")),
    Stack("docs", "packages/shared-contracts/", "contrats & docs", (),
          tests_note="documentation : aucun test, aucun lint"),
)

DOC_PREFIXES = ("docs/", "packages/shared-contracts/", "scripts/", ".claude/")
DOC_FILES = ("Makefile", "compose.yml", "CLAUDE.md", "README.md", ".gitignore")


def stack_of(path: str) -> str | None:
    """Retourne le nom du stack propriétaire du fichier, ou None."""
    for st in STACKS:
        if st.prefix and path.startswith(st.prefix):
            return st.name
    if path.startswith(DOC_PREFIXES) or path in DOC_FILES or path.endswith(".md"):
        return "docs"
    return None


# --------------------------------------------------------------------------- #
# Exécution de commandes
# --------------------------------------------------------------------------- #

@dataclass
class Step:
    """Une commande lancée par la porte, avec son résultat."""
    name: str
    cmd: list[str]
    cwd: str
    tier: int
    returncode: int | None = None
    duration_s: float = 0.0
    status: str = "pending"        # ok | fail | unavailable | skipped
    output_tail: str = ""
    detail: dict = field(default_factory=dict)


def run(step: Step, timeout: int = 900, capture_file: Path | None = None) -> Step:
    """Lance la commande de `step` et remplit son résultat."""
    prog = step.cmd[0]
    # Un chemin relatif (vendor/bin/phpstan) se résout depuis le cwd de l'étape,
    # pas depuis le PATH — shutil.which seul déclarait l'outil absent à tort.
    if "/" in prog and not prog.startswith("/"):
        available = (REPO / step.cwd / prog).exists()
    else:
        available = prog.startswith("/") or shutil.which(prog) is not None
    if not available:
        step.status = "unavailable"
        step.output_tail = f"outil introuvable : {prog} (cwd {step.cwd})"
        return step
    started = time.time()
    try:
        proc = subprocess.run(
            step.cmd,
            cwd=str(REPO / step.cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        step.status = "fail"
        step.duration_s = round(time.time() - started, 2)
        step.output_tail = f"TIMEOUT après {timeout}s"
        return step
    step.duration_s = round(time.time() - started, 2)
    step.returncode = proc.returncode
    combined = (proc.stdout or "") + (proc.stderr or "")
    step.output_tail = "\n".join(combined.strip().splitlines()[-40:])
    step.status = "ok" if proc.returncode == 0 else "fail"
    if capture_file is not None:
        capture_file.write_text(proc.stdout, encoding="utf-8")
    return step


# --------------------------------------------------------------------------- #
# Comptage de N (lignes de code) pour la formule de score
# --------------------------------------------------------------------------- #

def count_loc(paths: list[str]) -> int:
    """Lignes non vides et non commentaires des fichiers donnés."""
    total = 0
    for rel in paths:
        f = REPO / rel
        if not f.is_file():
            continue
        prefix = COMMENT_PREFIX.get(f.suffix)
        try:
            for raw in f.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw.strip()
                if not line:
                    continue
                if prefix and line.startswith(prefix):
                    continue
                total += 1
        except OSError:
            continue
    return total


def score_from_points(points: float, loc: int) -> float | None:
    """Formule pylint généralisée : 10 × (1 − points/N), bornée [0, 10]."""
    if loc <= 0:
        return None
    return round(max(0.0, min(10.0, 10.0 * (1.0 - points / loc))), 2)


# --------------------------------------------------------------------------- #
# Niveau 1 & 2, par stack
# --------------------------------------------------------------------------- #

# ast.parse plutôt que py_compile : ne produit aucun .pyc (le __pycache__ de
# apps/omr-service/app appartient à root depuis un ancien run Docker monté).
SYNTAX_CHECK = ["python3", "scripts/quality/syntax_check.py"]


def tier1_steps(stack: str, files: list[str]) -> list[Step]:
    """Contrôles bloquants du stack."""
    py = [f for f in files if f.endswith(".py")]
    php = [f for f in files if f.endswith(".php")]

    if stack == "omr":
        steps = [Step("tests unittest", ["python3", "-m", "unittest", "discover", "-s", "tests"],
                      "apps/omr-service", 1)]
        if py:
            steps.insert(0, Step("syntaxe python", SYNTAX_CHECK + py, ".", 1))
        return steps

    if stack == "audiveris":
        steps = [Step("tests unittest", ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                      "apps/audiveris-service", 1)]
        if py:
            steps.insert(0, Step("syntaxe python", SYNTAX_CHECK + py, ".", 1))
        return steps

    if stack == "api":
        # Pas de suite PHPUnit dans le repo : le Niveau 1 se limite à la syntaxe.
        # C'est une lacune réelle, signalée telle quelle dans le rapport.
        # Les chemins sont relativisés : la commande tourne avec cwd=apps/api.
        return [Step(f"php -l {Path(f).name}", ["php", "-l", f[len("apps/api/"):]],
                     "apps/api", 1)
                for f in (php or [])]

    if stack == "frontend":
        return [
            Step("tsc --noEmit", ["npm", "run", "--silent", "typecheck"], "apps/frontend", 1),
            Step("tests (tsx)", ["npm", "run", "--silent", "test"], "apps/frontend", 1),
        ]

    return []


def tier2_steps(stack: str, files: list[str], tmp: Path, phpstan_level: int) -> list[Step]:
    """Contrôles scorés du stack (style, conventions, analyse statique)."""
    if stack in ("omr", "audiveris"):
        # pip est cassé en local → pylint vit dans l'image `omr-lint`.
        # Les chemins sont relatifs à /app dans le conteneur : app/... pour
        # omr-service, audiveris_app/... pour audiveris-service (cf. compose.yml).
        prefix = "apps/omr-service/" if stack == "omr" else "apps/audiveris-service/"
        targets = [f[len(prefix):] for f in files if f.endswith(".py")]
        if not targets:
            return []
        # Chaque service est linté depuis SA racine (-w) : app/ et tests/ se
        # résolvent alors comme des modules normaux. Sans ça, pylint sort des
        # « fatal: No module named … » qui écrasent le score à 0.
        workdir = "/app" if stack == "omr" else "/audiveris"
        return [Step("pylint", ["docker", "compose", "run", "--rm", "-T", "-w", workdir,
                                "omr-lint", "pylint", "--rcfile=/app/.pylintrc",
                                "--output-format=json2", "--score=y", *targets],
                     ".", 2, detail={"json_out": str(tmp / f"pylint-{stack}.json")})]

    if stack == "api":
        php = [f[len("apps/api/"):] for f in files if f.endswith(".php")]
        if not php:
            return []
        return [
            Step("phpstan", ["vendor/bin/phpstan", "analyse", "-c", "phpstan.dist.neon",
                             "--error-format=json", "--no-progress", f"--level={phpstan_level}",
                             *php], "apps/api", 2,
                 detail={"json_out": str(tmp / "phpstan.json")}),
            Step("php-cs-fixer", ["vendor/bin/php-cs-fixer", "check",
                                  "--config=.php-cs-fixer.dist.php", "--format=json",
                                  "--show-progress=none", *php], "apps/api", 2,
                 detail={"json_out": str(tmp / "cs-fixer.json")}),
        ]

    if stack == "frontend":
        src = [f[len("apps/frontend/"):] for f in files
               if f.endswith((".ts", ".tsx", ".js", ".mjs"))]
        if not src:
            return []
        out = tmp / "eslint.json"
        out.unlink(missing_ok=True)
        return [Step("eslint", ["npx", "eslint", "--format", "json",
                                "--output-file", str(out), *src], "apps/frontend", 2,
                     detail={"json_out": str(out)})]

    return []


# --------------------------------------------------------------------------- #
# Extraction des points depuis la sortie des outils
# --------------------------------------------------------------------------- #

def read_json_out(step: Step):
    """Charge la sortie JSON complète capturée par run() (output_tail est tronqué)."""
    out = Path(step.detail.get("json_out", ""))
    if not out.is_file():
        return None
    text = out.read_text(encoding="utf-8").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def points_pylint(step: Step) -> tuple[float | None, float | None, dict]:
    """pylint json2 → (points, score natif, détail). Le score natif fait foi."""
    payload = read_json_out(step)
    if payload is None:
        return None, None, {"parse": "sortie pylint non exploitable"}
    stats = payload.get("statistics", {})
    counts = stats.get("messageTypeCount", {})
    points = (5 * counts.get("error", 0) + 5 * counts.get("fatal", 0)
              + counts.get("warning", 0) + counts.get("refactor", 0)
              + counts.get("convention", 0))
    return float(points), stats.get("score"), {
        "messageTypeCount": counts,
        "modulesLinted": stats.get("modulesLinted"),
    }


def points_phpstan(step: Step) -> tuple[float | None, dict]:
    payload = read_json_out(step)
    if payload is None:
        return None, {"parse": "sortie phpstan non JSON"}
    totals = payload.get("totals", {})
    n = totals.get("file_errors", 0) + totals.get("errors", 0)
    return float(n), {"file_errors": totals.get("file_errors"),
                      "errors": totals.get("errors")}


def points_cs_fixer(step: Step) -> tuple[float | None, dict]:
    payload = read_json_out(step)
    if payload is None:
        return None, {"parse": "sortie php-cs-fixer non JSON"}
    files = payload.get("files", [])
    return float(len(files)), {"files_to_fix": [f.get("name") for f in files]}


def points_eslint(step: Step) -> tuple[float | None, dict]:
    # eslint écrit lui-même son rapport (--output-file) : rien à capturer.
    payload = read_json_out(step)
    if payload is None:
        return None, {"parse": "rapport eslint absent ou non JSON"}
    errors = sum(f.get("errorCount", 0) for f in payload)
    warnings = sum(f.get("warningCount", 0) for f in payload)
    rules: dict[str, int] = {}
    for f in payload:
        for m in f.get("messages", []):
            key = m.get("ruleId") or "(fatal)"
            rules[key] = rules.get(key, 0) + 1
    return float(errors) + 0.5 * warnings, {
        "errors": errors, "warnings": warnings, "rules": rules,
    }


POINT_EXTRACTORS = {
    "phpstan": points_phpstan,
    "php-cs-fixer": points_cs_fixer,
    "eslint": points_eslint,
}


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def staged_files() -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=str(REPO), capture_output=True, text=True, check=True,
    )
    return [l for l in proc.stdout.splitlines() if l.strip()]


def git_lines(*args: str) -> list[str]:
    proc = subprocess.run(["git", *args], cwd=str(REPO),
                          capture_output=True, text=True, check=True)
    return [l for l in proc.stdout.splitlines() if l.strip()]


def all_changed_files() -> list[str]:
    """Mode --all-files : suivis modifiés + non suivis, en respectant .gitignore.

    `git ls-files --others --exclude-standard` (et non un rglob maison) : sinon
    __pycache__/ et compagnie remontent alors que .gitignore les exclut.
    """
    tracked = git_lines("diff", "--name-only", "HEAD")
    untracked = git_lines("ls-files", "--others", "--exclude-standard")
    seen, out = set(), []
    for f in tracked + untracked:
        if f not in seen and (REPO / f).is_file():
            seen.add(f)
            out.append(f)
    return out


def count_changed_lines(files: list[str], staged: bool) -> int:
    """Lignes AJOUTÉES par le diff — le vrai « périmètre de ta modification ».

    C'est le dénominateur pertinent pour le score : avec les LOC des fichiers
    entiers, N est si grand (>10 000) qu'aucun seuil ne se déclenche jamais.
    Un fichier non suivi compte pour la totalité de ses lignes.
    """
    if not files:
        return 0
    args = ["diff", "--numstat"] + (["--cached"] if staged else ["HEAD"]) + ["--", *files]
    added, seen = 0, set()
    for line in git_lines(*args):
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        plus, _minus, path = parts
        seen.add(path)
        if plus.isdigit():
            added += int(plus)
    # Fichiers non suivis : absents du diff → tout leur contenu est « ajouté ».
    missing = [f for f in files if f not in seen]
    return added + count_loc(missing)


def forbidden(files: list[str]) -> list[str]:
    from fnmatch import fnmatch
    bad = []
    for f in files:
        name = Path(f).name
        if any(fnmatch(name, g) for g in FORBIDDEN_GLOBS):
            bad.append(f)
    return bad


def load_thresholds() -> dict:
    if THRESHOLDS_PATH.is_file():
        return json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))
    return {"score_threshold": None, "phpstan_level": 5}


def main() -> int:
    ap = argparse.ArgumentParser(description="Porte de qualité pré-commit (déterministe).")
    ap.add_argument("--report-only", action="store_true",
                    help="mesure sans bloquer : retourne toujours 0")
    ap.add_argument("--all-files", action="store_true",
                    help="analyse tout le worktree modifié au lieu de l'index")
    ap.add_argument("--stack", action="append", default=[],
                    help="forcer un stack (répétable)")
    ap.add_argument("--json", action="store_true", help="rapport JSON sur stdout")
    ap.add_argument("--threshold", type=float, default=None,
                    help="seuil de score Niveau 2 (surcharge thresholds.json)")
    args = ap.parse_args()

    cfg = load_thresholds()
    threshold = args.threshold if args.threshold is not None else cfg.get("score_threshold")
    phpstan_level = cfg.get("phpstan_level", 5)

    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / "moozika-gate"
    tmp.mkdir(parents=True, exist_ok=True)

    files = all_changed_files() if args.all_files else staged_files()
    report: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": "all-files" if args.all_files else "staged",
        "report_only": args.report_only or threshold is None,
        "score_threshold": threshold,
        "phpstan_level": phpstan_level,
        "files": files,
        "blockers": [],
        "stacks": {},
        "verdict": "unknown",
    }

    if not files:
        report["verdict"] = "empty"
        report["blockers"].append(
            "index vide : rien n'est indexé (`git add <fichiers>` avant de relancer)")
        emit(report, args)
        return 0 if args.report_only else 1

    bad = forbidden(files)
    if bad:
        report["blockers"].append(f"artefacts interdits dans le périmètre : {', '.join(bad)}")

    # Répartition par stack.
    by_stack: dict[str, list[str]] = {}
    unmapped: list[str] = []
    for f in files:
        st = stack_of(f)
        if st is None:
            unmapped.append(f)
        else:
            by_stack.setdefault(st, []).append(f)
    report["unmapped_files"] = unmapped

    if args.stack:
        by_stack = {k: v for k, v in by_stack.items() if k in args.stack}

    stack_meta = {s.name: s for s in STACKS}

    for name, stack_files in sorted(by_stack.items()):
        meta = stack_meta[name]
        # Le score ne doit se mesurer que sur ce qui est RÉELLEMENT linté :
        # composer.lock / *.md / *.json gonflaient N (10 129 LOC pour api) et
        # diluaient le score jusqu'à le rendre insensible.
        lintable = ([f for f in stack_files if f.endswith(meta.source_ext)]
                    if meta.source_ext else [])
        entry: dict = {
            "label": meta.label,
            "files": stack_files,
            "lintable_files": lintable,
            "loc": count_loc(lintable),
            "changed_lines": count_changed_lines(lintable, staged=not args.all_files),
            "note": meta.tests_note,
            "tier1": [],
            "tier2": [],
            "score": None,
            "verdict": "ok",
        }

        # --- Niveau 1 : bloquant ---
        t1_ok = True
        for step in tier1_steps(name, stack_files):
            run(step)
            entry["tier1"].append(asdict(step))
            if step.status == "fail":
                t1_ok = False
        if not tier1_steps(name, stack_files):
            entry["tier1_note"] = "aucun contrôle Niveau 1 pour ce stack"

        if not t1_ok:
            entry["verdict"] = "fail-tier1"
            report["stacks"][name] = entry
            continue

        # --- Niveau 2 : scoré ---
        total_points = 0.0
        native_score = None
        measurable = False
        for step in tier2_steps(name, stack_files, tmp, phpstan_level):
            # eslint écrit son rapport tout seul (--output-file) : ne pas
            # écraser le fichier avec le stdout (vide) de la commande.
            capture = None if step.name == "eslint" else Path(step.detail["json_out"])
            run(step, capture_file=capture)
            # Un linter sort en 1 dès qu'il trouve quelque chose : au Niveau 2
            # c'est un CONSTAT (c'est le score qui tranche), pas un échec.
            if step.status == "fail":
                step.status = "findings"
            if step.name == "pylint":
                pts, native, detail = points_pylint(step)
                step.detail.update(detail)
            else:
                extractor = POINT_EXTRACTORS.get(step.name)
                pts, detail = extractor(step) if extractor else (None, {})
                step.detail.update(detail)
                native = None
            if pts is not None:
                total_points += pts
                measurable = True
            if native is not None:
                native_score = native
            step.detail["points"] = pts
            entry["tier2"].append(asdict(step))

        entry["points"] = total_points
        if measurable:
            # Deux dénominateurs, deux sensibilités très différentes :
            #   score_loc   : fichiers entiers — indulgent, comparable à pylint
            #   score_diff  : lignes ajoutées — mesure ce que TU viens d'écrire
            entry["score_loc"] = score_from_points(total_points, entry["loc"])
            entry["score_diff"] = score_from_points(total_points, entry["changed_lines"])
        if native_score is not None:
            entry["score_pylint_native"] = native_score
        denom = cfg.get("score_denominator", "changed_lines")
        entry["score"] = entry.get("score_diff") if denom == "changed_lines" else entry.get("score_loc")
        entry["score_source"] = (
            f"10 × (1 − {total_points:g}/{entry['changed_lines']} lignes ajoutées)"
            if denom == "changed_lines"
            else f"10 × (1 − {total_points:g}/{entry['loc']} LOC)"
        ) if measurable else ""

        if entry["score"] is not None and threshold is not None and entry["score"] < threshold:
            entry["verdict"] = "fail-tier2"

        report["stacks"][name] = entry

    failed = [n for n, e in report["stacks"].items() if e["verdict"] != "ok"]
    report["verdict"] = "pass" if not failed and not report["blockers"] else "fail"
    report["failed_stacks"] = failed

    emit(report, args)
    if args.report_only:
        return 0
    return 0 if report["verdict"] == "pass" else 1


def emit(report: dict, args) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    print_summary(report)


ICON = {"ok": "✓", "fail": "✗", "findings": "!", "unavailable": "·",
        "skipped": "-", "pending": "?"}


def print_summary(report: dict) -> None:
    mode = "MESURE (ne bloque pas)" if report["report_only"] else "PORTE"
    print(f"\n── Porte de qualité — {mode} — périmètre : {report['mode']} "
          f"({len(report['files'])} fichiers) ──")

    for blocker in report["blockers"]:
        print(f"\n  ✗ BLOQUANT : {blocker}")

    if report.get("unmapped_files"):
        print(f"\n  · non rattachés à un stack (ignorés) : "
              f"{', '.join(report['unmapped_files'][:6])}"
              f"{' …' if len(report['unmapped_files']) > 6 else ''}")

    for name, entry in report["stacks"].items():
        print(f"\n  {entry['label']} — {len(entry['files'])} fichiers "
              f"({len(entry.get('lintable_files', []))} lintés, {entry['loc']} LOC, "
              f"{entry.get('changed_lines', 0)} lignes ajoutées)")
        if entry.get("note"):
            print(f"    ⚠ {entry['note']}")
        for key, title in (("tier1", "Niveau 1 (bloquant)"), ("tier2", "Niveau 2 (scoré)")):
            steps = entry.get(key) or []
            if not steps:
                continue
            print(f"    {title}")
            for s in steps:
                extra = ""
                if key == "tier2" and s["detail"].get("points") is not None:
                    extra = f"  [{s['detail']['points']:g} pt]"
                print(f"      {ICON.get(s['status'], '?')} {s['name']:<24}"
                      f" {s['duration_s']:>6.2f}s{extra}")
                if s["status"] in ("fail", "unavailable") and s["output_tail"]:
                    for line in s["output_tail"].splitlines()[-8:]:
                        print(f"          │ {line[:120]}")
        if entry.get("score") is not None:
            thr = report["score_threshold"]
            verdict = "" if thr is None else (" ✓" if entry["score"] >= thr else " ✗ SOUS LE SEUIL")
            print(f"    score : {entry['score']}/10"
                  f"{f' (seuil {thr})' if thr is not None else ' (seuil non calibré)'}"
                  f"{verdict}   ← {entry.get('score_source', '')}")
            print(f"      autre dénominateur : {entry.get('score_loc')}/10 sur fichiers entiers"
                  f" · {entry.get('points', 0):g} pt"
                  + (f" · pylint natif {entry['score_pylint_native']}/10"
                     if entry.get("score_pylint_native") is not None else ""))

    print(f"\n  VERDICT : {report['verdict'].upper()}", end="")
    if report.get("failed_stacks"):
        print(f" — stacks en échec : {', '.join(report['failed_stacks'])}")
    else:
        print()
    print(f"  rapport : {REPORT_PATH.relative_to(REPO)}\n")


if __name__ == "__main__":
    sys.exit(main())
