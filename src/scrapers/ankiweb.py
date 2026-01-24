"""
Scraper para AnkiWeb.

Este módulo contiene la clase AnkiWebScraper que extrae estadísticas
de mazos de Anki desde ankiweb.net usando web scraping y la API Protobuf.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from src.config import (
    ANKIWEB_BASE_URL,
    ANKIWEB_LOGIN_URL,
    ANKIWEB_DECKS_URL,
    ANKIWEB_STUDY_URL,
    REQUEST_TIMEOUT,
    CURSOS,
    match_course_in_deck,
    CURSO_DECK_KEYWORDS,
)

logger = logging.getLogger(__name__)


class AnkiWebScraper:
    """
    Cliente para extraer estadísticas de AnkiWeb por mazo.
    
    Implementa:
    - Login con manejo de CSRF usando API Protobuf
    - Extracción de mazos desde /decks/
    - Extracción de contadores Review/Learning/New
    """
    
    def __init__(self):
        """Inicializa el scraper con una sesión limpia."""
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
        Realiza el login en AnkiWeb usando el API Protobuf.
        
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
            resp = self.session.get(ANKIWEB_LOGIN_URL, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            
            # Construir payload binario Protobuf
            payload = self._build_login_payload(username, password)
            
            # Nuevo endpoint de login
            login_url = f"{ANKIWEB_BASE_URL}/svc/account/login"
            
            # Headers requeridos para el nuevo API
            headers = {
                'Content-Type': 'application/octet-stream',
                'Referer': 'https://ankiweb.net/account/login',
                'Origin': 'https://ankiweb.net',
            }
            
            resp = self.session.post(login_url, data=payload, headers=headers, timeout=REQUEST_TIMEOUT)
            
            # Verificar respuesta
            if resp.status_code == 200:
                self.logged_in = True
                logger.info(f"Login exitoso para {username[:3]}***")
                return True, "OK"
            elif resp.status_code == 401 or resp.status_code == 403:
                logger.warning(f"Credenciales inválidas para {username[:3]}***")
                return False, "Credenciales inválidas"
            else:
                logger.error(f"Error HTTP {resp.status_code} en login")
                return False, f"HTTP {resp.status_code}"
            
        except requests.Timeout:
            logger.error("Timeout en login")
            return False, "Timeout"
        except requests.RequestException as e:
            logger.error(f"Error de conexión: {e}")
            return False, str(e)
    
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
            url = f"{ANKIWEB_BASE_URL}/svc/decks/deck-list-info"
            headers = {
                'Content-Type': 'application/octet-stream',
                'Accept': '*/*',
            }
            
            # Request POST con body vacío
            resp = self.session.post(url, data=b'', headers=headers, timeout=REQUEST_TIMEOUT)
            debug_msgs.append(f"📡 API Response: {resp.status_code}, {len(resp.content)} bytes")
            
            if resp.status_code == 200 and resp.content:
                decks = self._parse_protobuf_decks(resp.content, debug_msgs)
                debug_msgs.append(f"📊 Mazos parseados: {len(decks)}")
                return decks, debug_msgs
            else:
                debug_msgs.append(f"❌ Error API: HTTP {resp.status_code}")
                
        except Exception as e:
            debug_msgs.append(f"💥 Error API: {str(e)}")
            logger.exception("Error al obtener mazos via API")
        
        return [], debug_msgs
    
    def _parse_protobuf_decks(self, data: bytes, debug_msgs: List[str]) -> List[Dict]:
        """
        Parsea la respuesta Protobuf de deck-list-info de AnkiWeb.
        
        Estructura del mensaje Protobuf:
        - Cada mazo es un submensaje que empieza con tag 0x1a (campo 3)
        - Campo 1 (0x08): ID del mazo (varint)
        - Campo 2 (0x12): Nombre del mazo (string)
        - Campo 6 (0x30): review count
        - Campo 7 (0x38): learning count
        - Campo 8 (0x40): new count
        
        Args:
            data: Bytes de respuesta Protobuf
            debug_msgs: Lista para agregar mensajes de debug
            
        Returns:
            Lista de diccionarios {name, due, new, learning}
        """
        
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
            """Parsea un submensaje de mazo y extrae nombre y contadores."""
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
                    if field_num == 6:  # review_count
                        result['due'] = value
                    elif field_num == 7:  # learn_count
                        result['learning'] = value
                    elif field_num == 8:  # new_count
                        result['new'] = value
                        
                elif wire_type == 2:  # Length-delimited (string o submensaje)
                    length, pos = read_varint(data, pos)
                    if pos + length > end:
                        break
                    
                    if field_num == 2:  # Nombre del mazo
                        try:
                            result['name'] = data[pos:pos+length].decode('utf-8')
                        except UnicodeDecodeError:
                            pass
                    elif field_num == 3:  # Submazo - PARSEAR RECURSIVAMENTE
                        child = parse_deck_message(data, pos, pos + length, all_decks)
                        if child['name'] and len(child['name']) >= 2:
                            name = child['name']
                            # Filtrar nombres que parecen código
                            if (not name.startswith('/') and
                                not name.startswith('_app') and
                                'svelte' not in name.lower() and
                                '.js' not in name.lower() and
                                sum(1 for c in name if c.isalpha()) >= 2):
                                all_decks.append(child)
                                if 'children' not in result:
                                    result['children'] = []
                                result['children'].append(child)
                    pos += length
                else:
                    # Otros wire types, avanzar
                    pos += 1
            
            return result
        
        decks = []
        
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
                                'svelte' not in name.lower() and
                                '.js' not in name.lower() and
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
                debug_msgs.append(
                    f"  📚 {deck['name'][:35]}: due={deck['due']}, "
                    f"new={deck['new']}, learn={deck['learning']}"
                )
            
            return all_decks
            
        except Exception as e:
            debug_msgs.append(f"💥 Error: {str(e)}")
            logger.exception("Error al parsear protobuf")
            return []
    
    def get_stats_by_course(self, cursos: List[str]) -> Dict[str, Dict[str, int]]:
        """
        Obtiene estadísticas por curso usando el API de AnkiWeb.
        
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
        stats['_notas_internas'].append("🔌 Intentando API Protobuf...")
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
                        
                        # Buscar submazo "Teoría"
                        children = deck.get('children', [])
                        submazos = []
                        
                        teoria_due = 0
                        teoria_learning = 0
                        teoria_new = 0
                        teoria_encontrada = False
                        
                        for child in children:
                            child_name = child.get('name', '').lower()
                            
                            if 'teoría' in child_name or 'teoria' in child_name:
                                teoria_encontrada = True
                                teoria_due = child.get('due', 0)
                                teoria_learning = child.get('learning', 0)
                                teoria_new = child.get('new', 0)
                                
                                # Obtener los temas (nietos)
                                nietos = child.get('children', [])
                                for nieto in nietos:
                                    submazos.append({
                                        'nombre': nieto.get('name', ''),
                                        'review': nieto.get('due', 0),
                                        'learning': nieto.get('learning', 0),
                                        'new': nieto.get('new', 0)
                                    })
                                break
                        
                        if not teoria_encontrada:
                            teoria_due = due
                            teoria_learning = learning
                            teoria_new = new
                        
                        stats['_mazos_encontrados'].append({
                            'mazo': deck_name,
                            'curso': curso,
                            'stats': {
                                'review': teoria_due,
                                'learning': teoria_learning,
                                'new': teoria_new
                            },
                            'submazos': submazos
                        })
                        
                        # Sumar al curso
                        stats[curso]['review'] += teoria_due
                        stats[curso]['learning'] += teoria_learning
                        stats[curso]['new'] += teoria_new
                        
                        # Sumar al total
                        stats['_total']['review'] += teoria_due
                        stats['_total']['learning'] += teoria_learning
                        stats['_total']['new'] += teoria_new
                        break
        else:
            stats['_notas_internas'].append("⚠️ API no devolvió datos")
            
            # === MÉTODO 2: Scraping como fallback ===
            try:
                resp = self.session.get(ANKIWEB_DECKS_URL, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                stats['_notas_internas'].append(f"📄 Scraping: {len(resp.text)} chars HTML")
                
                if len(resp.text) < 3000:
                    stats['_notas_internas'].append("⚠️ Página SPA detectada (HTML corto)")
                    
            except Exception as e:
                stats['_notas_internas'].append(f"❌ Error scraping: {str(e)}")
                logger.exception("Error en scraping fallback")
        
        # Registrar cursos sin mazos encontrados
        for curso in cursos:
            if (stats[curso]['review'] == 0 and 
                stats[curso]['learning'] == 0 and 
                stats[curso]['new'] == 0):
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
                self.session.get(f"{ANKIWEB_BASE_URL}/account/logout", timeout=5)
            except Exception as e:
                logger.debug(f"Error en logout: {e}")
        self.session = requests.Session()
        self.logged_in = False
