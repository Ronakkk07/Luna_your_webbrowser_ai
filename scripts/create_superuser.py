import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'luna_backend.settings')
django.setup()
from django.contrib.auth import get_user_model
U = get_user_model()
if not U.objects.filter(username='testuser').exists():
    U.objects.create_superuser('testuser', 'test@example.com', 'StrongPassword123')
    print("Superuser created")
else:
    print("Superuser already exists")
