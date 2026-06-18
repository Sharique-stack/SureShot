import razorpay
from datetime import timedelta

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.core.mail import send_mail

from .models import (
    AspirantProfile, ComplianceLog, Task, TaskSubmission, 
    MandatoryExam, LiveSession, PaymentTransaction
)


# ==========================================
# 1. DASHBOARD & TASK SUBMISSION
# ==========================================

@login_required(login_url='/admin/login/') 
def student_dashboard(request):
    # Safely check if the logged-in user actually has an AspirantProfile
    if hasattr(request.user, 'aspirantprofile'):
        profile = request.user.aspirantprofile
        now = timezone.now()
        
        # Fetch Exams & Logs
        mandatory_exams = MandatoryExam.objects.filter(aspirant=profile).order_by('exam_level')
        logs = ComplianceLog.objects.filter(user=request.user).order_by('-timestamp') 
        
        # Identify Pending Tasks
        submitted_task_ids = TaskSubmission.objects.filter(
            aspirant=profile
        ).values_list('task_id', flat=True)
        
        pending_tasks = Task.objects.exclude(
            id__in=submitted_task_ids
        ).filter(deadline__gte=now).order_by('deadline')
        
        # Fetch Live Session
        next_session = LiveSession.objects.filter(is_active=True).order_by('scheduled_time').first()

    else:
        # Fallback for admins or users who haven't completed onboarding
        profile = None
        mandatory_exams = []
        pending_tasks = []
        logs = []
        next_session = None

    context = {
        'profile': profile,
        'mandatory_exams': mandatory_exams,
        'pending_tasks': pending_tasks,
        'logs': logs,
        'next_session': next_session,
    }
    
    return render(request, 'tracker/dashboard.html', context)


@login_required(login_url='/admin/login/')
def submit_task(request, task_id):
    if request.method == "POST":
        task = get_object_or_404(Task, id=task_id)
        
        if not hasattr(request.user, 'aspirantprofile'):
            messages.error(request, "Error: You must be an enrolled aspirant to submit tasks.")
            return redirect('/dashboard/')

        profile = request.user.aspirantprofile

        if TaskSubmission.objects.filter(task=task, aspirant=profile).exists():
            messages.warning(request, "Task already submitted.")
            return redirect('/dashboard/')

        # Grab either a file upload OR a text link from the form
        proof = request.FILES.get('proof_file') or request.POST.get('proof_file')

        if proof:
            TaskSubmission.objects.create(
                task=task,
                aspirant=profile,
                proof_file=proof
            )
            messages.success(request, f"Proof logged for '{task.title}'. Shield secured.")
        else:
            messages.error(request, "You must attach a file or link to submit.")

    return redirect('/dashboard/')


# ==========================================
# 2. PAYMENT GATEWAY (RAZORPAY)
# ==========================================

@login_required
def initiate_payment(request):
    amount_in_paise = 4000000 
    
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    
    order_data = {
        'amount': amount_in_paise,
        'currency': 'INR',
        'payment_capture': '1' 
    }
    
    razorpay_order = client.order.create(data=order_data)
    razorpay_order_id = razorpay_order['id']
    
    PaymentTransaction.objects.create(
        user=request.user,
        amount=40000.00,
        razorpay_order_id=razorpay_order_id,
        is_successful=False 
    )
    
    context = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        'amount': amount_in_paise,
        'user_email': request.user.email,
        'user_username': request.user.username,
    }
    
    return render(request, 'tracker/checkout.html', context)


@csrf_exempt
def verify_payment(request):
    if request.method == "POST":
        payment_id = request.POST.get('razorpay_payment_id', '')
        order_id = request.POST.get('razorpay_order_id', '')
        signature = request.POST.get('razorpay_signature', '')

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

        params_dict = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }

        try:
            client.utility.verify_payment_signature(params_dict)

            transaction = PaymentTransaction.objects.get(razorpay_order_id=order_id)
            transaction.razorpay_payment_id = payment_id
            transaction.razorpay_signature = signature
            transaction.is_successful = True
            transaction.save()

            if hasattr(transaction.user, 'aspirantprofile'):
                profile = transaction.user.aspirantprofile
                profile.is_active = True 
                profile.save()

            messages.success(request, "Enrollment Complete! Welcome to Sureshot.")
            return redirect('/dashboard/')

        except razorpay.errors.SignatureVerificationError:
            return HttpResponseBadRequest("Security Alert: Cryptographic Signature Verification Failed.")
        except PaymentTransaction.DoesNotExist:
            return HttpResponseBadRequest("Transaction record not found in system ledger.")
            
    return HttpResponseBadRequest("Invalid Request Method.")


# ==========================================
# 3. ACCOUNTABILITY ENGINE (CRON)
# ==========================================

@csrf_exempt
def run_compliance_engine(request):
    if request.GET.get('token') != settings.SECRET_KEY:
        return JsonResponse({"error": "Unauthorized"}, status=403)

    now = timezone.now()
    warning_window = now + timedelta(hours=24)
    
    shields_dropped = 0
    warnings_sent = 0
    
    aspirants = AspirantProfile.objects.filter(is_refund_eligible=True)
    
    for profile in aspirants:
        # --- PHASE A: RED DROP ENFORCEMENT ---
        mandatory_tasks = Task.objects.filter(is_mandatory=True, deadline__lt=now)
        for task in mandatory_tasks:
            submitted = task.tasksubmission_set.filter(aspirant=profile).exists()
            if not submitted:
                profile.is_refund_eligible = False
                profile.refund_voided_reason = f"Missed deadline: {task.title}"
                profile.save()
                
                ComplianceLog.objects.create(
                    user=profile.user,
                    violation_type="Missed Mandatory Deadline",
                    details=f"Failed to submit: {task.title} (Due: {task.deadline})",
                    timestamp=now
                )
                shields_dropped += 1
                break 

        # --- PHASE B: YELLOW ALERT WARNING ---
        if profile.is_refund_eligible:
            upcoming_tasks = Task.objects.filter(
                is_mandatory=True, 
                deadline__gt=now, 
                deadline__lte=warning_window
            )
            
            for task in upcoming_tasks:
                submitted = task.tasksubmission_set.filter(aspirant=profile).exists()
                if not submitted:
                    already_warned = ComplianceLog.objects.filter(
                        user=profile.user,
                        violation_type="Yellow Alert Warning",
                        details__contains=task.title
                    ).exists()

                    if not already_warned:
                        send_mail(
                            subject=f"URGENT: 24-Hour Warning for {task.title}",
                            message=f"Hi {profile.user.username},\n\nYou have less than 24 hours to submit '{task.title}'. If you miss this deadline, your ₹40,000 refund guarantee will be permanently voided.\n\nLog in to your Sureshot dashboard to submit immediately.",
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[profile.user.email],
                            fail_silently=True, 
                        )
                        
                        ComplianceLog.objects.create(
                            user=profile.user,
                            violation_type="Yellow Alert Warning",
                            details=f"Warning sent for: {task.title}",
                            timestamp=now
                        )
                        warnings_sent += 1

    return JsonResponse({
        "status": "Sweep Complete",
        "shields_dropped": shields_dropped,
        "warnings_sent": warnings_sent
    })