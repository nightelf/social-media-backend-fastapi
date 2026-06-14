"""Pluggable code delivery, selected by the NOTIFIER env var (console | smtp | twilio)."""
import logging

from .config import settings

logger = logging.getLogger("notifier")


class ConsoleNotifier:
    def send(self, *, channel, destination, code, purpose):
        logger.warning("[notifier:console] %s code for %s via %s -> %s",
                       purpose, destination, channel, code)
        print(f"\n*** {channel} code to {destination} ({purpose}): {code} ***\n", flush=True)


class SMTPNotifier:
    def send(self, *, channel, destination, code, purpose):
        if channel != "EMAIL":
            return ConsoleNotifier().send(channel=channel, destination=destination,
                                          code=code, purpose=purpose)
        import os
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["Subject"] = "Your verification code"
        msg["From"] = os.environ.get("SMTP_FROM", "no-reply@example.com")
        msg["To"] = destination
        msg.set_content(f"Your code is {code}. Expires in {settings.CODE_TTL_MINUTES} minutes.")
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 587))) as s:
            s.starttls()
            if os.environ.get("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            s.send_message(msg)


class TwilioNotifier:
    def send(self, *, channel, destination, code, purpose):
        if channel != "SMS":
            return SMTPNotifier().send(channel=channel, destination=destination,
                                       code=code, purpose=purpose)
        import os

        from twilio.rest import Client

        client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
        client.messages.create(
            body=f"Your code is {code} (expires in {settings.CODE_TTL_MINUTES} min).",
            from_=os.environ["TWILIO_FROM"],
            to=destination,
        )


_NOTIFIERS = {"console": ConsoleNotifier, "smtp": SMTPNotifier, "twilio": TwilioNotifier}


def get_notifier():
    return _NOTIFIERS.get(settings.NOTIFIER, ConsoleNotifier)()
