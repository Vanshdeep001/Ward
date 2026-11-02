"""Email alerts over SMTP, tested against a fake server — nothing is actually sent."""
import smtplib

from app.notify.channels import Delivery, EmailChannel, FanOut, LogChannel, _subject, from_settings

ALERT = '🚨 ml-training (g5.xlarge), running 14h. Broke your rule “No GPU instance runs more than 6 hours”. It costs ₹1,585/day.'


class FakeSMTP:
    sent = []

    def __init__(self, host, port, fail=None):
        self.host, self.port, self.fail, self.logged_in = host, port, fail, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        if self.fail == 'auth':
            raise smtplib.SMTPAuthenticationError(535, b'Username and Password not accepted')
        self.logged_in = (user, password)

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


def channel(recipients=('me@example.com',), fail=None):
    return EmailChannel('smtp.example.com', 587, 'bot@example.com', 'app-password', 'Ward <bot@example.com>',
                        recipients, smtp_factory=lambda h, p: FakeSMTP(h, p, fail))


def test_an_alert_is_emailed_with_a_readable_subject():
    FakeSMTP.sent.clear()
    delivery = channel().send(ALERT)
    assert delivery == Delivery('email', True)
    msg = FakeSMTP.sent[-1]
    assert msg['To'] == 'me@example.com'
    assert msg['Subject'] == 'Ward alert: ml-training (g5.xlarge), running 14h'
    body = msg.get_content()
    assert 'No GPU instance runs more than 6 hours' in body and 'has not changed anything' in body


def test_warnings_are_labelled_as_warnings():
    assert _subject('⚠️ riya-dev (t3.micro), running 5h is getting close to your rule “…”.').startswith('Ward warning: riya-dev')


def test_a_wrong_password_is_reported_not_raised():
    delivery = channel(fail='auth').send(ALERT)
    assert not delivery.delivered and 'SMTPAuthenticationError' in delivery.error


def test_no_recipients_is_an_explained_failure():
    delivery = channel(recipients=()).send(ALERT)
    assert not delivery.delivered and 'WARD_ALERT_EMAILS' in delivery.error


def test_recipients_are_looked_up_when_sending():
    people = ['first@example.com']
    ch = channel(recipients=lambda: people)
    people.append('second@example.com')
    FakeSMTP.sent.clear()
    ch.send(ALERT)
    assert FakeSMTP.sent[-1]['To'] == 'first@example.com, second@example.com'


def test_telegram_and_email_together_deliver_if_either_does():
    class Down:
        def send(self, text):
            return Delivery('telegram', False, 'HTTP 401')

    delivery = FanOut([Down(), channel()]).send(ALERT)
    assert delivery.delivered and delivery.channel == 'telegram+email' and 'telegram: HTTP 401' in delivery.error


def test_settings_choose_the_channels():
    class S:
        telegram_token = telegram_chat_id = None
        smtp_host, smtp_port, smtp_username, smtp_password = None, 587, None, None
        smtp_from, alert_emails = None, ()

    assert isinstance(from_settings(S), LogChannel)
    S.smtp_host, S.smtp_username, S.alert_emails = 'smtp.gmail.com', 'me@gmail.com', ('me@gmail.com',)
    email = from_settings(S)
    assert isinstance(email, EmailChannel) and email.sender == 'me@gmail.com'
    S.telegram_token, S.telegram_chat_id = 't', 'c'
    assert isinstance(from_settings(S), FanOut)
