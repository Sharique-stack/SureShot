from django.contrib import admin
from .models import (
    AspirantProfile, 
    FinancialCommitment, 
    ComplianceLog, 
    MandatoryExam, 
    Task, 
    TaskSubmission,
    LiveSession,
    CashfreeTransaction
)

@admin.register(AspirantProfile)
class AspirantProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'target_exam', 'target_level', 'is_refund_eligible', 'is_selected')
    list_filter = ('is_refund_eligible', 'is_selected', 'target_level')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'phone_number')
    readonly_fields = ('onboarding_completed_at',)

@admin.register(FinancialCommitment)
class FinancialCommitmentAdmin(admin.ModelAdmin):
    list_display = ('aspirant', 'amount_paid', 'payment_date', 'is_refunded')
    list_filter = ('is_refunded', 'payment_date')
    search_fields = ('transaction_id', 'aspirant__user__email')

@admin.register(ComplianceLog)
class ComplianceLogAdmin(admin.ModelAdmin):
    list_display = ('aspirant', 'activity_type', 'activity_name', 'is_compliant', 'timestamp')
    list_filter = ('is_compliant', 'activity_type', 'timestamp')
    search_fields = ('aspirant__user__email', 'activity_name')

@admin.register(MandatoryExam)
class MandatoryExamAdmin(admin.ModelAdmin):
    list_display = ('aspirant', 'exam_name', 'exam_level', 'application_form_submitted', 'appeared_for_exam', 'cleared_exam', 'breached_exam_rules')
    list_filter = ('exam_level', 'cleared_exam', 'breached_exam_rules', 'application_form_submitted')
    search_fields = ('aspirant__user__email', 'exam_name')
    
    # Groups the fields visually in the admin edit page
    fieldsets = (
        ('Aspirant & Exam Details', {
            'fields': ('aspirant', 'exam_name', 'exam_level')
        }),
        ('Action Checklist', {
            'fields': ('application_form_submitted', 'admit_card_submitted', 'appeared_for_exam')
        }),
        ('Outcomes (The Trapdoors)', {
            'fields': ('cleared_exam', 'breached_exam_rules')
        }),
    )

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'deadline', 'is_mandatory')
    list_filter = ('is_mandatory', 'deadline')
    search_fields = ('title',)

@admin.register(TaskSubmission)
class TaskSubmissionAdmin(admin.ModelAdmin):
    list_display = ('aspirant', 'task', 'submitted_at', 'is_reviewed')
    list_filter = ('is_reviewed', 'submitted_at')
    search_fields = ('aspirant__user__email', 'task__title')
    
    # Adds a quick action to mark multiple submissions as reviewed at once
    actions = ['mark_as_reviewed']

    @admin.action(description='Mark selected submissions as reviewed')
    def mark_as_reviewed(self, request, queryset):
        queryset.update(is_reviewed=True)

@admin.register(LiveSession)
class LiveSessionAdmin(admin.ModelAdmin):
    list_display = ('title', 'scheduled_time', 'is_active')
    list_filter = ('is_active', 'scheduled_time')

@admin.register(CashfreeTransaction)
class CashfreeTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'order_id', 'is_successful', 'created_at')
    list_filter = ('is_successful', 'created_at')
    readonly_fields = ('created_at',)
    search_fields = ('user__username', 'order_id', 'payment_session_id')