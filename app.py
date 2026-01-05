"""
Dashboard de Competencia Académica Multi-Curso
==============================================
Aplicación Streamlit para grupos de estudio de medicina.
Integra datos de AnkiWeb (por mazo/curso) y Notion (API directa con requests).

Autor: Expert Python Developer & Cloud Architect
Versión: 3.0 - Sin dependencia de notion-client
"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import re
import time
from typing import Dict, List, Optional, Tuple

# ============================================================================
# CONFIGURACIÓN Y CONSTANTES
# ============================================================================

# Lista de cursos disponibles
CURSOS = ["Fisiopatología", "Epidemiología", "Farmacología", "Patología"]

# Nombres EXACTOS de los mazos oficiales en AnkiWeb (mapeo curso -> nombre exacto del mazo)
# Cada estudiante DEBE tener el mazo con este nombre exacto para que se contabilice
CURSO_DECKS_EXACTOS = {
    "Fisiopatología": "Estudio universitario::V ciclo::Fisiopatología",
    "Epidemiología": "Estudio universitario::V ciclo::Epidemiología",
    "Farmacología": "Estudio universitario::V ciclo::Farmacología",
    "Patología": "Estudio universitario::V ciclo::Patología",
}

# Multiplicadores para el cálculo de score
ANKI_MULTIPLIER = 0.5
NOTION_MULTIPLIER = 10

# Notion API Version
NOTION_API_VERSION = "2022-06-28"
NOTION_API_BASE_URL = "https://api.notion.com/v1"


# ============================================================================
# FUNCIONES DE UTILIDAD
# ============================================================================

def normalize_text(text: str) -> str:
    """Normaliza texto para comparación (lowercase, sin acentos)."""
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
    Verifica si el nombre de un mazo coincide EXACTAMENTE con el mazo oficial del curso.
    
    La comparación es case-insensitive (ignora mayúsculas/minúsculas).
    
    Args:
        deck_name: Nombre del mazo encontrado en AnkiWeb
        curso: Nombre del curso a verificar
    
    Returns:
        True si hay coincidencia exacta, False en caso contrario
    """
    nombre_mazo_oficial = CURSO_DECKS_EXACTOS.get(curso)
    
    if not nombre_mazo_oficial:
        return False
    
    # Comparación exacta ignorando mayúsculas/minúsculas
    return deck_name.strip().lower() == nombre_mazo_oficial.lower()


def get_secrets() -> Tuple[Optional[str], Optional[str]]:
    """
    Obtiene los secretos de Notion de forma segura.
    
    Returns:
        Tuple (notion_token, database_id) o (None, None) si no están configurados
    """
    notion_token = None
    database_id = None
    
    try:
        notion_token = st.secrets.get("NOTION_TOKEN")
        database_id = st.secrets.get("NOTION_DATABASE_ID")
    except FileNotFoundError:
        pass
    except Exception:
        pass
    
    return notion_token, database_id


# ============================================================================
# CONEXIÓN A NOTION - API DIRECTA CON REQUESTS
# ============================================================================

