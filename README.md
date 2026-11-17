# Mantenedor de Calificaciones Tributarias

## Instalación

### Requisitos

- [Python](https://www.python.org/downloads/) 3.12 o superior
- [Git](https://git-scm.com/downloads)

### 1. Clonar el repositorio

```bash
git clone https://github.com/Yvngbabuin0/Proyecto-Integrado-eva3.git
cd Proyecto-Integrado-eva3
git checkout develop
```

### 2. Crear y activar el entorno virtual

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Si se activó bien, la línea de la terminal empieza con `(.venv)`.

> En Windows, si PowerShell no deja ejecutar `activate`, ejecuta una vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y vuelve a intentarlo.

### 3. Instalar las dependencias

```bash
pip install -r requirements.txt
```

### 4. Crear el archivo `.env`

Copia la plantilla:

```bash
copy .env.example .env      # Windows
cp .env.example .env        # macOS / Linux
```

Genera una clave secreta:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Abre `.env` y pega la clave después de `DJANGO_SECRET_KEY=`. El archivo `.env` no se sube al repositorio.

### 5. Crear la base de datos y cargar los datos de prueba

```bash
python manage.py migrate
python manage.py cargar_demo
```

### 6. Iniciar la aplicación

```bash
python manage.py runserver
```

Abre http://127.0.0.1:8000/ e ingresa con alguno de estos usuarios. Todos tienen la contraseña `demo1234`:

| Usuario | Rol |
|---|---|
| `analista_a`, `analista_b` | Analista Tributario |
| `corredor_a`, `corredor_b` | Corredor |
| `administrador` | Administrador (http://127.0.0.1:8000/admin/) |
| `auditor` | Auditor |

Para detener el servidor, presiona `Ctrl + C`.

### Cada vez que vuelvas a abrir el proyecto

```bash
.venv\Scripts\activate      # Windows (en macOS / Linux: source .venv/bin/activate)
git pull
python manage.py migrate
python manage.py runserver
```
