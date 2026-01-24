"""
Cliente de API para Notion.

Este módulo proporciona una implementación directa del cliente de Notion 
usando requests sin dependencias externas como notion-client.
"""

import logging
from typing import Dict, List, Optional, Tuple

import requests

from src.config import NOTION_API_VERSION, NOTION_API_BASE_URL, NOTION_TIMEOUT, normalize_text

logger = logging.getLogger(__name__)


class NotionAPI:
    """
    Cliente de Notion usando requests directos (sin notion-client).
    A prueba de conflictos de dependencias en Streamlit Cloud.
    """
    
    def __init__(self, token: str, database_id: str):
        """
        Inicializa el cliente de Notion.
        
        Args:
            token: Token de integración de Notion
            database_id: ID de la base de datos a consultar
        """
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
        
        Args:
            start_cursor: Cursor para paginación
        
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
                timeout=NOTION_TIMEOUT
            )
            
            if response.status_code == 200:
                return response.json(), None
            elif response.status_code == 401:
                logger.error("Token de Notion inválido o expirado")
                return {}, "Token de Notion inválido o expirado"
            elif response.status_code == 404:
                logger.error("Base de datos no encontrada")
                return {}, "Base de datos no encontrada. Verifica el ID y los permisos de la integración"
            elif response.status_code == 400:
                error_msg = response.json().get('message', 'Error desconocido')
                logger.error(f"Solicitud inválida: {error_msg}")
                return {}, f"Solicitud inválida: {error_msg}"
            else:
                logger.error(f"Error HTTP {response.status_code}")
                return {}, f"Error HTTP {response.status_code}: {response.text[:200]}"
                
        except requests.Timeout:
            logger.error("Timeout al conectar con Notion API")
            return {}, "Timeout al conectar con Notion API"
        except requests.RequestException as e:
            logger.error(f"Error de conexión con Notion: {e}")
            return {}, f"Error de conexión: {str(e)}"
    
    def _extract_text_from_property(self, prop: Dict) -> Optional[str]:
        """
        Extrae texto de una propiedad de Notion.
        
        Args:
            prop: Diccionario de propiedad de Notion
            
        Returns:
            Texto extraído o None
        """
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
        """
        Extrae número de una propiedad de Notion.
        
        Args:
            prop: Diccionario de propiedad de Notion
            
        Returns:
            Número extraído o 0
        """
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
        
        Args:
            cursos: Lista de cursos a buscar
        
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
                        if (normalize_text(curso) in normalize_text(curso_encontrado) or
                            normalize_text(curso_encontrado) in normalize_text(curso)):
                            scores[student_name][curso] += puntaje
                            break
                
                # Siempre sumar al total
                scores[student_name]["_total"] += puntaje
            
            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")
        
        logger.info(f"Obtenidos puntajes de {len(scores)} estudiantes desde Notion")
        return scores, None
