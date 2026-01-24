"""
Tests para el módulo de scoring.
"""

import pytest
import pandas as pd
import sys
import os

# Añadir el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scoring import calculate_delta, calculate_anki_points, calculate_scores


class TestCalculateDelta:
    """Tests para la función calculate_delta."""
    
    def test_delta_positive_when_cards_completed(self):
        """Test: delta positivo cuando se completan tarjetas."""
        current = {"_total": {"review": 10, "learning": 5, "new": 0}}
        previous = {"_total": {"review": 20, "learning": 10, "new": 5}}
        
        delta = calculate_delta(current, previous, "_total")
        
        # 35 - 15 = 20 tarjetas completadas
        assert delta == 20
    
    def test_delta_zero_when_no_previous(self):
        """Test: delta es 0 cuando no hay datos previos."""
        current = {"_total": {"review": 10, "learning": 5, "new": 0}}
        
        delta = calculate_delta(current, None, "_total")
        
        assert delta == 0
    
    def test_delta_zero_when_cards_added(self):
        """Test: delta es 0 cuando se añaden tarjetas (no negativo)."""
        current = {"_total": {"review": 30, "learning": 15, "new": 10}}
        previous = {"_total": {"review": 20, "learning": 10, "new": 5}}
        
        delta = calculate_delta(current, previous, "_total")
        
        # 55 - 35 = -20, pero retornamos 0 porque no puede ser negativo
        assert delta == 0
    
    def test_delta_for_specific_course(self):
        """Test: delta para un curso específico."""
        current = {
            "_total": {"review": 50, "learning": 10, "new": 20},
            "Anatomía": {"review": 10, "learning": 5, "new": 5}
        }
        previous = {
            "_total": {"review": 70, "learning": 15, "new": 25},
            "Anatomía": {"review": 20, "learning": 8, "new": 10}
        }
        
        delta = calculate_delta(current, previous, "Anatomía")
        
        # (20+8+10) - (10+5+5) = 38 - 20 = 18
        assert delta == 18


class TestCalculateAnkiPoints:
    """Tests para la función calculate_anki_points."""
    
    def test_only_review_cards(self):
        """Test: solo tarjetas de repaso."""
        points = calculate_anki_points(review=10, learning=0, new=0)
        
        # 10 * 1.0 = 10
        assert points == 10.0
    
    def test_only_learning_cards(self):
        """Test: solo tarjetas en aprendizaje."""
        points = calculate_anki_points(review=0, learning=10, new=0)
        
        # 10 * 0.5 = 5
        assert points == 5.0
    
    def test_new_cards_give_zero_points(self):
        """Test: tarjetas nuevas no dan puntos."""
        points = calculate_anki_points(review=0, learning=0, new=100)
        
        # 100 * 0.0 = 0
        assert points == 0.0
    
    def test_mixed_cards(self):
        """Test: combinación de tipos de tarjetas."""
        points = calculate_anki_points(review=20, learning=10, new=30)
        
        # (20 * 1.0) + (10 * 0.5) + (30 * 0.0) = 20 + 5 + 0 = 25
        assert points == 25.0


class TestCalculateScores:
    """Tests para la función calculate_scores."""
    
    def test_calculates_scores_for_all_students(
        self, mock_anki_stats, mock_notion_scores, mock_cursos
    ):
        """Test: calcula scores para todos los estudiantes."""
        scores = calculate_scores(
            mock_anki_stats,
            mock_notion_scores,
            mock_cursos
        )
        
        # Debe haber un DataFrame para cada curso más el general
        assert "_general" in scores
        for curso in mock_cursos:
            assert curso in scores
    
    def test_general_df_sorted_by_score(
        self, mock_anki_stats, mock_notion_scores, mock_cursos
    ):
        """Test: el DataFrame general está ordenado por Score descendente."""
        scores = calculate_scores(
            mock_anki_stats,
            mock_notion_scores,
            mock_cursos
        )
        
        df = scores["_general"]
        
        # Verificar que está ordenado descendentemente
        score_values = df["Score"].tolist()
        assert score_values == sorted(score_values, reverse=True)
    
    def test_score_includes_delta_when_previous_provided(
        self, mock_anki_stats, mock_notion_scores, mock_cursos, mock_previous_anki
    ):
        """Test: incluye delta cuando se proporcionan datos previos."""
        scores = calculate_scores(
            mock_anki_stats,
            mock_notion_scores,
            mock_cursos,
            mock_previous_anki
        )
        
        df = scores["_general"]
        
        # Debe haber columna de Completadas con valores >= 0
        assert "Completadas" in df.columns
        assert (df["Completadas"] >= 0).all()
    
    def test_no_delta_without_previous(
        self, mock_anki_stats, mock_notion_scores, mock_cursos
    ):
        """Test: sin delta cuando no hay datos previos."""
        scores = calculate_scores(
            mock_anki_stats,
            mock_notion_scores,
            mock_cursos,
            None
        )
        
        df = scores["_general"]
        
        # Completadas debe ser 0 para todos
        assert (df["Completadas"] == 0).all()


class TestLoadDemoData:
    """Tests para la función load_demo_data."""
    
    def test_returns_anki_and_notion_data(self, mock_cursos):
        """Test: retorna datos de Anki y Notion."""
        from src.scoring import load_demo_data
        
        anki, notion = load_demo_data(mock_cursos)
        
        assert isinstance(anki, dict)
        assert isinstance(notion, dict)
        assert len(anki) > 0
        assert len(notion) > 0
    
    def test_demo_data_has_correct_structure(self, mock_cursos):
        """Test: datos demo tienen la estructura correcta."""
        from src.scoring import load_demo_data
        
        anki, notion = load_demo_data(mock_cursos)
        
        for student, data in anki.items():
            assert "_total" in data
            assert "review" in data["_total"]
            assert "learning" in data["_total"]
            assert "new" in data["_total"]
            
            for curso in mock_cursos:
                assert curso in data
