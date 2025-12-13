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
    subject: str,
    html_content: str,
    excel_path: str | None = None,
):
    sender_email = os.getenv("EMAIL_SENDER")
    app_password = os.getenv("EMAIL_PASSWORD")

    display_name = "LeadFoundry AI"

    if not sender_email or not app_password:
        print("❌ Error: Missing credentials in .env file")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = formataddr((display_name, sender_email))
        msg["To"] = recipient_email
        msg["Subject"] = subject

        excel_attached = False
        excel_error_note = ""

        # Attempt Excel attachment if path provided
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
                    "<p><b>⚠️ Note:</b> We encountered an unexpected issue while "
                    "generating or attaching the Excel file for this run.</p>"
                    "<p>The lead generation completed, but the spreadsheet could not be attached.</p>"
                )
                print(f"⚠️ Excel attachment skipped: {e}")

        # HTML body (always sent)
        final_html = html_content
        if not excel_attached and excel_path:
            final_html += excel_error_note

        msg.attach(MIMEText(final_html, "html"))

        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()

        print(f"✅ Email sent to {recipient_email} from {display_name}")
        return True

    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False
