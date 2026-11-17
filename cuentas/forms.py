from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.core.exceptions import ValidationError

MAX_INTENTOS = 5
BLOQUEO_SEGUNDOS = 15 * 60


def clave_intentos(username):
    return f'login-fallidos:{username.strip().lower()}'


class LoginForm(AuthenticationForm):
    """Login que bloquea la cuenta por 15 minutos después de 5 intentos fallidos seguidos."""

    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'Usuario o contraseña incorrectos.',
        'bloqueado': 'Demasiados intentos fallidos. Espera 15 minutos antes de volver a intentarlo.',
    }

    def clean(self):
        clave = clave_intentos(self.cleaned_data.get('username') or '')
        intentos = cache.get(clave, 0)
        if intentos >= MAX_INTENTOS:
            # No se revisa la contraseña: así un atacante no puede seguir probando durante el bloqueo.
            raise ValidationError(self.error_messages['bloqueado'], code='bloqueado')

        try:
            datos = super().clean()
        except ValidationError:
            # Cada fallo reinicia los 15 minutos.
            cache.set(clave, intentos + 1, BLOQUEO_SEGUNDOS)
            raise

        cache.delete(clave)
        return datos
