"""
Markdown run report -- shared by cat1 / cat2 / cat3.

Implements rule 5 of the project: *anything skipped or failed must be
logged with its reason, and every run must leave a trace on disk*. Until
this module existed, failures lived only in stdout (lost as soon as the
terminal closed) and, for phase 2 only, in the "skipped" section of
corpus_stats.md. Phase 1 left nothing at all.

Each run of an entry point opens a RunReport, declares events as it goes,
and writes the result to logs/<stamp>-<name>.md.

Four possible outcomes per item:
  ok    -- processed successfully
  skip  -- deliberately set aside (license, contamination, missing file).
           This is NOT an anomaly, but it must be traced.
  fail  -- technical failure (parsing, network, corrupt PDF)
  warn  -- processed, but with a caveat worth knowing (e.g. URDF repaired
           before parsing, text obtained through OCR)

Usage:

    from common.run_report import RunReport

    report = RunReport("cat3-collect", category="cat3")
    report.info("Catalogue", len(PILOT_CATALOG))
    ...
    report.ok("unitree_g1", kind="urdf", detail="BSD-3-Clause")
    report.skip("tiago", kind="urdf", reason="CC-BY-NC-ND-3.0 license")
    report.fail("fetch", kind="urdf", exc=exception)
    path = report.write()

The module depends only on the standard library and common.paths, so it is
usable as-is by any category.
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
    OK: "Succeeded",
    SKIP: "Set aside (traced decision)",
    FAIL: "Failures",
    WARN: "Warnings",
}


@dataclass
class Event:
    outcome: str
    item: str
    kind: str = ""
    message: str = ""
    trace: Optional[str] = None


@dataclass
class RunReport:
    """Collects the events of a run and renders them as Markdown."""

    name: str
    category: Optional[str] = None
    title: Optional[str] = None
    events: List[Event] = field(default_factory=list)
    context: List[Tuple[str, str]] = field(default_factory=list)
    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # -- declaring events ---------------------------------------------------

    def info(self, key: str, value) -> None:
        """Context line shown at the top of the report (run parameters)."""
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
        Technical failure. When `exc` is supplied the full traceback is kept
        in the report (collapsed): that is what allows diagnosis without
        re-running.
        """
        message = reason or (f"{type(exc).__name__}: {exc}" if exc else "failure")
        trace = None
        if exc is not None:
            trace = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ).strip()
        self.events.append(Event(FAIL, item, kind, message, trace))

    # -- querying -----------------------------------------------------------

    def of(self, outcome: str) -> List[Event]:
        return [e for e in self.events if e.outcome == outcome]

    def counts(self) -> dict:
        return {o: len(self.of(o)) for o in (OK, SKIP, FAIL, WARN)}

    @property
    def has_failures(self) -> bool:
        return bool(self.of(FAIL))

    def summary_line(self) -> str:
        c = self.counts()
        return (f"{c[OK]} ok | {c[SKIP]} set aside | {c[FAIL]} failures "
                f"| {c[WARN]} warnings")

    # -- rendering ----------------------------------------------------------

    def _stamp(self) -> str:
        return self.started_at.strftime("%Y%m%d-%H%M%S")

    def render(self) -> str:
        finished = datetime.now(timezone.utc)
        duration = (finished - self.started_at).total_seconds()
        c = self.counts()

        lines: List[str] = []
        lines.append(f"# {self.title or self.name} — run report")
        lines.append("")
        lines.append(f"- Started: {self.started_at.isoformat()}")
        lines.append(f"- Finished: {finished.isoformat()} ({duration:.1f} s)")
        lines.append(f"- Project root: `{paths.PROJECT_ROOT}`")
        if self.category:
            lines.append(f"- Category: {self.category}")
        for k, v in self.context:
            lines.append(f"- {k}: {v}")
        lines.append("")

        lines.append("## Summary")
        lines.append("")
        lines.append("| Outcome | Count |")
        lines.append("|---|---|")
        for o in (OK, SKIP, FAIL, WARN):
            lines.append(f"| {_LABELS[o]} | {c[o]} |")
        lines.append(f"| **Total** | **{len(self.events)}** |")
        lines.append("")

        # Sections that require action come first: an error report is read
        # to find what broke, not to admire what worked.
        for outcome in (FAIL, WARN, SKIP, OK):
            evs = self.of(outcome)
            if not evs:
                continue
            lines.append(f"## {_LABELS[outcome]} ({len(evs)})")
            lines.append("")
            lines.append("| Item | Kind | Detail |")
            lines.append("|---|---|---|")
            for e in evs:
                detail = e.message.replace("|", "\\|").replace("\n", " ")
                lines.append(f"| `{e.item}` | {e.kind or '—'} | {detail} |")
            lines.append("")
            traces = [e for e in evs if e.trace]
            if traces:
                lines.append("### Full tracebacks")
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
