# Monitor Mercado Público — Trinidad Callejas

Revisa diariamente la API de Mercado Público (Chile) y avisa por correo sobre licitaciones nuevas que coinciden con perfiles temáticos del área de salud, cuidados, capacitación clínica y demencias.

## Cómo funciona

- Consulta todas las licitaciones publicadas del día.
- Filtra por tipos de licitación: LS, L1, LE, LP.
- Aplica los perfiles configurados en `config.py`:
  - **Plan + Salud** (ambas palabras deben aparecer — lógica AND)
  - **Curso + Salud**
  - **Capacitación + Salud**
  - **Cuidados** (basta con que aparezca)
  - **Demencias** (basta con que aparezca)
- Si alguna licitación matchea al menos un perfil, entra al reporte.
- Envía un correo con la lista y mostrando qué perfil(es) coincidió en cada caso.
- Solo notifica licitaciones nuevas (compara con `seen.json`).

## Estructura del repositorio

```
mp-trinidad/
├── monitor_trinidad.py
├── config.py                 ← perfiles y palabras clave (edítalo aquí)
├── requirements.txt
├── seen.json                 ← se actualiza solo, no editar manualmente
├── README.md
└── .github/
    └── workflows/
        └── monitor_trinidad.yml
```

## Setup

### 1. Crear repo en GitHub

Repo nuevo (privado). Sube todos los archivos respetando la estructura.

### 2. Configurar secretos

**Settings → Secrets and variables → Actions**:

| Secret | Valor |
|--------|-------|
| `MP_TICKET` | Ticket de la API de Mercado Público |
| `SMTP_HOST` | `smtp.gmail.com` (o el que uses) |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | tu correo Gmail |
| `SMTP_PASSWORD` | contraseña de aplicación |
| `NOTIFY_TO` | correo(s) de Trinidad, separados por coma si son varios |

> Los secretos son por repo. Aunque ya tengas configurados en otros repos, hay que crearlos de nuevo acá.

### 3. Habilitar permisos de escritura del workflow

**Settings → Actions → General → Workflow permissions** → seleccionar **Read and write permissions**.

### 4. Primer run

**Actions → Monitor MP - Trinidad → Run workflow**.

La primera ejecución es modo **bootstrap**: guarda todos los IDs sin enviar correo. Desde el segundo día notifica solo licitaciones nuevas.

## Personalización

### Agregar/quitar palabras clave

Edita `config.py` y modifica la lista `PERFILES`. Cada perfil es:

```python
{
    "nombre": "Mi perfil",
    "palabras": ["palabra1", "palabra2"],  # AND
}
```

Si quieres lógica OR (que basta con una palabra), define varios perfiles separados.

### Cambiar tipos de licitación

Edita `CODIGOS_TIPO` en `config.py`:
- `LS`: Servicios especializados
- `L1`: Compra ágil (<100 UTM)
- `LE`: Licitación 100-1000 UTM
- `LP`: Licitación 1000-2000 UTM

### Cambiar horario

Edita el cron en `.github/workflows/monitor_trinidad.yml`.

## Limitaciones

- El monitor depende del ticket de la API de Mercado Público.
- El cron de GitHub Actions puede atrasarse hasta 15 minutos en horarios peak.
- En el plan free de GitHub Actions tienes 2000 minutos/mes, sobra para esto.
