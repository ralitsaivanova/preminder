import requests

import logging
logger = logging.getLogger(__name__)

slack_error_messages = {
    "not_authed": "No authentication token provided.",
    "invalid_auth": "Invalid authentication token.",
    "account_inactive": "Authentication token is for a deleted user or team.",
    "channel_not_found": "Value passed for channel was invalid.",
    "not_in_channel": "Cannot post user messages to a channel they are not in.",
    "is_archived": "Channel has been archived.",
    "msg_too_long": "Message text is too long",
    "no_text": "No message text provided",
    "rate_limited": "Application has posted too many messages",
}


class SlackConnector(object):
    def __init__(self, auth_token):
        self.auth_token = auth_token
        self.base_url = "https://slack.com/api/"

    def get_team_members(self):
        endpoint = "users.list"

        result = self._send_request(endpoint)
        if result["ok"]:
            return SlackMapper.map_team_members(result['members'])
        else:
            self._map_error(result, endpoint)
            return []

    def get_team_info(self):
        endpoint = "team.info"

        result = self._send_request(endpoint)
        if result["ok"]:
            return SlackMapper.map_team_info(result['team'])
        else:
            self._map_error(result, endpoint)
            return {}

    def get_channels(self):
        """
        mixes together the 2 API calls for channels
        this is the call displayed on the FE
        """
        public = self.get_public_channels()
        private = self.get_private_channels()
        return public + private

    def get_public_channels(self):
        endpoint = "channels.list"

        result = self._send_request(endpoint)
        if result["ok"]:
            return SlackMapper.map_public_channels(result['channels'])
        else:
            self._map_error(result, endpoint)
            return []

    def get_private_channels(self):
        """
        private channels in slack are called groups
        everyone calls them private channels tho
        so beyond this connector for us they are called private channels
        """
        endpoint = "groups.list"

        result = self._send_request(endpoint)
        if result["ok"]:
            return SlackMapper.map_private_channels(result['groups'])
        else:
            self._map_error(result, endpoint)
            return []

    def send_message(self, recipient, **kwargs):
        """
        :param recipient: can be a channel (both channel name and id work)
                          or a user ("@{name}") N.B.:"@..."
                          or a user slack id without @
        :param text: text msg to send
        """
        endpoint = "chat.postMessage"
        try:
            username = kwargs["username"]
        except KeyError:
            username = "Marvel bot"

        try:
            icon_url = kwargs["avatar_url"]
        except KeyError:
            icon_url = ''

        params = {"username": username,
                  "icon_url": icon_url,
                  "channel": recipient}

        if "text" in kwargs.keys():
            params["text"] = kwargs["text"]

        if "attachments" in kwargs.keys():
            params["attachments"] = kwargs["attachments"]

        result = self._send_request(endpoint, **params)
        if not result["ok"]:
            self._map_error(result, endpoint)

    def _map_error(self, result, endpoint):
        try:
            error_msg = slack_error_messages[result["error"]]
        except KeyError:
            error_msg = result
        logger.error("slack %s - error:%s ", endpoint, error_msg)

    def _send_request(self, endpoint, **kwargs):
        kwargs.update({"token": self.auth_token})
        headers = {'content-type': 'application/json'}
        url = "{}{}".format(self.base_url, endpoint)

        response = requests.get(url, params=kwargs, headers=headers)

        if response.status_code != 200:
            errors = (url, response.status_code, response.text)
            return {"ok": False, "error": "url: %s status: %s text: %s" % errors}
        else:
            result = response.json()
        return result


class SlackMapper(object):

    @staticmethod
    def map_team_members(team_members):
        mapped_members = []

        team_members_filtered = []
        for member in team_members:
            if member["deleted"] is False:
                if "is_bot" not in member.keys() or member["is_bot"] is False:
                    team_members_filtered.append(member)

        for member in team_members_filtered:
            mapped_member = {}
            try:
                # slackbot returns is_bot False hence the "special" if to skip it
                if member["name"] == 'slackbot':
                    continue
                mapped_member["slack_id"] = member["id"]
                mapped_member["team_id"] = member["team_id"]
                mapped_member["name"] = member["name"]
                member_profile = member["profile"]
                mapped_member["email"] = member_profile["email"]
            except KeyError as kerr:
                logger.warning("member skipped. %s error %s",
                               member,
                               kerr.message)
                continue

            mapped_member["real_name"] = member_profile.get("real_name", "")
            mapped_member["skype"] = member_profile.get("skype", "")
            mapped_member["phone"] = member_profile.get("phone", "")
            mapped_member["avatar"] = member_profile.get("image_48", "")

            mapped_members.append(mapped_member)
        return mapped_members

    @staticmethod
    def map_team_info(team_result):
        team = {}
        try:
            team["id"] = team_result["id"]
            team["name"] = team_result["name"]
        except KeyError as kerr:
            logger.error("team key values missing %s error %s",
                         team_result,
                         kerr.message)
            return {}

        try:
            team["avatar"] = team_result["icon"]["image_132"]
        except KeyError:
            team["avatar"] = ""

        return team

    @staticmethod
    def map_public_channels(channels_result):
        channels = []

        for ch in channels_result:
            if not ch["is_archived"]:
                a_channel = {}
                try:
                    a_channel["id"] = ch["id"]
                    a_channel["name"] = ch["name"]
                    channels.append(a_channel)
                except KeyError as kerr:
                    logger.error("skipping channel, key values missing %s error %s",
                                 a_channel,
                                 kerr.message)
                    continue
        return channels

    @staticmethod
    def map_private_channels(groups_result):
        groups = []

        for gr in groups_result:
            if not gr["is_archived"]:
                group = {}
                try:
                    group["id"] = gr["id"]
                    group["name"] = gr["name"]
                    groups.append(group)
                except KeyError as kerr:
                    logger.error("skipping group, key values missing %s error %s",
                                 gr,
                                 kerr.message)
                    continue
        return groups
