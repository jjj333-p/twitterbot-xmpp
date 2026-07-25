# twitterbot-xmpp

An XMPP bot that watches chats for `https://x.com/...` links and replies with tweet text and media links.

## Features

- Detects `x.com` tweet URLs in XMPP chats
- Replies with the tweet author and text
- Sends media URLs when available
- Supports direct MUC invites
- Persists invited rooms to `login.json`

## Configuration

Create a `login.json` file in the project root:
```json
{
  "jid": "bot@example.com",
  "password": "your-xmpp-password",
  "displayname": "twitterbot",
  "rooms": [
    "room@conference.example.com"
  ],
  "twitter_prefix": "https://api.fxtwitter.com/v2/status/"
}
```
### `login.json` parameters

| Parameter        | Required | Description                                       |
|------------------|----------|---------------------------------------------------|
| `jid`            | Yes      | The XMPP account JID used by the bot.             |
| `password`       | Yes      | Password for the XMPP account.                    |
| `displayname`    | Yes      | Nickname used when joining MUC rooms.             |
| `rooms`          | Yes      | List of MUC room JIDs to join on startup.         |
| `twitter_prefix` | Yes      | URL prefix used to fetch tweet JSON by tweet ID.  |
```

## Running

Install dependencies, then run:
```bash
python main.py
```
## Public Instance

A public instance is available and can be invited to your XMPP MUC:
```text
twitterbot@pain.agency
```
Invite it to a room, then post an `https://x.com/...` tweet link to use it.
