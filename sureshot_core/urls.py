from django.contrib.auth import views as auth_views
from django.urls import path
from tracker import views

urlpatterns = [
    # Routes to your new Tailwind login.html
    path('login/', auth_views.LoginView.as_view(template_name='tracker/login.html'), name='login'),
    
    # Routes to your Command Tower dashboard.html
    path('dashboard/', views.student_dashboard, name='dashboard'),
]