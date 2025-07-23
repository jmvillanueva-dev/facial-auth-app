import os
import uuid
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

