"""
Integración con Discord para notificaciones.

Este módulo proporciona funciones para enviar notificaciones
a Discord usando webhooks.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
import pandas as pd

from src.config import REQUEST_TIMEOUT, MEDALS

logger = logging.getLogger(__name__)


def send_discord_notification(
    webhook_url: str,
    title: str,
    description: str,
    fields: Optional[List[Dict]] = None,
    color: int = 0x00D2FF,
    footer: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Envía una notificación a Discord via webhook.
    
    Args:
        webhook_url: URL del webhook de Discord
        title: Título del embed
        description: Descripción principal
        fields: Lista de campos [{name, value, inline}]
        color: Color del embed en formato hex
        footer: Texto del footer
        
    Returns:
        Tuple (éxito, mensaje)
    """
    if not webhook_url:
        return False, "Webhook de Discord no configurado"
    
    # Construir embed
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.now().isoformat()
    }
    
    if fields:
        embed["fields"] = fields
    
    if footer:
        embed["footer"] = {"text": footer}
    
    payload = {
        "embeds": [embed],
        "username": "🏆 Competencia Académica"
    }
    
    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT
        )
        
        if response.status_code in (200, 204):
            logger.info("Notificación enviada a Discord exitosamente")
            return True, "Notificación enviada"
        else:
            logger.error(f"Error HTTP {response.status_code} al enviar a Discord")
            return False, f"Error HTTP {response.status_code}"
            
    except requests.Timeout:
        logger.error("Timeout al conectar con Discord")
        return False, "Timeout al conectar con Discord"
    except requests.RequestException as e:
        logger.error(f"Error de conexión con Discord: {e}")
        return False, f"Error de conexión: {str(e)}"


def build_ranking_embed(
    scores: Dict[str, pd.DataFrame],
    curso: Optional[str] = None,
    include_delta: bool = False
) -> Tuple[str, str, List[Dict]]:
    """
    Construye los datos para un embed de Discord con el ranking.
    
    Args:
        scores: Dict con DataFrames de scores por curso
        curso: Nombre del curso específico o None para general
        include_delta: Si incluir información de tarjetas completadas
        
    Returns:
        Tuple (título, descripción, campos)
    """
    if curso:
        df = scores.get(curso, pd.DataFrame())
        title = f"📚 Ranking de {curso}"
    else:
        df = scores.get('_general', pd.DataFrame())
        title = "🏆 Ranking General"
    
    if df.empty:
        return title, "Sin datos disponibles", []
    
    # Construir descripción con top 5
    lines = []
    for i, (_, row) in enumerate(df.head(5).iterrows()):
        medal = MEDALS[i] if i < len(MEDALS) else f"{i+1}."
        student = row['Estudiante']
        score = row['Score']
        
        # Añadir info de delta si está disponible
        delta_info = ""
        if include_delta and 'Completadas' in row:
            completadas = row.get('Completadas', 0)
            if completadas > 0:
                delta_info = f" (+{completadas})"
        
        lines.append(f"{medal} **{student}**: {score} pts{delta_info}")
    
    description = "\n".join(lines)
    
    # Campos adicionales
    fields = [
        {
            "name": "📊 Total Participantes",
            "value": str(len(df)),
            "inline": True
        },
        {
            "name": "🕐 Actualizado",
            "value": datetime.now().strftime("%H:%M:%S"),
            "inline": True
        }
    ]
    
    return title, description, fields


def notify_ranking_to_discord(
    webhook_url: str,
    scores: Dict,
    curso: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Envía el ranking actual a Discord.
    
    Args:
        webhook_url: URL del webhook de Discord
        scores: Dict con DataFrames de scores
        curso: Curso específico o None para general
        
    Returns:
        Tuple (éxito, mensaje)
    """
    title, description, fields = build_ranking_embed(scores, curso)
    
    # Color según el curso
    if curso:
        color = 0x3A7BD5  # Azul para cursos específicos
    else:
        color = 0xFFD700  # Dorado para ranking general
    
    return send_discord_notification(
        webhook_url=webhook_url,
        title=title,
        description=description,
        fields=fields,
        color=color,
        footer="Dashboard de Competencia Académica • Medicina"
    )
