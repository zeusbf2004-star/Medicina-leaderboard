"""
Dashboard de Competencia Académica Multi-Curso
==============================================
Aplicación Streamlit para grupos de estudio de medicina.
Integra datos de AnkiWeb (por mazo/curso) y Notion (API directa con requests).

Autor: Expert Python Developer & Cloud Architect
Versión: 5.1 - Arquitectura Modular
"""

import streamlit as st
import time
import logging
from datetime import datetime
from typing import Dict, List

# Importar módulos del proyecto
from src.config import (
    CURSOS,
    REVIEW_MULTIPLIER,
    LEARNING_MULTIPLIER,
    COMPLETED_MULTIPLIER,
    NOTION_MULTIPLIER,
)
from src.scoring import calculate_scores, calculate_delta, load_demo_data
from src.scrapers.ankiweb import AnkiWebScraper
from src.integrations.notion import NotionAPI
from src.integrations.discord import notify_ranking_to_discord
from src.ui.styles import get_pwa_meta_tags, get_main_css, get_empty_state_html
from src.ui.components import (
    render_podium,
    render_table,
    render_submazos_table,
    render_sidebar,
    render_connection_debug,
    get_secrets,
    get_students_from_secrets,
    get_discord_webhook,
)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# FUNCIONES DE FETCH DE DATOS
# ============================================================================

def fetch_notion_scores(cursos: List[str]) -> Dict[str, Dict[str, float]]:
    """
    Wrapper para obtener puntajes de Notion con manejo de errores en UI.
    
    Returns:
        Dict {estudiante: {curso: puntaje}}
    """
    notion_token, database_id = get_secrets()
    
    if not notion_token:
        st.error("❌ **NOTION_TOKEN** no configurado en los secretos de Streamlit")
        st.info("📖 Ve a Settings → Secrets en Streamlit Cloud y agrega tu token de Notion")
        return {}
    
    if not database_id:
        st.error("❌ **NOTION_DATABASE_ID** no configurado en los secretos de Streamlit")
        st.info("📖 Copia el ID de tu base de datos desde la URL de Notion")
        return {}
    
    api = NotionAPI(notion_token, database_id)
    scores, error = api.fetch_scores_by_course(cursos)
    
    if error:
        st.error(f"❌ Error de Notion: {error}")
        return {}
    
    return scores


def fetch_anki_stats(students: List[Dict], cursos: List[str]) -> Dict:
    """
    Obtiene estadísticas de Anki para todos los estudiantes.
    
    Estructura de retorno por estudiante:
    {curso: {'review': int, 'learning': int, 'new': int}}
    """
    results = {}
    debug_info = []
    
    if not students:
        st.warning("No hay estudiantes configurados")
        return results
    
    progress = st.progress(0)
    status = st.empty()
    
    for i, student in enumerate(students):
        name = student.get('name', f'Estudiante {i+1}')
        username = student.get('username', '')
        password = student.get('password', '')
        
        status.text(f"📚 Conectando Anki: {name}...")
        student_debug = {"nombre": name, "pasos": []}
        
        # Estructura por defecto
        default_stats = {c: {'review': 0, 'learning': 0, 'new': 0} for c in cursos}
        default_stats['_total'] = {'review': 0, 'learning': 0, 'new': 0}
        
        if not username or not password:
            student_debug["pasos"].append("❌ Sin credenciales")
            results[name] = default_stats
            debug_info.append(student_debug)
            continue
        
        scraper = AnkiWebScraper()
        
        try:
            student_debug["pasos"].append(f"🔑 Intentando login con: {username[:3]}***")
            ok, msg = scraper.login(username, password)
            
            if ok:
                student_debug["pasos"].append("✅ Login exitoso")
                
                stats = scraper.get_stats_by_course(cursos)
                results[name] = stats
                
                # Registrar info de debug
                if '_mazos_encontrados' in stats:
                    for mazo in stats['_mazos_encontrados']:
                        student_debug["pasos"].append(
                            f"📚 Mazo: {mazo['mazo']} → {mazo['curso']} | Stats: {mazo['stats']}"
                        )
                
                if '_notas_internas' in stats:
                    for nota in stats['_notas_internas']:
                        student_debug["pasos"].append(f"⚠️ {nota}")
                
                # Resumen
                total = stats.get('_total', {})
                student_debug["pasos"].append(
                    f"📊 Total: Review={total.get('review', 0)}, "
                    f"Learning={total.get('learning', 0)}, New={total.get('new', 0)}"
                )
            else:
                student_debug["pasos"].append(f"❌ Login fallido: {msg}")
                results[name] = default_stats
                
        except Exception as e:
            student_debug["pasos"].append(f"💥 Error: {str(e)}")
            logger.exception(f"Error al obtener stats para {name}")
            results[name] = default_stats
        finally:
            scraper.logout()
            time.sleep(0.5)
        
        debug_info.append(student_debug)
        progress.progress((i + 1) / len(students))
    
    status.empty()
    progress.empty()
    
    # Mostrar información de debug
    render_connection_debug(debug_info)
    
    return results


