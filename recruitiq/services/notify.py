import smtplib
from email.message import EmailMessage

FOOTER = ("\n\nIf you would like a person to review this again, or you want your data removed from our records, "
          "reply to this email and we will do that.")


def invite(name: str, job_title: str, when_text: str, link: str, minutes: int, grace: int) -> tuple[str, str]:
    body = (f"Hello {name},\n\nThank you for applying for {job_title}. We would like to invite you to a written interview.\n\n"
            f"When: {when_text}\nLink: {link}\n\n"
            f"The link opens at that time and stays open for {grace} minutes after it, and you will have about {minutes} minutes once you start. "
            "You answer the questions by typing. Your camera and microphone are not used.\n"
            "While you work, the page records how many times you switch tabs or paste text, and how long you take. "
            "A person reads this next to your answers, and it is not used on its own to judge you." + FOOTER)
    return f"Interview invitation: {job_title}", body


def decision(name: str, job_title: str, outcome: str) -> tuple[str, str]:
    if outcome == "shortlisted":
        body = (f"Hello {name},\n\nThank you for applying for {job_title}. We would like to take your application to the next step "
                "and will write to you shortly with details." + FOOTER)
    else:
        body = (f"Hello {name},\n\nThank you for applying for {job_title} and for the time you put into it. "
                "After review we will not be taking your application further for this role." + FOOTER)
    return f"Your application for {job_title}", body


def send(host: str, port: int, user: str, password: str, sender: str, to: str, subject: str, body: str) -> tuple[bool, str]:
    if not (host and user and password and sender):
        return False, "mail is not configured"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL(host, port, timeout=20) as s:
            s.login(user, password)
            s.send_message(msg)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}"
