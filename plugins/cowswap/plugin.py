import json
import time
from decimal import Decimal
from pathlib import Path

import requests
from ape import accounts
from eip712 import EIP712Message
from eth_abi import encode
from eth_account.messages import _hash_eip191_message, encode_typed_data
from eth_utils import decode_hex, encode_hex
from safe_eth.eth import EthereumClient
from safe_eth.safe import Safe as GnosisSafe
from safe_eth.safe.safe_tx import SafeTx
from web3 import Web3

from core.plugin import Plugin
from plugins.cowswap.constants import ERC20_ABI, SAFE_ABI

BASE_COW_API = "https://api.cow.fi/base"
SAFE_TRANSACTION_SERVICE_URL = "https://safe-transaction-base.safe.global"
COWSWAP_CONTRACT_ADDRESS = "0x9008D19f58AAbD9eD0D60971565AA8510560ab41"
BASE_GPV2_VAULT_RELAYER = "0xC92E8bdf79f0507f65a392b0ab4667716BFE0110"
BASE_GPV2_SETTLEMENT = "0x9008D19f58AAbD9eD0D60971565AA8510560ab41"
MAX_APPROVAL = 2**256 - 1
BASE_CHAIN_ID = 8453
SAFE_ADDRESS = "0x44CBf6E9b4473EFC47BBE8198d19929E3Bc5552c"
USDC_ADDRESS_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


class SafeMessage(EIP712Message):
    _chainId_ = BASE_CHAIN_ID
    _verifyingContract_ = SAFE_ADDRESS

    message: "bytes"


class Order(EIP712Message):
    _name_ = "Gnosis Protocol"
    _version_ = "v2"
    _chainId_ = BASE_CHAIN_ID
    _verifyingContract_ = BASE_GPV2_SETTLEMENT

    sellToken: "address"
    buyToken: "address"
    receiver: "address"
    sellAmount: "uint256"
    buyAmount: "uint256"
    validTo: "uint32"
    appData: "bytes32"
    feeAmount: "uint256"
    kind: "string"
    partiallyFillable: "bool"
    sellTokenBalance: "string"
    buyTokenBalance: "string"


