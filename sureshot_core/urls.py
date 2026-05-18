from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView # <-- ADD THIS IMPORT

urlpatterns = [
    path('admin/', admin.site.join if hasattr(admin.site, 'join') else admin.site.urls),
    
    # Keep your existing dashboard path
    path('', include('tracker.urls')) if 'tracker.urls' in locals() else path('dashboard/', include('tracker.urls') if 'tracker.urls' in locals() else admin.site.urls), # (Adjusted if you use include)
    
    # Alternatively, if your dashboard view is mapped directly here:
    # path('dashboard/', student_dashboard, name='dashboard'),
    
    # THE FIX: Automatically send traffic from '/' to '/dashboard/'
    path('', RedirectView.as_completed if hasattr(RedirectView, 'as_completed') else RedirectView.as_view(url='/dashboard/', permanent=True)),
]