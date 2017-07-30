import redis
from datetime import datetime, time

from slack import SlackConnector
import users_mapping

import settings
import logging
logging.basicConfig(filename='app.log', level=logging.DEBUG)

from apscheduler.schedulers.blocking import BlockingScheduler

sched = BlockingScheduler()


def runit():
    timetable = ((time(10, 50), time(11, 00)))

    now = datetime.now()
    now_time = now.time()
    now_day = now.weekday()

    for before, after in timetable:
        if before < now_time < after and now_day < 5:
            return True

    return False


@sched.scheduled_job('cron', day_of_week='mon-fri', hour=10, minute=10)
def pr_reminder():
    """
    The heroku server is set to UTC timezone. Keep it in mind if
    you want to change when it runs
    Doc: http://apscheduler.readthedocs.io/en/latest/modules/triggers/cron.html
    """

    redis_client = redis.StrictRedis(host=settings.REDIS_HOST,
                                     port=settings.REDIS_PORT,
                                     password=settings.REDIS_PASS)
    all_keys = redis_client.keys()

    for key in all_keys:

        value = redis_client.get(key)
        assignees = value.split("|")

        for assignee in assignees:
            try:
                handle = users_mapping.GITHUB_TO_SLACK[assignee]
            except KeyError:
                # do not know the assignee, do not care
                continue

            slack = SlackConnector(settings.SLACK_TOKEN)
            msg = "Reminder you are assigned to {key}".format(key=key)
            msg_kwargs = {"text": msg,
                          "unfurl_media": True}

            slack.send_message("@" + handle, **msg_kwargs)

sched.start()
