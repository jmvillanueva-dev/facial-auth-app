import os
import uuid
from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()


def user_face_image_path(instance, filename):
    # Generate file path for user face image
    ext = filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join("face_images/", filename)


class FacialRecognitionProfile(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="facial_profiles"
    )
    face_encoding = models.BinaryField()
    face_image = models.ImageField(
        upload_to=user_face_image_path, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    description = models.CharField(max_length=255, default="Initial registration")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile for {self.user.email} ({self.description})"

    class Meta:
        verbose_name = "Facial Recognition Profile"
        verbose_name_plural = "Facial Recognition Profiles"


class FaceFeedback(models.Model):
    """
    Almacena imágenes de feedback para casos de falsos positivos o coincidencias ambiguas.
    Se crea set de datos para re-entrenar o mejorar el modelo.
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="face_feedback"
    )
    submitted_image = models.ImageField(upload_to="face_feedback_images/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (
            f"Feedback for {self.user.email} on {self.created_at.strftime('%Y-%m-%d')}"
        )
