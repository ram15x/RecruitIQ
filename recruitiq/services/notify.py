import smtplib
from email.message import EmailMessage

FOOTER = ("\n\nIf you would like a person to review this again, or you want your data removed from our records, "
          "reply to this email and we will do that.")


def invite(name: str, job_title: str, when_text: str, link: str, minutes: int, grace: int, mode: str = "written", video: bool = False) -> tuple[str, str]:
    if mode == "voice":
        what = ("The questions are read aloud and you answer by speaking. Your microphone is used" + (" and your camera is switched on" if video else "") +
                ", and your answers are recorded so a person can listen" + (" and watch" if video else "") + " to them. "
                "You can type your answers instead if you prefer, or if speaking is hard for you, and that is never held against you. "
                "Nothing you say or show is scored by software, and no software tries to judge your face or voice. ")
    else:
        what = "You answer the questions by typing. Your camera and microphone are not used. "
    body = (f"Hello {name},\n\nThank you for applying for {job_title}. We would like to invite you to an interview.\n\n"
            f"When: {when_text}\nLink: {link}\n\n"
            f"The link opens at that time and stays open for {_span(grace)} after it, and you will have about {minutes} minutes once you start. "
            + what +
            "While you work, the page records how many times you switch tabs or paste text, and how long you take. "
            "A person reads this next to your answers, and it is not used on its own to judge you." + FOOTER)
    return f"Interview invitation: {job_title}", body


def received(name: str, job_title: str) -> tuple[str, str]:
    body = (f"Hello {name},\n\nThank you for applying for {job_title}. We have received your application. "
            "Software helps us organise applications and put them in order, and a person makes every decision about it. "
            "We will write to you again when there is news." + FOOTER)
    return f"We received your application for {job_title}", body


def _span(minutes: int) -> str:
    if minutes >= 2880 and minutes % 1440 == 0:
        return f"{minutes // 1440} days"
    if minutes >= 120:
        return f"{round(minutes / 60)} hours"
    return f"{minutes} minutes"


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
