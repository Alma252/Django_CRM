import datetime
import logging
from celery import Celery
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.conf import settings
from common.models import Comment, Profile, User
from common.token_generator import account_activation_token

logger = logging.getLogger(__name__)

app = Celery("redis://")

@shared_task
def send_email_to_new_user(user_id):
    """Send activation email to newly registered users."""

    user = User.objects.filter(id=user_id).first()
    if not user:
        logger.warning(f"send_email_to_new_user: No user found with id={user_id}")
        return

    try:
        # Generate activation data
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = account_activation_token.make_token(user)
        expires_at = timezone.now() + datetime.timedelta(hours=2)

        # Save activation info in DB
        user.activation_key = token
        user.key_expires = expires_at
        user.save()

        # Build activation link
        complete_url = (
            f"{settings.DOMAIN_NAME}/auth/activate-user/{uid}/{token}/"
        )

        # Prepare context for email template
        context = {
            "url": settings.DOMAIN_NAME,
            "uid": uid,
            "token": token,
            "activation_key": user.activation_key,
            "complete_url": complete_url,
            "expires_at": expires_at,
        }

        # Render email
        subject = "Welcome to Bottle CRM"
        html_content = render_to_string("user_status_in.html", context)
        msg = EmailMessage(
            subject,
            html_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.content_subtype = "html"
        msg.send()

        logger.info(f"Activation email sent to {user.email}")

    except Exception as e:
        logger.error(f"Failed to send activation email to {user.email}: {e}")


@shared_task
def send_email_user_mentions(comment_id, called_from):
    comment = Comment.objects.filter(id=comment_id).first()
    if not comment:
        return
    mentioned_usernames = {
        word.strip("@").strip(",")
        for word in comment.comment.split()
        if word.startswith("@")

    }
    users = User.objects.filter(username_in=mentioned_usernames, is_active=True)
    recipients = [user.email for user in users]

    subject_map = {
        "accounts": "New comment on Account.",
        "contacts": "New comment on Contact.",
        "leads": "New comment on Lead.",
        "opportunity": "New comment on Opportunity.",
        "cases": "New comment on Case.",
        "tasks": "New comment on Task.",
        "invoices": "New comment on Invoice.",
        "events": "New comment on Event.",
    }

    subject = subject_map.get(called_from, "New comment.")

    context = {
        "commented_by": comment.commented_by,
        "comment_description": comment.comment,
        "url": settings.DOMAIN_NAME,
    }

    for user in users:
        context["mentioned_user"] = user.username
        html_content = render_to_string("comment_email.html", context)
        msg = EmailMessage(
            subject,
            html_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.content_subtype = "html"
        msg.send()




@app.task
def send_email_user_status(
    user_id,
    status_changed_user="",
):
    """Send Mail To Users Regarding their status i.e active or inactive"""
    user = User.objects.filter(id=user_id).first()
    if user:
        context = {}
        context["message"] = "deactivated"
        context["email"] = user.email
        context["url"] = settings.DOMAIN_NAME
        if user.has_marketing_access:
            context["url"] = context["url"] + "/marketing"
        if user.is_active:
            context["message"] = "activated"
        context["status_changed_user"] = status_changed_user
        if context["message"] == "activated":
            subject = "Account Activated "
            html_content = render_to_string(
                "user_status_activate.html", context=context
            )
        else:
            subject = "Account Deactivated "
            html_content = render_to_string(
                "user_status_deactivate.html", context=context
            )
        recipients = []
        recipients.append(user.email)
        if recipients:
            msg = EmailMessage(
                subject,
                html_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            )
            msg.content_subtype = "html"
            msg.send()


@app.task
def send_email_user_delete(
    user_email,
    deleted_by="",
):
    """Send Mail To Users When their account is deleted"""
    if user_email:
        context = {}
        context["message"] = "deleted"
        context["deleted_by"] = deleted_by
        context["email"] = user_email
        recipients = []
        recipients.append(user_email)
        subject = "CRM : Your account is Deleted. "
        html_content = render_to_string("user_delete_email.html", context=context)
        if recipients:
            msg = EmailMessage(
                subject,
                html_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            )
            msg.content_subtype = "html"
            msg.send()


@app.task
def resend_activation_link_to_user(
    user_email="",
):
    """Send Mail To Users When their account is created"""

    user_obj = User.objects.filter(email=user_email).first()
    user_obj.is_active = False
    user_obj.save()
    if user_obj:
        context = {}
        context["user_email"] = user_email
        context["url"] = settings.DOMAIN_NAME
        context["uid"] = (urlsafe_base64_encode(force_bytes(user_obj.pk)),)
        context["token"] = account_activation_token.make_token(user_obj)
        time_delta_two_hours = datetime.datetime.strftime(
            timezone.now() + datetime.timedelta(hours=2), "%Y-%m-%d-%H-%M-%S"
        )
        context["token"] = context["token"]
        activation_key = context["token"] + time_delta_two_hours
        # Profile.objects.filter(user=user_obj).update(
        #     activation_key=activation_key,
        #     key_expires=timezone.now() + datetime.timedelta(hours=2),
        # )
        user_obj.activation_key = activation_key
        user_obj.key_expires = timezone.now() + datetime.timedelta(hours=2)
        user_obj.save()

        context["complete_url"] = context[
            "url"
        ] + "/auth/activate_user/{}/{}/{}/".format(
            context["uid"][0],
            context["token"],
            activation_key,
        )
        recipients = [context["complete_url"]]
        recipients.append(user_email)
        subject = "Welcome to Bottle CRM"
        html_content = render_to_string("user_status_in.html", context=context)
        if recipients:
            msg = EmailMessage(
                subject,
                html_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            )
            msg.content_subtype = "html"
            msg.send()


@app.task
def send_email_to_reset_password(user_email):
    """Send Mail To Users When their account is created"""
    user = User.objects.filter(email=user_email).first()
    context = {}
    context["user_email"] = user_email
    context["url"] = settings.DOMAIN_NAME
    context["uid"] = (urlsafe_base64_encode(force_bytes(user.pk)),)
    context["token"] = default_token_generator.make_token(user)
    context["token"] = context["token"]
    context["complete_url"] = context[
        "url"
    ] + "/auth/reset-password/{uidb64}/{token}/".format(
        uidb64=context["uid"][0], token=context["token"]
    )
    subject = "Set a New Password"
    recipients = []
    recipients.append(user_email)
    html_content = render_to_string(
        "registration/password_reset_email.html", context=context
    )
    if recipients:
        msg = EmailMessage(
            subject, html_content, from_email=settings.DEFAULT_FROM_EMAIL, to=recipients
        )
        msg.content_subtype = "html"
        msg.send()