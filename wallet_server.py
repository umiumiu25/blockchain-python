import urllib.parse

from flask import Flask
from flask import jsonify
from flask import render_template
from flask import request
import requests

import wallet

app = Flask(__name__, template_folder="./templates")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/wallet", methods=["POST"])
def create_wallet():
    w = wallet.Wallet()
    response = {
        "private_key": w.private_key,
        "public_key": w.public_key,
        "blockchain_address": w.blockchain_address,
    }
    return jsonify(response), 200


@app.route("/transactions", methods=["POST"])
def create_transaction():
    request_json = request.json
    required_fields = [
        "sender_public_key",
        "sender_private_key",
        "sender_blockchain_address",
        "recipient_blockchain_address",
        "value",
    ]
    if not all([field in request_json for field in required_fields]):
        response = {"message": "missing required fields"}
        return jsonify(response), 400

    sender_public_key = request_json["sender_public_key"]
    sender_private_key = request_json["sender_private_key"]
    sender_blockchain_address = request_json["sender_blockchain_address"]
    recipient_blockchain_address = request_json["recipient_blockchain_address"]
    value = float(request_json["value"])

    t = wallet.Transaction(
        sender_blockchain_address,
        recipient_blockchain_address,
        value,
        sender_private_key,
        sender_public_key,
    )

    json_data = {
        "sender_blockchain_address": sender_blockchain_address,
        "recipient_blockchain_address": recipient_blockchain_address,
        "value": value,
        "sender_public_key": sender_public_key,
        "signature": t.generate_signature(),
    }

    response = requests.post(
        urllib.parse.urljoin(app.config["gateway"], "/transactions"),
        json=json_data,
        timeout=3,
    )

    if response.status_code == 201:
        return jsonify({"message": "success"}), 201
    return jsonify({"message": "fail", "response": response}), 400


@app.route("/wallet/amount", methods=["GET"])
def calculate_amount():
    required = ["blockchain_address"]
    if not all([field in request.args for field in required]):
        response = {"message": "missing required fields"}
        return jsonify(response), 400

    my_blockchain_address = request.args.get("blockchain_address")
    response = requests.get(
        urllib.parse.urljoin(app.config["gateway"], "amount"),
        params={"blockchain_address": my_blockchain_address},
        timeout=3,
    )
    if response.status_code == 200:
        total = response.json()["amount"]
        return jsonify({"message": "success", "amount": total}), 200
    return jsonify({"message": "fail", "error": response.content}), 400


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument(
        "-p", "--port", default=8080, type=int, help="port to listen on"
    )
    parser.add_argument(
        "-g",
        "--gateway",
        default="http://127.0.0.1:5001",
        type=str,
        help="blockchain gateway",
    )
    args = parser.parse_args()
    port = args.port
    app.config["gateway"] = args.gateway

    app.run(host="0.0.0.0", port=port, threaded=True, debug=True)
