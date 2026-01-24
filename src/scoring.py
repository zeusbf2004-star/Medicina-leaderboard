"""
Motor de cálculo de puntajes.

Este módulo contiene la lógica para calcular los scores de los estudiantes
usando la Fórmula Médica.
"""

import logging
from typing import Dict, List, Optional

import pandas as pd

from src.config import (
    REVIEW_MULTIPLIER,
    LEARNING_MULTIPLIER,
    NEW_MULTIPLIER,
    NOTION_MULTIPLIER,
    COMPLETED_MULTIPLIER,
)

logger = logging.getLogger(__name__)


def calculate_delta(current: Dict, previous: Optional[Dict], key: str) -> int:
    """
    Calcula las tarjetas completadas (delta) entre dos snapshots.
    
    Si las tarjetas pendientes actuales son MENOS que antes,
    significa que el usuario completó tarjetas.
    
    Args:
        current: Stats actuales {review, learning, new}
        previous: Stats anteriores {review, learning, new}
        key: Clave del curso o '_total'
        
    Returns:
        Número de tarjetas completadas (delta positivo)
    """
    if not previous:
        return 0
    
    curr = current.get(key, {'review': 0, 'learning': 0, 'new': 0})
    prev = previous.get(key, {'review': 0, 'learning': 0, 'new': 0})
    
    # Total pendientes = review + learning + new
    curr_total = curr.get('review', 0) + curr.get('learning', 0) + curr.get('new', 0)
    prev_total = prev.get('review', 0) + prev.get('learning', 0) + prev.get('new', 0)
    
    # Delta = tarjetas que ya no están pendientes (completadas)
    delta = prev_total - curr_total
    
    # Solo contar si es positivo (tarjetas completadas)
    return max(0, delta)


def calculate_anki_points(review: int, learning: int, new: int) -> float:
    """
    Calcula puntos de Anki usando la Fórmula Médica.
    
    Fórmula: (Review * 1.0) + (Learning * 0.5) + (New * 0)
    
    Args:
        review: Tarjetas de repaso
        learning: Tarjetas en aprendizaje
        new: Tarjetas nuevas
        
    Returns:
        Puntos calculados
    """
    return (review * REVIEW_MULTIPLIER) + (learning * LEARNING_MULTIPLIER) + (new * NEW_MULTIPLIER)


def calculate_scores(
    anki: Dict,
    notion: Dict,
    cursos: List[str],
    previous_anki: Optional[Dict] = None
) -> Dict[str, pd.DataFrame]:
    """
    Calcula scores por curso y general usando la Fórmula Médica.
    
    Fórmula:
    Score Anki = (Review * 1.0) + (Learning * 0.5) + (New * 0)
    Score Completadas = Tarjetas completadas * 0.8
    Score Total = Score Anki + Score Completadas + (Quices * 10)
    
    Args:
        anki: Stats actuales de AnkiWeb por estudiante
        notion: Scores de Notion por estudiante
        cursos: Lista de cursos
        previous_anki: Stats anteriores para calcular delta (opcional)
        
    Returns:
        Dict con DataFrames de scores por curso y general
    """
    all_students = set(anki.keys()) | set(notion.keys())
    results = {}
    
    # Por curso
    for curso in cursos:
        data = []
        for student in all_students:
            a = anki.get(student, {}).get(curso, {'review': 0, 'learning': 0, 'new': 0})
            prev_student = previous_anki.get(student, {}) if previous_anki else {}
            
            # Extraer contadores
            review = a.get('review', 0)
            learning = a.get('learning', 0)
            new = a.get('new', 0)
            
            # Calcular delta (tarjetas completadas)
            delta = calculate_delta(
                anki.get(student, {}),
                prev_student,
                curso
            )
            
            # Fórmula Médica para Anki
            anki_pts = calculate_anki_points(review, learning, new)
            
            # Puntos por tarjetas completadas
            delta_pts = delta * COMPLETED_MULTIPLIER
            
            # Puntaje de Notion (quices)
            n = notion.get(student, {}).get(curso, 0)
            notion_pts = n * NOTION_MULTIPLIER
            
            total = anki_pts + delta_pts + notion_pts
            
            data.append({
                'Estudiante': student,
                'Review': review,
                'Learning': learning,
                'New': new,
                'Completadas': delta,
                'Pts Anki': round(anki_pts, 1),
                'Pts Delta': round(delta_pts, 1),
                'Quices': n,
                'Pts Notion': round(notion_pts, 1),
                'Score': round(total, 1)
            })
        
        df = pd.DataFrame(data)
        if not df.empty:
            df = df.sort_values('Score', ascending=False).reset_index(drop=True)
            df.index = df.index + 1
        results[curso] = df
    
    # General
    data = []
    for student in all_students:
        a_total = anki.get(student, {}).get('_total', {'review': 0, 'learning': 0, 'new': 0})
        prev_student = previous_anki.get(student, {}) if previous_anki else {}
        
        # Extraer contadores totales
        review = a_total.get('review', 0)
        learning = a_total.get('learning', 0)
        new = a_total.get('new', 0)
        
        # Calcular delta total
        delta = calculate_delta(
            anki.get(student, {}),
            prev_student,
            '_total'
        )
        
        # Fórmula Médica para Anki
        anki_pts = calculate_anki_points(review, learning, new)
        
        # Puntos por tarjetas completadas
        delta_pts = delta * COMPLETED_MULTIPLIER
        
        # Puntaje de Notion (quices)
        n_total = notion.get(student, {}).get('_total', 0)
        notion_pts = n_total * NOTION_MULTIPLIER
        
        total = anki_pts + delta_pts + notion_pts
        
        data.append({
            'Estudiante': student,
            'Review': review,
            'Learning': learning,
            'New': new,
            'Completadas': delta,
            'Pts Anki': round(anki_pts, 1),
            'Pts Delta': round(delta_pts, 1),
            'Quices': n_total,
            'Pts Notion': round(notion_pts, 1),
            'Score': round(total, 1)
        })
    
    df = pd.DataFrame(data)
    if not df.empty:
        df = df.sort_values('Score', ascending=False).reset_index(drop=True)
        df.index = df.index + 1
    results['_general'] = df
    
    logger.info(f"Calculados scores para {len(all_students)} estudiantes en {len(cursos)} cursos")
    return results


def load_demo_data(cursos: List[str]) -> tuple:
    """
    Genera datos demo con la estructura review, learning, new.
    
    Args:
        cursos: Lista de cursos
        
    Returns:
        Tuple (anki_data, notion_data)
    """
    import random
    random.seed(42)
    
    names = ['Ana Martínez', 'Carlos López', 'María García', 'Luis Hernández', 'Sofia Rodríguez']
    
    anki = {}
    notion = {}
    
    for name in names:
        # Estructura con review, learning, new
        anki[name] = {
            '_total': {
                'review': random.randint(20, 80),
                'learning': random.randint(5, 20),
                'new': random.randint(10, 50)
            }
        }
        notion[name] = {'_total': random.randint(60, 100)}
        
        for c in cursos:
            anki[name][c] = {
                'review': random.randint(5, 30),
                'learning': random.randint(2, 10),
                'new': random.randint(5, 20)
            }
            notion[name][c] = random.randint(0, 20)
    
    return anki, notion
