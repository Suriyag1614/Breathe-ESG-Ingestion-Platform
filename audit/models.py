"""
audit/models.py
Contains: AuditEvent (append-only log)

CONSTRAINT: Nothing is ever deleted from this table.
All FKs use string references to avoid circular imports.
"""
import uuid
from django.db import models


class AuditEvent(models.Model):
    """
    Append-only log of every state-changing action on any entity.
    before_state and after_state capture full serialized state at the moment of change.
    actor_ip is captured for regulatory compliance.
    """

    class EventType(models.TextChoices):
        ROW_APPROVED = "ROW_APPROVED", "Row Approved"
        ROW_REJECTED = "ROW_REJECTED", "Row Rejected"
        ROW_EDITED = "ROW_EDITED", "Row Edited"
        ROW_DELETED = "ROW_DELETED", "Row Soft Deleted"
        BATCH_UPLOADED = "BATCH_UPLOADED", "Batch Uploaded"
        BATCH_SUPERSEDED = "BATCH_SUPERSEDED", "Batch Superseded"
        ISSUE_RESOLVED = "ISSUE_RESOLVED", "Validation Issue Resolved"
        BULK_APPROVE = "BULK_APPROVE", "Bulk Approval"
        BULK_REJECT = "BULK_REJECT", "Bulk Rejection"
        USER_INVITED = "USER_INVITED", "User Invited"
        SOURCE_CONFIGURED = "SOURCE_CONFIGURED", "Data Source Configured"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="audit_events"
    )
    event_type = models.CharField(max_length=50, choices=EventType.choices)
    actor = models.ForeignKey(
        "tenants.User", on_delete=models.PROTECT, related_name="audit_events"
    )
    actor_ip = models.GenericIPAddressField(null=True, blank=True)
    target_type = models.CharField(max_length=50)
    target_id = models.UUIDField()
    before_state = models.JSONField(null=True, blank=True)
    after_state = models.JSONField(null=True, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    batch_event_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "audit_auditevent"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_type", "target_id"]),
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["actor", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} by {self.actor.email} at {self.created_at}"
