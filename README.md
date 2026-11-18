# Mantenedor de Calificaciones Tributarias

## Instalación

Requisitos: Python 3.12 o superior y Git.

**1. Clonar el repositorio**

```bash
git clone https://github.com/Yvngbabuin0/Proyecto-Integrado-eva3.git
cd Proyecto-Integrado-eva3
git checkout develop
```

**2. Crear el entorno virtual**

```bash
python -m venv .venv
```

**3. Activar el entorno virtual**

```bash
.venv\Scripts\activate
```

En macOS / Linux: `source .venv/bin/activate`

**4. Instalar las dependencias**

```bash
pip install -r requirements.txt
```

**5. Crear el archivo `.env`**

```bash
copy .env.example .env
```

En macOS / Linux: `cp .env.example .env`

**6. Generar la clave secreta**

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

**7. Pegar la clave en el `.env`**, después de `DJANGO_SECRET_KEY=`

```
DJANGO_SECRET_KEY=la-clave-que-generaste
```

**8. Crear la base de datos**

```bash
python manage.py migrate
```

**9. Cargar los datos de prueba**

```bash
python manage.py cargar_demo
```

**10. Iniciar la aplicación**

```bash
python manage.py runserver
```

**11. Abrir http://127.0.0.1:8000/ en el navegador** e ingresar con:

```
Usuario:    analista_a
Contraseña: demo1234
```
