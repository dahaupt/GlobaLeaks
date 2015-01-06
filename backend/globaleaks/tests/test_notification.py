from twisted.internet.defer import inlineCallbacks

# override GLsetting
from globaleaks.settings import GLSetting

GLSetting.notification_plugins = ['MailNotification']
GLSetting.memory_copy.notif_source_name = "name fake"
GLSetting.memory_copy.notif_source_email = "mail@fake.xxx"

from globaleaks.tests import helpers
from globaleaks.handlers import submission
from globaleaks.jobs import delivery_sched
from globaleaks.jobs.notification_sched import NotificationSchedule

class TestEmail(helpers.TestGLWithPopulatedDB):

    @inlineCallbacks
    def setUp(self):
        yield helpers.TestGLWithPopulatedDB.setUp(self)

        yield NotificationSchedule().operation()

        wb_steps = yield helpers.fill_random_fields(self.dummyContext['id'])

        self.recipe = yield submission.create_submission({
            'wb_steps': wb_steps,
            'context_id': self.dummyContext['id'],
            'receivers': [self.dummyReceiver_1['id']],
            'files': [],
            'finalize': True,
            }, True, 'en')

        yield delivery_sched.tip_creation()

    @inlineCallbacks
    def test_sendmail(self):
        aps = NotificationSchedule()

        # 100 as limit
        (tip_events, enqueued) = yield aps.create_tip_notification_events(0)
        self.assertEqual(enqueued, 1)

        yield aps.do_tip_notification(tip_events)