class NotionAPI:
    """
    Cliente de Notion usando requests directos (sin notion-client).
    A prueba de conflictos de dependencias en Streamlit Cloud.
    """
    
    def __init__(self, token: str, database_id: str):
        self.token = token
        self.database_id = database_id
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_API_VERSION
        }
    
    def query_database(self, start_cursor: Optional[str] = None) -> Tuple[Dict, Optional[str]]:
        """
        Consulta la base de datos de Notion.
        
        Returns:
            Tuple (response_data, error_message)
        """
        url = f"{NOTION_API_BASE_URL}/databases/{self.database_id}/query"
        
        payload = {}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        
        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json(), None
            elif response.status_code == 401:
                return {}, "Token de Notion inválido o expirado"
            elif response.status_code == 404:
                return {}, "Base de datos no encontrada. Verifica el ID y los permisos de la integración"
            elif response.status_code == 400:
                return {}, f"Solicitud inválida: {response.json().get('message', 'Error desconocido')}"
            else:
                return {}, f"Error HTTP {response.status_code}: {response.text[:200]}"
                
        except requests.Timeout:
            return {}, "Timeout al conectar con Notion API"
        except requests.RequestException as e:
            return {}, f"Error de conexión: {str(e)}"
    
    def _extract_text_from_property(self, prop: Dict) -> Optional[str]:
        """Extrae texto de una propiedad de Notion."""
        prop_type = prop.get("type", "")
        
        if prop_type == "title":
            title_arr = prop.get("title", [])
            if title_arr:
                return title_arr[0].get("text", {}).get("content", "")
        
        elif prop_type == "rich_text":
            text_arr = prop.get("rich_text", [])
            if text_arr:
                return text_arr[0].get("text", {}).get("content", "")
        
        elif prop_type == "select":
            select_data = prop.get("select")
            if select_data:
                return select_data.get("name", "")
        
        elif prop_type == "people":
            people_arr = prop.get("people", [])
            if people_arr:
                return people_arr[0].get("name", "")
        
        return None
    
    def _extract_number_from_property(self, prop: Dict) -> float:
        """Extrae número de una propiedad de Notion."""
        prop_type = prop.get("type", "")
        
        if prop_type == "number":
            return prop.get("number", 0) or 0
        
        elif prop_type == "formula":
            formula = prop.get("formula", {})
            if formula.get("type") == "number":
                return formula.get("number", 0) or 0
        
        elif prop_type == "rollup":
            rollup = prop.get("rollup", {})
            if rollup.get("type") == "number":
                return rollup.get("number", 0) or 0
        
        return 0
    
    def fetch_scores_by_course(self, cursos: List[str]) -> Tuple[Dict[str, Dict[str, float]], Optional[str]]:
        """
        Obtiene puntajes agrupados por estudiante y curso.
        
        Returns:
            Tuple ({estudiante: {curso: puntaje}}, error_message)
        """
        scores = {}
        has_more = True
        start_cursor = None
        
        # Nombres de propiedades a buscar
        student_props = ['Nombre', 'Estudiante', 'Name', 'Student', 'Alumno', 'Participante']
        course_props = ['Curso', 'Course', 'Materia', 'Subject', 'Asignatura']
        score_props = ['Puntaje', 'Score', 'Puntos', 'Points', 'Calificacion', 'Nota', 'Resultado']
        
        while has_more:
            data, error = self.query_database(start_cursor)
            
            if error:
                return scores, error
            
            results = data.get("results", [])
            
            for page in results:
                properties = page.get("properties", {})
                
                # Extraer nombre del estudiante
                student_name = None
                for prop_name in student_props:
                    if prop_name in properties:
                        student_name = self._extract_text_from_property(properties[prop_name])
                        if student_name:
                            break
                
                if not student_name:
                    continue
                
                # Inicializar estudiante
                if student_name not in scores:
                    scores[student_name] = {c: 0.0 for c in cursos}
                    scores[student_name]["_total"] = 0.0
                
                # Extraer curso
                curso_encontrado = None
                for prop_name in course_props:
                    if prop_name in properties:
                        curso_encontrado = self._extract_text_from_property(properties[prop_name])
                        if curso_encontrado:
                            break
                
                # Extraer puntaje
                puntaje = 0.0
                for prop_name in score_props:
                    if prop_name in properties:
                        puntaje = self._extract_number_from_property(properties[prop_name])
                        if puntaje:
                            break
                
                # Asignar puntaje al curso correspondiente
                if curso_encontrado:
                    for curso in cursos:
                        if normalize_text(curso) in normalize_text(curso_encontrado) or \
                           normalize_text(curso_encontrado) in normalize_text(curso):
                            scores[student_name][curso] += puntaje
                            break
                
                # Siempre sumar al total
                scores[student_name]["_total"] += puntaje
            
            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")
        
        return scores, None


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


# ============================================================================
# CLASE PARA SCRAPING DE ANKIWEB
# ============================================================================

