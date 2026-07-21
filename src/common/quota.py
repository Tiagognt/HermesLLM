"""
Sélection de documents sous plafond de tokens -- transverse cat1 / cat2.

Le volume disponible dépasse largement la cible dans les deux catégories.
Le problème n'est donc pas d'atteindre un nombre de tokens, mais de choisir
LESQUELS, sans laisser une poignée de sous-arbres confisquer le budget.

La sélection se fait en TOURNIOIR sur les groupes d'origine : on prend un
document de chaque groupe, puis un deuxième de chaque groupe, et ainsi de
suite. Prendre simplement les N premiers par ordre alphabétique
concentrerait tout le quota de la documentation ROS sur `source/Concepts`,
et le corpus ne verrait jamais les tutoriels.

Déterministe : groupes triés, documents triés dans chaque groupe. Deux
exécutions produisent la même sélection.
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
    Retourne (retenus, écartés).

    Le dernier document accepté peut faire légèrement dépasser le plafond :
    c'est voulu. L'alternative -- refuser puis continuer à chercher un
    document qui rentre -- favoriserait systématiquement les documents
    courts en fin de sélection, ce qui biaiserait le corpus.
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
