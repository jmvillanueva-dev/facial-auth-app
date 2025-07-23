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
    strictness = models.FloatField(
        default=0.6
    )  # nivel de rigurosidad (0.4 = menos estricto, 0.6 = normal, 0.8 = muy estricto)
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
    )  # Si desean usar pass opcionalmente
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