class AnkiWebScraper:
    """Cliente para extraer estadísticas de AnkiWeb por mazo."""
    
    BASE_URL = "https://ankiweb.net"
    LOGIN_URL = f"{BASE_URL}/account/login"
    DECKS_URL = f"{BASE_URL}/decks/"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        })
        self.logged_in = False
    
    def _get_csrf_token(self, html: str) -> str:
        """Extrae el token CSRF."""
        soup = BeautifulSoup(html, 'html.parser')
        csrf = soup.find('input', {'name': 'csrf_token'})
        if csrf and csrf.get('value'):
            return csrf.get('value', '')
        meta = soup.find('meta', {'name': 'csrf-token'})
        if meta and meta.get('content'):
            return meta.get('content', '')
        return ''
    
    def login(self, username: str, password: str) -> Tuple[bool, str]:
        """Realiza el login en AnkiWeb."""
        try:
            resp = self.session.get(self.LOGIN_URL, timeout=15)
            resp.raise_for_status()
            
            csrf = self._get_csrf_token(resp.text)
            
            data = {
                'csrf_token': csrf,
                'submitted': '1',
                'username': username,
                'password': password,
            }
            
            resp = self.session.post(self.LOGIN_URL, data=data, allow_redirects=True, timeout=15)
            
            if 'logout' in resp.text.lower() or '/decks' in resp.url:
                self.logged_in = True
                return True, "OK"
            
            return False, "Credenciales inválidas"
            
        except requests.Timeout:
            return False, "Timeout"
        except requests.RequestException as e:
            return False, str(e)
    
    def get_decks_data(self) -> List[Dict]:
        """Obtiene datos de la tabla de mazos."""
        if not self.logged_in:
            return []
        
        decks = []
        
        try:
            resp = self.session.get(self.DECKS_URL, timeout=15)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            table = soup.find('table', {'id': 'decks'})
            
            if table:
                for row in table.find_all('tr'):
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        link = cols[0].find('a')
                        name = link.get_text(strip=True) if link else cols[0].get_text(strip=True)
                        
                        due = 0
                        new = 0
                        reviews = 0
                        
                        for i, col in enumerate(cols[1:], 1):
                            nums = re.findall(r'\d+', col.get_text(strip=True))
                            if nums:
                                if i == 1:
                                    due = int(nums[0])
                                elif i == 2:
                                    new = int(nums[0])
                                elif i == 3:
                                    reviews = int(nums[0])
                        
                        if name:
                            decks.append({'name': name, 'due': due, 'new': new, 'reviews': reviews})
        except:
            pass
        
        return decks
    
    def get_stats_by_course(self, cursos: List[str]) -> Dict[str, Dict[str, int]]:
        """
        Agrupa estadísticas por curso basándose en coincidencia EXACTA de nombres de mazos.
        
        Solo se suman tarjetas de mazos que coincidan exactamente con los nombres
        definidos en CURSO_DECKS_EXACTOS. Si un mazo oficial no existe para un
        estudiante, se asigna 0 puntos sin generar error.
        
        Args:
            cursos: Lista de cursos a buscar
            
        Returns:
            Dict con estadísticas por curso y notas internas sobre mazos faltantes
        """
        stats = {c: {'due': 0, 'reviews': 0, 'new': 0} for c in cursos}
        stats['_total'] = {'due': 0, 'reviews': 0, 'new': 0}
        stats['_notas_internas'] = []  # Registro de mazos no encontrados
        
        decks = self.get_decks_data()
        
        # Crear un set de nombres de mazos encontrados (normalizados) para validación
        mazos_encontrados = {deck['name'].strip().lower() for deck in decks}
        
        # Verificar qué mazos oficiales faltan y registrar nota interna
        for curso in cursos:
            nombre_mazo_oficial = CURSO_DECKS_EXACTOS.get(curso, "")
            if nombre_mazo_oficial and nombre_mazo_oficial.lower() not in mazos_encontrados:
                stats['_notas_internas'].append(
                    f"Mazo '{nombre_mazo_oficial}' para {curso} no encontrado"
                )
        
        # Procesar cada mazo encontrado
        for deck in decks:
            # Siempre sumar al total general
            stats['_total']['due'] += deck['due']
            stats['_total']['reviews'] += deck['reviews']
            stats['_total']['new'] += deck['new']
            
            # Solo sumar a un curso si hay coincidencia EXACTA con el mazo oficial
            for curso in cursos:
                if match_course_in_deck(deck['name'], curso):
                    stats[curso]['due'] += deck['due']
                    stats[curso]['reviews'] += deck['reviews']
                    stats[curso]['new'] += deck['new']
                    break  # Un mazo solo puede pertenecer a un curso
        
        return stats
    
    def logout(self):
        """Cierra sesión."""
        if self.logged_in:
            try:
                self.session.get(f"{self.BASE_URL}/account/logout", timeout=5)
            except:
                pass
        self.session = requests.Session()
        self.logged_in = False


def get_students_from_secrets() -> List[Dict]:
    """Obtiene estudiantes desde secrets."""
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
    except:
        pass
    return students


