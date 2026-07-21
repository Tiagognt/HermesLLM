"""
Document selection under a token cap -- shared by cat1 / cat2.

Available volume far exceeds the target in both categories. The problem is
therefore not reaching a token count, but choosing WHICH documents, without
letting a handful of subtrees monopolise the budget.

Selection is done ROUND-ROBIN over the source subtrees: one document from
each group, then a second from each group, and so on. Simply taking the
first N in alphabetical order would concentrate the whole ROS documentation
quota on `source/Concepts`, and the corpus would never see the tutorials.

Deterministic: groups are sorted, documents are sorted within each group.
Two runs produce the same selection.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Callable, List, Sequence, Tuple


def select_within_budget(
    candidates: Sequence,
    budget: int,
    *,
    group_of: Callable = lambda c: c.group,
    order_of: Callable = lambda c: c.rel_path,
    tokens_of: Callable = lambda c: c.n_tokens,
    id_of: Callable = lambda c: c.doc_id,
) -> Tuple[List, List]:
    """
    Returns (kept, dropped).

    The last accepted document may push slightly past the cap: this is
    intentional. The alternative -- rejecting it and continuing to look for
    one that fits -- would systematically favour short documents at the end
    of the selection, biasing the corpus.
    """
    if budget <= 0:
        return [], list(candidates)

    groups: "OrderedDict[str, List]" = OrderedDict()
    for c in sorted(candidates, key=lambda c: (group_of(c), order_of(c))):
        groups.setdefault(group_of(c), []).append(c)

    kept: List = []
    total = 0
    cursors = {g: 0 for g in groups}
    exhausted = False
    while total < budget and not exhausted:
        exhausted = True
        for g, docs in groups.items():
            if total >= budget:
                break
            i = cursors[g]
            if i >= len(docs):
                continue
            exhausted = False
            cursors[g] = i + 1
            kept.append(docs[i])
            total += tokens_of(docs[i])

    kept_ids = {id_of(c) for c in kept}
    dropped = [c for c in candidates if id_of(c) not in kept_ids]
    return kept, dropped
