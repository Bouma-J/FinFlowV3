from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Delegation, TenantRole, User


@admin.register(TenantRole)
class TenantRoleAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "group", "created_at"]
    list_filter = ["tenant"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        "username", "email", "first_name", "last_name",
        "tenant", "is_group_level", "is_active",
    ]
    list_filter = ["is_group_level", "is_active", "tenant", "groups"]
    fieldsets = BaseUserAdmin.fieldsets + (
        ("FIN_FLOW", {
            "fields": (
                "tenant", "agency", "is_group_level",
                "employee_id", "cbs_id", "phone", "mfa_enabled",
            )
        }),
    )


@admin.register(Delegation)
class DelegationAdmin(admin.ModelAdmin):
    list_display = [
        "delegator", "delegate", "start_date", "end_date", "is_active",
    ]
    list_filter = ["is_active"]
