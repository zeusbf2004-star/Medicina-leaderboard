"""
Componentes de UI reutilizables para Streamlit.

Este módulo contiene funciones para renderizar componentes
comunes del dashboard.
"""

import logging
from typing import Dict, List, Optional

import streamlit as st
import pandas as pd

from src.config import (
    CURSOS,
    COLORS,
    MEDALS,
    REVIEW_MULTIPLIER,
    LEARNING_MULTIPLIER,
    COMPLETED_MULTIPLIER,
    NOTION_MULTIPLIER,
    DISCORD_WEBHOOK_URL_KEY,
)
from src.ui.styles import get_podium_html, get_empty_state_html

logger = logging.getLogger(__name__)


def render_podium(df: pd.DataFrame, title: str):
    """
    Renderiza el podio Top 3.
    
    Args:
        df: DataFrame con los scores
        title: Título de la sección
    """
    if df.empty:
        st.info("Sin datos")
        return
    
    st.markdown(f"### 🏆 Top 3 - {title}")
    
    cols = st.columns(3)
    medals = ['🥇', '🥈', '🥉']
    colors = [COLORS['gold'], COLORS['silver'], COLORS['bronze']]
    css_classes = ['gold', 'silver', 'bronze']
    order = [1, 0, 2] if len(df) >= 3 else list(range(min(3, len(df))))
    
    for col_idx, pos in enumerate(order):
        if pos >= len(df):
            continue
        with cols[col_idx]:
            row = df.iloc[pos]
            html = get_podium_html(
                name=row['Estudiante'],
                score=row['Score'],
                medal=medals[pos],
                medal_color=colors[pos],
                css_class=css_classes[pos]
            )
            st.markdown(html, unsafe_allow_html=True)


def render_table(df: pd.DataFrame):
    """
    Renderiza la tabla de clasificación.
    
    Args:
        df: DataFrame con los scores
    """
    if df.empty:
        st.info("No hay datos")
        return
    
    st.markdown("### 📊 Clasificación")
    
    display = df.copy()
    display.insert(
        0, 
        'Pos', 
        [f"{i}°" if i > 3 else ['🥇', '🥈', '🥉'][i-1] for i in range(1, len(display)+1)]
    )
    
    st.dataframe(display, use_container_width=True, hide_index=True)


def render_submazos_table(
    anki_raw: Dict, 
    curso_actual: str,
    review_mult: float = REVIEW_MULTIPLIER,
    learning_mult: float = LEARNING_MULTIPLIER
):
    """
    Renderiza la tabla de submazos en un expander.
    
    Args:
        anki_raw: Datos raw de Anki con mazos encontrados
        curso_actual: Curso actual seleccionado
        review_mult: Multiplicador de review
        learning_mult: Multiplicador de learning
    """
    with st.expander("📚 Ver Detalle por Submazos", expanded=False):
        for student_name, student_data in anki_raw.items():
            if '_mazos_encontrados' in student_data:
                mazos_curso = [
                    m for m in student_data['_mazos_encontrados']
                    if m.get('curso') == curso_actual
                ]
                
                if mazos_curso:
                    st.markdown(f"### 📊 Submazos de {student_name}")
                    
                    for mazo in mazos_curso:
                        submazos = mazo.get('submazos', [])
                        
                        if submazos:
                            submazo_data = []
                            for sub in submazos:
                                review = sub.get('review', 0)
                                learning = sub.get('learning', 0)
                                new = sub.get('new', 0)
                                pts = (review * review_mult) + (learning * learning_mult)
                                submazo_data.append({
                                    'Submazo': sub.get('nombre', '')[:40],
                                    'Review': review,
                                    'Learning': learning,
                                    'New': new,
                                    'Pts': round(pts, 1)
                                })
                            
                            if submazo_data:
                                df_submazos = pd.DataFrame(submazo_data)
                                df_submazos = df_submazos.sort_values('Pts', ascending=False)
                                st.dataframe(
                                    df_submazos, 
                                    use_container_width=True, 
                                    hide_index=True
                                )
                        else:
                            st.info(f"No se encontraron submazos para {mazo['mazo']}")
                    break  # Solo primer estudiante con datos


