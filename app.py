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

# Palabras clave para identificar mazos en AnkiWeb (mapeo curso -> palabras clave)
# 
# IMPORTANTE: Usa nombres EXACTOS de mazos para evitar falsos positivos
# - Prefijo "=" indica coincidencia EXACTA (ej: "=Fisiopatología Uribe")
# - Sin prefijo indica que el mazo debe CONTENER la palabra clave
#
# Esto permite encontrar mazos independientemente de su jerarquía (::)
CURSO_DECK_KEYWORDS = {
    # Para Fisiopatología: SOLO el mazo específico "Fisiopatología Uribe"
    "Fisiopatología": ["=Fisiopatología Uribe", "=fisiopatologia uribe"],
    
    # Para Epidemiología: SOLO mazos que se llamen exactamente "Epidemiología"
    "Epidemiología": ["=Epidemiología", "=epidemiologia"],
    
    # Para Farmacología: SOLO mazos que se llamen exactamente "Farmacología" o "Farmacología médica"
    "Farmacología": ["=Farmacología", "=Farmacología médica", "=farmacologia", "=farmacologia medica"],
    
    # Para Patología: SOLO mazos que se llamen exactamente "Patología" o "Patología general"
    "Patología": ["=Patología", "=Patología general", "=Patología clínica", "=patologia"],
}

# Multiplicadores para el cálculo de score (Fórmula Médica)
# Score = (Review * 1.0) + (Learning * 0.5) + (New * 0)
# Las tarjetas NUEVAS no dan puntos - solo las que ya has estudiado
REVIEW_MULTIPLIER = 1.0    # Tarjetas de repaso (verdes) - Peso completo
LEARNING_MULTIPLIER = 0.5  # Tarjetas en aprendizaje (rojas) - Peso medio
NEW_MULTIPLIER = 0.0       # Tarjetas nuevas (azules) - NO dan puntos

