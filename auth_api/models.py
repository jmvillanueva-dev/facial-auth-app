from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


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
