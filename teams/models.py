
import arrow
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import Org, Profile
from common.base import BaseModel


class Team(BaseModel):
    name = models.CharField(max_length=100)
    description = models.TextField()
    users = models.ManyToManyField(Profile, related_name="user_teams")
    org = models.ForeignKey(Org, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Team"
        verbose_name_plural = "Teams"
        db_table = "teams"
        ordering = ("-created_at",)

    def __str__(self):
        return self.name

    @property
    def created_on_arrow(self):
        return arrow.get(self.created_at).humanize()

    def get_users(self):
        return ", ".join([str(user) for user in self.users.all()])
