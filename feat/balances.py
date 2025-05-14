import json
import time
import utils.query as query
import logging
import asyncio

class Balances:
    def __init__(self, app, apis, jsonrpcs, params):
        self.app: dict = app
        self.apis: list = apis
        self.jsonrpcs: list = jsonrpcs
        self.params: dict = params

        self.logger = logging.getLogger("Balances")
        self.logger.setLevel(logging.DEBUG)

    def get_eth_balance(self, address):
        """
        Fetching the eth balance
        """
        try:
            data = query.query(
                self.jsonrpcs, 
                method="GET", 
                body={
                    "jsonrpc": "2.0",
                    "method": "eth_getBalance",
                    "params": [address, "latest"],
                    "id": 1
                }
            )
            return int(data["result"], 16) / 10**18
        except Exception as e:
            self.logger.error(f"Error fetching eth balance: {e}")
            return None

    def get_inj_balance(self, address):
        """
        Fetching the inj balance
        """
        try:
            data = query.query(self.apis, path=f"/cosmos/bank/v1beta1/balances/{address}")
            for i in data["balances"]:
                if i["denom"] == "inj":
                    return int(i["amount"]) / 10**18
            return 0
        except Exception as e:
            self.logger.error(f"Error fetching inj balance: {e}")
            return None

    def check(self, validator, address):
        if address.startswith("inj1"):
            balance = self.get_inj_balance(address)
            if balance != None and balance <= self.params["threshold"]["inj"]:
                val_info = query.query(self.apis, path=f"/cosmos/staking/v1beta1/validators/{validator}")
                self.notify({
                    "type": "low_balance",
                    "args": {
                        "validator": validator,
                        "address": address,
                        "moniker": val_info["validator"]["description"]["moniker"],
                        "balance": f"{balance:,.2f} INJ",
                    },
                    "auto_delete": None
                })
        elif address.startswith("0x"):
            balance = self.get_eth_balance(address)
            if balance != None and balance <= self.params["threshold"]["eth"]:
                val_info = query.query(self.apis, path=f"/cosmos/staking/v1beta1/validators/{validator}")
                self.notify({
                    "type": "low_balance",
                    "args": {
                        "validator": validator,
                        "address": address,
                        "moniker": val_info["validator"]["description"]["moniker"],
                        "balance": f"{balance:,.2f} ETH",
                    },
                    "auto_delete": None
                })
        else:
            self.logger.error(f"Invalid address: {address}")
            self.notify({
                "type": "invalid_address",
                "args": {
                    "validator": validator,
                    "address": address
                },
                "auto_delete": None
            })
            return
        
    def notify(self, platform, message):
        # try:
            # Discord
            if platform == "discord" and self.app["discord"] is not None:
                discord_client = self.app["discord"]
                if discord_client.loop:
                    subscriptions = discord_client.subscriptions
                    msg = None
                    user = ""
                    for sub in subscriptions:
                        if sub["validator"] == message['args']['validator']:
                            user += f" <@{sub['user']}>"
                    if message['type'] == "low_balance":
                        msg = discord_client.compose_embed(
                            title = f"{message['args']['moniker']} has low balance!",
                            description = "Peggo Address: " + message['args']['address'],
                            fields = [
                                {
                                    "name": "Balance",
                                    "value": message['args']['balance'],
                                    "inline": True
                                }
                            ],
                            footer=f"This message will be automatically deleted in {message['auto_delete']}s" if message['auto_delete'] != None else "",
                            color = 0xffd100
                        )
                    elif message['type'] == "invalid_address":
                        msg = discord_client.compose_embed(
                            title = f"Invalid address!",
                            description = "Peggo Address: " + message['args']['address'],
                            footer=f"This message will be automatically deleted in {message['auto_delete']}s" if message['auto_delete'] != None else "",
                            color = 0xffd100
                        )

                    future = asyncio.run_coroutine_threadsafe(
                        discord_client.reply(
                            discord_client.channels["wallet"]["id"],
                            msg,
                            user,
                            message['auto_delete']
                        ),
                        discord_client.loop
                    )
                    # Optionally, wait for the coroutine to finish and handle exceptions
                    future.result()
                else:
                    self.logger.error("Discord client loop not ready.")
            else:
                self.logger.error("Discord client is not initialized.")

            # Slack 
            if platform == "slack" and self.app["slack"] is not None:
                slack_client = self.app["slack"]
                subscriptions = slack_client.subscriptions
                msg = None
                for sub in subscriptions:
                    if sub["validator"] == message['args']['validator']:
                        if message['type'] == "low_balance":
                            msg = f"Low balance: {message['args']['address']}!\n" \
                                f"Balance: {message['args']['balance']}"
                        elif message['type'] == "invalid_address":
                            msg = f"Invalid address: {message['args']['address']}!"

                        slack_client.reply(
                            msg,
                            slack_client.channels["wallet"]["webhook_url"],
                        )
            else:
                self.logger.error("Slack client is not initialized")

            # Telegram
            if platform =="telegram" and self.app["telegram"] is not None and len(self.app["telegram"].subscriptions):
                telegram_client = self.app["telegram"]
                if telegram_client.loop:
                    subscriptions = telegram_client.subscriptions
                    msg = None
                    for sub in subscriptions:
                        if sub["validator"] == message['args']['validator']:
                            if message['type'] == "low_balance":
                                msg = f"Low balance: {message['args']['address']}!\n" \
                                    f"Balance: {message['args']['balance']}"
                            elif message['type'] == "invalid_address":
                                msg = f"Invalid address: {message['args']['address']}!"

                            future = asyncio.run_coroutine_threadsafe(
                                telegram_client.send_message(
                                    msg,
                                    sub["user"]
                                ),
                                telegram_client.loop
                            )
                            future.result()
                else:
                    self.logger.error("Telegram client loop not ready.")
            else:
                self.logger.error("Telegram client is not initialized")
            
        # except Exception as e:
        #     self.logger.error(f"Error sending message: {e}")

    async def start_balances_polling(self):
        while True:
            time.sleep(30)
            self.logger.info("Fetching addresses balance status ...")
            for platform in ["discord", "slack", "telegram"]:
                if self.app[platform] is not None:
                    client = self.app[platform]
                    subscriptions = client.subscriptions
                    for sub in subscriptions:
                        self.logger.debug(f"Checking balance: {sub['validator']}")
                        if sub["validator"].startswith("inj"):
                            address = query.query(self.apis, path=f"/peggy/v1/query_delegate_keys_by_validator?validator_address={sub['validator']}")
                            self.check(sub["validator"], address["eth_address"])
                            self.check(sub["validator"], address["orchestrator_address"])
                        else:
                            self.notify(
                                platform,
                                {
                                "type": "invalid_address",
                                "args": {
                                    "validator": sub["validator"],
                                    "address": sub["validator"]
                                },
                                "auto_delete": None
                            })

            time.sleep(self.params["interval"] - 30)

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.start_balances_polling())