class Safe(Plugin):
    """A plugin to interact with a Safe multisig wallet and Cowswap"""

    NAME = "Safe"
    ENV_VARS = ["BASE_RPC", "SIGNER_PRIVATE_KEY", "SAFE_ADDRESS", "APE_ACCOUNTS_NAME"]

    def __init__(self):
        """Init"""
        super().__init__()

        self.ledger = Web3(Web3.HTTPProvider(self.base_rpc))
        self.wallet = Web3().eth.account.from_key(self.private_key)
        self.safe = GnosisSafe(self.address, EthereumClient(self.base_rpc))

        self.signer = accounts.load(self.ape_accounts_name)
        self.signer.set_autosign(True)

        with open(
            Path(__file__).parent / "abis" / "erc20.json", "r", encoding="utf-8"
        ) as abi_file:
            self.erc20_abi = json.load(abi_file)

    def get_latest_block(self):
        """Get the current block"""
        return self.ledger.eth.get_block("latest")

    def get_erc20_balance(self, erc20_contract_address: str):
        """Get the ERC20 balance of a wallet address"""
        contract = self.ledger.eth.contract(
            address=erc20_contract_address, abi=self.erc20_abi
        )
        balance = contract.functions.balanceOf(self.safe_address).call()
        decimals = contract.functions.decimals().call()
        return balance / (10**decimals)

    def cowswap_sell_tokens_tool(
        self,
        sell_token_address: str,
    ):
        """A tool to sell tokens on Cowswap"""

        buy_token_address = USDC_ADDRESS_BASE
        sell_amount_eth = self.get_erc20_balance(sell_token_address)
        sell_amount_wei = Web3.to_wei(sell_amount_eth, "ether")

        self.swap(
            sell_token_address,
            buy_token_address,
            sell_amount_wei,
        )

    def cowswap_buy_tokens_tool(
        self,
        buy_token_address: str,
    ):
        """A tool to buy tokens on Cowswap"""

        self.approve_allowance(buy_token_address)
        sell_token_address = USDC_ADDRESS_BASE
        sell_amount_wei = 1000000  # 1$ (USDC has 6 decimals)

        self.swap(
            sell_token_address,
            buy_token_address,
            sell_amount_wei,
        )

    def swap(
        self, sell_token_address: str, buy_token_address: str, sell_amount_wei: int
    ):
        """Swap on Cowswap"""
        payload = {
            "sellToken": sell_token_address,
            "buyToken": buy_token_address,
            "appData": "0x0000000000000000000000000000000000000000000000000000000000000000",
            "from": SAFE_ADDRESS,
            "receiver": SAFE_ADDRESS,
            "validTo": int(time.time()) + 600,
            "sellTokenBalance": "erc20",
            "buyTokenBalance": "erc20",
            "kind": "sell",
            "priceQuality": "optimal",
            "signingScheme": "eip712",
            "sellAmountBeforeFee": str(sell_amount_wei),
            "partiallyFillable": False,
            "onchainOrder": False,
        }

        response = requests.post(
            f"{BASE_COW_API}/api/v1/quote", json=payload, timeout=60
        )

        quote = response.json()["quote"]
        buy_amount = int(int(quote["buyAmount"]) * 0.99)

        # Encode cowswap order data
        order = Order(
            sellToken=quote["sellToken"],
            buyToken=quote["buyToken"],
            receiver=SAFE_ADDRESS,
            sellAmount=int(quote["sellAmount"]),
            buyAmount=buy_amount,
            validTo=quote["validTo"],
            appData=decode_hex(quote["appData"]),
            feeAmount=0,
            kind=quote["kind"],
            partiallyFillable=quote["partiallyFillable"],
            sellTokenBalance=quote["sellTokenBalance"],
            buyTokenBalance=quote["buyTokenBalance"],
        )

        print(f"Order: {order.sellAmount / 1e18} -> {order.buyAmount / 1e18}")

        order_digest = _hash_eip191_message(order.signable_message)
        safe_message = SafeMessage(message=order_digest)

        signatures = [
            dev.sign_message(safe_message.signable_message) for dev in [self.signer]
        ]
        encoded_signature = b"".join(sig.encode_rsv() for sig in signatures)

        payload = {
            "sellToken": order.sellToken,
            "buyToken": order.buyToken,
            "receiver": order.receiver,
            "sellAmount": str(order.sellAmount),
            "buyAmount": str(buy_amount),
            "validTo": order.validTo,
            "appData": encode_hex(order.appData),
            "feeAmount": str(order.feeAmount),
            "kind": order.kind,
            "partiallyFillable": order.partiallyFillable,
            "sellTokenBalance": order.sellTokenBalance,
            "buyTokenBalance": order.buyTokenBalance,
            "signingScheme": "eip1271",
            "signature": encode_hex(encoded_signature),
            "from": SAFE_ADDRESS,
        }
        resp = requests.post(f"{BASE_COW_API}/api/v1/orders", json=payload, timeout=60)

        return resp.status_code == 201

    def approve_allowance(self, erc20_contract_address):
        """Approve allowance"""

        safe_contract = self.ledger.eth.contract(
            address=self.safe_address, abi=SAFE_ABI
        )
        erc20_contract = self.ledger.eth.contract(
            address=erc20_contract_address, abi=ERC20_ABI
        )

        approve_data = erc20_contract.encode_abi(
            "approve", args=[BASE_GPV2_VAULT_RELAYER, MAX_APPROVAL]
        )

        # Crear transacción del Safe
        safe_tx = safe_contract.functions.execTransaction(
            erc20_contract_address,  # to
            0,  # value
            approve_data,  # data
            0,  # operation (CALL)
            0,
            0,
            0,  # safeTxGas, baseGas, gasPrice
            "0x0000000000000000000000000000000000000000",  # gasToken
            "0x0000000000000000000000000000000000000000",  # refundReceiver
        ).build_transaction(
            {
                "chainId": BASE_CHAIN_ID,
                "from": self.safe_address,
                "nonce": self.ledger.eth.get_transaction_count(self.safe_address),
                "gas": 1000000,
                "gasPrice": self.ledger.to_wei("3", "gwei"),
            }
        )

        signed_tx = self.ledger.eth.account.sign_transaction(
            safe_tx, self.signer_private_key
        )
        tx_hash = self.ledger.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_receipt = self.ledger.eth.wait_for_transaction_receipt(tx_hash)
        success = tx_receipt.status == 1
        print(f"Swap success: {success}")
        return success