def fetch_anki_stats(students: List[Dict], cursos: List[str]) -> Dict:
    """Obtiene estadísticas de Anki para todos los estudiantes."""
    results = {}
    
    if not students:
        return results
    
    progress = st.progress(0)
    status = st.empty()
    
    for i, student in enumerate(students):
        name = student.get('name', f'Estudiante {i+1}')
        username = student.get('username', '')
        password = student.get('password', '')
        
        status.text(f"📚 Conectando Anki: {name}...")
        
        if not username or not password:
            results[name] = {c: {'due': 0, 'reviews': 0, 'new': 0} for c in cursos}
            results[name]['_total'] = {'due': 0, 'reviews': 0, 'new': 0}
            continue
        
        scraper = AnkiWebScraper()
        
        try:
            ok, _ = scraper.login(username, password)
            if ok:
                results[name] = scraper.get_stats_by_course(cursos)
            else:
                results[name] = {c: {'due': 0, 'reviews': 0, 'new': 0} for c in cursos}
                results[name]['_total'] = {'due': 0, 'reviews': 0, 'new': 0}
        except:
            results[name] = {c: {'due': 0, 'reviews': 0, 'new': 0} for c in cursos}
            results[name]['_total'] = {'due': 0, 'reviews': 0, 'new': 0}
        finally:
            scraper.logout()
            time.sleep(1)
        
        progress.progress((i + 1) / len(students))
    
    status.empty()
    progress.empty()
    
    return results


# ============================================================================
# CÁLCULO DE PUNTAJES
# ============================================================================

