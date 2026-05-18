from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import AspirantProfile, ComplianceLog, Task, TaskSubmission, MandatoryExam, LiveSession

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