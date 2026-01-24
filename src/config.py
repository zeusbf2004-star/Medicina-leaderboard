"""
Configuración centralizada para el Dashboard de Competencia Académica.

Este módulo contiene todas las constantes, configuraciones y settings
que antes estaban dispersas en app.py.
"""

from typing import Dict, List
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# CURSOS Y PALABRAS CLAVE
# ============================================================================

CURSOS: List[str] = [
    "Anatomía",
    "Histología",
    "Embriología",
    "Bioquímica",
    "Fisiología",
    "Fisiopatología",
    "Patología",
    "Farmacología",
    "Microbiología",
    "Parasitología"
]

# Palabras clave para identificar mazos en AnkiWeb (mapeo curso -> palabras clave)
# 
# IMPORTANTE: Usa nombres EXACTOS de mazos para evitar falsos positivos
# - Prefijo "=" indica coincidencia EXACTA (ej: "=Anatomía humana Pró")
# - Sin prefijo indica que el mazo debe CONTENER la palabra clave
#
# Estructura esperada: Curso -> Teoría -> Temas (submazos)
CURSO_DECK_KEYWORDS: Dict[str, List[str]] = {
    "Anatomía": ["=Anatomía humana Pró", "=anatomía humana pró", "=Anatomia humana Pro"],
    "Histología": ["=Histología Ross", "=histología ross", "=Histologia Ross"],
    "Embriología": ["=Embriología humana Moore", "=embriología humana moore", "=Embriologia humana Moore"],
    "Bioquímica": ["=Bioquímica Harper", "=bioquímica harper", "=Bioquimica Harper"],
    "Fisiología": ["=Fisiología humana Guyton", "=fisiología humana guyton", "=Fisiologia humana Guyton"],
    "Fisiopatología": ["=Fisiopatología Uribe", "=fisiopatología uribe", "=Fisiopatologia Uribe"],
    "Patología": ["=Patología general Robbins", "=patología general robbins", "=Patologia general Robbins"],
    "Farmacología": ["=Farmacología médica Goodman", "=farmacología médica goodman", "=Farmacologia medica Goodman"],
    "Microbiología": ["=Microbiología médica Murray", "=microbiología médica murray", "=Microbiologia medica Murray"],
    "Parasitología": ["=Parasitología médica Becerril", "=parasitología médica becerril", "=Parasitologia medica Becerril"],
}


# ============================================================================
# MULTIPLICADORES DE SCORING
# ============================================================================

# Fórmula Médica: Score = (Review * 1.0) + (Learning * 0.5) + (New * 0)
# Las tarjetas NUEVAS no dan puntos - solo las que ya has estudiado
REVIEW_MULTIPLIER: float = 1.0      # Tarjetas de repaso (verdes) - Peso completo
LEARNING_MULTIPLIER: float = 0.5   # Tarjetas en aprendizaje (rojas) - Peso medio
NEW_MULTIPLIER: float = 0.0        # Tarjetas nuevas (azules) - NO dan puntos

# Multiplicador para Notion (quices)
NOTION_MULTIPLIER: int = 10

# Multiplicador para tarjetas completadas (delta scoring)
# Se calculan puntos por la diferencia entre tarjetas pendientes anteriores y actuales
COMPLETED_MULTIPLIER: float = 0.8


# ============================================================================
# CONFIGURACIÓN DE APIs
# ============================================================================

# Notion API
NOTION_API_VERSION: str = "2022-06-28"
NOTION_API_BASE_URL: str = "https://api.notion.com/v1"

# AnkiWeb
ANKIWEB_BASE_URL: str = "https://ankiweb.net"
ANKIWEB_LOGIN_URL: str = f"{ANKIWEB_BASE_URL}/account/login"
ANKIWEB_DECKS_URL: str = f"{ANKIWEB_BASE_URL}/decks/"
ANKIWEB_STUDY_URL: str = "https://ankiuser.net/study"

# Discord
DISCORD_WEBHOOK_URL_KEY: str = "DISCORD_WEBHOOK_URL"


# ============================================================================
# CONFIGURACIÓN DE UI
# ============================================================================

# GitHub Raw URL para recursos estáticos (PWA)
GITHUB_RAW_BASE: str = "https://raw.githubusercontent.com/zeusbf2004-star/Medicina-leaderboard/main"

# Colores para UI
COLORS = {
    "gold": "#FFD700",
    "silver": "#C0C0C0",
    "bronze": "#CD7F32",
    "primary": "#00D2FF",
    "secondary": "#3A7BD5",
    "background_start": "#0f0f23",
    "background_end": "#1a1a3e",
}

# Emojis para medallas
MEDALS: List[str] = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣']


# ============================================================================
# TIMEOUTS Y LÍMITES
# ============================================================================

REQUEST_TIMEOUT: int = 15  # segundos
NOTION_TIMEOUT: int = 30   # segundos
MAX_SCRAPER_WORKERS: int = 3  # trabajadores paralelos


# ============================================================================
# FUNCIONES DE UTILIDAD
# ============================================================================

def normalize_text(text: str) -> str:
    """
    Normaliza texto para comparación (lowercase, sin acentos).
    
    Args:
        text: Texto a normalizar
        
    Returns:
        Texto normalizado sin acentos y en minúsculas
    """
    text = text.lower().strip()
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ñ': 'n', 'ü': 'u'
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def match_course_in_deck(deck_name: str, curso: str) -> bool:
    """
    Verifica si el nombre de un mazo corresponde a un curso.
    
    Modos de coincidencia:
    - "=Nombre Exacto": El mazo debe coincidir EXACTAMENTE con el nombre
    - "palabra clave": El mazo debe CONTENER la palabra clave
    
    Args:
        deck_name: Nombre del mazo encontrado en AnkiWeb
        curso: Nombre del curso a verificar
    
    Returns:
        True si el mazo coincide con alguna palabra clave del curso
    """
    keywords = CURSO_DECK_KEYWORDS.get(curso, [])
    
    if not keywords:
        return False
    
    # Normalizar el nombre del mazo
    deck_normalized = normalize_text(deck_name)
    
    for keyword in keywords:
        # Verificar si es coincidencia exacta (prefijo "=")
        if keyword.startswith("="):
            exact_name = normalize_text(keyword[1:])  # Quitar el "="
            if deck_normalized == exact_name:
                return True
        else:
            # Coincidencia por contenido
            keyword_normalized = normalize_text(keyword)
            if keyword_normalized in deck_normalized:
                return True
    
    return False