# ============================================================================
# CONFIGURACIÓN DE PÁGINA
# ============================================================================

def setup_page():
    """Configura la página de Streamlit."""
    st.set_page_config(
        page_title="🏆 Dashboard Multi-Curso",
        page_icon="🏆",
        layout="wide"
    )


def apply_css():
    """Aplica estilos CSS y configuración PWA."""
    st.markdown(get_pwa_meta_tags(), unsafe_allow_html=True)
    st.markdown(get_main_css(), unsafe_allow_html=True)


# ============================================================================
# FUNCIÓN PRINCIPAL
# ============================================================================

def main():
    """Función principal de la aplicación."""
    setup_page()
    apply_css()
    
    # Inicializar session state
    if 'scores' not in st.session_state:
        st.session_state.scores = {}
    
    # Header
    st.markdown(
        '<h1 class="main-title">🏆 Dashboard de Competencia</h1>',
        unsafe_allow_html=True
    )
    st.markdown(
        f'<p class="subtitle">Medicina • {len(CURSOS)} Cursos</p>',
        unsafe_allow_html=True
    )
    
    # Sidebar
    render_sidebar(
        scores=st.session_state.scores,
        discord_callback=notify_ranking_to_discord
    )
    
    # Botón actualizar
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🔄 Actualizar Datos", use_container_width=True, type="primary"):
            with st.spinner("Obteniendo datos..."):
                try:
                    students = get_students_from_secrets()
                    
                    # Guardar datos anteriores para calcular delta
                    previous_anki = None
                    if 'anki_raw' in st.session_state:
                        previous_anki = st.session_state.anki_raw.copy()
                    
                    if not students:
                        st.warning("⚠️ Sin estudiantes configurados. Mostrando demo...")
                        anki, notion = load_demo_data(CURSOS)
                    else:
                        anki = fetch_anki_stats(students, CURSOS)
                        notion = fetch_notion_scores(CURSOS)
                    
                    # Calcular scores con delta
                    st.session_state.scores = calculate_scores(
                        anki, notion, CURSOS, previous_anki
                    )
                    st.session_state.anki_raw = anki
                    st.session_state.last_update = datetime.now().strftime("%H:%M:%S")
                    
                    # Mostrar resumen de tarjetas completadas
                    if previous_anki:
                        total_completadas = 0
                        for student in anki.keys():
                            if student in previous_anki:
                                delta = calculate_delta(
                                    anki.get(student, {}),
                                    previous_anki.get(student, {}),
                                    '_total'
                                )
                                total_completadas += delta
                        if total_completadas > 0:
                            st.success(
                                f"✅ Datos actualizados • "
                                f"{total_completadas} tarjetas completadas en total"
                            )
                        else:
                            st.success("✅ Datos actualizados")
                    else:
                        st.success("✅ Datos actualizados (primera carga)")
                except Exception as e:
                    st.error(f"❌ Error: {e}")
                    logger.exception("Error al actualizar datos")
    
    st.markdown("---")
    
    # Vista de datos
    scores = st.session_state.scores
    
    if scores:
        # Dropdown para seleccionar vista
        opciones = ["🏆 General"] + [f"📚 {c}" for c in CURSOS]
        vista_seleccionada = st.selectbox(
            "Seleccionar Vista",
            opciones,
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        
        # Determinar qué datos mostrar
        if vista_seleccionada == "🏆 General":
            df = scores.get('_general', None)
            titulo = "General"
            curso_actual = None
        else:
            curso_actual = vista_seleccionada.replace("📚 ", "")
            df = scores.get(curso_actual, None)
            titulo = curso_actual
        
        if df is not None and not df.empty:
            # Mostrar podio y tabla principal
            render_podium(df, titulo)
            st.markdown("---")
            render_table(df)
            
            # Tabla de submazos (si hay curso seleccionado)
            if 'anki_raw' in st.session_state and curso_actual:
                render_submazos_table(st.session_state.anki_raw, curso_actual)
        else:
            st.info("Sin datos para esta vista")
    else:
        st.markdown(get_empty_state_html(), unsafe_allow_html=True)
    
    # Footer
    st.markdown("---")
    st.caption(
        f"📐 Fórmula: (Review×{REVIEW_MULTIPLIER}) + "
        f"(Learning×{LEARNING_MULTIPLIER}) + "
        f"(Completadas×{COMPLETED_MULTIPLIER}) + "
        f"(Quiz×{NOTION_MULTIPLIER}) | v5.1 - Arquitectura Modular"
    )


if __name__ == "__main__":
    main()
