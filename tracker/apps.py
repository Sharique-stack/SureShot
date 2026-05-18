from django.apps import AppConfig
import os

class TrackerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tracker'

    def ready(self):
        # This code runs automatically when Gunicorn starts the server
        from django.contrib.auth.models import User
        
        username = "admin"
        email = "founder@govtdrish.com"
        password = "MasterSureshot2026!"  # Your master password
        
        try:
            if not User.objects.filter(username=username).exists():
                User.objects.create_superuser(username=username, email=email, password=password)
                print("🚀 AUTO-ADMIN: Superuser created successfully!")
            else:
                user = User.objects.get(username=username)
                user.set_password(password)
                user.is_staff = True
                user.is_superuser = True
                user.is_active = True
                user.save()
                print("🔄 AUTO-ADMIN: Master account verified and password reset!")
        except Exception as e:
            # Prevents deployment crash if database tables aren't fully migrated yet
            print(f"⚠️ AUTO-ADMIN status: {e}")