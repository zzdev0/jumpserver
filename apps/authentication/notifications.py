from django.utils import timezone
from django.utils.translation import ugettext as _

from audits.models import UserLoginLog
from audits.const import DEFAULT_CITY
from notifications.notifications import UserMessage
from common.utils import validate_ip, get_ip_city
from common.utils import get_request_ip
from common.utils import get_logger

logger = get_logger(__file__)

EMAIL_TEMPLATE = '''
<h3>异地登陆提醒</h3>
<p>尊敬的JumpServer用户:&nbsp; &nbsp;您好!</p>
<p>您的账号存在异地登陆行为，请关注。</p>
<p>账号: {username}</p>
<p>登陆时间: {time}</p>
<p>登陆地点: {city} ({ip})</p>
<p>若怀疑此次登陆行为异常，请及时修改账号密码。</p>
<br>
<p>感谢您对JumpServer的关注!</p>
'''


class RemoteLandingMessage(UserMessage):
    def __init__(self, user, request):
        self.ip = get_request_ip(request) or '0.0.0.0'
        super().__init__(user)

    @property
    def city(self):
        ip = self.ip
        if not (ip and validate_ip(ip)):
            city = DEFAULT_CITY
        else:
            city = get_ip_city(ip) or DEFAULT_CITY
        return city

    @property
    def time(self):
        return timezone.now().strftime("%Y-%m-%d %H:%M:%S")

    @property
    def subject(self):
        return 'JumpServer异地登陆提醒'

    def get_text_msg(self) -> dict:
        message = """
异地登陆提醒
尊敬的JumpServer用户: 您好!
您的账号存在异地登陆行为，请关注。
账号: {username}
登陆时间: {time}
登陆地点: {city} ({ip})
若怀疑此次登陆行为异常，请及时修改账号密码。
感谢您对JumpServer的关注!
        """.format(
            username=self.user.username,
            ip=self.ip,
            time=self.time,
            city=self.city,
        )
        return {
            'subject': self.subject,
            'message': message
        }

    def get_html_msg(self) -> dict:
        message = EMAIL_TEMPLATE.format(
            username=self.user.username,
            ip=self.ip,
            time=self.time,
            city=self.city,
        )
        return {
            'subject': self.subject,
            'message': message
        }

    def publish_async(self):
        last_user_login = UserLoginLog.objects.filter(username=self.user.username, status=True).first()
        if last_user_login.city != self.city:
            super().publish_async()
