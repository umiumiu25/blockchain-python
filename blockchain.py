import contextlib
import hashlib
import json
import logging
import sys
import time
import threading

from ecdsa import NIST256p
from ecdsa import VerifyingKey
import requests

import utils

MINING_DIFFICULTY = 3
MINING_SENDER = "THE BLOCKCHAIN"
MINING_REWARD = 1.0
MINING_TIMER_SEC = 20

BLOCKCHAIN_PORT_RANGE = (5001, 5004)
NEIGHBORS_IP_RANGE = (0, 1)
BLOCKCHAIN_NEIGHBORS_SYNC_TIME_SEC = 20

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)


class BlockChain(object):
    def __init__(self, blockchain_address=None, port=None):
        self.transaction_pool = []
        self.chain = []
        self.neighbors = []
        self.create_block(0, self.hash({}))
        self.blockchain_address = blockchain_address
        self.port = port
        self.mining_semaphore = threading.Semaphore(1)
        self.sync_neighbors_semaphore = threading.Semaphore(1)

    def run(self):
        self.sync_neighbors()
        self.resolve_conflicts()
        self.start_mining()

    def set_neighbors(self):
        self.neighbors = utils.find_neighbors(
            utils.get_host(),
            self.port,
            NEIGHBORS_IP_RANGE[0],
            NEIGHBORS_IP_RANGE[1],
            BLOCKCHAIN_PORT_RANGE[0],
            BLOCKCHAIN_PORT_RANGE[1],
        )
        logger.info({"action": "set_neighbors", "neighbors": self.neighbors})

    def sync_neighbors(self):
        is_acuire = self.sync_neighbors_semaphore.acquire(blocking=False)
        if is_acuire:
            with contextlib.ExitStack() as stack:
                stack.callback(self.sync_neighbors_semaphore.release)
                self.set_neighbors()
                loop = threading.Timer(
                    BLOCKCHAIN_NEIGHBORS_SYNC_TIME_SEC, self.sync_neighbors
                )
                loop.start()

    def create_block(self, nonce, previous_hash):
        block = utils.sorted_dict_by_key(
            {
                "timestamp": time.time(),
                "nonce": nonce,
                "previous_hash": previous_hash,
                "transactions": self.transaction_pool,
            }
        )
        self.chain.append(block)
        self.transaction_pool = []

        for node in self.neighbors:
            requests.delete(f"http://{node}/transactions")

        return block

    def hash(self, block):
        sorted_block = json.dumps(block, sort_keys=True)
        return hashlib.sha256(sorted_block.encode()).hexdigest()

    def add_transaction(
        self,
        sender_blockchain_address,
        recipient_blockchain_address,
        value,
        sender_public_key=None,
        signature=None,
    ):
        transaction = utils.sorted_dict_by_key(
            {
                "sender_blockchain_address": sender_blockchain_address,
                "recipient_blockchain_address": recipient_blockchain_address,
                "value": float(value),
            }
        )

        if sender_blockchain_address == MINING_SENDER:
            self.transaction_pool.append(transaction)
            return True

        is_transaction_valid = self.verify_transaction_signature(
            sender_public_key, signature, transaction
        )
        if is_transaction_valid:
            if self.calculate_total_amount(sender_blockchain_address) < float(value):
                logger.error(
                    {
                        "action": "add_transaction",
                        "status": "fail",
                        "error": "no balance",
                    }
                )
                return False
            self.transaction_pool.append(transaction)
        return is_transaction_valid

    def create_transaction(
        self,
        sender_blockchain_address,
        recipient_blockchain_address,
        value,
        sender_public_key,
        signature,
    ):
        is_transacted = self.add_transaction(
            sender_blockchain_address,
            recipient_blockchain_address,
            value,
            sender_public_key,
            signature,
        )

        if is_transacted:
            for node in self.neighbors:
                requests.put(
                    f"http://{node}/transactions",
                    json={
                        "sender_blockchain_address": sender_blockchain_address,
                        "recipient_blockchain_address": recipient_blockchain_address,
                        "sender_public_key": sender_public_key,
                        "value": value,
                        "signature": signature,
                    },
                )

        return is_transacted

    def verify_transaction_signature(self, sender_public_key, signature, transaction):
        sha256 = hashlib.sha256()
        sha256.update(str(transaction).encode("utf-8"))
        message = sha256.digest()

        public_key = VerifyingKey.from_string(
            bytes.fromhex(sender_public_key), curve=NIST256p
        )

        return public_key.verify(bytes.fromhex(signature), message)

    def valid_proof(
        self, transactions, previous_hash, challenge, difficulty=MINING_DIFFICULTY
    ):
        guess_block = utils.sorted_dict_by_key(
            {
                "transactions": transactions,
                "previous_hash": previous_hash,
                "nonce": challenge,
            }
        )
        guess_hash = self.hash(guess_block)
        return guess_hash[:difficulty] == "0" * difficulty

    def proof_of_work(self):
        previous_hash = self.hash(self.chain[-1])
        challenge = 0
        while (
            self.valid_proof(self.transaction_pool, previous_hash, challenge) is False
        ):
            challenge += 1
        return challenge

    def mining(self):
        # if not self.transaction_pool:
            # logger.info({"action": "mining", "status": "fail", "error": "no transactions"})
            # return False
        self.add_transaction(
            sender_blockchain_address=MINING_SENDER,
            recipient_blockchain_address=self.blockchain_address,
            value=MINING_REWARD,
        )
        nonce = self.proof_of_work()
        previous_hash = self.hash(self.chain[-1])
        self.create_block(nonce, previous_hash)
        logger.info({"action": "mining", "status": "success"})

        for node in self.neighbors:
            requests.put(f"http://{node}/consensus")

        return True

    def start_mining(self):
        is_acquire = self.mining_semaphore.acquire(blocking=False)
        if is_acquire:
            with contextlib.ExitStack() as stack:
                stack.callback(self.mining_semaphore.release)
                self.mining()  # 10 min
                loop = threading.Timer(MINING_TIMER_SEC, self.start_mining)
                loop.start()

    def calculate_total_amount(self, blockchain_address):
        total_amount = 0.0
        for block in self.chain:
            for transaction in block["transactions"]:
                value = float(transaction["value"])
                if blockchain_address == transaction["recipient_blockchain_address"]:
                    total_amount += value
                if blockchain_address == transaction["sender_blockchain_address"]:
                    total_amount -= value
        return total_amount

    def valid_chain(self, chain):
        pre_block = chain[0]
        current_index = 1
        while current_index < len(chain):
            block = chain[current_index]
            if block["previous_hash"] != self.hash(pre_block):
                return False
            if not self.valid_proof(
                block["transactions"], block["previous_hash"], block["nonce"]
            ):
                return False
            pre_block = block
            current_index += 1
        return True

    def resolve_conflicts(self):
        longest_chain = None
        max_length = len(self.chain)
        for node in self.neighbors:
            response = requests.get(f"http://{node}/chain")
            if response.status_code == 200:
                response_json = response.json()
                chain = response_json["chain"]
                chain_length = len(chain)
                if chain_length > max_length and self.valid_chain(chain):
                    max_length = chain_length
                    longest_chain = chain

        if longest_chain:
            self.chain = longest_chain
            logger.info({"action": "resolve_conflicts", "status": "replaced"})
            return True

        logger.info({"action": "resolve_conflicts", "status": "no replaced"})
        return False
