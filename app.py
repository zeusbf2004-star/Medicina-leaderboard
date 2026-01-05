"""
Dashboard de Competencia Académica Multi-Curso
==============================================
Aplicación Streamlit para grupos de estudio de medicina.
Integra datos de AnkiWeb (por mazo/curso) y Notion (quices por curso).

Autor: Lead Python Developer - Data Engineering
"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from notion_client import Client
from datetime import datetime
import re
import time
from typing import Dict, List, Optional, Tuple

# ============================================================================
# CONFIGURACIÓN Y CONSTANTES
# ============================================================================

# Lista de cursos disponibles - MODIFICAR SEGÚN NECESIDAD
CURSOS = ["Fisiopatología", "Epidemiología", "Farmacología", "Patología"]

# Palabras clave para buscar mazos en AnkiWeb (mapeo curso -> keywords)
CURSO_KEYWORDS = {
    "Fisiopatología": ["fisiopatologia", "fisiopatol", "fisiopatolog", "fisiopatolgia"],
    "Epidemiología": ["epidemio", "epi", "bioestadística", "bioestad"],
    "Farmacología": ["farma", "farmaco", "farmacología"],
    "Patología": ["pato", "patología", "patologia"],
}

# Multiplicadores para el cálculo de score
ANKI_MULTIPLIER = 0.5
NOTION_MULTIPLIER = 10

# ID de la Base de Datos de Notion (se lee de secrets si está disponible)
DEFAULT_NOTION_DATABASE_ID = "TU_DATABASE_ID_AQUI"


# ============================================================================
# FUNCIONES DE UTILIDAD
# ============================================================================

def safe_get_secret(key: str, default: str = "") -> str:
    """Obtiene un secreto de forma segura, retornando default si no existe."""
    try:
        return st.secrets.get(key, default)
    except FileNotFoundError:
        return default
    except Exception:
        return default


def normalize_text(text: str) -> str:
    """Normaliza texto para comparación (lowercase, sin acentos comunes)."""
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
    Verifica si el nombre de un mazo corresponde a un curso específico.
    
    Args:
        deck_name: Nombre del mazo de Anki
        curso: Nombre del curso a buscar
        
    Returns:
        True si el mazo corresponde al curso
    """
    deck_normalized = normalize_text(deck_name)
    
    # Obtener keywords del curso
    keywords = CURSO_KEYWORDS.get(curso, [normalize_text(curso)])
    
    # Verificar si alguna keyword está en el nombre del mazo
    return any(kw in deck_normalized for kw in keywords)


# ============================================================================
# CLASE PARA SCRAPING DE ANKIWEB - VERSIÓN MEJORADA
# ============================================================================

