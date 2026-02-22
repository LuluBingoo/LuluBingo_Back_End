from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape


def _resolve_from_email() -> str:
    return getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@lulu-bingo.local")


def send_branded_email(
    to_email: str,
    subject: str,
    heading: str,
    message: str,
    cta_text: str | None = None,
    cta_url: str | None = None,
) -> None:
    if not to_email:
        return

    from_email = _resolve_from_email()
    brand_name = getattr(settings, "BRAND_NAME", "LULU Bingo")
    brand_logo_url = getattr(settings, "BRAND_LOGO_URL", "")
    safe_heading = escape(heading)
    safe_message = escape(message).replace("\n", "<br>")

    logo_html = ""
    if brand_logo_url:
      logo_html = (
        f'<img src="{escape(brand_logo_url)}" alt="{escape(brand_name)} logo" '
        'style="height:40px;width:auto;display:block;margin-bottom:10px;" />'
      )

    cta_html = ""
    if cta_text and cta_url:
        cta_html = (
            f'<div style="margin:24px 0 8px;">'
            f'<a href="{escape(cta_url)}" '
            f'style="display:inline-block;padding:12px 18px;background:#b91c1c;color:#fff;text-decoration:none;border-radius:10px;font-weight:700;">'
            f"{escape(cta_text)}</a></div>"
        )

    html_body = f"""
    <div style=\"margin:0;padding:0;background:#f8fafc;font-family:Inter,Segoe UI,Arial,sans-serif;\">
      <div style=\"max-width:640px;margin:24px auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:16px;overflow:hidden;\">
        <div style=\"background:linear-gradient(135deg,#b91c1c,#7f1d1d);padding:20px 24px;color:#fff;\">
          {logo_html}
          <div style=\"font-size:22px;font-weight:800;letter-spacing:0.3px;\">{escape(brand_name)}</div>
          <div style=\"font-size:13px;opacity:0.9;margin-top:4px;\">Security Notification</div>
        </div>
        <div style=\"padding:24px;\">
          <h2 style=\"margin:0 0 12px;color:#0f172a;font-size:20px;\">{safe_heading}</h2>
          <p style=\"margin:0;color:#334155;line-height:1.65;font-size:15px;\">{safe_message}</p>
          {cta_html}
          <hr style=\"border:none;border-top:1px solid #e2e8f0;margin:20px 0 16px;\" />
          <p style=\"margin:0;color:#475569;font-size:12px;line-height:1.6;\">
            Sent by {escape(brand_name)} Security • From: {escape(from_email)}
          </p>
          <p style=\"margin:24px 0 0;color:#64748b;font-size:12px;line-height:1.5;\">
            This mailbox is not monitored. Please do not reply to this email.
          </p>
        </div>
      </div>
    </div>
    """

    plain_body = f"{heading}\n\n{message}\n\nThis mailbox is not monitored. Please do not reply to this email."

    email = EmailMultiAlternatives(
        subject=subject,
        body=plain_body,
        from_email=from_email,
        to=[to_email],
    )
    email.attach_alternative(html_body, "text/html")
    email.send(fail_silently=getattr(settings, "EMAIL_FAIL_SILENTLY", False))
