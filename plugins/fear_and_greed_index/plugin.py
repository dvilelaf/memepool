from typing import List, Optional

import requests

from core.plugin import Plugin


class FearAndGreedIndex(Plugin):
    """A plugin to read the crypto fear and greed index"""

    NAME = "FearAndGreedIndex"

    def fearandgreedindex_get_index_tool(self) -> Optional[List]:
        """Get the current fear and greed index"""

        url = "https://api.alternative.me/fng/"

        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            return None
