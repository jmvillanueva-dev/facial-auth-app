from django.contrib import admin

# Register your models here.
from auth_api.models import CustomUser
from facial_auth_app.models import FacialRecognitionProfile
@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'full_name', 'face_auth_enabled')
    search_fields = ('username', 'email')
    list_filter = ('face_auth_enabled',)
@admin.register(FacialRecognitionProfile)
class FacialRecognitionProfileAdmin(admin.ModelAdmin):  
    list_display = ('user', 'created_at')
    search_fields = ('user__username',)
    list_filter = ('created_at',)
