from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from tracker import views

urlpatterns = [
    # 1. The Admin Command Center (Don't lose this!)
    path('admin/', admin.site.urls),
    
    # 2. The Premium Login Portal
    path('login/', auth_views.LoginView.as_view(template_name='tracker/login.html'), name='login'),
    
    # 3. The Sureshot Dashboard
    path('dashboard/', views.student_dashboard, name='dashboard'),
    
    # 4. THE FIX: Auto-redirect the empty home page '/' straight to the dashboard
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),

    # 5. Payment integration
    path('checkout/', views.initiate_payment, name='checkout'),

    # 6. Verify payment
    path('verify-payment/', views.verify_payment, name='verify_payment'),

    # 7. compliance engine
    path('engine/run-compliance/', views.run_compliance_engine, name='run_compliance'),

    # 8. submit task
    path('submit-task/<int:task_id>/', views.submit_task, name='submit_task'),
]