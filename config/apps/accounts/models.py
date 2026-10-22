import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=120, default="Nuser")
    is_premium = models.BooleanField(default=True)
    avatar_url = models.URLField(
        max_length = 500,
        blank = True,
        default = "https://i.pravatar.cc/150?img=47",
    )
    current_symbol =  models.CharField(max_length = 5, default = "$")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username" , "full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.email})"