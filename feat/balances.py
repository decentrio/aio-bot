import time
import utils.query as query
import logging
import asyncio
import requests

class Balances:
    def __init__(self, app, api, params):
        self.app = app
        self.api = api
        self.params = params

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("Balances")

    def get_eth_balance(self, address):
        """
        Fetching the eth balance
        """
        try:
            data = requests.get(f"",{
                "jsonrpc": "2.0",
                "method": "eth_getBalance",
                "params": [address, "latest"],
                "id": 1
            }).json()
            height = int(data['block']['header']['height'])
            return height
        except Exception as e:
            self.logger.error(f"Error fetching eth balance: {e}")
            self.notify({
                "type": "invalid_address",
                "args": {
                    "address": address
                }
            })

    def get_inj_balance(self, address):
        """
        Fetching the inj balance
        """
        try:
            data = query.query(f"{self.api}/cosmos/bank/v1beta1/balances/{address}")
            print(data)
            for i in data["balances"]:
                if i["denom"] == "inj":
                    return int(i["amount"])
        except Exception as e:
            self.logger.error(f"Error fetching inj balance: {e}")
            self.notify({
                "type": "invalid_address",
                "args": {
                    "address": address
                }
            })

    def check(self, address):
        if address.startswith("inj1"):
            balance = self.get_inj_balance(address)
            if balance <= self.params["threshold"]:
                self.notify({
                    "type": "low_balance",
                    "args": {
                        "address": address,
                        "balance": balance,
                    }
                })
        elif address.startswith("0x"):
            balance = self.get_eth_balance(address)
            if balance <= self.params["threshold"]:
                self.notify({
                    "type": "low_balance",
                    "args": {
                        "address": address,
                        "balance": balance,
                    }
                })
        else:
            self.logger.error(f"Invalid address: {address}")
            self.notify({
                "type": "invalid_address",
                "args": {
                    "address": address
                }
            })

    def notify(self, message):
        try:
            # Discord
            if self.app["discord"] is not None:
                discord_client = self.app["discord"]
                if discord_client.loop:
                    subscriptions = discord_client.subscriptions
                    msg = None
                    user = ""
                    for sub in subscriptions:
                        if "address" in sub.keys() and sub["address"] == message['args']['address']:
                            user += f" <@{sub['user']}>"
                    if message['type'] == "low_balance":
                        msg = discord_client.compose_embed(
                            title = f"Low balance: {message['args']['address']}!",
                            description = user,
                            fields = [
                                {
                                    "name": "Balance",
                                    "value": message['args']['balance'],
                                    "inline": True
                                }
                            ],
                            footer = "This message will be automatically deleted in 60s",
                            color = 0xffd100
                        )
                    elif message['type'] == "invalid_address":
                        msg = discord_client.compose_embed(
                            title = f"Invalid address: {message['args']['address']}!",
                            description = user,
                            footer = "This message will be automatically deleted in 60s",
                            color = 0xffd100
                        )
                    future = asyncio.run_coroutine_threadsafe(
                        discord_client.reply(
                            discord_client.channels[0]["id"],
                            msg,
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
            if self.app["slack"] is not None:
                slack_client = self.app["slack"]
                subscriptions = slack_client.subscriptions
                msg = None
                for sub in subscriptions:
                    if sub["validator"] == message['args']['address']:
                        if message['type'] == "low_balance":
                            msg = f"Low balance: {message['args']['address']}!\n" \
                                f"Balance: {message['args']['balance']}"
                        elif message['type'] == "invalid_address":
                            msg = f"Invalid address: {message['args']['address']}!"

                        slack_client.reply(
                            msg,
                            slack_client.channels[0]["id"],
                        )
            else:
                self.logger.error("Slack client is not initialized")

            # Telegram
            if self.app["telegram"] is not None:
                telegram_client = self.app["telegram"]
                if telegram_client.loop:
                    subscriptions = telegram_client.subscriptions
                    msg = None
                    for sub in subscriptions:
                        if sub["address"] == message['args']['address']:
                            if message['type'] == "low_balance":
                                msg = f"Low balance: {message['args']['address']}!\n" \
                                    f"Balance: {message['args']['balance']}"
                            elif message['type'] == "invalid_address":
                                msg = f"Invalid address: {message['args']['address']}!"

                            future = asyncio.run_coroutine_threadsafe(
                                telegram_client.send_message(
                                    msg,
                                    telegram_client.channels[0]["id"]
                                ),
                                telegram_client.loop
                            )
                            future.result()
                else:
                    self.logger.error("Telegram client loop not ready.")
            else:
                self.logger.error("Telegram client is not initialized")
            
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")

    async def start_balances_polling(self):
        while True:
            time.sleep(30)
            self.logger.info("Fetching addresses status ...")
            if self.app["discord"] is not None:
                discord_client = self.app["discord"]
                subscriptions = discord_client.subscriptions;
                for sub in subscriptions:
                    if "address" in sub.keys():
                        self.logger.info(f"Checking {sub['address']} ...")
                        self.check(sub["address"])

            if self.app["slack"] is not None:
                slack_client = self.app["slack"]
                subscriptions = slack_client.subscriptions
                for sub in subscriptions:
                    if "address" in sub.keys():
                        self.logger.info(f"Checking {sub['address']} ...")
                        self.check(sub["address"])

            if self.app["telegram"] is not None:
                telegram_client = self.app["telegram"]
                subscriptions = telegram_client.subscriptions
                for sub in subscriptions:
                    if "address" in sub.keys():
                        self.logger.info(f"Checking {sub['address']} ...")
                        self.check(sub["address"])
            time.sleep(1170)

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.start_balances_polling())