class AnkiWebScraper:
    """
    Cliente mejorado para extraer estadísticas de AnkiWeb por mazo.
    Soporta extracción granular de mazos específicos por curso.
    """
    
    BASE_URL = "https://ankiweb.net"
    LOGIN_URL = f"{BASE_URL}/account/login"
    DECKS_URL = f"{BASE_URL}/decks/"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        })
        self.logged_in = False
    
    def _get_csrf_token(self, html_content: str) -> str:
        """Extrae el token CSRF del formulario de login."""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Buscar en input hidden
        csrf_input = soup.find('input', {'name': 'csrf_token'})
        if csrf_input and csrf_input.get('value'):
            return csrf_input.get('value', '')
        
        # Buscar en meta tags
        csrf_meta = soup.find('meta', {'name': 'csrf-token'})
        if csrf_meta and csrf_meta.get('content'):
            return csrf_meta.get('content', '')
        
        return ''
    
    def login(self, username: str, password: str) -> Tuple[bool, str]:
        """
        Realiza el login en AnkiWeb.
        
        Returns:
            Tuple (éxito: bool, mensaje: str)
        """
        try:
            # Obtener página de login para CSRF token
            response = self.session.get(self.LOGIN_URL, timeout=15)
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
                allow_redirects=True,
                timeout=15
            )
            
            # Verificar si el login fue exitoso
            if 'logout' in response.text.lower() or '/decks' in response.url:
                self.logged_in = True
                return True, "Login exitoso"
            
            # Verificar errores específicos
            if 'invalid' in response.text.lower() or 'incorrect' in response.text.lower():
                return False, "Credenciales inválidas"
            
            return False, "Login fallido por razón desconocida"
            
        except requests.Timeout:
            return False, "Timeout al conectar con AnkiWeb"
        except requests.RequestException as e:
            return False, f"Error de conexión: {str(e)}"
    
    def get_decks_data(self) -> Tuple[List[Dict], str]:
        """
        Obtiene datos de todos los mazos desde la tabla de AnkiWeb.
        
        Returns:
            Tuple (lista de mazos, mensaje de error si hay)
        """
        decks = []
        
        if not self.logged_in:
            return decks, "No hay sesión activa"
        
        try:
            response = self.session.get(self.DECKS_URL, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Buscar la tabla de mazos
            deck_table = soup.find('table', {'id': 'decks'})
            
            if not deck_table:
                # Buscar cualquier tabla con clase que contenga 'deck'
                deck_table = soup.find('table', class_=re.compile(r'deck', re.I))
            
            if deck_table:
                rows = deck_table.find_all('tr')
                
                for row in rows:
                    cols = row.find_all('td')
                    
                    if len(cols) >= 2:
                        # Estructura típica: Nombre | Due | New (o similar)
                        deck_name_elem = cols[0]
                        
                        # Obtener nombre del mazo (puede estar en un enlace)
                        link = deck_name_elem.find('a')
                        deck_name = link.get_text(strip=True) if link else deck_name_elem.get_text(strip=True)
                        
                        # Extraer números de las columnas restantes
                        due_count = 0
                        new_count = 0
                        review_count = 0
                        
                        for i, col in enumerate(cols[1:], start=1):
                            text = col.get_text(strip=True)
                            # Extraer solo números
                            numbers = re.findall(r'\d+', text)
                            if numbers:
                                num = int(numbers[0])
                                if i == 1:
                                    due_count = num
                                elif i == 2:
                                    new_count = num
                                elif i == 3:
                                    review_count = num
                        
                        if deck_name:
                            decks.append({
                                'name': deck_name,
                                'due': due_count,
                                'new': new_count,
                                'reviews': review_count
                            })
            
            # Método alternativo: buscar en scripts JSON
            if not decks:
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string and 'decks' in script.string.lower():
                        # Intentar extraer datos JSON
                        try:
                            import json
                            matches = re.findall(r'\{[^{}]*"name"[^{}]*\}', script.string)
                            for match in matches:
                                data = json.loads(match)
                                if 'name' in data:
                                    decks.append({
                                        'name': data.get('name', ''),
                                        'due': data.get('due', 0),
                                        'new': data.get('new', 0),
                                        'reviews': data.get('reviews', 0)
                                    })
                        except:
                            continue
            
            return decks, ""
            
        except requests.Timeout:
            return [], "Timeout al obtener mazos"
        except requests.RequestException as e:
            return [], f"Error de conexión: {str(e)}"
    
    def get_stats_by_course(self, cursos: List[str]) -> Dict[str, Dict[str, int]]:
        """
        Obtiene estadísticas agrupadas por curso.
        
        Args:
            cursos: Lista de nombres de cursos
            
        Returns:
            Dict {curso: {'due': int, 'reviews': int, 'new': int}}
        """
        stats = {curso: {'due': 0, 'reviews': 0, 'new': 0} for curso in cursos}
        stats['_total'] = {'due': 0, 'reviews': 0, 'new': 0}
        
        decks, error = self.get_decks_data()
        
        if error:
            return stats
        
        for deck in decks:
            deck_name = deck['name']
            
            # Sumar al total
            stats['_total']['due'] += deck['due']
            stats['_total']['reviews'] += deck['reviews']
            stats['_total']['new'] += deck['new']
            
            # Clasificar por curso
            for curso in cursos:
                if match_course_in_deck(deck_name, curso):
                    stats[curso]['due'] += deck['due']
                    stats[curso]['reviews'] += deck['reviews']
                    stats[curso]['new'] += deck['new']
                    break  # Un mazo solo pertenece a un curso
        
        return stats
    
    def logout(self):
        """Cierra la sesión actual."""
        if self.logged_in:
            try:
                self.session.get(f"{self.BASE_URL}/account/logout", timeout=5)
            except:
                pass
        self.session = requests.Session()
        self.logged_in = False


def fetch_anki_stats_all_students(students_list: List[Dict], cursos: List[str]) -> Dict[str, Dict]:
    """
    Obtiene estadísticas de AnkiWeb para todos los estudiantes por curso.
    
    Args:
        students_list: Lista de diccionarios con credenciales
        cursos: Lista de cursos para agrupar
        
    Returns:
        Dict {nombre_estudiante: {curso: {'due': int, 'reviews': int}}}
    """
    results = {}
    
    if not students_list:
        return results
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, student in enumerate(students_list):
        name = student.get('name', f'Estudiante {i+1}')
        username = student.get('username', '')
        password = student.get('password', '')
        
        status_text.text(f"📚 Conectando con AnkiWeb: {name}...")
        
        if not username or not password:
            # Inicializar con ceros
            results[name] = {curso: {'due': 0, 'reviews': 0, 'new': 0} for curso in cursos}
            results[name]['_total'] = {'due': 0, 'reviews': 0, 'new': 0}
            results[name]['_error'] = 'Credenciales faltantes'
            continue
        
        scraper = AnkiWebScraper()
        
        try:
            success, message = scraper.login(username, password)
            
            if success:
                stats = scraper.get_stats_by_course(cursos)
                results[name] = stats
                results[name]['_error'] = None
            else:
                results[name] = {curso: {'due': 0, 'reviews': 0, 'new': 0} for curso in cursos}
                results[name]['_total'] = {'due': 0, 'reviews': 0, 'new': 0}
                results[name]['_error'] = message
                
        except Exception as e:
            results[name] = {curso: {'due': 0, 'reviews': 0, 'new': 0} for curso in cursos}
            results[name]['_total'] = {'due': 0, 'reviews': 0, 'new': 0}
            results[name]['_error'] = str(e)
        finally:
            scraper.logout()
            time.sleep(1)  # Rate limiting
        
        progress_bar.progress((i + 1) / len(students_list))
    
    status_text.empty()
    progress_bar.empty()
    
    return results


# ============================================================================
# INTEGRACIÓN CON NOTION - VERSIÓN CORREGIDA
# ============================================================================

def get_notion_client() -> Optional[Client]:
    """
    Crea un cliente de Notion usando el token de los secretos.
    
    Returns:
        Cliente de Notion autenticado o None si hay error
    """
    notion_token = safe_get_secret("NOTION_TOKEN", "")
    
    if not notion_token:
        return None
    
    try:
        return Client(auth=notion_token)
    except Exception as e:
        st.error(f"❌ Error al crear cliente de Notion: {str(e)}")
        return None


def fetch_notion_scores_by_course(cursos: List[str]) -> Dict[str, Dict[str, float]]:
    """
    Obtiene y suma los puntajes de exámenes desde Notion, filtrados por curso.
    
    Args:
        cursos: Lista de cursos para filtrar
        
    Returns:
        Dict {nombre_estudiante: {curso: puntaje}}
    """
    scores = {}
    
    notion = get_notion_client()
    if not notion:
        st.warning("⚠️ Token de Notion no configurado. Los puntajes de quices mostrarán 0.")
        return scores
    
    db_id = safe_get_secret("NOTION_DATABASE_ID", DEFAULT_NOTION_DATABASE_ID)
    
    if db_id == DEFAULT_NOTION_DATABASE_ID:
        st.warning("⚠️ ID de base de datos de Notion no configurado.")
        return scores
    
    try:
        # Consultar la base de datos usando el método correcto
        has_more = True
        start_cursor = None
        
        while has_more:
            # Usar el método correcto de la API de Notion
            if start_cursor:
                response = notion.databases.query(
                    database_id=db_id,
                    start_cursor=start_cursor
                )
            else:
                response = notion.databases.query(database_id=db_id)
            
            for page in response.get('results', []):
                properties = page.get('properties', {})
                
                # Buscar el nombre del estudiante
                student_name = None
                for prop_name in ['Nombre', 'Estudiante', 'Name', 'Student', 'Alumno', 'Participante']:
                    if prop_name in properties:
                        prop = properties[prop_name]
                        prop_type = prop.get('type', '')
                        
                        if prop_type == 'title':
                            title_content = prop.get('title', [])
                            if title_content:
                                student_name = title_content[0].get('text', {}).get('content', '')
                        elif prop_type == 'rich_text':
                            text_content = prop.get('rich_text', [])
                            if text_content:
                                student_name = text_content[0].get('text', {}).get('content', '')
                        elif prop_type == 'people':
                            people = prop.get('people', [])
                            if people:
                                student_name = people[0].get('name', '')
                        
                        if student_name:
                            break
                
                if not student_name:
                    continue
                
                # Inicializar estudiante si no existe
                if student_name not in scores:
                    scores[student_name] = {curso: 0.0 for curso in cursos}
                    scores[student_name]['_total'] = 0.0
                
                # Buscar el curso
                curso_encontrado = None
                for prop_name in ['Curso', 'Course', 'Materia', 'Subject', 'Asignatura']:
                    if prop_name in properties:
                        prop = properties[prop_name]
                        prop_type = prop.get('type', '')
                        
                        if prop_type == 'select':
                            select_data = prop.get('select', {})
                            if select_data:
                                curso_encontrado = select_data.get('name', '')
                        elif prop_type == 'rich_text':
                            text_content = prop.get('rich_text', [])
                            if text_content:
                                curso_encontrado = text_content[0].get('text', {}).get('content', '')
                        elif prop_type == 'title':
                            title_content = prop.get('title', [])
                            if title_content:
                                curso_encontrado = title_content[0].get('text', {}).get('content', '')
                        
                        if curso_encontrado:
                            break
                
                # Buscar el puntaje
                score = 0.0
                for prop_name in ['Puntaje', 'Score', 'Puntos', 'Points', 'Calificacion', 'Nota', 'Resultado']:
                    if prop_name in properties:
                        prop = properties[prop_name]
                        prop_type = prop.get('type', '')
                        
                        if prop_type == 'number':
                            score = prop.get('number', 0) or 0
                        elif prop_type == 'formula':
                            formula_result = prop.get('formula', {})
                            if formula_result.get('type') == 'number':
                                score = formula_result.get('number', 0) or 0
                        elif prop_type == 'rollup':
                            rollup_result = prop.get('rollup', {})
                            if rollup_result.get('type') == 'number':
                                score = rollup_result.get('number', 0) or 0
                        
                        if score:
                            break
                
                # Sumar al curso correspondiente
                if curso_encontrado:
                    # Buscar match con cursos configurados
                    for curso in cursos:
                        if normalize_text(curso) in normalize_text(curso_encontrado) or \
                           normalize_text(curso_encontrado) in normalize_text(curso):
                            scores[student_name][curso] += score
                            break
                
                # Siempre sumar al total
                scores[student_name]['_total'] += score
            
            has_more = response.get('has_more', False)
            start_cursor = response.get('next_cursor')
    
    except AttributeError as e:
        st.error(f"❌ Error de API de Notion: {str(e)}. Verifica la versión de notion-client.")
    except Exception as e:
        error_msg = str(e)
        if 'unauthorized' in error_msg.lower():
            st.error("❌ Token de Notion inválido o sin permisos para esta base de datos.")
        elif 'not_found' in error_msg.lower():
            st.error("❌ Base de datos de Notion no encontrada. Verifica el ID.")
        else:
            st.error(f"❌ Error al consultar Notion: {error_msg}")
    
    return scores


# ============================================================================
# CÁLCULO DE PUNTAJES POR CURSO
# ============================================================================

def calculate_scores_by_course(
    anki_data: Dict[str, Dict],
    notion_data: Dict[str, Dict[str, float]],
    cursos: List[str]
) -> Dict[str, pd.DataFrame]:
    """
    Calcula el puntaje total por curso para todos los estudiantes.
    
    Fórmula por curso: (Tarjetas Mazo Curso * 0.5) + (Puntos Quices Curso * 10)
    
    Returns:
        Dict {nombre_curso: DataFrame ordenado}
    """
    # Combinar todos los nombres de estudiantes
    all_students = set(anki_data.keys()) | set(notion_data.keys())
    
    results = {}
    
    # DataFrame para cada curso
    for curso in cursos:
        data = []
        
        for student in all_students:
            anki_info = anki_data.get(student, {})
            notion_info = notion_data.get(student, {})
            
            # Obtener stats del curso específico (con fallback seguro)
            curso_anki = anki_info.get(curso, {'due': 0, 'reviews': 0, 'new': 0})
            anki_reviews = curso_anki.get('reviews', 0) + curso_anki.get('due', 0)
            
            notion_score = notion_info.get(curso, 0) if isinstance(notion_info, dict) else 0
            
            # Calcular puntuación
            anki_points = anki_reviews * ANKI_MULTIPLIER
            notion_points = notion_score * NOTION_MULTIPLIER
            total_score = anki_points + notion_points
            
            data.append({
                'Estudiante': student,
                'Tarjetas': anki_reviews,
                'Pts Anki': round(anki_points, 1),
                'Quices': notion_score,
                'Pts Notion': round(notion_points, 1),
                'Score': round(total_score, 1)
            })
        
        df = pd.DataFrame(data)
        if not df.empty:
            df = df.sort_values('Score', ascending=False).reset_index(drop=True)
            df.index = df.index + 1
        results[curso] = df
    
    # DataFrame para ranking general
    general_data = []
    for student in all_students:
        anki_info = anki_data.get(student, {})
        notion_info = notion_data.get(student, {})
        
        # Total de Anki
        total_anki = anki_info.get('_total', {})
        anki_reviews = total_anki.get('reviews', 0) + total_anki.get('due', 0) if isinstance(total_anki, dict) else 0
        
        # Total de Notion
        notion_score = notion_info.get('_total', 0) if isinstance(notion_info, dict) else 0
        
        # Calcular puntuación
        anki_points = anki_reviews * ANKI_MULTIPLIER
        notion_points = notion_score * NOTION_MULTIPLIER
        total_score = anki_points + notion_points
        
        general_data.append({
            'Estudiante': student,
            'Tarjetas Total': anki_reviews,
            'Pts Anki': round(anki_points, 1),
            'Quices Total': notion_score,
            'Pts Notion': round(notion_points, 1),
            'Score Total': round(total_score, 1)
        })
    
    df_general = pd.DataFrame(general_data)
    if not df_general.empty:
        df_general = df_general.sort_values('Score Total', ascending=False).reset_index(drop=True)
        df_general.index = df_general.index + 1
    results['_general'] = df_general
    
    return results


# ============================================================================
# INTERFAZ DE STREAMLIT
# ============================================================================

def setup_page_config():
    """Configura la página de Streamlit."""
    st.set_page_config(
        page_title="🏆 Dashboard Multi-Curso",
        page_icon="🏆",
        layout="wide",
        initial_sidebar_state="expanded"
    )


def apply_custom_css():
    """Aplica estilos CSS personalizados."""
    st.markdown("""
    <style>
        .stApp {
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 100%);
        }
        
        .main-title {
            text-align: center;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5, #00d2ff);
            background-size: 200% auto;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.8rem;
            font-weight: 800;
            margin-bottom: 0.5rem;
            animation: gradient 3s linear infinite;
        }
        
        @keyframes gradient {
            0% { background-position: 0% center; }
            100% { background-position: 200% center; }
        }
        
        .subtitle {
            text-align: center;
            color: #a0a0a0;
            font-size: 1.1rem;
            margin-bottom: 1.5rem;
        }
        
        .metric-card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 15px;
            padding: 1.2rem;
            border: 1px solid rgba(255, 255, 255, 0.1);
            text-align: center;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        
        .metric-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0, 210, 255, 0.2);
        }
        
        .podium-card {
            background: rgba(255, 255, 255, 0.03);
            border-radius: 20px;
            padding: 1.5rem;
            text-align: center;
            border: 2px solid transparent;
            transition: all 0.3s ease;
        }
        
        .gold { border-color: #FFD700; box-shadow: 0 0 20px rgba(255, 215, 0, 0.3); }
        .silver { border-color: #C0C0C0; box-shadow: 0 0 15px rgba(192, 192, 192, 0.3); }
        .bronze { border-color: #CD7F32; box-shadow: 0 0 10px rgba(205, 127, 50, 0.3); }
        
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
        
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 10px;
            padding: 5px;
        }
        
        .stTabs [data-baseweb="tab"] {
            border-radius: 8px;
            color: #888;
            font-weight: 500;
        }
        
        .stTabs [aria-selected="true"] {
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            color: white !important;
        }
        
        @media (max-width: 768px) {
            .main-title { font-size: 1.8rem; }
            .metric-card { padding: 0.8rem; }
        }
    </style>
    """, unsafe_allow_html=True)


def render_header():
    """Renderiza el encabezado."""
    st.markdown('<h1 class="main-title">🏆 Dashboard de Competencia</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="subtitle">Grupo de Medicina • {len(CURSOS)} Cursos Activos</p>', unsafe_allow_html=True)


def render_podium(df: pd.DataFrame, curso: str = "General"):
    """Renderiza el podio con los Top 3."""
    if df.empty or len(df) < 1:
        st.info("No hay datos para mostrar el podio.")
        return
    
    score_col = 'Score Total' if 'Score Total' in df.columns else 'Score'
    
    st.markdown(f"### 🏆 Top 3 - {curso}")
    
    cols = st.columns(3)
    medals = ['🥇', '🥈', '🥉']
    colors = ['#FFD700', '#C0C0C0', '#CD7F32']
    css_classes = ['gold', 'silver', 'bronze']
    
    display_order = [1, 0, 2] if len(df) >= 3 else list(range(min(3, len(df))))
    
    for col_idx, pos_idx in enumerate(display_order):
        if pos_idx >= len(df):
            continue
            
        with cols[col_idx]:
            row = df.iloc[pos_idx]
            score = row[score_col]
            
            st.markdown(f"""
            <div class="podium-card {css_classes[pos_idx]}">
                <div style="font-size: 2.5rem;">{medals[pos_idx]}</div>
                <div style="font-size: 1.2rem; font-weight: bold; color: white; margin: 0.5rem 0;">
                    {row['Estudiante']}
                </div>
                <div style="font-size: 1.8rem; color: {colors[pos_idx]}; font-weight: bold;">
                    {score} pts
                </div>
            </div>
            """, unsafe_allow_html=True)


def render_leaderboard_table(df: pd.DataFrame):
    """Renderiza la tabla del leaderboard."""
    if df.empty:
        st.info("📊 No hay datos para mostrar.")
        return
    
    st.markdown("### 📊 Clasificación Completa")
    
    df_display = df.copy()
    
    def get_rank_icon(rank):
        icons = {1: '🥇', 2: '🥈', 3: '🥉'}
        return icons.get(rank, f'{rank}°')
    
    df_display.insert(0, 'Pos', [get_rank_icon(i+1) for i in range(len(df_display))])
    
    st.dataframe(df_display, use_container_width=True, hide_index=True)


def render_stats_summary(df: pd.DataFrame, curso: str = "General"):
    """Renderiza estadísticas resumidas."""
    if df.empty:
        return
    
    score_col = 'Score Total' if 'Score Total' in df.columns else 'Score'
    tarjetas_col = 'Tarjetas Total' if 'Tarjetas Total' in df.columns else 'Tarjetas'
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("👥 Participantes", len(df))
    
    with col2:
        avg = df[score_col].mean()
        st.metric("📊 Promedio", f"{avg:.1f} pts")
    
    with col3:
        total = df[tarjetas_col].sum() if tarjetas_col in df.columns else 0
        st.metric("📚 Tarjetas", f"{total:,}")
    
    with col4:
        max_score = df[score_col].max()
        st.metric("🏆 Máximo", f"{max_score:.1f} pts")


def render_sidebar():
    """Renderiza la barra lateral."""
    with st.sidebar:
        st.markdown("## ⚙️ Configuración")
        
        st.markdown("---")
        
        st.markdown("### 📚 Cursos Activos")
        for curso in CURSOS:
            st.markdown(f"• {curso}")
        
        st.markdown("---")
        
        st.markdown("### 📐 Fórmula")
        st.code(f"Score = (Anki × {ANKI_MULTIPLIER}) + (Quiz × {NOTION_MULTIPLIER})")
        
        st.markdown("---")
        
        if 'last_update' in st.session_state:
            st.caption(f"🕐 Última actualización: {st.session_state.last_update}")
        
        st.markdown("---")
        st.caption("Dashboard Multi-Curso v2.0")


def get_students_from_secrets() -> List[Dict]:
    """Obtiene la lista de estudiantes desde los secretos."""
    students = []
    
    try:
        if "students" in st.secrets:
            return list(st.secrets["students"])
        
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
        pass
    except Exception:
        pass
    
    return students


def load_demo_data(cursos: List[str]) -> Tuple[Dict, Dict]:
    """Genera datos de demostración."""
    demo_students = ['Ana Martínez', 'Carlos López', 'María García', 'Luis Hernández', 'Sofia Rodríguez']
    
    import random
    random.seed(42)
    
    anki_data = {}
    notion_data = {}
    
    for student in demo_students:
        anki_data[student] = {
            '_total': {'due': random.randint(20, 80), 'reviews': random.randint(50, 200), 'new': random.randint(5, 30)}
        }
        notion_data[student] = {'_total': random.randint(60, 100)}
        
        for curso in cursos:
            anki_data[student][curso] = {
                'due': random.randint(5, 30),
                'reviews': random.randint(20, 80),
                'new': random.randint(2, 15)
            }
            notion_data[student][curso] = random.randint(0, 20)
    
    return anki_data, notion_data


def main():
    """Función principal de la aplicación."""
    setup_page_config()
    apply_custom_css()
    
    # Inicializar estado
    if 'scores_by_course' not in st.session_state:
        st.session_state.scores_by_course = {}
    
    render_header()
    render_sidebar()
    
    # Botón de actualizar
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🔄 Actualizar Datos", use_container_width=True, type="primary"):
            with st.spinner("⏳ Obteniendo datos..."):
                try:
                    students = get_students_from_secrets()
                    
                    if not students:
                        st.warning("⚠️ No hay estudiantes configurados. Mostrando datos demo...")
                        anki_data, notion_data = load_demo_data(CURSOS)
                    else:
                        anki_data = fetch_anki_stats_all_students(students, CURSOS)
                        notion_data = fetch_notion_scores_by_course(CURSOS)
                    
                    scores = calculate_scores_by_course(anki_data, notion_data, CURSOS)
                    st.session_state.scores_by_course = scores
                    st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    st.success("✅ Datos actualizados correctamente")
                    
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
    
    st.markdown("---")
    
    # Pestañas
    scores = st.session_state.scores_by_course
    
    if scores:
        tab_names = ["🏆 Ranking General"] + [f"📚 {curso}" for curso in CURSOS]
        tabs = st.tabs(tab_names)
        
        # Tab General
        with tabs[0]:
            df_general = scores.get('_general', pd.DataFrame())
            render_podium(df_general, "General")
            st.markdown("---")
            render_stats_summary(df_general, "General")
            st.markdown("---")
            render_leaderboard_table(df_general)
        
        # Tabs por curso
        for i, curso in enumerate(CURSOS):
            with tabs[i + 1]:
                df_curso = scores.get(curso, pd.DataFrame())
                render_podium(df_curso, curso)
                st.markdown("---")
                render_stats_summary(df_curso, curso)
                st.markdown("---")
                render_leaderboard_table(df_curso)
    else:
        st.markdown("""
        <div style="text-align: center; padding: 3rem; color: #888;">
            <div style="font-size: 4rem; margin-bottom: 1rem;">📊</div>
            <h3>No hay datos cargados</h3>
            <p>Presiona "Actualizar Datos" para comenzar</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Footer
    st.markdown("---")
    st.markdown(f"""
    <div style="text-align: center; color: #666; padding: 1rem;">
        <p>📐 <code>Score = (Tarjetas × {ANKI_MULTIPLIER}) + (Quices × {NOTION_MULTIPLIER})</code></p>
        <p>Dashboard Multi-Curso • AnkiWeb + Notion</p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
