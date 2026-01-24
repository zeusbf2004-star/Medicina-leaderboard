"""
Fixtures de pytest para tests del dashboard.
"""

import pytest
from typing import Dict, List


@pytest.fixture
def mock_cursos() -> List[str]:
    """Lista de cursos para testing."""
    return ["Anatomía", "Histología", "Fisiología"]


@pytest.fixture
def mock_anki_stats() -> Dict:
    """Datos mock de Anki para testing."""
    return {
        "Ana Martínez": {
            "_total": {"review": 50, "learning": 10, "new": 20},
            "Anatomía": {"review": 20, "learning": 5, "new": 10},
            "Histología": {"review": 15, "learning": 3, "new": 5},
            "Fisiología": {"review": 15, "learning": 2, "new": 5},
        },
        "Carlos López": {
            "_total": {"review": 30, "learning": 5, "new": 15},
            "Anatomía": {"review": 10, "learning": 2, "new": 5},
            "Histología": {"review": 10, "learning": 2, "new": 5},
            "Fisiología": {"review": 10, "learning": 1, "new": 5},
        },
    }


@pytest.fixture
def mock_notion_scores() -> Dict:
    """Datos mock de Notion para testing."""
    return {
        "Ana Martínez": {
            "_total": 85,
            "Anatomía": 30,
            "Histología": 25,
            "Fisiología": 30,
        },
        "Carlos López": {
            "_total": 70,
            "Anatomía": 25,
            "Histología": 20,
            "Fisiología": 25,
        },
    }


@pytest.fixture
def mock_previous_anki() -> Dict:
    """Datos mock de Anki anteriores para calcular delta."""
    return {
        "Ana Martínez": {
            "_total": {"review": 70, "learning": 15, "new": 25},
            "Anatomía": {"review": 30, "learning": 7, "new": 12},
            "Histología": {"review": 20, "learning": 5, "new": 8},
            "Fisiología": {"review": 20, "learning": 3, "new": 5},
        },
        "Carlos López": {
            "_total": {"review": 35, "learning": 8, "new": 18},
            "Anatomía": {"review": 12, "learning": 3, "new": 6},
            "Histología": {"review": 12, "learning": 3, "new": 6},
            "Fisiología": {"review": 11, "learning": 2, "new": 6},
        },
    }
