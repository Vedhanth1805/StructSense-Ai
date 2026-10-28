"""Authentication audit hooks for the existing persistent audit stream."""
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import AuditEvent


@receiver(user_logged_in, dispatch_uid="webdata.audit_user_login")
def audit_user_login(sender, request, user, **kwargs):
    """Record successful Django logins without storing credentials or session data."""
    AuditEvent.objects.create(
        project=None,
        actor=user,
        action="login",
        details={"path": request.path if request is not None else ""},
    )
