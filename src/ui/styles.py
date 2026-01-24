"""
Estilos CSS para el Dashboard.

Este módulo contiene todo el CSS y configuración de estilos
para la interfaz de Streamlit.
"""

from src.config import GITHUB_RAW_BASE, COLORS


def get_pwa_meta_tags() -> str:
    """
    Genera los meta tags para PWA y móvil.
    
    Returns:
        HTML con meta tags
    """
    return f"""
    <!-- PWA Meta Tags -->
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Competencia">
    <meta name="theme-color" content="{COLORS['primary']}">
    <link rel="manifest" href="{GITHUB_RAW_BASE}/static/manifest.json">
    <link rel="apple-touch-icon" href="{GITHUB_RAW_BASE}/static/icon-192.png">
    <link rel="icon" type="image/png" sizes="192x192" href="{GITHUB_RAW_BASE}/static/icon-192.png">
    <link rel="icon" type="image/png" sizes="512x512" href="{GITHUB_RAW_BASE}/static/icon-512.png">
    """


def get_main_css() -> str:
    """
    Genera el CSS principal para el dashboard.
    
    Returns:
        CSS como string
    """
    return f"""
    <style>
        /* === Variables CSS === */
        :root {{
            --color-gold: {COLORS['gold']};
            --color-silver: {COLORS['silver']};
            --color-bronze: {COLORS['bronze']};
            --color-primary: {COLORS['primary']};
            --color-secondary: {COLORS['secondary']};
            --bg-start: {COLORS['background_start']};
            --bg-end: {COLORS['background_end']};
        }}
        
        /* === Fondo y App === */
        .stApp {{
            background: linear-gradient(135deg, var(--bg-start) 0%, var(--bg-end) 100%);
        }}
        
        /* === Título Principal === */
        .main-title {{
            text-align: center;
            background: linear-gradient(90deg, var(--color-primary), var(--color-secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-size: 2.5rem;
            font-weight: 800;
            margin-bottom: 0.5rem;
        }}
        
        .subtitle {{
            text-align: center;
            color: #888;
            margin-bottom: 1.5rem;
        }}
        
        /* === Podio === */
        .podium {{
            background: rgba(255, 255, 255, 0.05);
            border-radius: 15px;
            padding: 1rem;
            text-align: center;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        
        .podium:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }}
        
        .gold {{
            border: 2px solid var(--color-gold);
            box-shadow: 0 0 10px rgba(255, 215, 0, 0.3);
        }}
        
        .silver {{
            border: 2px solid var(--color-silver);
            box-shadow: 0 0 10px rgba(192, 192, 192, 0.3);
        }}
        
        .bronze {{
            border: 2px solid var(--color-bronze);
            box-shadow: 0 0 10px rgba(205, 127, 50, 0.3);
        }}
        
        /* === Responsive para móvil === */
        @media (max-width: 768px) {{
            .main-title {{
                font-size: 1.8rem;
            }}
            
            .podium {{
                padding: 0.5rem;
            }}
            
            [data-testid="stSidebar"] {{
                min-width: 250px;
            }}
        }}
        
        /* === Botones touch-friendly === */
        .stButton > button {{
            min-height: 44px;
            touch-action: manipulation;
            transition: all 0.2s ease;
        }}
        
        .stButton > button:hover {{
            transform: scale(1.02);
        }}
        
        .stButton > button:active {{
            transform: scale(0.98);
        }}
        
        /* === Smooth scrolling === */
        html {{
            scroll-behavior: smooth;
        }}
        
        /* === Tablas mejoradas === */
        .stDataFrame {{
            border-radius: 10px;
            overflow: hidden;
        }}
        
        /* === Selectbox mejorado === */
        .stSelectbox > div > div {{
            border-radius: 8px;
        }}
        
        /* === Progress bar === */
        .stProgress > div > div > div > div {{
            background: linear-gradient(90deg, var(--color-primary), var(--color-secondary));
        }}
        
        /* === Expander mejorado === */
        .streamlit-expanderHeader {{
            background: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
        }}
        
        /* === Animaciones === */
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .animate-in {{
            animation: fadeIn 0.3s ease-out;
        }}
    </style>
    """


def get_empty_state_html() -> str:
    """
    Genera el HTML para el estado vacío (sin datos).
    
    Returns:
        HTML del estado vacío
    """
    return """
    <div style="text-align:center;padding:3rem;color:#888;">
        <div style="font-size:4rem;">📊</div>
        <h3>Sin datos</h3>
        <p>Presiona "Actualizar Datos"</p>
    </div>
    """


def get_podium_html(name: str, score: float, medal: str, medal_color: str, css_class: str) -> str:
    """
    Genera el HTML para una posición del podio.
    
    Args:
        name: Nombre del estudiante
        score: Puntuación
        medal: Emoji de la medalla
        medal_color: Color de la medalla (hex)
        css_class: Clase CSS (gold, silver, bronze)
        
    Returns:
        HTML del podio
    """
    return f"""
    <div class="podium {css_class}">
        <div style="font-size:2rem;">{medal}</div>
        <div style="font-weight:bold;color:white;">{name}</div>
        <div style="font-size:1.5rem;color:{medal_color};">{score} pts</div>
    </div>
    """
