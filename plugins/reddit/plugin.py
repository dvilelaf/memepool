import praw

from core.plugin import Plugin


class Reddit(Plugin):
    """A plugin to interact with Reddit"""

    NAME = "Reddit"
    ENV_VARS = ["CLIENT_ID", "CLIENT_SECRET"]

    def __init__(self):
        """Init"""
        super().__init__()

        self.client = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent="memepool:v0.1",
        )

    def post_to_json(self, post):
        """Post to JSON"""
        return {
            "title": post.title,
            "score": post.score,
            "url": post.url,
        }

    def reddit_get_top_posts_tool(self, subreddit_name: str, posts_limit: int = 10):
        """Get the top posts for a given subreddit"""
        subreddit = self.client.subreddit(subreddit_name)
        return [self.post_to_json(post) for post in subreddit.hot(limit=posts_limit)]