# Multiplicador para Notion (quices)
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
    Verifica si el nombre de un mazo corresponde a un curso.
    
    Modos de coincidencia:
    - "=Nombre Exacto": El mazo debe coincidir EXACTAMENTE con el nombre
    - "palabra clave": El mazo debe CONTENER la palabra clave
    
    Ejemplos:
    - "=Fisiopatología Uribe" coincide SOLO con "Fisiopatología Uribe"
    - "patología" coincidiría con "Patología", "Fisiopatología", etc. (NO recomendado)
    
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
            # Coincidencia por contenido (comportamiento anterior)
            keyword_normalized = normalize_text(keyword)
            if keyword_normalized in deck_normalized:
                return True
    
    return False


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
    """
    Cliente para extraer estadísticas de AnkiWeb por mazo.
    
    Implementa:
    - Login con manejo de CSRF
    - Extracción de mazos desde /decks/ con clase 'row light-bottom-border'
    - Selección de mazo con POST para obtener desglose
    - Extracción de contadores Review/Learning/New desde /study
    """
    
    BASE_URL = "https://ankiweb.net"
    LOGIN_URL = f"{BASE_URL}/account/login"
    DECKS_URL = f"{BASE_URL}/decks/"
    STUDY_URL = f"https://ankiuser.net/study"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })
        self.logged_in = False
        self.csrf_token = ''
    
    def _build_login_payload(self, email: str, password: str) -> bytes:
        """
        Construye el payload binario Protobuf para el login de AnkiWeb.
        
        AnkiWeb usa formato Protobuf:
        - Campo 1 (tag 0x0A): Email
        - Campo 2 (tag 0x12): Password
        
        Args:
            email: Correo electrónico del usuario
            password: Contraseña del usuario
            
        Returns:
            Bytes del payload Protobuf
        """
        payload = bytearray()
        
        # Campo 1: Email
        email_bytes = email.encode('utf-8')
        payload.append(0x0A)  # Tag para campo 1 (string)
        payload.append(len(email_bytes))
        payload.extend(email_bytes)
        
        # Campo 2: Password
        password_bytes = password.encode('utf-8')
        payload.append(0x12)  # Tag para campo 2 (string)
        payload.append(len(password_bytes))
        payload.extend(password_bytes)
        
        return bytes(payload)
    
    def login(self, username: str, password: str) -> Tuple[bool, str]:
        """
        Realiza el login en AnkiWeb usando el nuevo API Protobuf.
        
        AnkiWeb migró a SvelteKit y ahora usa:
        - Endpoint: /svc/account/login
        - Content-Type: application/octet-stream
        - Formato: Protobuf binario
        
        Args:
            username: Email del usuario
            password: Contraseña
            
        Returns:
            Tuple (éxito: bool, mensaje: str)
        """
        try:
            # Primero visitar la página de login para obtener cookies de sesión
            resp = self.session.get(self.LOGIN_URL, timeout=15)
            resp.raise_for_status()
            
            # Construir payload binario Protobuf
            payload = self._build_login_payload(username, password)
            
            # Nuevo endpoint de login
            login_url = f"{self.BASE_URL}/svc/account/login"
            
            # Headers requeridos para el nuevo API
            headers = {
                'Content-Type': 'application/octet-stream',
                'Referer': 'https://ankiweb.net/account/login',
                'Origin': 'https://ankiweb.net',
            }
            
            resp = self.session.post(login_url, data=payload, headers=headers, timeout=15)
            
            # Verificar respuesta
            if resp.status_code == 200:
                self.logged_in = True
                return True, "OK"
            elif resp.status_code == 401 or resp.status_code == 403:
                return False, "Credenciales inválidas"
            else:
                return False, f"HTTP {resp.status_code}"
            
        except requests.Timeout:
            return False, "Timeout"
        except requests.RequestException as e:
            return False, str(e)
    
    def get_decks_list(self, debug: bool = False) -> List[Dict]:
        """
        Obtiene la lista de mazos desde /decks/.
        
        Busca filas con clase 'row light-bottom-border' según la estructura real de AnkiWeb.
        Solo extrae mazos principales (sin indentación) para evitar duplicar submazos.
        
        Args:
            debug: Si True, imprime información de debug
            
        Returns:
            Lista de diccionarios con {name, deck_id} de cada mazo principal
        """
        if not self.logged_in:
            return []
        
        decks = []
        
        try:
            resp = self.session.get(self.DECKS_URL, timeout=15)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Buscar filas con la clase específica de AnkiWeb
            rows = soup.find_all('div', class_=re.compile(r'row.*light-bottom-border', re.I))
            
            if not rows:
                # Fallback: buscar en tabla tradicional
                rows = soup.find_all('tr', class_=re.compile(r'row', re.I))
            
            if not rows:
                # Segundo fallback: buscar cualquier elemento con clase row
                rows = soup.select('.row.light-bottom-border')
            
            if debug:
                print(f"[DEBUG] Encontradas {len(rows)} filas de mazos")
            
            for row in rows:
                # Buscar el enlace del mazo
                link = row.find('a', href=True)
                if not link:
                    continue
                
                name = link.get_text(strip=True)
                href = link.get('href', '')
                
                # Extraer deck_id del href (formato: /decks/DECK_ID/ o similar)
                deck_id = None
                if '/decks/' in href:
                    parts = href.split('/decks/')
                    if len(parts) > 1:
                        deck_id = parts[1].strip('/')
                
                # Detectar si es un submazo (tiene indentación o padding)
                # Los submazos suelen tener clase adicional o estar indentados
                is_submaze = False
                style = row.get('style', '')
                classes = ' '.join(row.get('class', []))
                
                # Verificar indentación por padding-left o clase de submazo
                if 'padding-left' in style or 'indent' in classes.lower() or 'sub' in classes.lower():
                    is_submaze = True
                
                # También verificar si el nombre tiene "::" (indica submazo en la jerarquía)
                # Solo tomamos la parte final si queremos el nombre corto
                # PERO: queremos el mazo principal que contiene la suma
                
                if name and not is_submaze:
                    deck_data = {
                        'name': name,
                        'deck_id': deck_id,
                        'href': href
                    }
                    decks.append(deck_data)
                    
                    if debug:
                        print(f"[DEBUG] Mazo encontrado: '{name}' (ID: {deck_id})")
                elif debug and is_submaze:
                    print(f"[DEBUG] Submazo ignorado: '{name}'")
                    
        except Exception as e:
            if debug:
                print(f"[DEBUG] Error al obtener lista de mazos: {e}")
        
        return decks
    
    def select_deck_and_get_study_counts(self, deck_name: str, debug: bool = False) -> Dict[str, int]:
        """
        Selecciona un mazo y obtiene los contadores de la página de estudio.
        
        AnkiWeb muestra en /study:
        - Review (verde): Tarjetas de repaso programadas
        - Learning (rojo): Tarjetas en proceso de aprendizaje
        - New (azul): Tarjetas nuevas sin ver
        
        Args:
            deck_name: Nombre del mazo a seleccionar
            debug: Si True, imprime información de debug
            
        Returns:
            Dict con {'review': int, 'learning': int, 'new': int}
        """
        result = {'review': 0, 'learning': 0, 'new': 0}
        
        if not self.logged_in:
            return result
        
        try:
            # Primero, obtener la lista de mazos para encontrar el deck_id
            decks = self.get_decks_list(debug=False)
            
            target_deck = None
            for deck in decks:
                if deck['name'].strip().lower() == deck_name.strip().lower():
                    target_deck = deck
                    break
            
            if not target_deck:
                if debug:
                    print(f"[DEBUG] Mazo '{deck_name}' no encontrado en la lista")
                return result
            
            if debug:
                print(f"[DEBUG] Seleccionando mazo: '{deck_name}'")
            
            # Navegar a la página del mazo o hacer POST para seleccionarlo
            # AnkiWeb usa /study con el deck seleccionado
            if target_deck.get('href'):
                # Ir directamente al mazo
                deck_url = f"{self.BASE_URL}{target_deck['href']}"
                resp = self.session.get(deck_url, timeout=15)
                resp.raise_for_status()
                
                # Ahora ir a /study
                resp = self.session.get(self.STUDY_URL, timeout=15)
                resp.raise_for_status()
            else:
                # Ir directamente a study
                resp = self.session.get(self.STUDY_URL, timeout=15)
                resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Buscar los contadores en la página de estudio
            # AnkiWeb muestra los números en spans o divs con clases específicas
            
            # Método 1: Buscar por texto/clase que contenga los números
            # Los contadores suelen estar en formato "Review: X" o similar
            
            # Buscar spans con números
            count_elements = soup.find_all(['span', 'div'], class_=re.compile(r'count|num|badge', re.I))
            
            # Método 2: Buscar el texto directamente en la página
            page_text = soup.get_text()
            
            # Patrones comunes en AnkiWeb
            # Buscar "X review" o "review: X"
            review_match = re.search(r'(\d+)\s*(?:review|repas)', page_text, re.I)
            if review_match:
                result['review'] = int(review_match.group(1))
            
            learning_match = re.search(r'(\d+)\s*(?:learning|apren|lrn)', page_text, re.I)
            if learning_match:
                result['learning'] = int(learning_match.group(1))
            
            new_match = re.search(r'(\d+)\s*(?:new|nuev)', page_text, re.I)
            if new_match:
                result['new'] = int(new_match.group(1))
            
            # Método 3: Buscar en la estructura específica de AnkiWeb
            # Los contadores suelen estar en un grupo de 3 números
            all_numbers = re.findall(r'\b(\d+)\b', page_text)
            
            # Si no encontramos con los patrones anteriores, 
            # intentar extraer de la página del mazo directamente
            if result['review'] == 0 and result['learning'] == 0 and result['new'] == 0:
                # Buscar en divs con clase que contenga 'count' o 'stat'
                stat_divs = soup.find_all(['div', 'span', 'td'], 
                    class_=re.compile(r'due|new|learn|review|count|stat', re.I))
                
                for div in stat_divs:
                    text = div.get_text(strip=True)
                    classes = ' '.join(div.get('class', [])).lower()
                    
                    nums = re.findall(r'\d+', text)
                    if nums:
                        num = int(nums[0])
                        if 'review' in classes or 'due' in classes:
                            result['review'] = num
                        elif 'learn' in classes or 'lrn' in classes:
                            result['learning'] = num
                        elif 'new' in classes:
                            result['new'] = num
            
            if debug:
                print(f"[DEBUG] Contadores para '{deck_name}': Review={result['review']}, Learning={result['learning']}, New={result['new']}")
                
        except Exception as e:
            if debug:
                print(f"[DEBUG] Error al obtener contadores de estudio: {e}")
        
        return result
    
    def get_deck_stats_from_decks_page(self, deck_name: str, debug: bool = False) -> Dict[str, int]:
        """
        Obtiene estadísticas de un mazo directamente desde la página /decks/.
        
        Esta es una alternativa más simple que extrae Due y New de la tabla principal.
        
        Args:
            deck_name: Nombre exacto del mazo
            debug: Si True, imprime información de debug
            
        Returns:
            Dict con {'review': int, 'learning': int, 'new': int}
        """
        result = {'review': 0, 'learning': 0, 'new': 0}
        
        if not self.logged_in:
            return result
        
        try:
            resp = self.session.get(self.DECKS_URL, timeout=15)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Buscar todas las filas de mazos
            # Intentar múltiples selectores
            rows = soup.find_all('div', class_=re.compile(r'row.*light-bottom-border', re.I))
            
            if not rows:
                # Fallback a tabla
                table = soup.find('table')
                if table:
                    rows = table.find_all('tr')
            
            if not rows:
                # Intentar con selectores más genéricos
                rows = soup.select('[class*="deck"]')
            
            for row in rows:
                # Buscar el nombre del mazo
                link = row.find('a')
                if not link:
                    # Intentar buscar texto directo
                    name_elem = row.find(class_=re.compile(r'name|title|deck', re.I))
                    if name_elem:
                        row_name = name_elem.get_text(strip=True)
                    else:
                        continue
                else:
                    row_name = link.get_text(strip=True)
                
                # Comparar nombres (case-insensitive)
                if row_name.strip().lower() != deck_name.strip().lower():
                    continue
                
                if debug:
                    print(f"[DEBUG] Encontrado mazo '{row_name}' en la tabla")
                
                # Buscar los números en esta fila
                # Pueden estar en spans, divs, o tds
                numbers = []
                
                # Buscar elementos con números
                num_elements = row.find_all(['span', 'div', 'td'], 
                    class_=re.compile(r'count|num|due|new|learn|badge', re.I))
                
                for elem in num_elements:
                    text = elem.get_text(strip=True)
                    nums = re.findall(r'\d+', text)
                    if nums:
                        numbers.append(int(nums[0]))
                
                # Si no encontramos con clases, buscar todos los números en la fila
                if not numbers:
                    row_text = row.get_text()
                    numbers = [int(n) for n in re.findall(r'\b(\d+)\b', row_text)]
                
                # Asignar números según posición típica: [Due/Review, New] o [Review, Learning, New]
                if len(numbers) >= 3:
                    result['review'] = numbers[0]
                    result['learning'] = numbers[1]
                    result['new'] = numbers[2]
                elif len(numbers) >= 2:
                    result['review'] = numbers[0]  # Due = Review
                    result['new'] = numbers[1]
                elif len(numbers) >= 1:
                    result['review'] = numbers[0]
                
                if debug:
                    print(f"[DEBUG] Estadísticas extraídas: {result}")
                
                break  # Encontramos el mazo, salir del loop
                
        except Exception as e:
            if debug:
                print(f"[DEBUG] Error al obtener stats desde /decks/: {e}")
        
        return result
    
    def get_decks_via_api(self) -> Tuple[List[Dict], List[str]]:
        """
        Obtiene mazos desde el API de AnkiWeb.
        
        Endpoint: POST /svc/decks/deck-list-info
        Formato: Protobuf binario
        
        Returns:
            Tuple (lista de mazos, mensajes de debug)
        """
        debug_msgs = []
        
        if not self.logged_in:
            return [], ["No se ha iniciado sesión"]
        
        try:
            url = f"{self.BASE_URL}/svc/decks/deck-list-info"
            headers = {
                'Content-Type': 'application/octet-stream',
                'Accept': '*/*',
            }
            
            # Request POST con body vacío
            resp = self.session.post(url, data=b'', headers=headers, timeout=15)
            debug_msgs.append(f"📡 API Response: {resp.status_code}, {len(resp.content)} bytes")
            
            # DEBUG: Mostrar bytes hexadecimales de los primeros 200 bytes
            hex_preview = resp.content[:200].hex()
            debug_msgs.append(f"🔢 Hex (primeros 200): {hex_preview[:100]}...")
            
            # DEBUG: Buscar "Fisiopatología Uribe" en los datos
            search_term = "Fisiopatología Uribe"
            try:
                pos = resp.content.find(search_term.encode('utf-8'))
                if pos >= 0:
                    # Mostrar 50 bytes antes y 50 después del nombre
                    start = max(0, pos - 20)
                    end = min(len(resp.content), pos + len(search_term) + 50)
                    context = resp.content[start:end]
                    debug_msgs.append(f"🎯 '{search_term}' encontrado en pos {pos}")
                    debug_msgs.append(f"📋 Contexto hex: {context.hex()}")
                    debug_msgs.append(f"📋 Contexto txt: {context.decode('utf-8', errors='replace')}")
                else:
                    debug_msgs.append(f"❌ '{search_term}' NO encontrado en bytes")
            except Exception as e:
                debug_msgs.append(f"❌ Error buscando: {e}")
            
            if resp.status_code == 200 and resp.content:
                decks = self._parse_protobuf_decks(resp.content, debug_msgs)
                debug_msgs.append(f"📊 Mazos parseados: {len(decks)}")
                return decks, debug_msgs
            else:
                debug_msgs.append(f"❌ Error API: HTTP {resp.status_code}")
                
        except Exception as e:
            debug_msgs.append(f"💥 Error API: {str(e)}")
        
        return [], debug_msgs
    
    def _parse_protobuf_decks(self, data: bytes, debug_msgs: List[str]) -> List[Dict]:
        """
        Parsea la respuesta Protobuf de deck-list-info de AnkiWeb.
        
        Estructura del mensaje Protobuf (deducida del análisis hex):
        - Cada mazo es un submensaje que empieza con tag 0x1a (campo 3)
        - Campo 1 (0x08): ID del mazo (varint)
        - Campo 2 (0x12): Nombre del mazo (string)
        - Campo 3 (0x1a): Submazos (submensaje repetido)
        - Campos 4-9 (0x20-0x48): Contadores numéricos
          - Campo 8 (0x40): new cards (tarjetas nuevas)
          - Campo 7 (0x38): learn cards (en aprendizaje)
          - Campo 4-6: review/due cards
        
        Args:
            data: Bytes de respuesta Protobuf
            
        Returns:
            Lista de diccionarios {name, due, new, learning}
        """
        decks = []
        
        def read_varint(data: bytes, pos: int) -> Tuple[int, int]:
            """Lee un varint y retorna (valor, nueva_posición)."""
            value = 0
            shift = 0
            while pos < len(data):
                byte = data[pos]
                value |= (byte & 0x7F) << shift
                pos += 1
                if not (byte & 0x80):
                    break
                shift += 7
            return value, pos
        
        def parse_deck_message(data: bytes, start: int, end: int, all_decks: List[Dict]) -> Dict:
            """Parsea un submensaje de mazo y extrae nombre, contadores, y submazos recursivamente."""
            result = {'name': '', 'due': 0, 'new': 0, 'learning': 0}
            pos = start
            
            while pos < end:
                if pos >= len(data):
                    break
                    
                tag_byte = data[pos]
                field_num = tag_byte >> 3
                wire_type = tag_byte & 0x07
                pos += 1
                
                if wire_type == 0:  # Varint
                    value, pos = read_varint(data, pos)
                    # Mapeo de campos a contadores (basado en análisis hex)
                    # Campo 7 (0x38): learning count
                    # Campo 8 (0x40): new count
                    # Campo 9 (0x48): due/review count
                    if field_num == 7:  # learn_count
                        result['learning'] = value
                    elif field_num == 8:  # new_count
                        result['new'] = value
                    elif field_num == 9:  # due/review count
                        result['due'] = value
                        
                elif wire_type == 2:  # Length-delimited (string o submensaje)
                    length, pos = read_varint(data, pos)
                    if pos + length > end:
                        break
                    
                    if field_num == 2:  # Nombre del mazo
                        try:
                            result['name'] = data[pos:pos+length].decode('utf-8')
                        except:
                            pass
                    elif field_num == 3:  # Submazo - PARSEAR RECURSIVAMENTE
                        child = parse_deck_message(data, pos, pos + length, all_decks)
                        if child['name'] and len(child['name']) >= 2:
                            # Filtrar nombres que parecen código
                            name = child['name']
                            if (not name.startswith('/') and
                                not name.startswith('_app') and
                                not 'svelte' in name.lower() and
                                not '.js' in name.lower() and
                                sum(1 for c in name if c.isalpha()) >= 2):
                                all_decks.append(child)
                    pos += length
                else:
                    # Otros wire types, avanzar
                    pos += 1
            
            return result
        
        try:
            debug_msgs.append(f"🔍 Parseando {len(data)} bytes (recursivo)")
            
            # Lista para acumular todos los mazos (incluyendo submazos)
            all_decks = []
            
            # El mensaje raíz tiene estructura diferente, buscar los mazos de nivel superior
            pos = 0
            while pos < len(data) - 2:
                if data[pos] == 0x1a:  # Campo 3, submensaje
                    pos += 1
                    length, pos = read_varint(data, pos)
                    
                    if length > 0 and length < 10000 and pos + length <= len(data):
                        # Parsear este mazo y sus hijos recursivamente
                        deck = parse_deck_message(data, pos, pos + length, all_decks)
                        
                        if deck['name'] and len(deck['name']) >= 2:
                            name = deck['name']
                            if (not name.startswith('/') and
                                not name.startswith('_app') and
                                not 'svelte' in name.lower() and
                                not '.js' in name.lower() and
                                sum(1 for c in name if c.isalpha()) >= 2):
                                all_decks.append(deck)
                        
                        pos += length
                    else:
                        pos += 1
                else:
                    pos += 1
            
            debug_msgs.append(f"✅ Mazos parseados: {len(all_decks)}")
            
            # Mostrar primeros mazos para debug
            for deck in all_decks[:5]:
                debug_msgs.append(f"  📚 {deck['name'][:35]}: due={deck['due']}, new={deck['new']}, learn={deck['learning']}")
            
            return all_decks
            
        except Exception as e:
            debug_msgs.append(f"💥 Error: {str(e)}")
            import traceback
            debug_msgs.append(traceback.format_exc()[:200])
            return []
    
    def get_stats_by_course(self, cursos: List[str]) -> Dict[str, Dict[str, int]]:
        """
        Obtiene estadísticas por curso usando el API de AnkiWeb.
        
        Estrategia:
        1. Primero intenta obtener mazos via API (endpoint Protobuf)
        2. Si falla, intenta scraping de página como fallback
        
        Args:
            cursos: Lista de cursos a buscar
            
        Returns:
            Dict con estadísticas por curso
        """
        stats = {c: {'review': 0, 'learning': 0, 'new': 0} for c in cursos}
        stats['_total'] = {'review': 0, 'learning': 0, 'new': 0}
        stats['_notas_internas'] = []
        stats['_mazos_encontrados'] = []
        
        if not self.logged_in:
            stats['_notas_internas'].append("No se ha iniciado sesión")
            return stats
        
        # === MÉTODO 1: API Protobuf (preferido) ===
        stats['_notas_internas'].append("� Intentando API Protobuf...")
        decks, api_debug = self.get_decks_via_api()
        
        # Agregar mensajes de debug del API
        for msg in api_debug:
            stats['_notas_internas'].append(msg)
        
        if decks:
            stats['_notas_internas'].append(f"✅ API exitosa: {len(decks)} mazos obtenidos")
            
            # Procesar mazos obtenidos del API
            for deck in decks:
                deck_name = deck.get('name', '')
                due = deck.get('due', 0)
                new = deck.get('new', 0)
                learning = deck.get('learning', 0)
                
                # Verificar si coincide con algún curso
                for curso in cursos:
                    if match_course_in_deck(deck_name, curso):
                        stats['_notas_internas'].append(f"✓ Mazo '{deck_name}' → {curso}")
                        stats['_mazos_encontrados'].append({
                            'mazo': deck_name,
                            'curso': curso,
                            'stats': {'review': due, 'learning': learning, 'new': new}
                        })
                        
                        # Sumar al curso
                        stats[curso]['review'] += due
                        stats[curso]['learning'] += learning
                        stats[curso]['new'] += new
                        
                        # Sumar al total SOLO si coincide con un curso
                        stats['_total']['review'] += due
                        stats['_total']['learning'] += learning
                        stats['_total']['new'] += new
                        break
        else:
            stats['_notas_internas'].append("⚠️ API no devolvió datos, intentando scraping...")
            
            # === MÉTODO 2: Scraping como fallback ===
            try:
                resp = self.session.get(self.DECKS_URL, timeout=15)
                resp.raise_for_status()
                stats['_notas_internas'].append(f"📄 Scraping: {len(resp.text)} chars HTML")
                
                # Si el HTML es muy corto, es la página SPA sin datos
                if len(resp.text) < 3000:
                    stats['_notas_internas'].append("⚠️ Página SPA detectada (HTML corto)")
                    
            except Exception as e:
                stats['_notas_internas'].append(f"❌ Error scraping: {str(e)}")
        
        # Registrar cursos sin mazos encontrados
        for curso in cursos:
            if stats[curso]['review'] == 0 and stats[curso]['learning'] == 0 and stats[curso]['new'] == 0:
                keywords = CURSO_DECK_KEYWORDS.get(curso, [])
                if keywords:
                    stats['_notas_internas'].append(
                        f"Sin datos para '{curso}' (buscando: {', '.join(keywords[:2])})"
                    )
        
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
    """
    Obtiene estadísticas de Anki para todos los estudiantes.
    
    Estructura de retorno por estudiante:
    {curso: {'review': int, 'learning': int, 'new': int}}
    """
    results = {}
    debug_info = []  # Para mostrar info de debug
    
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
        
        # Estructura por defecto con review, learning, new
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
                
                # Obtener stats
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
                    f"📊 Total: Review={total.get('review', 0)}, Learning={total.get('learning', 0)}, New={total.get('new', 0)}"
                )
            else:
                student_debug["pasos"].append(f"❌ Login fallido: {msg}")
                results[name] = default_stats
                
        except Exception as e:
            student_debug["pasos"].append(f"💥 Error: {str(e)}")
            import traceback
            student_debug["pasos"].append(f"📋 Traceback: {traceback.format_exc()[:500]}")
            results[name] = default_stats
        finally:
            scraper.logout()
            time.sleep(0.5)  # Reducido para más velocidad
        
        debug_info.append(student_debug)
        progress.progress((i + 1) / len(students))
    
    status.empty()
    progress.empty()
    
    # Mostrar información de debug en un expander
    with st.expander("🔍 Ver Detalles de Conexión AnkiWeb", expanded=True):
        for student_info in debug_info:
            st.markdown(f"**{student_info['nombre']}**")
            for paso in student_info["pasos"]:
                st.text(paso)
            st.markdown("---")
        
        # Mostrar HTML preview si está disponible
        if results:
            first_student = list(results.keys())[0] if results else None
            if first_student and '_html_preview' in results.get(first_student, {}):
                html_preview = results[first_student].get('_html_preview', '')
                if html_preview:
                    st.markdown("**📄 Vista previa HTML recibido (primeros 1000 chars):**")
                    st.code(html_preview[:1000], language="html")
    
    return results


