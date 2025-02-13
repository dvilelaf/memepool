import json
import time
from pathlib import Path

import requests
from ape import accounts
from eip712 import EIP712Message
from eth_account.messages import _hash_eip191_message
from eth_utils import decode_hex, encode_hex
from safe_eth.eth import EthereumClient
from safe_eth.safe import Safe as GnosisSafe
from web3 import Web3

from core.plugin import Plugin
from plugins.cowswap.constants import SAFE_ABI

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


class CowSwap(Plugin):
    """A plugin to interact with Cowswap via a Safe multisig wallet"""

    NAME = "CowSwap"
    ENV_VARS = ["BASE_RPC", "SIGNER_PRIVATE_KEY", "SAFE_ADDRESS", "APE_ACCOUNTS_NAME"]

    def __init__(self):
        """Init"""
        super().__init__()

        self.ledger = Web3(Web3.HTTPProvider(self.base_rpc))
        self.safe = GnosisSafe(self.safe_address, EthereumClient(self.base_rpc))

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
        sell_token_name: str,
    ):
        """A tool to sell tokens on Cowswap"""

        sell_token_address = self.get_memecoin_address(sell_token_name)
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
        buy_token_name: str,
    ):
        """A tool to buy tokens on Cowswap"""

        buy_token_address = self.get_memecoin_address(buy_token_name)
        sell_token_address = USDC_ADDRESS_BASE
        self.approve_allowance(sell_token_address)
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

        if sell_token_address == USDC_ADDRESS_BASE:
            print(
                f"Order: {order.sellAmount / 1e6} USDC -> {order.buyAmount / 1e18} {buy_token_address}"
            )
        else:
            print(
                f"Order: {order.sellAmount} {sell_token_address / 1e18} -> {order.buyAmount / 1e6} USDC"
            )

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
        response = requests.post(
            f"{BASE_COW_API}/api/v1/orders", json=payload, timeout=60
        )

        success = response.status_code == 201
        print(response.text)
        print(
            f"Swap success: {success} https://explorer.cow.fi/base/orders/{response.json()}"
        )
        return success

    def approve_allowance(self, erc20_contract_address):
        """Approve allowance"""

        print(f"Approving {BASE_GPV2_VAULT_RELAYER} to spend {erc20_contract_address}")

        erc20_contract = self.ledger.eth.contract(
            address=erc20_contract_address, abi=self.erc20_abi
        )

        # Get the safe nonce
        response = requests.get(
            url=f"{SAFE_TRANSACTION_SERVICE_URL}/api/v1/safes/{SAFE_ADDRESS}",
            timeout=60,
        )
        safe_nonce = response.json()["nonce"]

        # Build the internal transaction
        estimated_gas = self.ledger.eth.estimate_gas(
            {
                "from": self.safe.address,
                "to": erc20_contract.address,
                "data": erc20_contract.encode_abi(
                    "approve", args=[BASE_GPV2_VAULT_RELAYER, MAX_APPROVAL]
                ),
            }
        )
        gas_price = max(self.ledger.eth.gas_price, self.ledger.to_wei("1", "gwei"))

        estimated_gas = 1000000
        gas_price = self.ledger.to_wei("10", "gwei")

        approve_tx = erc20_contract.functions.approve(
            BASE_GPV2_VAULT_RELAYER,
            MAX_APPROVAL,
        ).build_transaction(
            {
                "chainId": BASE_CHAIN_ID,
                "gas": estimated_gas,
                "gasPrice": gas_price,
                "nonce": safe_nonce,
            }
        )

        # Build the safe transaction
        safe_tx = self.safe.build_multisig_tx(  # nosec
            to=erc20_contract.address,
            value=0,
            data=approve_tx["data"],
            operation=0,
            safe_tx_gas=1000000,
            base_gas=0,
            # gas_price=gas_price,
            gas_token="0x0000000000000000000000000000000000000000",
            refund_receiver="0x0000000000000000000000000000000000000000",
        )

        # Sign
        safe_tx.sign(self.signer_private_key)
        print(safe_tx)
        print(safe_tx.safe_tx_hash.hex())

        # Send
        tx_hash, _ = safe_tx.execute(self.signer_private_key)

        # Wait
        tx_receipt = self.ledger.eth.wait_for_transaction_receipt(tx_hash)
        success = tx_receipt.status == 1
        print(f"Allowance success: {success}")
        return success

    def get_memecoin_address(self, memecoin_name):
        """Get the address"""

        coin_id = memecoin_name.lower()
        detailed_url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }

        try:
            # Fetch detailed coin information
            detailed_response = requests.get(detailed_url, headers=headers, timeout=60)
            detailed_response.raise_for_status()
            detailed_data = detailed_response.json()

            # Extract Base network contract address
            contract_address = detailed_data.get("platforms", {}).get("base", None)
            print(f"{memecoin_name} adress is {contract_address}")
            return Web3.to_checksum_address(contract_address)
        except Exception:
            print(f"Couldnt get the address for {memecoin_name}")
            return None
