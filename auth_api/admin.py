from django.contrib import admin
from django.urls import path
from django.shortcuts import render
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from .models import CustomUser, ClientApp, EndUser, EndUserFeedback, EndUserLoginAttempt

from facial_auth_app.models import FacialRecognitionProfile


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = (
        "username",
        "email",
        "full_name",
        "face_auth_enabled",
        "is_staff",
        "date_joined",
    )
    search_fields = ("username", "email", "full_name")
    list_filter = ("is_staff", "face_auth_enabled")
    ordering = ("-date_joined",)


@admin.register(ClientApp)
class ClientAppAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "owner",
        "token",
        "CONFIDENCE_THRESHOLD",
        "FALLBACK_THRESHOLD",
        "created_at",
        "view_metrics_link",
    )
    search_fields = ("name", "owner__username", "token")
    list_filter = ("owner",)
    readonly_fields = ("token", "created_at")
    fieldsets = (
        (None, {"fields": ("owner", "name", "description", "token")}),
        (
            "Configuración de Reconocimiento Facial",
            {"fields": ("CONFIDENCE_THRESHOLD", "FALLBACK_THRESHOLD")},
        ),
    )

    def view_metrics_link(self, obj):
        from django.utils.html import format_html

        return format_html('<a href="{}/metrics/">Ver Métricas</a>', obj.id)

    view_metrics_link.short_description = "Métricas"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<path:object_id>/metrics/",
                self.admin_site.admin_view(self.metrics_view),
                name="clientapp_metrics",
            ),
        ]
        return custom_urls + urls

    def metrics_view(self, request, object_id):
        app = self.get_object(request, object_id)
        if not app:
            # Handle case where app is not found (e.g., deleted)
            return render(
                request,
                "admin/clientapp_metrics_error.html",
                {"message": "Aplicación no encontrada."},
            )

        # Define time ranges
        now = timezone.now()
        time_ranges = {
            "last_24_hours": now - timedelta(hours=24),
            "last_7_days": now - timedelta(days=7),
            "last_30_days": now - timedelta(days=30),
            "all_time": None,
        }

        metrics_data = {}

        for period_name, start_time in time_ranges.items():
            # Filter attempts by time range
            attempts_query = EndUserLoginAttempt.objects.filter(app=app)
            if start_time:
                attempts_query = attempts_query.filter(timestamp__gte=start_time)

            total_attempts = attempts_query.count()

            # Initial Status Counts
            initial_success = attempts_query.filter(initial_status="success").count()
            initial_ambiguous = attempts_query.filter(
                initial_status="ambiguous_match"
            ).count()
            initial_no_match = attempts_query.filter(initial_status="no_match").count()
            initial_error = attempts_query.filter(initial_status="error").count()

            # Feedback-based counts
            # Confirmed correct: Where the user verified their identity.
            # This is our primary source for "True Positives"
            confirmed_correct_by_feedback = attempts_query.filter(
                is_verified_and_correct=True
            ).count()

            # Potential False Positives (system said success/ambiguous, but user didn't confirm or said "not me")
            # This is harder to track without explicit "not me" feedback.
            # For now, we can consider attempts that were 'success' or 'ambiguous' but NOT 'is_verified_and_correct'
            # as potential FPs, but this is an oversimplification.
            # A more robust FP requires user explicitly denying the match.

            # Potential False Negatives (system said no_match/ambiguous, but user was actually registered and could have confirmed)
            # This is also hard without knowing the "true" identity of the person who attempted.
            # We can infer some FNs if an 'ambiguous_match' or 'no_match' attempt was later confirmed by feedback.

            # For simplicity, let's use `is_verified_and_correct` as our TP count.
            # And `initial_no_match` as a proxy for FNs (system couldn't find them).
            # FPs are hard without user explicitly saying "that wasn't me".

            # Simplified metrics for display
            metrics_data[period_name] = {
                "total_attempts": total_attempts,
                "initial_success": initial_success,
                "initial_ambiguous": initial_ambiguous,
                "initial_no_match": initial_no_match,
                "initial_error": initial_error,
                "confirmed_correct_by_feedback": confirmed_correct_by_feedback,
                "initial_success_rate": (
                    f"{initial_success / total_attempts * 100:.2f}%"
                    if total_attempts > 0
                    else "0.00%"
                ),
                "confirmed_correct_rate": (
                    f"{confirmed_correct_by_feedback / total_attempts * 100:.2f}%"
                    if total_attempts > 0
                    else "0.00%"
                ),
            }

        context = self.admin_site.each_context(request)
        context.update(
            {
                "title": f"Métricas de Rendimiento para {app.name}",
                "app": app,
                "metrics_data": metrics_data,
                "opts": self.model._meta,  # Required for admin templates
                "has_permission": True,  # Assume superuser has permission
            }
        )
        return render(request, "admin/clientapp_metrics.html", context)


@admin.register(EndUser)
class EndUserAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "app", "role", "deleted", "created_at")
    search_fields = ("full_name", "email", "app__name")
    list_filter = ("app", "deleted")
    ordering = ("app", "full_name")
    raw_id_fields = (
        "app",
    )  # Use raw_id_fields for FKs to improve performance for many records


@admin.register(EndUserFeedback)
class EndUserFeedbackAdmin(admin.ModelAdmin):
    list_display = ("end_user", "app", "timestamp", "submitted_image_thumbnail")
    search_fields = ("end_user__full_name", "end_user__email", "app__name")
    list_filter = ("app", "timestamp")
    readonly_fields = (
        "end_user",
        "app",
        "submitted_image",
        "timestamp",
        "submitted_image_preview",
    )

    def submitted_image_thumbnail(self, obj):
        from django.utils.html import format_html

        if obj.submitted_image:
            return format_html(
                '<img src="{}" width="50" height="50" style="border-radius: 5px;" />',
                obj.submitted_image.url,
            )
        return "No Image"

    submitted_image_thumbnail.short_description = "Miniatura"

    def submitted_image_preview(self, obj):
        from django.utils.html import format_html

        if obj.submitted_image:
            return format_html(
                '<img src="{}" style="max-width: 300px; height: auto;" />',
                obj.submitted_image.url,
            )
        return "No Image"

    submitted_image_preview.short_description = "Previsualización de Imagen"


@admin.register(EndUserLoginAttempt)
class EndUserLoginAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "app",
        "timestamp",
        "attempting_end_user",
        "best_match_user",
        "initial_status",
        "is_verified_and_correct",
    )
    list_filter = ("app", "initial_status", "is_verified_and_correct", "timestamp")
    search_fields = (
        "app__name",
        "attempting_end_user__full_name",
        "best_match_user__full_name",
    )
    readonly_fields = (
        "app",
        "timestamp",
        "submitted_image",
        "attempting_end_user",
        "best_match_user",
        "best_match_distance",
        "initial_status",
        "confirmed_by_feedback",
        "is_verified_and_correct",
        "submitted_image_preview",
    )

    def submitted_image_preview(self, obj):
        from django.utils.html import format_html

        if obj.submitted_image:
            return format_html(
                '<img src="{}" style="max-width: 300px; height: auto;" />',
                obj.submitted_image.url,
            )
        return "No Image"

    submitted_image_preview.short_description = "Imagen Enviada"
