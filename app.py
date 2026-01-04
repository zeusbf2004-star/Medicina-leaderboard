"""
Leaderboard - Tabla de Clasificación para Grupo de Estudio de Medicina
=======================================================================
Aplicación Streamlit que integra datos de AnkiWeb y Notion para crear
un dashboard interactivo de seguimiento de estudio.

Autor: Desarrollador Senior Python - Data Engineering
"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from notion_client import Client
from datetime import datetime
import re
import time

# ============================================================================
# CONFIGURACIÓN Y CONSTANTES
# ============================================================================

# ID de la Base de Datos de Notion (configurar según tu workspace)
NOTION_DATABASE_ID = "TU_DATABASE_ID_AQUI"

# Fórmula de puntaje: (Tarjetas Anki * 0.5) + (Puntos Notion * 10)
ANKI_MULTIPLIER = 0.5
NOTION_MULTIPLIER = 10

# ============================================================================
# CLASE PARA SCRAPING DE ANKIWEB
# ============================================================================

class AnkiWebScraper:
    """
    Cliente para extraer estadísticas de AnkiWeb mediante web scraping.
    Utiliza requests con manejo de sesión y cookies.
    """
    
    BASE_URL = "https://ankiweb.net"
    LOGIN_URL = f"{BASE_URL}/account/login"
    STATS_URL = f"{BASE_URL}/decks/"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        })
    
    def _get_csrf_token(self, html_content: str) -> str:
        """Extrae el token CSRF del formulario de login."""
        soup = BeautifulSoup(html_content, 'html.parser')
        csrf_input = soup.find('input', {'name': 'csrf_token'})
        if csrf_input:
            return csrf_input.get('value', '')
        # Alternativa: buscar en meta tags
        csrf_meta = soup.find('meta', {'name': 'csrf-token'})
        if csrf_meta:
            return csrf_meta.get('content', '')
        return ''
    
    def login(self, username: str, password: str) -> bool:
        """
        Realiza el login en AnkiWeb.
        
        Args:
            username: Email o nombre de usuario de AnkiWeb
            password: Contraseña de la cuenta
            
        Returns:
            True si el login fue exitoso, False en caso contrario
        """
        try:
            # Obtener página de login para CSRF token
            response = self.session.get(self.LOGIN_URL)
            response.raise_for_status()
            
            csrf_token = self._get_csrf_token(response.text)
            
            # Datos del formulario de login
            login_data = {
                'csrf_token': csrf_token,
                'submitted': '1',
                'username': username,
                'password': password,
            }
            
            # Realizar login
            response = self.session.post(
                self.LOGIN_URL,
                data=login_data,
                allow_redirects=True
            )
            
            # Verificar si el login fue exitoso
            if 'logout' in response.text.lower() or '/decks' in response.url:
                return True
            
            return False
            
        except requests.RequestException as e:
            st.error(f"Error de conexión durante login: {str(e)}")
            return False
    
    def get_review_stats(self) -> dict:
        """
        Obtiene las estadísticas de repaso del usuario logueado.
        
        Returns:
            Diccionario con 'review_count' (repasadas hoy) y 'due_count' (pendientes)
        """
        stats = {
            'review_count': 0,
            'due_count': 0,
            'success': False
        }
        
        try:
            response = self.session.get(self.STATS_URL)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Buscar estadísticas en la página
            # Nota: La estructura HTML de AnkiWeb puede cambiar
            
            # Método 1: Buscar en elementos de estadísticas
            stats_elements = soup.find_all(['span', 'div'], class_=re.compile(r'stat|count|due|review', re.I))
            
            for elem in stats_elements:
                text = elem.get_text(strip=True).lower()
                # Buscar números asociados a "reviewed" o "due"
                if 'review' in text:
                    numbers = re.findall(r'\d+', text)
                    if numbers:
                        stats['review_count'] = int(numbers[0])
                elif 'due' in text:
                    numbers = re.findall(r'\d+', text)
                    if numbers:
                        stats['due_count'] = int(numbers[0])
            
            # Método 2: Buscar en tabla de mazos
            deck_table = soup.find('table', {'id': 'decks'})
            if deck_table:
                rows = deck_table.find_all('tr')
                total_due = 0
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 3:
                        # Típicamente: Nombre | Due | New
                        try:
                            due_text = cols[1].get_text(strip=True)
                            due_num = int(re.sub(r'\D', '', due_text) or '0')
                            total_due += due_num
                        except (ValueError, IndexError):
                            continue
                stats['due_count'] = total_due
            
            # Método 3: Buscar en scripts JSON embebidos
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string and 'review' in script.string.lower():
                    # Buscar patrones como "reviewed": 123
                    reviewed_match = re.search(r'"reviewed?":\s*(\d+)', script.string)
                    if reviewed_match:
                        stats['review_count'] = int(reviewed_match.group(1))
                    due_match = re.search(r'"due":\s*(\d+)', script.string)
                    if due_match:
                        stats['due_count'] = int(due_match.group(1))
            
            stats['success'] = True
            
        except requests.RequestException as e:
            st.error(f"Error obteniendo estadísticas: {str(e)}")
        
        return stats
    
    def logout(self):
        """Cierra la sesión actual."""
        try:
            self.session.get(f"{self.BASE_URL}/account/logout")
        except:
            pass
        finally:
            self.session = requests.Session()


def fetch_anki_stats_for_students(students_list: list) -> dict:
    """
    Obtiene estadísticas de AnkiWeb para múltiples estudiantes.
    
    Args:
        students_list: Lista de diccionarios con 'name', 'username', 'password'
        
    Returns:
        Diccionario {nombre_estudiante: {'review_count': int, 'due_count': int}}
    """
    results = {}
    scraper = AnkiWebScraper()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, student in enumerate(students_list):
        name = student.get('name', 'Desconocido')
        username = student.get('username', '')
        password = student.get('password', '')
        
        status_text.text(f"📚 Obteniendo datos de Anki para: {name}...")
        
        if not username or not password:
            results[name] = {'review_count': 0, 'due_count': 0, 'error': 'Credenciales faltantes'}
            continue
        
        try:
            if scraper.login(username, password):
                stats = scraper.get_review_stats()
                results[name] = {
                    'review_count': stats.get('review_count', 0),
                    'due_count': stats.get('due_count', 0),
                    'error': None
                }
            else:
                results[name] = {'review_count': 0, 'due_count': 0, 'error': 'Login fallido'}
        except Exception as e:
            results[name] = {'review_count': 0, 'due_count': 0, 'error': str(e)}
        finally:
            scraper.logout()
            time.sleep(1)  # Pausa entre requests para evitar rate limiting
        
        progress_bar.progress((i + 1) / len(students_list))
    
    status_text.empty()
    progress_bar.empty()
    
    return results


# ============================================================================
# INTEGRACIÓN CON NOTION
# ============================================================================

def get_notion_client() -> Client:
    """
    Crea un cliente de Notion usando el token de los secretos.
    
    Returns:
        Cliente de Notion autenticado
    """
    notion_token = st.secrets.get("NOTION_TOKEN", "")
    if not notion_token:
        st.error("⚠️ Token de Notion no configurado en secrets")
        return None
    return Client(auth=notion_token)


def fetch_notion_scores(database_id: str = None) -> dict:
    """
    Obtiene y suma los puntajes de exámenes desde Notion.
    
    Args:
        database_id: ID de la base de datos de Notion (opcional, usa el default)
        
    Returns:
        Diccionario {nombre_estudiante: puntaje_total}
    """
    notion = get_notion_client()
    if not notion:
        return {}
    
    db_id = database_id or st.secrets.get("NOTION_DATABASE_ID", NOTION_DATABASE_ID)
    
    if db_id == "TU_DATABASE_ID_AQUI":
        st.warning("⚠️ Configura el ID de la base de datos de Notion en secrets")
        return {}
    
    scores = {}
    
    try:
        # Consultar la base de datos
        has_more = True
        start_cursor = None
        
        while has_more:
            query_params = {"database_id": db_id}
            if start_cursor:
                query_params["start_cursor"] = start_cursor
            
            response = notion.databases.query(**query_params)
            
            for page in response.get('results', []):
                properties = page.get('properties', {})
                
                # Buscar el nombre del estudiante
                # La propiedad puede llamarse "Nombre", "Estudiante", "Name", etc.
                student_name = None
                for prop_name in ['Nombre', 'Estudiante', 'Name', 'Student', 'Alumno']:
                    if prop_name in properties:
                        prop = properties[prop_name]
                        if prop.get('type') == 'title':
                            title_content = prop.get('title', [])
                            if title_content:
                                student_name = title_content[0].get('text', {}).get('content', '')
                        elif prop.get('type') == 'rich_text':
                            text_content = prop.get('rich_text', [])
                            if text_content:
                                student_name = text_content[0].get('text', {}).get('content', '')
                        break
                
                if not student_name:
                    continue
                
                # Buscar el puntaje
                # La propiedad puede llamarse "Puntaje", "Score", "Puntos", etc.
                score = 0
                for prop_name in ['Puntaje', 'Score', 'Puntos', 'Points', 'Calificacion', 'Nota']:
                    if prop_name in properties:
                        prop = properties[prop_name]
                        if prop.get('type') == 'number':
                            score = prop.get('number', 0) or 0
                        elif prop.get('type') == 'formula':
                            formula_result = prop.get('formula', {})
                            if formula_result.get('type') == 'number':
                                score = formula_result.get('number', 0) or 0
                        break
                
                # Sumar al acumulador del estudiante
                if student_name not in scores:
                    scores[student_name] = 0
                scores[student_name] += score
            
            has_more = response.get('has_more', False)
            start_cursor = response.get('next_cursor')
    
    except Exception as e:
        st.error(f"❌ Error al consultar Notion: {str(e)}")
    
    return scores


# ============================================================================
# CÁLCULO DE PUNTAJES
# ============================================================================

def calculate_total_scores(anki_data: dict, notion_data: dict) -> pd.DataFrame:
    """
    Calcula el puntaje total combinando datos de Anki y Notion.
    
    Fórmula: (Tarjetas Anki * 0.5) + (Puntos Notion * 10) = Score Total
    
    Args:
        anki_data: Diccionario con estadísticas de Anki por estudiante
        notion_data: Diccionario con puntajes de Notion por estudiante
        
    Returns:
        DataFrame ordenado de mayor a menor puntaje
    """
    # Combinar todos los nombres de estudiantes
    all_students = set(anki_data.keys()) | set(notion_data.keys())
    
    data = []
    for student in all_students:
        anki_info = anki_data.get(student, {})
        anki_reviews = anki_info.get('review_count', 0) if isinstance(anki_info, dict) else 0
        anki_due = anki_info.get('due_count', 0) if isinstance(anki_info, dict) else 0
        notion_score = notion_data.get(student, 0)
        
        # Calcular puntaje total
        anki_points = anki_reviews * ANKI_MULTIPLIER
        notion_points = notion_score * NOTION_MULTIPLIER
        total_score = anki_points + notion_points
        
        data.append({
            'Estudiante': student,
            'Tarjetas Anki': anki_reviews,
            'Pendientes': anki_due,
            'Puntos Anki': round(anki_points, 1),
            'Quices Notion': notion_score,
            'Puntos Notion': round(notion_points, 1),
            'Score Total': round(total_score, 1)
        })
    
    df = pd.DataFrame(data)
    
    if not df.empty:
        df = df.sort_values('Score Total', ascending=False).reset_index(drop=True)
        df.index = df.index + 1  # Rankings empiezan en 1
        df.index.name = 'Rank'
    
    return df


# ============================================================================
# INTERFAZ DE STREAMLIT
# ============================================================================

def setup_page_config():
    """Configura la página de Streamlit."""
    st.set_page_config(
        page_title="🏆 Leaderboard - Grupo de Estudio",
        page_icon="🏆",
        layout="wide",
        initial_sidebar_state="expanded"
    )


def apply_custom_css():
    """Aplica estilos CSS personalizados para un diseño moderno."""
    st.markdown("""
    <style>
        /* Tema oscuro y limpio */
        .stApp {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        }
        
        /* Contenedor principal */
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        
        /* Título principal */
        .main-title {
            text-align: center;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 3rem;
            font-weight: 800;
            margin-bottom: 0.5rem;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .subtitle {
            text-align: center;
            color: #a0a0a0;
            font-size: 1.1rem;
            margin-bottom: 2rem;
        }
        
        /* Cards de métricas */
        .metric-container {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 15px;
            padding: 1.5rem;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
            backdrop-filter: blur(10px);
            transition: transform 0.3s ease;
        }
        
        .metric-container:hover {
            transform: translateY(-5px);
        }
        
        /* Tabla de leaderboard */
        .dataframe {
            background: rgba(255, 255, 255, 0.05) !important;
            border-radius: 10px;
            overflow: hidden;
        }
        
        /* Medallas para el podio */
        .gold { color: #FFD700; }
        .silver { color: #C0C0C0; }
        .bronze { color: #CD7F32; }
        
        /* Botón de actualizar */
        .stButton > button {
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            color: white;
            border: none;
            border-radius: 25px;
            padding: 0.75rem 2rem;
            font-weight: 600;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0, 210, 255, 0.3);
        }
        
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0, 210, 255, 0.5);
        }
        
        /* Sidebar */
        .css-1d391kg {
            background: rgba(26, 26, 46, 0.95);
        }
        
        /* Footer */
        .footer {
            text-align: center;
            color: #666;
            padding: 2rem;
            font-size: 0.9rem;
        }
        
        /* Responsive */
        @media (max-width: 768px) {
            .main-title {
                font-size: 2rem;
            }
            .metric-container {
                padding: 1rem;
            }
        }
    </style>
    """, unsafe_allow_html=True)


def render_header():
    """Renderiza el encabezado de la aplicación."""
    st.markdown('<h1 class="main-title">🏆 Leaderboard de Estudio</h1>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Grupo de Medicina • Seguimiento de Anki + Quices</p>', unsafe_allow_html=True)


def render_podium(df: pd.DataFrame):
    """Renderiza el podio con los Top 3."""
    if df.empty or len(df) < 1:
        return
    
    st.markdown("### 🥇 Podio de Honor")
    
    cols = st.columns(3)
    
    medals = ['🥇', '🥈', '🥉']
    colors = ['#FFD700', '#C0C0C0', '#CD7F32']
    
    # Orden: 2do, 1ro, 3ro para efecto visual
    display_order = [1, 0, 2] if len(df) >= 3 else range(len(df))
    
    for i, idx in enumerate(display_order):
        if idx >= len(df):
            continue
            
        with cols[i]:
            row = df.iloc[idx]
            col_order = 1 if idx == 0 else (0 if idx == 1 else 2)
            
            st.markdown(f"""
            <div class="metric-container" style="text-align: center; border-top: 3px solid {colors[idx]};">
                <div style="font-size: 2.5rem;">{medals[idx]}</div>
                <div style="font-size: 1.3rem; font-weight: bold; color: white; margin: 0.5rem 0;">
                    {row['Estudiante']}
                </div>
                <div style="font-size: 2rem; color: {colors[idx]}; font-weight: bold;">
                    {row['Score Total']} pts
                </div>
                <div style="font-size: 0.9rem; color: #888; margin-top: 0.5rem;">
                    📚 {row['Tarjetas Anki']} tarjetas • 📝 {row['Quices Notion']} quices
                </div>
            </div>
            """, unsafe_allow_html=True)


def render_leaderboard_table(df: pd.DataFrame):
    """Renderiza la tabla completa del leaderboard."""
    if df.empty:
        st.info("📊 No hay datos para mostrar. Haz clic en 'Actualizar Datos' para comenzar.")
        return
    
    st.markdown("### 📊 Clasificación Completa")
    
    # Agregar emojis a las posiciones
    df_display = df.copy()
    
    def get_rank_icon(rank):
        icons = {1: '🥇', 2: '🥈', 3: '🥉'}
        return icons.get(rank, f'{rank}°')
    
    df_display['Pos'] = [get_rank_icon(i+1) for i in range(len(df_display))]
    
    # Reordenar columnas
    cols_order = ['Pos', 'Estudiante', 'Score Total', 'Tarjetas Anki', 'Puntos Anki', 'Quices Notion', 'Puntos Notion', 'Pendientes']
    df_display = df_display[[c for c in cols_order if c in df_display.columns]]
    
    # Mostrar tabla con estilo
    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            'Pos': st.column_config.TextColumn('🏆', width=60),
            'Estudiante': st.column_config.TextColumn('Estudiante', width=150),
            'Score Total': st.column_config.NumberColumn('Score Total', format="%.1f ⭐"),
            'Tarjetas Anki': st.column_config.NumberColumn('📚 Anki', help='Tarjetas repasadas hoy'),
            'Puntos Anki': st.column_config.NumberColumn('Pts Anki', format="%.1f"),
            'Quices Notion': st.column_config.NumberColumn('📝 Quices', help='Puntaje total en quices'),
            'Puntos Notion': st.column_config.NumberColumn('Pts Notion', format="%.1f"),
            'Pendientes': st.column_config.NumberColumn('⏳ Due', help='Tarjetas pendientes')
        }
    )


def render_stats_summary(df: pd.DataFrame):
    """Renderiza un resumen de estadísticas del grupo."""
    if df.empty:
        return
    
    st.markdown("### 📈 Estadísticas del Grupo")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "👥 Estudiantes",
            len(df),
            help="Total de participantes"
        )
    
    with col2:
        avg_score = df['Score Total'].mean()
        st.metric(
            "📊 Promedio",
            f"{avg_score:.1f} pts",
            help="Puntaje promedio del grupo"
        )
    
    with col3:
        total_cards = df['Tarjetas Anki'].sum()
        st.metric(
            "📚 Total Tarjetas",
            f"{total_cards:,}",
            help="Tarjetas repasadas por todo el grupo"
        )
    
    with col4:
        total_pending = df['Pendientes'].sum()
        st.metric(
            "⏳ Pendientes",
            f"{total_pending:,}",
            help="Total de tarjetas pendientes"
        )


def render_sidebar():
    """Renderiza la barra lateral con configuración."""
    with st.sidebar:
        st.markdown("## ⚙️ Configuración")
        
        st.markdown("---")
        
        st.markdown("### 📐 Fórmula de Puntaje")
        st.code(f"Score = (Anki × {ANKI_MULTIPLIER}) + (Notion × {NOTION_MULTIPLIER})")
        
        st.markdown("---")
        
        st.markdown("### ℹ️ Información")
        st.markdown("""
        **Fuentes de datos:**
        - 📚 **AnkiWeb**: Tarjetas repasadas hoy
        - 📝 **Notion**: Puntajes de quices
        
        **Actualización:**
        Presiona el botón "Actualizar" en la página principal para obtener datos frescos.
        """)
        
        st.markdown("---")
        
        # Mostrar última actualización
        if 'last_update' in st.session_state:
            st.caption(f"🕐 Última actualización: {st.session_state.last_update}")
        
        st.markdown("---")
        st.caption("Desarrollado con ❤️ para el grupo de estudio")


def get_students_from_secrets() -> list:
    """
    Obtiene la lista de estudiantes desde los secretos de Streamlit.
    
    Returns:
        Lista de diccionarios con credenciales de estudiantes
    """
    students = []
    
    try:
        # Método 1: Lista estructurada en secrets
        if "students" in st.secrets:
            return list(st.secrets["students"])
        
        # Método 2: Leer estudiantes individuales (student_1, student_2, etc.)
        i = 1
        while True:
            key = f"student_{i}"
            if key in st.secrets:
                student_data = st.secrets[key]
                students.append({
                    'name': student_data.get('name', f'Estudiante {i}'),
                    'username': student_data.get('username', ''),
                    'password': student_data.get('password', '')
                })
                i += 1
            else:
                break
    except FileNotFoundError:
        # No hay archivo secrets.toml - esto es normal en modo demo
        pass
    except Exception:
        # Cualquier otro error, continuar sin secretos
        pass
    
    return students


def main():
    """Función principal de la aplicación."""
    setup_page_config()
    apply_custom_css()
    
    # Inicializar estado de sesión
    if 'leaderboard_data' not in st.session_state:
        st.session_state.leaderboard_data = pd.DataFrame()
    
    # Renderizar componentes
    render_header()
    render_sidebar()
    
    # Contenedor principal
    main_container = st.container()
    
    with main_container:
        # Botón de actualizar datos
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🔄 Actualizar Datos", use_container_width=True, type="primary"):
                with st.spinner("⏳ Recopilando datos de Anki y Notion..."):
                    try:
                        # Obtener lista de estudiantes desde secrets
                        students = get_students_from_secrets()
                        
                        if not students:
                            st.warning("⚠️ No hay estudiantes configurados en los secretos")
                            # Usar datos de demostración
                            st.info("Mostrando datos de demostración...")
                            anki_data = {
                                'María García': {'review_count': 150, 'due_count': 45},
                                'Carlos Rodríguez': {'review_count': 120, 'due_count': 30},
                                'Ana Martínez': {'review_count': 200, 'due_count': 20},
                                'Luis Hernández': {'review_count': 80, 'due_count': 60},
                                'Sofia López': {'review_count': 175, 'due_count': 25},
                            }
                            notion_data = {
                                'María García': 85,
                                'Carlos Rodríguez': 78,
                                'Ana Martínez': 92,
                                'Luis Hernández': 70,
                                'Sofia López': 88,
                            }
                        else:
                            # Obtener datos reales
                            anki_data = fetch_anki_stats_for_students(students)
                            notion_data = fetch_notion_scores()
                        
                        # Calcular puntajes
                        df = calculate_total_scores(anki_data, notion_data)
                        
                        # Guardar en estado
                        st.session_state.leaderboard_data = df
                        st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        st.success("✅ Datos actualizados correctamente")
                        
                    except Exception as e:
                        st.error(f"❌ Error al actualizar datos: {str(e)}")
        
        st.markdown("---")
        
        # Mostrar datos si existen
        df = st.session_state.leaderboard_data
        
        if not df.empty:
            render_podium(df)
            st.markdown("---")
            render_stats_summary(df)
            st.markdown("---")
            render_leaderboard_table(df)
        else:
            st.markdown("""
            <div style="text-align: center; padding: 3rem; color: #888;">
                <div style="font-size: 4rem; margin-bottom: 1rem;">📊</div>
                <h3>No hay datos cargados</h3>
                <p>Presiona el botón "Actualizar Datos" para comenzar</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Footer
        st.markdown("---")
        st.markdown("""
        <div class="footer">
            <p>📚 Fórmula: <code>(Tarjetas Anki × 0.5) + (Puntos Quices × 10) = Score Total</code></p>
            <p>Hecho con Streamlit • Datos de AnkiWeb & Notion</p>
        </div>
        """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
