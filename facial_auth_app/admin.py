from django.contrib import admin
from .models import ClientApp


@admin.register(ClientApp)
class ClientAppAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "strictness", "token", "created_at")
    search_fields = ("name", "owner__username")