# ============================================================================
# CÁLCULO DE PUNTAJES
# ============================================================================

def calculate_scores(anki: Dict, notion: Dict, cursos: List[str]) -> Dict[str, pd.DataFrame]:
    """
    Calcula scores por curso y general usando la Fórmula Médica.
    
    Fórmula:
    Score Anki = (Review * 0.8) + (Learning * 0.5) + (New * 0.2)
    Score Total = Score Anki + (Quices * 10)
    """
    all_students = set(anki.keys()) | set(notion.keys())
    results = {}
    
    # Por curso
    for curso in cursos:
        data = []
        for student in all_students:
            a = anki.get(student, {}).get(curso, {'review': 0, 'learning': 0, 'new': 0})
            
            # Extraer contadores
            review = a.get('review', 0)
            learning = a.get('learning', 0)
            new = a.get('new', 0)
            
            # Fórmula Médica para Anki
            anki_pts = (review * REVIEW_MULTIPLIER) + (learning * LEARNING_MULTIPLIER) + (new * NEW_MULTIPLIER)
            
            # Puntaje de Notion (quices)
            n = notion.get(student, {}).get(curso, 0)
            notion_pts = n * NOTION_MULTIPLIER
            
            total = anki_pts + notion_pts
            
            data.append({
                'Estudiante': student,
                'Review': review,
                'Learning': learning,
                'New': new,
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
        a_total = anki.get(student, {}).get('_total', {'review': 0, 'learning': 0, 'new': 0})
        
        # Extraer contadores totales
        review = a_total.get('review', 0)
        learning = a_total.get('learning', 0)
        new = a_total.get('new', 0)
        
        # Fórmula Médica para Anki
        anki_pts = (review * REVIEW_MULTIPLIER) + (learning * LEARNING_MULTIPLIER) + (new * NEW_MULTIPLIER)
        
        # Puntaje de Notion (quices)
        n_total = notion.get(student, {}).get('_total', 0)
        notion_pts = n_total * NOTION_MULTIPLIER
        
        total = anki_pts + notion_pts
        
        data.append({
            'Estudiante': student,
            'Review': review,
            'Learning': learning,
            'New': new,
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
    """
    Genera datos demo con la estructura review, learning, new.
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
    """Barra lateral con configuración y fórmula."""
    with st.sidebar:
        st.markdown("## ⚙️ Config")
        st.markdown("### 📚 Cursos")
        for c in CURSOS:
            st.markdown(f"• {c}")
        st.markdown("---")
        st.markdown("### 📐 Fórmula Médica")
        st.code(f"Review×{REVIEW_MULTIPLIER} + Learning×{LEARNING_MULTIPLIER} + New×{NEW_MULTIPLIER} + Quiz×{NOTION_MULTIPLIER}")
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
    st.caption(f"📐 Fórmula Médica: (Review×{REVIEW_MULTIPLIER}) + (Learning×{LEARNING_MULTIPLIER}) + (New×{NEW_MULTIPLIER}) + (Quiz×{NOTION_MULTIPLIER}) | v4.0 - Extracción Avanzada")


if __name__ == "__main__":
    main()
