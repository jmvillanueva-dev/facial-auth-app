import secrets
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.conf import settings


class CustomUser(AbstractUser):
    face_auth_enabled = models.BooleanField(default=False)
    full_name = models.CharField(max_length=150, blank=True, default="")
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email", "full_name"]

    def __str__(self):
        return self.email

    def unique_error_message(self, model_class, unique_check):
        if model_class == type(self) and unique_check == ("username",):
            return "El nombre de usuario ya está en uso. Por favor elige otro."
        return super().unique_error_message(model_class, unique_check)


class ClientApp(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="apps"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    token = models.CharField(max_length=40, unique=True, editable=False)
    CONFIDENCE_THRESHOLD = models.FloatField(default=0.18)
    FALLBACK_THRESHOLD = models.FloatField(default=0.25)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_hex(20)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.owner.username})"


class EndUser(models.Model):
    app = models.ForeignKey(
        ClientApp, on_delete=models.CASCADE, related_name="end_users"
    )
    email = models.EmailField()
    full_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=100, blank=True)
    password = models.CharField(
        max_length=128, blank=True
    )
    face_encoding = models.BinaryField()
    deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (
            "app",
            "email",
        )

    def __str__(self):
        return f"{self.full_name} ({self.email}) - App: {self.app.name}"


class EndUserFeedback(models.Model):
    """
    Modelo para almacenar el feedback de las imágenes de los EndUser.
    Cada instancia representa una imagen que un EndUser usó para confirmar su identidad,
    lo que puede ser usado para mejorar el modelo facial de ese usuario.
    """
    end_user = models.ForeignKey(EndUser, on_delete=models.CASCADE, related_name="feedback_images")
    app = models.ForeignKey(ClientApp, on_delete=models.CASCADE, related_name="enduser_feedback")
    submitted_image = models.ImageField(upload_to='enduser_feedback_images/')
    timestamp = models.DateTimeField(auto_now_add=True)
    feedback_type = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = "Feedback de Usuario Final"
        verbose_name_plural = "Feedbacks de Usuarios Finales"
        ordering = ['-timestamp'] 

    def __str__(self):
        return f"Feedback para {self.end_user.full_name} de {self.app.name} el {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class EndUserLoginAttempt(models.Model):
    """
    Registra cada intento de inicio de sesión facial de un EndUser.
    Utilizado para recolectar métricas de rendimiento del modelo.
    """

    app = models.ForeignKey(
        ClientApp, on_delete=models.CASCADE, related_name="login_attempts"
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    submitted_image = models.ImageField(
        upload_to="login_attempts_images/", null=True, blank=True
    )

    # Campo para el usuario que intenta iniciar sesión (puede ser nulo si no se reconoce)
    # Esto es el "ground truth" si el usuario existe y se identifica correctamente.
    attempting_end_user = models.ForeignKey(
        EndUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_attempts_as_attempting",
    )

    # El usuario que el sistema identificó como la mejor coincidencia (puede ser nulo)
    best_match_user = models.ForeignKey(
        EndUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_attempts_as_best_match",
    )
    best_match_distance = models.FloatField(null=True, blank=True)

    # Estado inicial del intento de login según el modelo
    STATUS_CHOICES = [
        ("success", "Éxito (alta confianza)"),
        ("ambiguous_match", "Coincidencia ambigua"),
        ("no_match", "Sin coincidencia"),
        ("error", "Error de procesamiento"),  # Para errores internos
    ]
    initial_status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    # El usuario que finalmente confirmó su identidad a través del feedback (si aplica)
    # Esto nos ayuda a clasificar si el intento inicial fue un FP o FN que se corrigió.
    confirmed_by_feedback = models.ForeignKey(
        EndUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_attempts_confirmed",
    )

    # Campo para almacenar el feedback del usuario
    # Nuevo campo para registrar si el usuario confirmó si el perfil era el suyo.
    # Los valores pueden ser: 'correcto' o 'incorrecto'.
    # Si el valor es null, no se ha recibido feedback aún.
    FEEDBACK_CHOICES = [
        ("correcto", "Correcto"),
        ("incorrecto", "Incorrecto"),
    ]
    user_feedback = models.CharField(
        max_length=10,
        choices=FEEDBACK_CHOICES,
        null=True,
        blank=True,
        help_text="Feedback directo del usuario sobre el intento de login.",
    )

    # Indica si el intento de login fue verificado y confirmado como correcto por el usuario
    # (ya sea por un match directo o a través del feedback).
    is_verified_and_correct = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Intento de Login de Usuario Final"
        verbose_name_plural = "Intentos de Login de Usuarios Finales"
        ordering = ["-timestamp"]

    def __str__(self):
        status_display = self.get_initial_status_display()
        user_info = self.best_match_user.full_name if self.best_match_user else "N/A"
        return f"Intento de {status_display} en {self.app.name} por {user_info} ({self.timestamp.strftime('%Y-%m-%d %H:%M')})"
