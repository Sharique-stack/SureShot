import razorpay
import requests
import uuid
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
    MandatoryExam, LiveSession, CashfreeTransaction
)

# ==========================================
# 1. DASHBOARD & TASK SUBMISSION
# ==========================================

@login_required(login_url='/accounts/login/') 
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
        
        # Only show pending tasks where the deadline is in the future AND the task was assigned after they joined
        # Identify Pending Tasks
        submitted_task_ids = TaskSubmission.objects.filter(
            aspirant=profile
        ).values_list('task_id', flat=True)
        
        # Only show upcoming pending tasks
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


@login_required(login_url='/accounts/login/')
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
# 2. PAYMENT GATEWAY (CASHFREE)
# ==========================================

@login_required(login_url='/accounts/login/')
def initiate_payment(request):
    # Generate a unique Order ID for this transaction
    order_id = f"SURESHOT_{uuid.uuid4().hex[:10].upper()}"
    
    # Determine API URL based on Environment
    if settings.CASHFREE_ENVIRONMENT == 'PRODUCTION':
        api_url = "https://api.cashfree.com/pg/orders"
    else:
        api_url = "https://sandbox.cashfree.com/pg/orders"
        
    headers = {
        "accept": "application/json",
        "x-api-version": "2023-08-01",
        "content-type": "application/json",
        "x-client-id": settings.CASHFREE_APP_ID,
        "x-client-secret": settings.CASHFREE_SECRET_KEY
    }
    
    # Sureshot specific return URL (Cashfree will redirect here after payment)
    return_url = request.build_absolute_uri(f'/verify-payment/?order_id={order_id}')
    
    payload = {
        "customer_details": {
            "customer_id": f"CUST_{request.user.id}",
            "customer_email": request.user.email or "aspirant@sureshot.com",
            "customer_phone": "9999999999", # Replace with actual user phone if collected
            "customer_name": request.user.username
        },
        "order_meta": {
            "return_url": return_url
        },
        "order_id": order_id,
        "order_amount": 40000.00,
        "order_currency": "INR"
    }
    
    # Request Payment Session from Cashfree
    response = requests.post(api_url, json=payload, headers=headers)
    
    if response.status_code == 200:
        cf_data = response.json()
        payment_session_id = cf_data.get('payment_session_id')
        
        # Log the pending transaction in the database
        CashfreeTransaction.objects.create(
            user=request.user,
            amount=40000.00,
            order_id=order_id,
            is_successful=False 
        )
        
        context = {
            'payment_session_id': payment_session_id,
            'environment': settings.CASHFREE_ENVIRONMENT.lower(),
        }
        return render(request, 'tracker/checkout.html', context)
    else:
        messages.error(request, "Failed to initialize secure payment gateway. Please try again.")
        return redirect('/dashboard/')


@login_required(login_url='/accounts/login/')
def verify_payment(request):
    # Cashfree returns the user here with the order_id in the URL
    order_id = request.GET.get('order_id')
    
    if not order_id:
        return HttpResponseBadRequest("Invalid Request: Order ID missing.")
        
    # Verify the actual status via API to prevent spoofing
    if settings.CASHFREE_ENVIRONMENT == 'PRODUCTION':
        api_url = f"https://api.cashfree.com/pg/orders/{order_id}"
    else:
        api_url = f"https://sandbox.cashfree.com/pg/orders/{order_id}"
        
    headers = {
        "accept": "application/json",
        "x-api-version": "2023-08-01",
        "x-client-id": settings.CASHFREE_APP_ID,
        "x-client-secret": settings.CASHFREE_SECRET_KEY
    }
    
    response = requests.get(api_url, headers=headers)
    
    if response.status_code == 200:
        order_data = response.json()
        
        if order_data.get('order_status') == 'PAID':
            # 1. Update Transaction Ledger
            transaction = get_object_or_404(CashfreeTransaction, cf_order_id=order_id)
            transaction.is_successful = True
            transaction.save()

            # 2. Unlock the Sureshot Command Tower (Gateway)
            if hasattr(request.user, 'aspirantprofile'):
                profile = request.user.aspirantprofile
                profile.is_refund_eligible = True # Activates the Green Shield
                profile.save()
            else:
                # If they don't have a profile yet, create one
                AspirantProfile.objects.create(
                    user=request.user,
                    is_refund_eligible=True
                )

            messages.success(request, "Enrollment Complete! Accountability Shield Activated.")
            return redirect('/dashboard/')
            
        else:
            messages.error(request, "Payment was not completed. Gateway remains locked.")
            return redirect('/dashboard/')
            
    return HttpResponseBadRequest("Security Alert: Unable to verify transaction with Cashfree.")

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
            
            # --- THE LATE JOINER PATCH ---
            # If the task deadline passed before the user even created their account, ignore it.
            if task.deadline < profile.user.date_joined:
                continue 
            # -----------------------------
            
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
                
                # Also ignore warnings for tasks that were due before they joined (edge case protection)
                if task.deadline < profile.user.date_joined:
                    continue

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