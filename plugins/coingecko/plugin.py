import json
from typing import List, Optional

import requests

from core.plugin import Plugin


class Coingecko(Plugin):
    """A plugin to interact with Coingecko"""

    NAME = "Coingecko"
    ENV_VARS = ["API_KEY"]

    def coingecko_get_base_memecoins_tool(self) -> Optional[List]:
        """Get memecoins on the Base network"""

        url = "https://api.coingecko.com/api/v3/coins/markets"

        params = {
            "vs_currency": "usd",
            "category": "base-meme-coins",
            "order": "market_cap_desc",
            "per_page": 100,
            "page": 1,
            "sparkline": "false",
            "locale": "en",
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }

        try:
            response = requests.get(url, params=params, headers=headers, timeout=60)
            response.raise_for_status()
            memecoins = response.json()

            with open(
                self.storage_path / "memecoins.json", "w", encoding="utf-8"
            ) as memecoins_file:
                json.dump(memecoins, memecoins_file, indent=4)

            return memecoins
        except requests.exceptions.RequestException:
            return None
