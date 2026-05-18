from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class AspirantProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='sureshot_profile')
    phone_number = models.CharField(max_length=15)
    target_exam = models.CharField(max_length=100) 
    
    # LEVELING STRATEGY: 0 to 7 (e.g., Level 4 = SSC CGL, Level 7 = UPSC)
    target_level = models.IntegerField(default=4)
    
    # STATUS TRACKING
    is_refund_eligible = models.BooleanField(default=True)
    is_selected = models.BooleanField(default=False) # Success indicator
    refund_voided_reason = models.TextField(blank=True, null=True)
    onboarding_completed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.get_full_name()} - Level {self.target_level}"

    @property
    def get_compliance_status(self):
        """
        The Sureshot Algo: Decides if the dashboard is Green, Yellow, or Red.
        """
        # 1. Immediate RED: If a mandatory exam rule is breached
        if self.mandatory_exams.filter(breached_exam_rules=True).exists() or not self.is_refund_eligible:
            return 'RED', self.refund_voided_reason or 'Refund Voided: Compliance Failure'

        # 2. Calculate compliance percentage
        total_logs = self.compliance_logs.count()
        compliant_logs = self.compliance_logs.filter(is_compliant=True).count()
        
        # Avoid division by zero
        if total_logs == 0:
            return 'GREEN', 'Welcome! Stay on track.'

        score = (compliant_logs / total_logs) * 100

        # 3. Status logic
        if score >= 90:
            return 'GREEN', 'Elite Performance: Protection Active'
        elif score >= 70:
            return 'YELLOW', 'Warning: Salvageable. Catch up on tasks.'
        else:
            return 'RED', 'Void: Participation below 70%'


class FinancialCommitment(models.Model):
    aspirant = models.OneToOneField(AspirantProfile, on_delete=models.CASCADE)
    amount_paid = models.DecimalField(max_digits=8, decimal_places=2, default=40000.00)
    payment_date = models.DateTimeField(auto_now_add=True)
    transaction_id = models.CharField(max_length=100, unique=True)
    is_refunded = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.aspirant.user.email} - Rs. {self.amount_paid}"


class ComplianceLog(models.Model):
    ACTIVITY_CHOICES = [
        ('LIVE_CLASS', 'Live Class Attendance'),
        ('MOCK_TEST', 'Mock Test Attempt'),
        ('ASSIGNMENT', 'Daily Target / Assignment'),
        ('EXAM_PROOF', 'Official Exam Admit Card/Scorecard')
    ]

    aspirant = models.ForeignKey(AspirantProfile, on_delete=models.CASCADE, related_name='compliance_logs')
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_CHOICES)
    activity_name = models.CharField(max_length=255) 
    score_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_compliant = models.BooleanField(default=True) 
    timestamp = models.DateTimeField(auto_now_add=True)
    proof_file = models.FileField(upload_to='compliance_proofs/', blank=True, null=True)

    def __str__(self):
        status = "COMPLIANT" if self.is_compliant else "VIOLATION"
        return f"[{status}] {self.aspirant.user.email} - {self.activity_name}"

    def save(self, *args, **kwargs):
        # TRAPDOOR: If manual entry sets compliance to False, nuke refund eligibility
        if not self.is_compliant and self.aspirant.is_refund_eligible:
            self.aspirant.is_refund_eligible = False
            self.aspirant.refund_voided_reason = f"Missed/Failed '{self.activity_name}' on {timezone.now().strftime('%d %b')}"
            self.aspirant.save()
        super().save(*args, **kwargs)


class MandatoryExam(models.Model):
    aspirant = models.ForeignKey(AspirantProfile, on_delete=models.CASCADE, related_name='mandatory_exams')
    exam_name = models.CharField(max_length=200)
    exam_level = models.IntegerField(default=4) # 0-7
    
    application_form_submitted = models.BooleanField(default=False)
    admit_card_submitted = models.BooleanField(default=False)
    appeared_for_exam = models.BooleanField(default=False)
    
    cleared_exam = models.BooleanField(default=False)
    breached_exam_rules = models.BooleanField(default=False)

    def __str__(self):
        return f"[Lvl {self.exam_level}] {self.exam_name} - {self.aspirant.user.first_name}"

    def save(self, *args, **kwargs):
        # ELIMINATION STRATEGY: Void refund if a job of equal or higher level is cleared
        if self.cleared_exam and self.aspirant.is_refund_eligible:
            if self.exam_level >= self.aspirant.target_level:
                self.aspirant.is_refund_eligible = False
                self.aspirant.is_selected = True
                self.aspirant.refund_voided_reason = f"SUCCESS: Cleared Level {self.exam_level} ({self.exam_name})"
                self.aspirant.save()

        # PENALTY: Void if they just didn't show up
        if self.breached_exam_rules and self.aspirant.is_refund_eligible:
            self.aspirant.is_refund_eligible = False
            self.aspirant.refund_voided_reason = f"Failed to appear/apply for {self.exam_name}"
            self.aspirant.save()

        super().save(*args, **kwargs)


class Task(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    deadline = models.DateTimeField()
    is_mandatory = models.BooleanField(default=True)

    def __str__(self):
        return self.title


class TaskSubmission(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    aspirant = models.ForeignKey(AspirantProfile, on_delete=models.CASCADE)
    submitted_at = models.DateTimeField(auto_now_add=True)
    proof_file = models.FileField(upload_to='task_submissions/', blank=True, null=True)
    is_reviewed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.aspirant.user.first_name} - {self.task.title}"

class LiveSession(models.Model):
    title = models.CharField(max_length=200)
    scheduled_time = models.DateTimeField()
    meeting_link = models.URLField(max_length=500)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title