def render_sidebar(scores: Dict, discord_callback=None):
    """
    Renderiza la barra lateral con configuración y fórmula.
    
    Args:
        scores: Dict con DataFrames de scores
        discord_callback: Función callback para enviar a Discord
    """
    with st.sidebar:
        st.markdown("## ⚙️ Config")
        st.markdown("### 📚 Cursos")
        for c in CURSOS:
            st.markdown(f"• {c}")
        st.markdown("---")
        
        st.markdown("### 📐 Fórmula Médica")
        st.code(
            f"Review×{REVIEW_MULTIPLIER} + Learning×{LEARNING_MULTIPLIER} + "
            f"Completadas×{COMPLETED_MULTIPLIER} + Quiz×{NOTION_MULTIPLIER}"
        )
        st.markdown("---")
        
        # Sección de Discord
        st.markdown("### 📢 Discord")
        webhook_url = get_discord_webhook()
        webhook_configured = webhook_url is not None
        
        if webhook_configured:
            st.success("✅ Webhook configurado")
            
            opciones_discord = ["🏆 General"] + [f"📚 {c}" for c in CURSOS]
            ranking_a_enviar = st.selectbox(
                "Ranking a enviar",
                opciones_discord,
                key="discord_ranking_select"
            )
            
            if st.button("📢 Enviar a Discord", use_container_width=True):
                if scores and discord_callback:
                    # Determinar curso
                    if ranking_a_enviar == "🏆 General":
                        curso = None
                    else:
                        curso = ranking_a_enviar.replace("📚 ", "")
                    
                    ok, msg = discord_callback(webhook_url, scores, curso)
                    if ok:
                        st.success(f"✅ {msg}")
                    else:
                        st.error(f"❌ {msg}")
                else:
                    st.warning("⚠️ Primero actualiza los datos")
        else:
            st.warning("⚠️ Webhook no configurado")
            st.caption("Añade `DISCORD_WEBHOOK_URL` en los secretos")
        
        st.markdown("---")
        if 'last_update' in st.session_state:
            st.caption(f"🕐 {st.session_state.last_update}")


def render_connection_debug(debug_info: List[Dict]):
    """
    Renderiza información de debug de conexión.
    
    Args:
        debug_info: Lista con información de debug por estudiante
    """
    with st.expander("🔍 Ver Detalles de Conexión AnkiWeb", expanded=True):
        for student_info in debug_info:
            st.markdown(f"**{student_info['nombre']}**")
            for paso in student_info["pasos"]:
                st.text(paso)
            st.markdown("---")


def get_discord_webhook() -> Optional[str]:
    """
    Obtiene la URL del webhook de Discord de los secretos.
    
    Returns:
        URL del webhook o None si no está configurado
    """
    try:
        return st.secrets.get(DISCORD_WEBHOOK_URL_KEY)
    except (FileNotFoundError, Exception):
        return None


def get_secrets() -> tuple:
    """
    Obtiene los secretos de Notion de forma segura.
    
    Returns:
        Tuple (notion_token, database_id) o (None, None)
    """
    notion_token = None
    database_id = None
    
    try:
        notion_token = st.secrets.get("NOTION_TOKEN")
        database_id = st.secrets.get("NOTION_DATABASE_ID")
    except (FileNotFoundError, Exception):
        pass
    
    return notion_token, database_id


def get_students_from_secrets() -> List[Dict]:
    """
    Obtiene estudiantes desde secrets.
    
    Returns:
        Lista de diccionarios con datos de estudiantes
    """
    students = []
    try:
        if "students" in st.secrets:
            return list(st.secrets["students"])
        
        i = 1
        while True:
            key = f"student_{i}"
            if key in st.secrets:
                s = st.secrets[key]
                students.append({
                    'name': s.get('name', f'Estudiante {i}'),
                    'username': s.get('username', ''),
                    'password': s.get('password', '')
                })
                i += 1
            else:
                break
    except Exception as e:
        logger.warning(f"Error al obtener estudiantes de secrets: {e}")
    return students
