from flask import Flask
app = Flask(__name__)

import json
import redis

from flask import make_response, request

import users_mapping
from slack import SlackConnector
import settings
import logging
logging.basicConfig(filename='app.log', level=logging.DEBUG)


def parse_payload(payload):

    interested_in = ["assigned", "unassigned", "closed", "reopened"]

    if payload["action"] not in interested_in:
        return None

    parsed = {
        "action": payload["action"]
    }

    try:
        pull_req = payload["pull_request"]
        parsed["user"] = pull_req["user"]["login"]
        parsed["url"] = pull_req["html_url"]
        parsed["title"] = pull_req["title"]

        parsed["actor"] = payload["sender"]["login"]
        if parsed["action"] == "reopened":
            parsed["assignees"] = \
                [assignee["login"] for assignee in pull_req["assignees"]]
        else:
            # it will hit for each assignee
            parsed["assignees"] = [payload["assignee"]["login"], ]

        parsed["state"] = pull_req["state"]

    except Exception as exp:
        pass
    return parsed


def syncronise_redis(payload):
    redis_client = redis.StrictRedis(host=settings.REDIS_HOST,
                                     port=settings.REDIS_PORT,
                                     password=settings.REDIS_PASS)

    title = payload["title"].encode("utf-8")
    key = "<{url}|{title}>".format(url=payload["url"],
                                   title=title)

    entry = redis_client.get(key)
    logging.info("key %s  value found %s", key, entry)
    logging.info("action %s ", payload["action"])

    payload["slack_handles"] = []
    # deleting the key, alerting no one, go home
    if payload["action"] == "closed":
        redis_client.delete(key)
        return payload

    for assignee in payload["assignees"]:
        logging.info("assignee %s ", assignee)

        if entry is None and payload["action"] != "unassigned":

            redis_client.set(key, assignee)
            try:
                handle = users_mapping.GITHUB_TO_SLACK[assignee]
                payload["slack_handles"].append(handle)
            except KeyError:
                pass
            return payload
        elif entry is not None:
            assignees = entry.split("|")
            logging.info("assignees found %s", assignees)

            if payload["action"] == "unassigned":
                assignees = entry.split("|")
                if assignee in assignees:
                    assignees.remove(assignee)
                    new_value = "|".join(assignees)
                    redis_client.set(key, new_value)
                    return payload
            elif payload["action"] in ("assigned", "reopened"):
                    if assignee in assignees:
                        return payload
                    else:
                        assignees = assignees + [assignee]
                        new_value = "|".join(assignees)
                        redis_client.set(key, new_value)
                        try:
                            handle = users_mapping.GITHUB_TO_SLACK[assignee]
                            payload["slack_handles"].append(handle)
                        except KeyError:
                            pass
                        return payload
    return payload


def create_msg_kwargs(payload):
    msg_tpl = "`{actor}` {action} <{url}|{title}> by `{user}` with state `{state}` to you"
    msg = msg_tpl.format(url=payload["url"],
                         title=payload["title"],
                         state=payload["state"],
                         action=payload["action"],
                         user=payload["user"],
                         actor=payload["actor"])

    msg_kwargs = {"text": msg,
                  "unfurl_media": True}
    return msg_kwargs


@app.route("/", methods=['POST', 'GET'])
def review_dat():
    response = make_response('')
    if request.method == 'POST':
        hook_payload = json.loads(request.data)
        parsed_payload = parse_payload(hook_payload)
        logging.info(parsed_payload)
        if parsed_payload is not None:
            parsed_payload = syncronise_redis(parsed_payload)
            slack = SlackConnector(settings.SLACK_TOKEN)

            for handle in parsed_payload["slack_handles"]:
                try:
                    msg_kwargs = create_msg_kwargs(parsed_payload)
                    slack.send_message("@" + handle, **msg_kwargs)
                except KeyError as ke:
                    # do not know that assignee
                    pass

        return response
    else:
        return make_response('nope')

if __name__ == "__main__":
    app.run(debug=True)
