from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import AspirantProfile, ComplianceLog, Task, TaskSubmission, MandatoryExam, LiveSession
import razorpay
from django.conf import settings
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import PaymentTransaction

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