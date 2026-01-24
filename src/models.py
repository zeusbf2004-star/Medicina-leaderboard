"""
Modelos de datos para el Dashboard de Competencia Académica.

Define las estructuras de datos utilizadas en toda la aplicación.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class AnkiStats:
    """Estadísticas de un mazo de Anki."""
    review: int = 0
    learning: int = 0
    new: int = 0
    
    @property
    def total_pending(self) -> int:
        """Total de tarjetas pendientes."""
        return self.review + self.learning + self.new
    
    def to_dict(self) -> Dict[str, int]:
        """Convierte a diccionario."""
        return {
            'review': self.review,
            'learning': self.learning,
            'new': self.new
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> 'AnkiStats':
        """Crea instancia desde diccionario."""
        return cls(
            review=data.get('review', 0),
            learning=data.get('learning', 0),
            new=data.get('new', 0)
        )


@dataclass
class DeckInfo:
    """Información de un mazo de Anki."""
    name: str
    deck_id: Optional[str] = None
    href: Optional[str] = None
    stats: AnkiStats = field(default_factory=AnkiStats)
    children: List['DeckInfo'] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convierte a diccionario."""
        return {
            'name': self.name,
            'deck_id': self.deck_id,
            'href': self.href,
            'due': self.stats.review,
            'learning': self.stats.learning,
            'new': self.stats.new,
            'children': [c.to_dict() for c in self.children]
        }


@dataclass
class StudentCredentials:
    """Credenciales de un estudiante."""
    name: str
    username: str
    password: str


@dataclass
class StudentScore:
    """Puntaje de un estudiante."""
    estudiante: str
    review: int = 0
    learning: int = 0
    new: int = 0
    completadas: int = 0
    pts_anki: float = 0.0
    pts_delta: float = 0.0
    quices: int = 0
    pts_notion: float = 0.0
    score: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convierte a diccionario para DataFrame."""
        return {
            'Estudiante': self.estudiante,
            'Review': self.review,
            'Learning': self.learning,
            'New': self.new,
            'Completadas': self.completadas,
            'Pts Anki': round(self.pts_anki, 1),
            'Pts Delta': round(self.pts_delta, 1),
            'Quices': self.quices,
            'Pts Notion': round(self.pts_notion, 1),
            'Score': round(self.score, 1)
        }


@dataclass
class NotionRecord:
    """Registro de un quiz en Notion."""
    estudiante: str
    curso: str
    puntaje: float
    fecha: Optional[datetime] = None


@dataclass 
class DiscordEmbed:
    """Embed para notificación de Discord."""
    title: str
    description: str
    color: int = 0x00D2FF
    fields: List[Dict] = field(default_factory=list)
    footer: Optional[str] = None
    timestamp: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convierte a formato de Discord API."""
        embed = {
            "title": self.title,
            "description": self.description,
            "color": self.color,
        }
        
        if self.fields:
            embed["fields"] = self.fields
            
        if self.footer:
            embed["footer"] = {"text": self.footer}
            
        if self.timestamp:
            embed["timestamp"] = self.timestamp
        else:
            embed["timestamp"] = datetime.now().isoformat()
            
        return embed


@dataclass
class SubmazoInfo:
    """Información de un submazo (tema)."""
    nombre: str
    review: int = 0
    learning: int = 0
    new: int = 0
    
    def to_dict(self) -> Dict:
        return {
            'nombre': self.nombre,
            'review': self.review,
            'learning': self.learning,
            'new': self.new
        }


@dataclass
class MazoEncontrado:
    """Información de un mazo encontrado que coincide con un curso."""
    mazo: str
    curso: str
    stats: AnkiStats = field(default_factory=AnkiStats)
    submazos: List[SubmazoInfo] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'mazo': self.mazo,
            'curso': self.curso,
            'stats': self.stats.to_dict(),
            'submazos': [s.to_dict() for s in self.submazos]
        }
