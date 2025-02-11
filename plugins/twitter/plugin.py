import asyncio
from typing import Any, Dict, Optional

import tweepy
from twikit import Client

from core.plugin import Plugin


def tweet_to_json(tweet: Any, user_id: Optional[str] = None) -> Dict:
    """Tweet to json"""
    return {
        "id": tweet.id,
        "user_name": tweet.user.name,
        "user_id": user_id or tweet.user.id,
        "text": tweet.text,
        "created_at": tweet.created_at,
        "view_count": tweet.view_count,
        "retweet_count": tweet.retweet_count,
        "quote_count": tweet.quote_count,
        "view_count_state": tweet.view_count_state,
    }


class Twitter(Plugin):
    """A plugin to interact with Twitter"""

    NAME = "Twitter"
    ENV_VARS = [
        "MAIN_CONSUMER_KEY",
        "MAIN_CONSUMER_SECRET",
        "MAIN_BEARER_TOKEN",
        "MAIN_ACCESS_TOKEN",
        "MAIN_ACCESS_SECRET",
        "MAIN_CLIENT_ID",
        "MAIN_CLIENT_SECRET",
        "SECONDARY_EMAIL",
        "SECONDARY_USER",
        "SECONDARY_PASSWORD",
    ]

    def __init__(self):
        """Init"""
        super().__init__()

        # Tweepy
        oauth = tweepy.OAuth1UserHandler(
            consumer_key=self.main_consumer_key,
            consumer_secret=self.main_consumer_secret,
            access_token=self.main_access_token,
            access_token_secret=self.main_access_secret,
        )
        self.tweepy_client = tweepy.Client(
            consumer_key=self.main_consumer_key,
            consumer_secret=self.main_consumer_secret,
            access_token=self.main_access_token,
            access_token_secret=self.main_access_secret,
        )
        self.tweepy_api = tweepy.API(oauth)

        # Twikit
        self.twikit_client = Client(language="en-US")
        self.loop = asyncio.get_event_loop()
        self.loop.run_until_complete(self.twikit_login())

    async def twikit_login(self):
        """Login into Twitter"""
        await self.twikit_client.login(
            auth_info_1=self.secondary_email,
            auth_info_2=self.secondary_user,
            password=self.secondary_password,
            cookies_file=str(self.storage_path / "twikit_cookies.json"),
        )

    def twitter_create_tweet_tool(self, text: str) -> Optional[int]:
        """Create a new tweet"""
        return self.tweepy_client.create_tweet(text=text)

    async def search_tweet(self, query: str, count: int = 20) -> Optional[Dict]:
        """Search tweets based on a query"""
        tweets = await self.twikit_client.search_tweet(
            query, product="Top", count=count
        )
        return [tweet_to_json(t) for t in tweets]

    def twitter_search_tweet_tool(self, query: str, count: int = 20) -> Optional[Dict]:
        """Search tweets based on a query"""
        return self.loop.run_until_complete(self.search_tweet(query, count))
