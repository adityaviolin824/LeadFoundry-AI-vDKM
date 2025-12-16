import smtplib
import os
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr

load_dotenv()

def send_lead_notification(
    recipient_email: str,
    excel_path: str | None = None,
):
    sender_email = os.getenv("EMAIL_SENDER")
    app_password = os.getenv("EMAIL_PASSWORD")

    display_name = "LeadFoundry AI"

    if not sender_email or not app_password:
        print("Error: Missing credentials in .env file")
        return False

    subject = "LeadFoundry Run Complete — Results Attached"

    html_content = """
    <html>
    <body style="font-family: Arial, Helvetica, sans-serif; line-height: 1.6;">
        <p>Hello,</p>

        <p>
        Your LeadFoundry run has completed successfully.
        </p>

        <p>
        The attached Excel file contains the finalized output — consolidated,
        deduplicated, and sorted for immediate use.
        </p>

        <p>
        If you’d like to adjust inputs, refine filters, or run a new search,
        you can start another run anytime.
        </p>

        <p style="margin-top: 24px;">
        <strong>LeadFoundry</strong><br>
        <span style="color: #666;">
            Built to extract signal from noisy markets.
        </span>
        </p>
    </body>
    </html>
    """

    try:
        msg = MIMEMultipart()
        msg["From"] = formataddr((display_name, sender_email))
        msg["To"] = recipient_email
        msg["Subject"] = subject

        excel_attached = False
        excel_error_note = ""

        # =========================
        # Attach Excel if available
        # =========================
        if excel_path:
            try:
                if not os.path.exists(excel_path):
                    raise FileNotFoundError(f"Excel file not found: {excel_path}")

                with open(excel_path, "rb") as f:
                    part = MIMEBase(
                        "application",
                        "vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                    part.set_payload(f.read())

                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{os.path.basename(excel_path)}"',
                )
                msg.attach(part)
                excel_attached = True

            except Exception as e:
                excel_error_note = (
                    "<hr>"
                    "<p><b>⚠️ Note:</b> The lead generation completed successfully, "
                    "but the Excel file could not be attached for this run.</p>"
                )
                print(f"⚠️ Excel attachment skipped: {e}")

        # =========================
        # Final email body
        # =========================
        final_html = html_content
        if not excel_attached and excel_path:
            final_html += excel_error_note

        msg.attach(MIMEText(final_html, "html"))

        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()

        print(f"Email sent to {recipient_email} from {display_name}")
        return True

    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False
