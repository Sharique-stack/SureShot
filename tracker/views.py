from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import AspirantProfile, ComplianceLog, Task, TaskSubmission, MandatoryExam, LiveSession
import razorpay
from django.conf import settings
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import PaymentTransaction
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Task, AspirantProfile, ComplianceLog
from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .models import Task, AspirantProfile, ComplianceLog

@login_required(login_url='/admin/login/') 
def student_dashboard(request):
    try:
        # 1. Identify the student
        profile = AspirantProfile.objects.get(user=request.user)
        
        # 2. Fetch Exams & Logs
        mandatory_exams = MandatoryExam.objects.filter(aspirant=profile).order_by('exam_level')
        logs = ComplianceLog.objects.filter(aspirant=profile).order_by('-timestamp')
        
        # 3. Identify Pending Tasks
        submitted_task_ids = TaskSubmission.objects.filter(aspirant=profile).values_list('task_id', flat=True)
        pending_tasks = Task.objects.exclude(id__in=submitted_task_ids).order_by('deadline')
        
        # 4. Fetch the next active Live Session
        next_session = LiveSession.objects.filter(is_active=True).order_by('scheduled_time').first()
        
    except AspirantProfile.DoesNotExist:
        # Fallbacks if the logged-in user doesn't have an AspirantProfile yet
        profile = None
        mandatory_exams = []
        pending_tasks = []
        logs = []
        next_session = None

    # 5. Send everything to the frontend
    context = {
        'profile': profile,
        'mandatory_exams': mandatory_exams,
        'pending_tasks': pending_tasks,
        'logs': logs,
        'next_session': next_session,
    }
    
    return render(request, 'tracker/dashboard.html', context)

@login_required
def initiate_payment(request):
    # ₹40,000 final premium price point. 
    # Razorpay expects amounts in paise (1 INR = 100 paise), so ₹40,000 = 4000000 paise.
    amount_in_paise = 4000000 
    
    # Initialize the Razorpay client with your keys
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    
    # 1. Create the order payload for Razorpay's API
    order_data = {
        'amount': amount_in_paise,
        'currency': 'INR',
        'payment_capture': '1'  # 1 means automatically capture payment immediately upon authorization
    }
    
    # 2. Call Razorpay API to generate a unique Order ID
    razorpay_order = client.order.create(data=order_data)
    razorpay_order_id = razorpay_order['id']
    
    # 3. Log this transaction initialization in our Neon database ledger
    PaymentTransaction.objects.create(
        user=request.user,
        amount=40000.00,
        razorpay_order_id=razorpay_order_id,
        is_successful=False  # Stays False until callback verifies payment success
    )
    
    # 4. Pass transaction variables to the frontend payment gateway popup
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
        # Extract the verification tokens sent back by the Razorpay checkout overlay
        payment_id = request.POST.get('razorpay_payment_id', '')
        order_id = request.POST.get('razorpay_order_id', '')
        signature = request.POST.get('razorpay_signature', '')

        # Initialize the official client
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

        # Create the exact dictionary structure required by the SDK validator
        params_dict = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }

        try:
            # Cryptographic verification step
            # This hashes the order_id + payment_id using your hidden Key Secret
            # and matches it perfectly against the signature header.
            client.utility.verify_payment_signature(params_dict)

            # Locate the matching transaction entry in our Neon database ledger
            transaction = PaymentTransaction.objects.get(razorpay_order_id=order_id)
            transaction.razorpay_payment_id = payment_id
            transaction.razorpay_signature = signature
            transaction.is_successful = True
            transaction.save()

            # Ensure an AspirantProfile exists for this user and activate them
            # (Assuming an AspirantProfile model linked to User)
            if hasattr(transaction.user, 'aspirantprofile'):
                profile = transaction.user.aspirantprofile
                profile.is_active = True # Flips the green dashboard shield to active
                profile.save()

            messages.success(request, "Enrollment Complete! Welcome to Sureshot.")
            return redirect('/dashboard/')

        except razorpay.errors.SignatureVerificationError:
            # Triggered if the keys don't match up, implying an altered request payload
            return HttpResponseBadRequest("Security Alert: Cryptographic Signature Verification Failed.")
        except PaymentTransaction.DoesNotExist:
            return HttpResponseBadRequest("Transaction record not found in system ledger.")
            
    return HttpResponseBadRequest("Invalid Request Method.")


@csrf_exempt
@csrf_exempt
def run_compliance_engine(request):
    if request.GET.get('token') != settings.SECRET_KEY:
        return JsonResponse({"error": "Unauthorized"}, status=403)

    now = timezone.now()
    warning_window = now + timedelta(hours=24)
    
    shields_dropped = 0
    warnings_sent = 0
    
    # 1. Get all aspirants who are still eligible for a refund
    aspirants = AspirantProfile.objects.filter(is_refund_eligible=True)
    
    for profile in aspirants:
        # --- PHASE A: RED DROP ENFORCEMENT (Past Deadlines) ---
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
                break # Shield is dropped, no need to check other tasks for this user

        # --- PHASE B: YELLOW ALERT WARNING (Next 24 Hours) ---
        # Only check warnings if their shield hasn't already dropped
        if profile.is_refund_eligible:
            upcoming_tasks = Task.objects.filter(
                is_mandatory=True, 
                deadline__gt=now, 
                deadline__lte=warning_window
            )
            
            for task in upcoming_tasks:
                submitted = task.tasksubmission_set.filter(aspirant=profile).exists()
                if not submitted:
                    # Check if we already warned them about this specific task
                    already_warned = ComplianceLog.objects.filter(
                        user=profile.user,
                        violation_type="Yellow Alert Warning",
                        details__contains=task.title
                    ).exists()

                    if not already_warned:
                        # 1. Send the Email
                        send_mail(
                            subject=f"URGENT: 24-Hour Warning for {task.title}",
                            message=f"Hi {profile.user.username},\n\nYou have less than 24 hours to submit '{task.title}'. If you miss this deadline, your ₹40,000 refund guarantee will be permanently voided.\n\nLog in to your Sureshot dashboard to submit immediately.",
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[profile.user.email],
                            fail_silently=True, # Set to False in production to catch email errors
                        )
                        
                        # 2. Log the warning so we don't spam them next hour
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