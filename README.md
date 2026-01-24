# 🏆 Dashboard de Competencia Académica

Dashboard interactivo de Streamlit para grupos de estudio de medicina que integra datos de **AnkiWeb** y **Notion** para gamificar el aprendizaje.

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![Streamlit](https://img.shields.io/badge/streamlit-1.28+-red.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## ✨ Características

- **🎮 Sistema de Gamificación**: Puntuación basada en la "Fórmula Médica"
- **📊 Rankings por Curso**: Visualiza el progreso en cada materia
- **🔄 Integración AnkiWeb**: Extrae automáticamente estadísticas de flashcards
- **📝 Integración Notion**: Sincroniza puntajes de quices
- **📢 Notificaciones Discord**: Envía rankings automáticos a tu servidor
- **📱 PWA**: Instalable como aplicación móvil
- **🌙 Modo Oscuro**: Interfaz moderna con gradientes

## 🧮 Fórmula Médica

```
Score = (Review × 1.0) + (Learning × 0.5) + (Completadas × 0.8) + (Quiz × 10)
```

| Tipo | Multiplicador | Descripción |
|------|---------------|-------------|
| Review | ×1.0 | Tarjetas de repaso (verdes) |
| Learning | ×0.5 | Tarjetas en aprendizaje (rojas) |
| New | ×0.0 | Tarjetas nuevas - no dan puntos |
| Completadas | ×0.8 | Tarjetas completadas desde última actualización |
| Quiz | ×10 | Puntaje de quices en Notion |

## 📁 Estructura del Proyecto

```
Medicina-leaderboard/
├── app.py                    # Entry point de Streamlit
├── src/
│   ├── config.py             # Configuración centralizada
│   ├── models.py             # Modelos de datos
│   ├── scoring.py            # Motor de cálculo de scores
│   ├── scrapers/
│   │   └── ankiweb.py        # Scraper de AnkiWeb
│   ├── integrations/
│   │   ├── notion.py         # Cliente de Notion API
│   │   └── discord.py        # Notificaciones Discord
│   └── ui/
│       ├── components.py     # Componentes de Streamlit
│       └── styles.py         # CSS y estilos
├── tests/
│   ├── conftest.py           # Fixtures de pytest
│   └── test_scoring.py       # Tests del módulo scoring
├── static/
│   ├── manifest.json         # Configuración PWA
│   ├── sw.js                 # Service Worker
│   └── icon-*.png            # Iconos
├── .streamlit/
│   └── secrets.toml.example  # Ejemplo de configuración
├── pyproject.toml            # Configuración del proyecto
└── requirements.txt          # Dependencias
```

## 🚀 Instalación

### Requisitos
- Python 3.9+
- Cuenta de AnkiWeb
- (Opcional) Base de datos en Notion
- (Opcional) Servidor de Discord con webhook

### 1. Clonar el repositorio

```bash
git clone https://github.com/zeusbf2004-star/Medicina-leaderboard.git
cd Medicina-leaderboard
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar secretos

Copia `.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` y configura:

```toml
# Notion API
NOTION_TOKEN = "ntn_TU_TOKEN_AQUI"
NOTION_DATABASE_ID = "TU_DATABASE_ID_AQUI"

# Discord (Opcional)
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."

# Estudiantes
[student_1]
name = "Nombre"
username = "email@ankiweb.com"
password = "contraseña"
```

### 4. Ejecutar localmente

```bash
streamlit run app.py
```

## ☁️ Despliegue en Streamlit Cloud

1. Haz fork del repositorio
2. Ve a [share.streamlit.io](https://share.streamlit.io)
3. Conecta tu repositorio
4. Configura los secretos en Settings → Secrets
5. ¡Deploy!

## 🧪 Testing

```bash
# Instalar dependencias de desarrollo
pip install pytest pytest-cov

# Ejecutar tests
pytest tests/ -v

# Con cobertura
pytest tests/ -v --cov=src
```

## 📝 Configuración de Notion

Tu base de datos de Notion debe tener las siguientes propiedades:

| Propiedad | Tipo | Descripción |
|-----------|------|-------------|
| Nombre/Estudiante | Title | Nombre del estudiante |
| Curso | Select | Nombre del curso |
| Puntaje | Number | Puntuación del quiz |

## 🔧 Personalización

### Añadir cursos

Edita `src/config.py`:

```python
CURSOS = [
    "Anatomía",
    "Histología",
    # Añade más cursos aquí
]

CURSO_DECK_KEYWORDS = {
    "Anatomía": ["=Anatomía humana Pró"],
    # Añade keywords para identificar mazos
}
```

### Modificar multiplicadores

```python
REVIEW_MULTIPLIER = 1.0
LEARNING_MULTIPLIER = 0.5
COMPLETED_MULTIPLIER = 0.8
NOTION_MULTIPLIER = 10
```

## 🤝 Contribuir

1. Fork el proyecto
2. Crea una rama (`git checkout -b feature/nueva-funcionalidad`)
3. Commit tus cambios (`git commit -m 'Add: nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para detalles.

## 🙏 Créditos

- [Streamlit](https://streamlit.io/) - Framework de dashboards
- [AnkiWeb](https://ankiweb.net/) - Plataforma de flashcards
- [Notion](https://notion.so/) - Base de datos
- Comunidad de estudiantes de medicina

---

<p align="center">
  Hecho con ❤️ para estudiantes de medicina
</p>