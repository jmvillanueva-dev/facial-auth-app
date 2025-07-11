from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    FACE_AUTH_ENABLED = models.BooleanField(default=False)
    
    def __str__(self):
        return self.username