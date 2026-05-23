"""
Configuración del monitor de Mercado Público para Trinidad Callejas Bello.

Foco: licitaciones del área de salud, terapia ocupacional, cuidados,
demencia, capacitación clínica.

LÓGICA DE BÚSQUEDA:
Cada "perfil" es una lista de palabras clave que deben aparecer TODAS
(lógica AND) en el nombre o descripción de la licitación.
Si alguno de los perfiles matchea, la licitación entra al reporte.
"""

# Tipos de licitación a monitorear (todos los principales)
CODIGOS_TIPO = ["LS", "L1", "LE", "LP"]

# Perfiles de búsqueda. Cada perfil es una lista de palabras que deben
# aparecer TODAS (AND). Si una sola lista tiene una sola palabra, basta
# con que aparezca esa.
PERFILES = [
    {
        "nombre": "Plan + Salud",
        "palabras": ["plan", "salud"],
    },
    {
        "nombre": "Curso + Salud",
        "palabras": ["curso", "salud"],
    },
    {
        "nombre": "Capacitación + Salud",
        "palabras": ["capacitación", "salud"],
    },
    {
        "nombre": "Cuidados",
        "palabras": ["cuidados"],
    },
    {
        "nombre": "Demencia",
        "palabras": ["demencia"],
    },
]
