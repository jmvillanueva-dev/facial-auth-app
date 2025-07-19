import os
import uuid
import secrets
from django.db import models
from django.conf import settings


def user_face_image_path(instance, filename):
    # Generate file path for user face image
    ext = filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join("face_images/", filename)


class FacialRecognitionProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="facial_profile",
    )
    face_encoding = models.BinaryField()
    face_image = models.ImageField( 
        upload_to=user_face_image_path, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Facial Profile for {self.user.username}"


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


