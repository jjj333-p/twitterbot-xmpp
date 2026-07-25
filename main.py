import logging
import subprocess

import aiohttp
import asyncio

import slixmpp
import json

from slixmpp.types import PresenceArgs

with open("./login.json", encoding="utf-8") as lf:
    login = json.load(lf)

PREFIX = login.get('twitter_prefix')
if not PREFIX:
    raise ValueError("twitter_prefix must be present in login.json.")

async def get_tweet(tweet_url):

    # this probably isnt needed but whatever
    headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0'}

    # attempt to get json, if its something else its basically an error
    async with aiohttp.ClientSession() as s:
        async with s.get(tweet_url, headers=headers) as response:
            data = await response.json()
            
    return data.get('tweet')


def get_git_info() -> tuple[str, str]:
    """
    Attempts to fetch the current Git version and remote origin URL.
    Returns (version, url) with safe fallbacks if Git is unavailable.
    """
    version = "unknown version"
    url = "https://github.com/jjj333-p/twitterbot-xmpp"

    try:
        version = subprocess.check_output(
            ["git", "describe", "--tags", "--always", "--dirty"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()

        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()

        # Optional: If you want to convert SSH URLs (git@...) to HTTPS for clickability
        if url.startswith("git@"):
            url = url.replace(":", "/").replace("git@", "https://")

    except Exception:
        # Fails silently if git is not installed or it's not a git repository
        pass

    return version, url

git_version, repo_url = get_git_info()

status_msg = f"twitterbot v{git_version} | Source: {repo_url}"

class MUCBot(slixmpp.ClientXMPP):

    def __init__(self, jid, password, rooms, nick):
        slixmpp.ClientXMPP.__init__(self, jid, password)

        self.rooms = rooms
        self.nick = nick

        self.add_event_handler("session_start", self.start)

        # The groupchat_message event is triggered whenever a message
        # stanza is received from any chat room. If you also also
        # register a handler for the 'message' event, MUC messages
        # will be processed by both handlers.
        self.add_event_handler("message", self.message)

        self.add_event_handler("groupchat_direct_invite", self.invite)

        self.register_plugin('xep_0030')  # Service Discovery
        self.register_plugin('xep_0045')  # Multi-User Chat
        self.register_plugin('xep_0199')  # XMPP Ping
        self.register_plugin('xep_0461')  # Message Replies
        self.register_plugin('xep_0066')  # oob (media)
        self.register_plugin('xep_0359')  # (Unique and Stable Stanza IDs)
        self.register_plugin('xep_0249')  # muc invites

    async def start(self, _):
        await self.get_roster()
        self.send_presence()

        # join configured rooms
        for room in self.rooms:
            await self.plugin['xep_0045'].join_muc_wait(
                room,
                self.nick,
                presence_options=PresenceArgs(
                    pstatus=status_msg
                ),
                maxchars=0,
            )

    async def invite(self, msg):
        """
                Handler triggered when a Direct MUC Invite (XEP-0249) is received.
                The plugin parses the XML and exposes it through message['xep_0249'].
                """
        # Extract the invite payload
        invite = msg['groupchat_invite']

        # The plugin gives you clean access to the underlying attributes
        room_jid = invite['jid']
        room_password = invite['password']
        # unsupported for now
        if room_password:
            return
        reason = invite['reason']

        sender = msg['from']
        print(f"Received a direct invite to {room_jid} from {sender}")

        if reason:
            print(f"Reason: {reason}")

        # Optional: Join the room immediately using XEP-0045
        try:
            await self.plugin['xep_0045'].join_muc_wait(
                room_jid,
                self.boundjid.user,  # Use your JID's user part as the nickname
                presence_options=PresenceArgs(
                    pstatus=status_msg
                ),
            )
            print(f"Successfully joined {room_jid}")
        except Exception as e:
            print(f"Failed to join {room_jid}: {e}")
            return


        # Add room to login.json and save
        try:
            with open("./login.json", "r", encoding="utf-8") as lf:
                login_data = json.load(lf)

            if room_jid not in login_data.get("rooms", []):
                login_data.setdefault("rooms", []).append(room_jid)
                self.rooms.append(room_jid)

                with open("./login.json", "w", encoding="utf-8") as lf:
                    json.dump(login_data, lf, indent=2, ensure_ascii=False)

                print(f"Added {room_jid} to login.json")
        except Exception as e:
            print(f"Failed to update login.json: {e}")

        self.send_message(
                mto=room_jid,
                mbody=f"Joined muc as I was invited by `{sender}` with reason `{reason}` .",
                mtype="groupchat"
            )

    async def message(self, msg):
        # dont respond to self
        if msg['mucnick'] == self.nick:
            return

        replyto_jid = msg['from'].bare if \
            (msg['from'].bare in self.rooms and msg['type'] == "groupchat") or \
            (msg['from'].bare not in self.rooms and msg['type'] == "chat") \
            else msg['from']

        origin_id = msg.get('origin_id', {}).get('id')

        replyto_id = msg.get('stanza_id', {}).get('id', '') if msg['type'] == 'groupchat' else (
            origin_id if origin_id else msg['id']
        )

        # slixmpp stanza interface [] always returns a string, empty if not present
        for word in msg['body'].split(' '):
            if not word.startswith('https://x.com/'):
                continue

            # naive parsing
            idpart = word.split('/')[-1]

            # get json
            try:
                result = await get_tweet(f"{PREFIX}{idpart}")
            except Exception as e:
                message: slixmpp.stanza.Message = self.plugin['xep_0461'].make_reply(
                    msg['from'],
                    replyto_id,
                    f"> {word}",
                    mto=msg['from'].bare,
                    mbody=str(e),
                    mtype=msg['type']
                )
                message.send()
                return

            author = result.get('author', {})

            firstbody = "\n> ".join(
                    [f"{author.get('name')} `@{author.get('screen_name')}`"] \
                    + result.get('text', '').splitlines()
            )

            message: slixmpp.stanza.Message = self.plugin['xep_0461'].make_reply(
                msg['from'],
                replyto_id,
                f"> {word}",
                mto=replyto_jid,
                mbody=firstbody,
                mtype=msg['type']
            )
            message.send()

            media = result.get('media', {}).get('all')
            if media is not None:
                for item in media:
                    if item is None:
                        continue
                    url = item.get('url')
                    if url is None:
                        continue

                    cleanurl = url.split('?')[0]

                    # boilerplate message obj
                    message = self.make_message(
                        mto=replyto_jid,
                        mbody=cleanurl,
                        mtype=msg['type']
                    )

                    # attach media tag
                    # pylint: disable=invalid-sequence-index
                    message['oob']['url'] = cleanurl
                    message.send()

if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)-8s %(message)s')

    xmpp = MUCBot(login["jid"], login["password"],
                  login["rooms"], login["displayname"])

    # Connect to the XMPP server and start processing XMPP stanzas.
    xmpp.connect()
    print("Connected and running forever...")
    asyncio.get_event_loop().run_forever()

