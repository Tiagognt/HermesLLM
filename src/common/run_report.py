"""
Rapport d'exécution Markdown -- transverse cat1 / cat2 / cat3.

Matérialise la règle 5 du projet : *un élément ignoré ou en échec doit être
journalisé avec sa raison, et le run doit laisser une trace sur disque*.
Jusqu'ici les échecs ne vivaient que dans stdout (perdus dès le terminal
fermé) et, pour la phase 2 seulement, dans la section « Ignorés » de
corpus_stats.md. La phase 1 ne laissait rien.

Chaque exécution d'un point d'entrée ouvre un RunReport, y déclare ses
événements au fil de l'eau, et l'écrit dans logs/<stamp>-<name>.md.

Quatre issues possibles par élément :
  ok      -- traité avec succès
  skip    -- volontairement écarté (licence, contamination, absence de
             fichier) : ce n'est PAS une anomalie, mais ça doit être tracé
  fail    -- échec technique (parsing, réseau, PDF corrompu)
  warn    -- traité, mais avec une réserve à connaître (ex. URDF réparé
             avant parsing, texte issu d'OCR)

Usage :

    from common.run_report import RunReport

    report = RunReport("cat3-collect", category="cat3")
    report.info("Catalogue", len(PILOT_CATALOG))
    ...
    report.ok("unitree_g1", kind="urdf", detail="BSD-3-Clause")
    report.skip("tiago", kind="urdf", reason="licence CC-BY-NC-ND-3.0")
    report.fail("fetch", kind="urdf", exc=exception)
    path = report.write()

Le module ne dépend que de la lib standard et de common.paths : il est
utilisable tel quel par cat1 et cat2.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from common import paths

OK, SKIP, FAIL, WARN = "ok", "skip", "fail", "warn"

_LABELS = {
    OK: "Succès",
    SKIP: "Écartés (décision tracée)",
    FAIL: "Échecs",
    WARN: "Avertissements",
}
_ICONS = {OK: "ok", SKIP: "skip", FAIL: "FAIL", WARN: "warn"}


@dataclass
class Event:
    outcome: str
    item: str
    kind: str = ""
    message: str = ""
    trace: Optional[str] = None


@dataclass
class RunReport:
    """Collecteur d'événements d'un run + rendu Markdown."""

    name: str
    category: Optional[str] = None
    title: Optional[str] = None
    events: List[Event] = field(default_factory=list)
    context: List[Tuple[str, str]] = field(default_factory=list)
    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # -- déclaration d'événements ------------------------------------------

    def info(self, key: str, value) -> None:
        """Ligne de contexte affichée en tête de rapport (paramètres du run)."""
        self.context.append((str(key), str(value)))

    def ok(self, item: str, *, kind: str = "", detail: str = "") -> None:
        self.events.append(Event(OK, item, kind, detail))

    def skip(self, item: str, *, kind: str = "", reason: str = "") -> None:
        self.events.append(Event(SKIP, item, kind, reason))

    def warn(self, item: str, *, kind: str = "", reason: str = "") -> None:
        self.events.append(Event(WARN, item, kind, reason))

    def fail(self, item: str, *, kind: str = "", exc: BaseException | None = None,
             reason: str = "") -> None:
        """
        Échec technique. Si `exc` est fourni, la trace complète est conservée
        dans le rapport (repliée) : c'est elle qui permet de diagnostiquer
        sans relancer le run.
        """
        message = reason or (f"{type(exc).__name__}: {exc}" if exc else "échec")
        trace = None
        if exc is not None:
            trace = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ).strip()
        self.events.append(Event(FAIL, item, kind, message, trace))

    # -- consultation -------------------------------------------------------

    def of(self, outcome: str) -> List[Event]:
        return [e for e in self.events if e.outcome == outcome]

    def counts(self) -> dict:
        return {o: len(self.of(o)) for o in (OK, SKIP, FAIL, WARN)}

    @property
    def has_failures(self) -> bool:
        return bool(self.of(FAIL))

    def summary_line(self) -> str:
        c = self.counts()
        return (f"{c[OK]} ok | {c[SKIP]} écartés | {c[FAIL]} échecs "
                f"| {c[WARN]} avertissements")

    # -- rendu --------------------------------------------------------------

    def _stamp(self) -> str:
        return self.started_at.strftime("%Y%m%d-%H%M%S")

    def render(self) -> str:
        finished = datetime.now(timezone.utc)
        duration = (finished - self.started_at).total_seconds()
        c = self.counts()

        lines: List[str] = []
        lines.append(f"# {self.title or self.name} — rapport d'exécution")
        lines.append("")
        lines.append(f"- Début : {self.started_at.isoformat()}")
        lines.append(f"- Fin : {finished.isoformat()} ({duration:.1f} s)")
        lines.append(f"- Racine projet : `{paths.PROJECT_ROOT}`")
        if self.category:
            lines.append(f"- Catégorie : {self.category}")
        for k, v in self.context:
            lines.append(f"- {k} : {v}")
        lines.append("")

        lines.append("## Bilan")
        lines.append("")
        lines.append("| Issue | Nombre |")
        lines.append("|---|---|")
        for o in (OK, SKIP, FAIL, WARN):
            lines.append(f"| {_LABELS[o]} | {c[o]} |")
        lines.append(f"| **Total** | **{len(self.events)}** |")
        lines.append("")

        # Les sections qui demandent une action viennent en premier : on lit
        # un rapport d'erreurs pour trouver ce qui a cassé, pas pour se
        # féliciter de ce qui a marché.
        for outcome in (FAIL, WARN, SKIP, OK):
            evs = self.of(outcome)
            if not evs:
                continue
            lines.append(f"## {_LABELS[outcome]} ({len(evs)})")
            lines.append("")
            lines.append("| Élément | Nature | Détail |")
            lines.append("|---|---|---|")
            for e in evs:
                detail = e.message.replace("|", "\\|").replace("\n", " ")
                lines.append(f"| `{e.item}` | {e.kind or '—'} | {detail} |")
            lines.append("")
            traces = [e for e in evs if e.trace]
            if traces:
                lines.append("### Traces complètes")
                lines.append("")
                for e in traces:
                    lines.append(f"<details><summary><code>{e.item}</code>"
                                 f"{' (' + e.kind + ')' if e.kind else ''}"
                                 f"</summary>")
                    lines.append("")
                    lines.append("```")
                    lines.append(e.trace)
                    lines.append("```")
                    lines.append("")
                    lines.append("</details>")
                    lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def write(self, path: Optional[Path] = None) -> Path:
        target = path or paths.report_path(self.name, self._stamp())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.render(), encoding="utf-8")
        return target
