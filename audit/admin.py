from django.contrib import admin
from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ["event_type", "actor", "target_type", "target_id", "actor_ip", "created_at"]
    list_filter = ["event_type"]
    search_fields = ["actor__email", "target_id"]
    readonly_fields = ["id", "tenant", "event_type", "actor", "actor_ip",
                       "target_type", "target_id", "before_state", "after_state",
                       "comment", "created_at", "batch_event_id"]

    def has_add_permission(self, request):
        return False  # Append-only: no manual creation via admin

    def has_change_permission(self, request, obj=None):
        return False  # Append-only: no edits

    def has_delete_permission(self, request, obj=None):
        return False  # Append-only: no deletes
