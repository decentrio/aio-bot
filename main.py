import logging
import sys
import json
import threading
import time
import queue
from app.discord import DiscordClient
from app.slack import SlackClient
from app.telegram import TelegramClient
from utils.websocket import WebsocketClient
from feat.validator import Validators, Validator
from feat.proposal import Proposal
from feat.peggo import Peggo
from feat.balances import Balances
from feat.ibc import IBC

block_queue = queue.Queue()
tx_queue = queue.Queue()
logging.basicConfig(level=logging.INFO)

def getConfig():
    with open('config.json', 'r') as file:
        config = json.load(file)
    config["websockets"] = [
        (rpc.replace("http", "ws") + "/websocket")
        for rpc in config["rpcs"]
    ]
    return config

if __name__ == "__main__":
    config = getConfig()
    app = {
        "discord": None,
        "slack": None,
        "telegram": None,
    }

    if config["app"]["discord"]["enable"]:
        if app["discord"] is None:  # Avoid initializing it more than once
            app["discord"] = DiscordClient(config)
            discord_thread = threading.Thread(target=app["discord"].run)
            discord_thread.daemon = True
            discord_thread.start()
            print("Discord client started")

    if config["app"]["slack"]["enable"]:
        if app["slack"] is None:  # Avoid initializing it more than once
            app["slack"] = SlackClient(config)
            slack_thread = threading.Thread(target=app['slack'].start)
            slack_thread.daemon = True
            slack_thread.start()
            print("Slack client started")
    
    if config["app"]["telegram"]["enable"]:
        if app["telegram"] is None:  # Avoid initializing it more than once
            app["telegram"] = TelegramClient(config)
            telegram_thread = threading.Thread(target=app['telegram'].start)
            telegram_thread.daemon = True
            telegram_thread.start()
            print("Telegram client started")

    if config["features"]["validators"]["enable"]:
        if config["app"]["discord"]["enable"] and config["app"]["discord"]["mode"] == "chain":
            validators = Validators(
                app,
                block_queue,
                config["features"]["validators"]["params"],
                config["chain"],
                config["apis"]
            )
            validators_thread = threading.Thread(target=validators.run)
            validators_thread.daemon = True
            validators_thread.start()
            print("Validators chain mode started")
        if (config["app"]["discord"]["enable"] and config["app"]["discord"]["mode"] == "single") or config["app"]["slack"]["enable"] or config["app"]["telegram"]["enable"]:
            validator = Validator(
                app,
                block_queue,
                config["features"]["validators"]["params"],
                config["chain"],
                config["apis"]
            )
            validator_thread = threading.Thread(target=validator.run)
            validator_thread.daemon = True
            validator_thread.start()
            print("Validator single mode  started")

    if config["features"]["peggo"]["enable"]:
        peggo = Peggo(
            app,
            config["features"]["peggo"]["params"],
            config["apis"]
        )
        peggo_thread = threading.Thread(target=peggo.run)
        peggo_thread.daemon = True
        peggo_thread.start()
        print("Peggo client started")

    if config["features"]["gov"]["enable"]:
        proposal = Proposal(
            app,
            tx_queue,
            config["features"]["gov"]["params"],
            config["apis"],
            config["chain"]
        )
        proposal_thread = threading.Thread(target=proposal.run)
        proposal_thread.daemon = True
        proposal_thread.start()
        print("Gov client started")

    if config["features"]["wallet"]["enable"]:
        wallet = Balances(
            app,
            config["apis"],
            config["jsonrpcs"],
            config["features"]["wallet"]["params"]
        )
        wallet_thread = threading.Thread(target=wallet.run)
        wallet_thread.daemon = True
        wallet_thread.start()
        print("Wallet client started")
    
    if config["features"]["ibc"]["enable"]:
        ibc = IBC(
            app,
            config["features"]["ibc"]["params"],
        )
        ibc_thread = threading.Thread(target=ibc.run)
        ibc_thread.daemon = True
        ibc_thread.start()
        print("IBC client started")

    if config["features"]["validators"]["enable"] or config["features"]["gov"]["enable"]:
        topics = [
            {
                "jsonrpc": "2.0",
                "method": "subscribe",
                "id": 0,
                "params": {"query": "tm.event='NewBlock'"} # check valset every block to see if any validator has been missed
            },
            {
                "jsonrpc": "2.0",
                "method": "subscribe",
                "id": 0,
                "params": {
                    "query": "tm.event='Tx' AND message.action CONTAINS 'MsgSubmitProposal'" # check any new submit_proposal tx and
                }
            },
            {
                "jsonrpc": "2.0",
                "method": "subscribe",
                "id": 0,
                "params": {
                    "query": "tm.event='ValidatorSetUpdates'" # check valset updates, VP changes, active/inactive statuses
                }
            }
        ]
        ws_client = WebsocketClient(config['websockets'], topics, block_queue, tx_queue)
        ws_thread = threading.Thread(target=ws_client.connect)
        ws_thread.daemon = True
        ws_thread.start()
        print("Websocket client started")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        logging.info("Application interrupted. Shutting down.")
        sys.exit(0)
