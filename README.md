# Mantenedor de Calificaciones Tributarias — Caso Nuam

Mantenedor de Calificaciones Tributarias para corredores de Nuam. Proyecto Integrado (TIHI43), ES3.

- **Grupo:** 4
- **Integrantes:** Jordán Varas, Carlos Seura, Dilan Veliz, Luis Jimenez

## Qué hace

Permite que cada corredora mantenga sus propias calificaciones tributarias a partir de las que publica la Bolsa, sin modificar las originales. El flujo ideal: el usuario inicia sesión, entra al mantenedor de su corredora, ingresa una calificación con los montos de los conceptos 8 a 37, presiona "Calcular factores" y graba la calificación con los factores calculados. También puede cargar muchas calificaciones juntas con un archivo CSV, que se previsualiza antes de confirmarlo. Cada cambio queda registrado en la auditoría.

## Requisitos

- Sistema operativo: Windows 11 (también funciona en macOS y Linux)
- Lenguaje y versión: Python 3.12 o superior (probado con Python 3.13) y Django 6.1
- Base de datos y versión: SQLite 3 (viene incluida con Python, no hay que instalar nada)
- Otras herramientas: Git y un navegador web

## Instalación paso a paso

1. Clonar el repositorio:

   ```bash
   git clone https://github.com/Yvngbabuin0/Proyecto-Integrado-eva3.git
   ```

2. Entrar a la carpeta:

   ```bash
   cd Proyecto-Integrado-eva3
   ```

3. Crear el entorno e instalar las dependencias:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

   En macOS / Linux, el segundo comando es `source .venv/bin/activate`.

4. Configurar las variables: copiar `.env.example` a `.env`:

   ```bash
   copy .env.example .env
   ```

   En macOS / Linux: `cp .env.example .env`. Luego generar una clave secreta:

   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

   y pegarla en el `.env`, después de `DJANGO_SECRET_KEY=`. No subir el `.env` ni llaves reales al repositorio.

5. Crear la base de datos:

   ```bash
   python manage.py migrate
   ```

6. Cargar los datos de ejemplo (opcional): crea dos corredoras, calificaciones de la Bolsa y un usuario por rol.

   ```bash
   python manage.py cargar_demo
   ```

## Cómo ejecutar

```bash
python manage.py runserver
```

Abrir [http://127.0.0.1:8000](http://127.0.0.1:8000) en el navegador. Usuarios de demostración (los crea `cargar_demo`, la clave de todos es `demo1234`):

| Usuario | Rol |
|---|---|
| `analista_a` / `analista_b` | Analista Tributario: mantenedor completo y carga CSV |
| `corredor_a` / `corredor_b` | Corredor: mantenedor sin carga CSV |
| `administrador` | Administrador: usuarios y corredoras |
| `auditor` | Auditor: solo lectura del log de auditoría |

Para probar la carga CSV hay archivos de ejemplo en `test-data/csv_pruebas/`.

## Cómo ejecutar las pruebas

```bash
python manage.py test
```

Las pruebas están en los archivos `tests.py` y `test_calculo.py` de cada app. El informe de pruebas está en el informe final del proyecto.

## Estructura del repositorio

- `config/`: configuración de Django (ajustes, URLs principales).
- `cuentas/`: usuarios, corredoras, roles, inicio de sesión con límite de intentos y redirección según el rol.
- `calificaciones/`: modelos de instrumentos y calificaciones, mantenedor (ingresar, modificar, dar de baja), cálculo de factores (`calculo.py`) y carga CSV (`importador_csv.py`).
- `auditoria/`: registro de eventos y pantallas del log para el Auditor.
- `templates/` y `static/`: plantilla base y estilos.
- `test-data/csv_pruebas/`: archivos CSV válidos y con errores para probar la carga.

## Decisiones del caso

- Rango de la suma de factores: 8 al 19. La suma no puede superar 1; si la supera, no se graba.
- Filas inválidas en un CSV: se rechaza todo el archivo y no se guarda nada (todo o nada).
- Llave que identifica una calificación: corredora + ejercicio + mercado + instrumento + secuencia del evento.
- Factores 34 a 37: no tienen fórmula; se ingresan a mano, deben estar entre 0 y 1 y no entran en la suma de los factores 8 a 19.

## Problemas frecuentes

- **PowerShell no deja activar el entorno** ("la ejecución de scripts está deshabilitada"): ejecutar `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y volver a activar.
- **`Falta DJANGO_SECRET_KEY`** al ejecutar cualquier comando: falta el `.env` o la clave está vacía. Repetir el paso 4.
- **`no such table`**: falta crear la base de datos. Ejecutar `python manage.py migrate`.
- **`cargar_demo solo se ejecuta con DJANGO_DEBUG=1`**: poner `DJANGO_DEBUG=1` en el `.env`.
- **"Demasiados intentos fallidos" al iniciar sesión**: después de 5 intentos fallidos el usuario se bloquea 15 minutos. Esperar o reiniciar el servidor.

## Equipo

Contribuciones por integrante: [historial del repositorio](https://github.com/Yvngbabuin0/Proyecto-Integrado-eva3/graphs/contributors).
