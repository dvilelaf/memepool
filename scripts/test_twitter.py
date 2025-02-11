# uv run python3 -m scripts.test_twitter
from plugins.twitter.plugin import Twitter

twitter = Twitter()
twitter.twitter_create_tweet_tool("test")