def calculate_scores(anki: Dict, notion: Dict, cursos: List[str]) -> Dict[str, pd.DataFrame]:
    """Calcula scores por curso y general."""
    all_students = set(anki.keys()) | set(notion.keys())
    results = {}
    
    # Por curso
    for curso in cursos:
        data = []
        for student in all_students:
            a = anki.get(student, {}).get(curso, {'due': 0, 'reviews': 0})
            anki_cards = a.get('reviews', 0) + a.get('due', 0)
            n = notion.get(student, {}).get(curso, 0)
            
            anki_pts = anki_cards * ANKI_MULTIPLIER
            notion_pts = n * NOTION_MULTIPLIER
            total = anki_pts + notion_pts
            
            data.append({
                'Estudiante': student,
                'Tarjetas': anki_cards,
                'Pts Anki': round(anki_pts, 1),
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
        a_total = anki.get(student, {}).get('_total', {'due': 0, 'reviews': 0})
        anki_cards = a_total.get('reviews', 0) + a_total.get('due', 0)
        n_total = notion.get(student, {}).get('_total', 0)
        
        anki_pts = anki_cards * ANKI_MULTIPLIER
        notion_pts = n_total * NOTION_MULTIPLIER
        total = anki_pts + notion_pts
        
        data.append({
            'Estudiante': student,
            'Tarjetas': anki_cards,
            'Pts Anki': round(anki_pts, 1),
            'Quices': n_total,
            'Pts Notion': round(notion_pts, 1),
            'Score': round(total, 1)
        })
    
    df = pd.DataFrame(data)
    if not df.empty:
        df = df.sort_values('Score', ascending=False).reset_index(drop=True)
        df.index = df.index + 1
    results['_general'] = df
    
    return results


# ============================================================================
# DATOS DE DEMOSTRACIÓN
# ============================================================================

def load_demo_data(cursos: List[str]) -> Tuple[Dict, Dict]:
    """Genera datos demo."""
    import random
    random.seed(42)
    
    names = ['Ana Martínez', 'Carlos López', 'María García', 'Luis Hernández', 'Sofia Rodríguez']
    anki = {}
    notion = {}
    
    for name in names:
        anki[name] = {'_total': {'due': random.randint(20, 80), 'reviews': random.randint(50, 200), 'new': 0}}
        notion[name] = {'_total': random.randint(60, 100)}
        
        for c in cursos:
            anki[name][c] = {'due': random.randint(5, 30), 'reviews': random.randint(20, 80), 'new': 0}
            notion[name][c] = random.randint(0, 20)
    
    return anki, notion


# ============================================================================
# INTERFAZ DE STREAMLIT
# ============================================================================

def setup_page():
    """Configura la página."""
    st.set_page_config(
        page_title="🏆 Dashboard Multi-Curso",
        page_icon="🏆",
        layout="wide"
    )


def apply_css():
    """Estilos CSS."""
    st.markdown("""
    <style>
        .stApp { background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 100%); }
        .main-title {
            text-align: center;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.5rem;
            font-weight: 800;
        }
        .subtitle { text-align: center; color: #888; margin-bottom: 1.5rem; }
        .podium {
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 1rem;
            text-align: center;
        }
        .gold { border: 2px solid #FFD700; }
        .silver { border: 2px solid #C0C0C0; }
        .bronze { border: 2px solid #CD7F32; }
    </style>
    """, unsafe_allow_html=True)


def render_podium(df: pd.DataFrame, title: str):
    """Renderiza el podio Top 3."""
    if df.empty:
        st.info("Sin datos")
        return
    
    st.markdown(f"### 🏆 Top 3 - {title}")
    
    cols = st.columns(3)
    medals = ['🥇', '🥈', '🥉']
    colors = ['#FFD700', '#C0C0C0', '#CD7F32']
    css = ['gold', 'silver', 'bronze']
    order = [1, 0, 2] if len(df) >= 3 else list(range(min(3, len(df))))
    
    for col_idx, pos in enumerate(order):
        if pos >= len(df):
            continue
        with cols[col_idx]:
            row = df.iloc[pos]
            st.markdown(f"""
            <div class="podium {css[pos]}">
                <div style="font-size:2rem;">{medals[pos]}</div>
                <div style="font-weight:bold;color:white;">{row['Estudiante']}</div>
                <div style="font-size:1.5rem;color:{colors[pos]};">{row['Score']} pts</div>
            </div>
            """, unsafe_allow_html=True)


def render_table(df: pd.DataFrame):
    """Renderiza la tabla."""
    if df.empty:
        st.info("No hay datos")
        return
    
    st.markdown("### 📊 Clasificación")
    
    display = df.copy()
    display.insert(0, 'Pos', [f"{i}°" if i > 3 else ['🥇','🥈','🥉'][i-1] for i in range(1, len(display)+1)])
    
    st.dataframe(display, use_container_width=True, hide_index=True)


def render_sidebar():
    """Barra lateral."""
    with st.sidebar:
        st.markdown("## ⚙️ Config")
        st.markdown("### 📚 Cursos")
        for c in CURSOS:
            st.markdown(f"• {c}")
        st.markdown("---")
        st.markdown("### 📐 Fórmula")
        st.code(f"Score = Anki×{ANKI_MULTIPLIER} + Quiz×{NOTION_MULTIPLIER}")
        st.markdown("---")
        if 'last_update' in st.session_state:
            st.caption(f"🕐 {st.session_state.last_update}")


def main():
    """Función principal."""
    setup_page()
    apply_css()
    
    if 'scores' not in st.session_state:
        st.session_state.scores = {}
    
    st.markdown('<h1 class="main-title">🏆 Dashboard de Competencia</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="subtitle">Medicina • {len(CURSOS)} Cursos</p>', unsafe_allow_html=True)
    
    render_sidebar()
    
    # Botón actualizar
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🔄 Actualizar Datos", use_container_width=True, type="primary"):
            with st.spinner("Obteniendo datos..."):
                try:
                    students = get_students_from_secrets()
                    
                    if not students:
                        st.warning("⚠️ Sin estudiantes configurados. Mostrando demo...")
                        anki, notion = load_demo_data(CURSOS)
                    else:
                        anki = fetch_anki_stats(students, CURSOS)
                        notion = fetch_notion_scores(CURSOS)
                    
                    st.session_state.scores = calculate_scores(anki, notion, CURSOS)
                    st.session_state.last_update = datetime.now().strftime("%H:%M:%S")
                    st.success("✅ Datos actualizados")
                except Exception as e:
                    st.error(f"❌ Error: {e}")
    
    st.markdown("---")
    
    # Pestañas
    scores = st.session_state.scores
    
    if scores:
        tabs = st.tabs(["🏆 General"] + [f"📚 {c}" for c in CURSOS])
        
        with tabs[0]:
            df = scores.get('_general', pd.DataFrame())
            render_podium(df, "General")
            st.markdown("---")
            render_table(df)
        
        for i, curso in enumerate(CURSOS):
            with tabs[i + 1]:
                df = scores.get(curso, pd.DataFrame())
                render_podium(df, curso)
                st.markdown("---")
                render_table(df)
    else:
        st.markdown("""
        <div style="text-align:center;padding:3rem;color:#888;">
            <div style="font-size:4rem;">📊</div>
            <h3>Sin datos</h3>
            <p>Presiona "Actualizar Datos"</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Footer
    st.markdown("---")
    st.caption(f"📐 Score = (Tarjetas × {ANKI_MULTIPLIER}) + (Quices × {NOTION_MULTIPLIER}) | v3.0 - API Directa")


if __name__ == "__main__":
    main()
