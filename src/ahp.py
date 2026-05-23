"""
ahp.py – Analytic Hierarchy Process (Saaty) zur Herleitung der Scoring-Gewichte.

Das AHP-Verfahren leitet die Gewichte der Faktoren aus paarweisen Vergleichen ab
(statt sie frei zu setzen) und prüft deren Konsistenz über die Consistency Ratio (CR).
Eine CR < 0.10 gilt als akzeptabel konsistent.

Verwendung:
    factors = ["a", "b", "c"]
    # obere Dreiecksmatrix: wie viel wichtiger ist Zeile gegenüber Spalte (Saaty 1–9)
    judgments = {("a", "b"): 3, ("a", "c"): 5, ("b", "c"): 2}
    matrix  = build_matrix(factors, judgments)
    weights = priority_vector(matrix)            # summiert zu 1
    cr      = consistency_ratio(matrix)
"""

from __future__ import annotations

import numpy as np

# Saaty Random Index (durchschnittlicher CI zufälliger Matrizen) je Matrixgröße n.
# Quelle: Saaty (1980). Index 0/1 = 0 (triviale Konsistenz).
RANDOM_INDEX = {
    1: 0.00,
    2: 0.00,
    3: 0.58,
    4: 0.90,
    5: 1.12,
    6: 1.24,
    7: 1.32,
    8: 1.41,
    9: 1.45,
    10: 1.49,
}


def build_matrix(factors: list[str], judgments: dict[tuple[str, str], float]) -> np.ndarray:
    """
    Baut die quadratische, reziproke Paarvergleichsmatrix.

    Parameters
    ----------
    factors : Reihenfolge der Faktoren (definiert die Achsen der Matrix)
    judgments : dict {(zeile, spalte): wert} mit Saaty-Werten 1–9.
        Nur die "obere" Richtung muss angegeben werden; die reziproken
        Werte (spalte, zeile) = 1/wert werden automatisch gesetzt.

    Returns
    -------
    np.ndarray (n×n) mit Diagonale 1 und a[j,i] = 1/a[i,j].
    """
    n = len(factors)
    idx = {f: i for i, f in enumerate(factors)}
    m = np.ones((n, n), dtype=float)

    for (row, col), value in judgments.items():
        if row not in idx or col not in idx:
            raise ValueError(f"Unbekannter Faktor in Vergleich ({row}, {col})")
        if value <= 0:
            raise ValueError(f"Saaty-Wert muss > 0 sein, war {value} für ({row}, {col})")
        i, j = idx[row], idx[col]
        m[i, j] = value
        m[j, i] = 1.0 / value

    # Prüfen, dass jeder Paarvergleich genau einmal abgedeckt ist
    expected = n * (n - 1) // 2
    if len(judgments) != expected:
        raise ValueError(
            f"Erwarte {expected} Paarvergleiche für {n} Faktoren, erhielt {len(judgments)}."
        )
    return m


def priority_vector(matrix: np.ndarray) -> np.ndarray:
    """
    Berechnet den Prioritätsvektor (Gewichte) via geometrisches Mittel der Zeilen,
    normiert auf Summe 1. Robustes, in der AHP-Praxis übliches Näherungsverfahren.
    """
    geom_mean = np.prod(matrix, axis=1) ** (1.0 / matrix.shape[0])
    return geom_mean / geom_mean.sum()


def consistency_ratio(matrix: np.ndarray) -> float:
    """
    Berechnet die Consistency Ratio CR = CI / RI.

    CI  = (λmax − n) / (n − 1)
    λmax = mittleres Verhältnis (A·w)_i / w_i
    RI  = Random Index (tabellarisch, größenabhängig)

    Rückgabe 0.0 für n ≤ 2 (immer konsistent).
    """
    n = matrix.shape[0]
    if n <= 2:
        return 0.0
    w = priority_vector(matrix)
    weighted_sum = matrix @ w
    lambda_max = float(np.mean(weighted_sum / w))
    ci = (lambda_max - n) / (n - 1)
    ri = RANDOM_INDEX.get(n)
    if ri is None or ri == 0:
        return 0.0
    return ci / ri


def derive_weights(
    factors: list[str], judgments: dict[tuple[str, str], float]
) -> tuple[dict[str, float], float]:
    """
    Komfort-Funktion: gibt (gewichte_dict, consistency_ratio) zurück.

    gewichte_dict bildet Faktor → Gewicht (Summe 1) ab.
    """
    matrix = build_matrix(factors, judgments)
    weights = priority_vector(matrix)
    cr = consistency_ratio(matrix)
    return dict(zip(factors, weights, strict=True)), cr
