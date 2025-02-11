import os
from pathlib import Path

from dotenv import load_dotenv


class Plugin:
    """Plugin base"""

    NAME = "Plugin"
    ENV_VARS = []

    def __init__(self):
        """Init"""
        load_dotenv(override=True)
        for env_var in self.ENV_VARS:
            setattr(self, env_var.lower(), os.environ[f"{self.NAME.upper()}_{env_var}"])

        self.storage_path = Path(__file__).parent.parent
