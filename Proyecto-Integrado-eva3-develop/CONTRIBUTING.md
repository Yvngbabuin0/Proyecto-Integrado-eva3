# Guía de contribución

Esta guía explica cómo trabajaremos en este repositorio.

## Ramas

| Rama | Para qué sirve |
|------|----------------|
| `main` | Versión estable y revisada. **Nadie hace push directo.** Solo recibe cambios desde `develop` mediante un PR. |
| `develop` | Integración del trabajo del equipo. **Nadie hace push directo.** Solo recibe cambios mediante PR desde ramas de trabajo. |
| `tipo/descripcion-breve` | Rama de trabajo personal para un cambio concreto. Se crea desde `develop`. |

```
tipo/descripcion ──► PR (revisión) ──► develop ──► PR (revisión) ──► main
```

## Nombres de ramas

Formato: `tipo/descripcion-breve`, en minúsculas y con guiones en lugar de espacios.

| Tipo | Uso | Ejemplo |
|------|-----|---------|
| `feat` | Nueva funcionalidad | `feat/login-usuarios` |
| `fix` | Corrección de un error | `fix/validacion-email` |
| `docs` | Documentación | `docs/instrucciones-instalacion` |
| `style` | Formato o estilos, sin cambiar la lógica | `style/colores-navbar` |
| `refactor` | Reorganizar código sin cambiar su comportamiento | `refactor/servicio-productos` |
| `test` | Agregar o corregir pruebas | `test/carrito-compras` |
| `chore` | Configuración, dependencias y tareas de mantenimiento | `chore/actualizar-dependencias` |

## Flujo de trabajo

### 1. Actualiza `develop` antes de empezar

```bash
git checkout develop
git pull origin develop
```

### 2. Crea tu rama desde `develop`

```bash
git checkout -b feat/login-usuarios
```

### 3. Trabaja y haz commits

```bash
git add .
git commit -m "feat: agrega formulario de inicio de sesión"
```

### 4. Sube tu rama

```bash
git push -u origin feat/login-usuarios
```

### 5. Abre un Pull Request hacia `develop`

- En GitHub, abre el PR con **base: `develop`** y **compare: tu rama**.
- Escribe un título claro y una descripción breve: qué cambiaste, por qué y cómo probarlo.
- Pide la revisión de al menos **un integrante**.

### 6. Revisión y merge

- Otro integrante revisa el PR, deja comentarios si hace falta y lo aprueba.
- Si te piden cambios, haz nuevos commits en tu misma rama y súbelos. El PR se actualiza solo.
- Cuando esté aprobado, se mergea a `develop` y se borra la rama de trabajo.

### 7. Paso de `develop` a `main`

Cuando `develop` esté estable y probado, se abre un PR de `develop` a `main`. El equipo lo revisa de nuevo y, una vez aprobado, se mergea.

## Mensajes de commit

Formato: `tipo: descripción breve en minúsculas`, con los mismos tipos que en los nombres de ramas.

```
feat: agrega página de registro
fix: corrige cálculo del total del carrito
docs: explica cómo levantar el proyecto
```

- Un commit debe contener un solo cambio lógico.
- Describe **qué** hace el cambio, no "cambios" o "arreglos varios".

## Conflictos

Si tu PR tiene conflictos con `develop`:

```bash
git checkout develop
git pull origin develop
git checkout tu-rama
git merge develop
# resuelve los conflictos, luego:
git add .
git commit
git push
```


## Reglas básicas

- Nunca hagas push directo a `main` ni a `develop`.
- Nunca uses `git push --force` (ni `-f` ni `--force-with-lease`). Reescribe el historial del repositorio remoto y puede borrar commits de otros integrantes. Si necesitas corregir algo, haz un commit nuevo.
- Una rama trabaja un solo tema. Si aparece otra tarea, crea otra rama.
- Antes de abrir un PR, comprueba que el proyecto funciona en tu equipo.
- No subas contraseñas, claves ni archivos `.env`.