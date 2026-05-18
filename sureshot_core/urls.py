from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.contrib.auth.models import User

# Temporary function to force-create your admin account
def secret_admin_creator(request):
    username = "admin"
    email = "founder@govtdrish.com"
    password = "MasterSureshot2026!" # Choose your secure password here
    
    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(username, email, password)
        return HttpResponse(f"🚀 Success! Master account '{username}' has been injected into Neon.")
    else:
        # If user exists, let's force reset the password just in case there was a typo before
        u = User.objects.get(username=username)
        u.set_password(password)
        u.is_staff = True
        u.is_superuser = True
        u.save()
        return HttpResponse(f"🔄 Password reset successful! Master account '{username}' is ready.")

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('tracker.urls') if 'tracker.urls' in locals() else admin.site.urls), # Adjust based on your routing
    
    # THE SECRET BACKDOOR (Delete this after you log in!)
    path('create-master-admin-xyz/', secret_admin_creator),
]