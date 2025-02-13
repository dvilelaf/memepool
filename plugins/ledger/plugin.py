import json
from pathlib import Path

from web3 import Web3

from core.plugin import Plugin


class Ledger(Plugin):
    """A plugin to interact with the blockchain"""

    NAME = "Ledger"
    ENV_VARS = ["BASE_RPC", "PRIVATE_KEY"]

    def __init__(self):
        """Init"""
        super().__init__()

        self.ledger = Web3(Web3.HTTPProvider(self.base_rpc))
        self.wallet = Web3().eth.account.from_key(self.private_key)

        with open(
            Path(__file__).parent / "abis" / "erc20.json", "r", encoding="utf-8"
        ) as abi_file:
            self.erc20_abi = json.load(abi_file)

    def get_latest_block(self):
        """Get the current block"""
        return self.ledger.eth.get_block("latest")

    def ledger_get_native_balance(self, wallet_address: str):
        """Get the native balance of a wallet address"""
        balance_wei = self.ledger.eth.get_balance(wallet_address)
        return self.ledger.from_wei(balance_wei, "ether")

    def ledger_get_erc20_balance(
        self, erc20_contract_address: str, wallet_address: str
    ):
        """Get the ERC20 balance of a wallet address"""
        contract = self.ledger.eth.contract(
            address=erc20_contract_address, abi=self.erc20_abi
        )
        balance = contract.functions.balanceOf(wallet_address).call()
        decimals = contract.functions.decimals().call()
        return balance / (10**decimals)
