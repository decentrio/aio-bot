import time
import utils.query as query
import json
import logging
import asyncio

class Peggo:
    def __init__(self, app, params, apis):
        self.operators: dict = {}
        self.app: dict = app
        self.apis: str = apis
        self.params: dict = params
        self.logger = logging.getLogger("Peggo")
        self.logger.setLevel(logging.INFO)
    
    def get_height(self) -> int:
        """
        Fetching the latest block height
        """
        try:
            data = query.query(self.apis, path=f"/cosmos/base/tendermint/v1beta1/blocks/latest")
            height = int(data['block']['header']['height'])
            return height
        except Exception as e:
            self.logger.error(f"Error fetching block height: {e}")
            return -1

    def get_module_state(self) -> tuple[int, list]:
        """
        Fetching Last Observed Peggo Nonce
        """
        try:
            data = query.query(self.apis, path=f"/peggy/v1/module_state")
            lon = int(data['state']['last_observed_nonce'])
            valset_confirms = data["state"]["valset_confirms"]
            batch_confirms = data["state"]["batch_confirms"]
            return lon, valset_confirms, batch_confirms
        except Exception as e:
            self.logger.error(f"Error fetching last observed nonce: {e}")
            return None
        
    def get_lce(self, orchestrator) -> int:
        try:
            data = query.query(self.apis, path=f"/peggy/v1/oracle/event/{orchestrator}")
            lce = int(data['last_claim_event']['ethereum_event_nonce'])
            return lce
        except Exception as e:
            self.logger.error(f"Error fetching last claim event: {e}")
            return None
        
    def check(self, operator: dict):
        if len(operator["valset_confirms"]) != 0:
            check = False
            for op in operator["valset_confirms"]:
                if op["orchestrator"] == operator["orchestrator_address"]:
                    check = True
                    break
            if not check:
                self.notify({
                    "type": "pending_valsets",
                    "args": {
                        "validator": operator["valoper_address"],
                        "orchestrator": operator["orchestrator_address"],
                        "moniker": operator["moniker"],
                        "last_height": f"{operator["last_height"]:,}"
                    },
                    "auto_delete": None
                })

        if len(operator["batch_confirms"]) != 0:
            check = False
            for op in operator["valset_confirms"]:
                if op["orchestrator"] == operator["orchestrator_address"]:
                    check = True
                    break
            if not check:
                self.notify({
                    "type": "pending_valsets",
                    "args": {
                        "validator": operator["valoper_address"],
                        "orchestrator": operator["orchestrator_address"],
                        "moniker": operator["moniker"],
                        "last_height": f"{operator["last_height"]:,}"
                    },
                    "auto_delete": None
                })

        if abs(operator["last_observed_nonce"] - operator["last_claim_eth_event_nonce"]) >= self.params["threshold"]:
            self.notify({
            "type": "nonce_mismatch",
            "args": {
                "validator": operator["valoper_address"],
                "orchestrator": operator["orchestrator_address"],
                "moniker": operator["moniker"],
                "last_observed_nonce": f"{operator["last_observed_nonce"]:,}",
                "last_claim_eth_event_nonce": f"{operator["last_claim_eth_event_nonce"]:,}",
                "last_height": f"{operator["last_height"]:,}"
            },
            "auto_delete": None
            })

    def notify(self, message):
        # Discord client
        try:
            if self.app["discord"] is not None:
                discord_client = self.app["discord"]
                if discord_client.loop:
                    subscriptions = discord_client.subscriptions
                    msg = None
                    user = ""
                    for sub in subscriptions:
                        if sub["validator"] == message['args']['validator']:
                            user += f" <@{sub['user']}>"
                            
                    if message['type'] == "pending_valsets":
                        msg = discord_client.compose_embed(
                            title = f"**{message['args']['moniker']} hasn't signed in latest valset_confirms!**",
                            fields = [
                                {
                                    "name": "Last Height Checked",
                                    "value": message['args']['last_height'],
                                    "inline": True
                                },
                                {
                                    "name": "Orchestrator Address",
                                    "value": message['args']['orchestrator'],
                                    "inline": True
                                }
                            ],
                            footer=f"This message will be automatically deleted in {message['auto_delete']}s" if message['auto_delete'] != None else "",
                            color = 0xffd100
                        )
                    elif message['type'] == "pending_batches":
                        msg = discord_client.compose_embed(
                            title = f"**Pending batches found!**",
                            fields = [
                                {
                                    "name": "Orchestrator Address",
                                    "value": message['args']['orchestrator'],
                                    "inline": True
                                },
                                {
                                    "name": "Pending Batches",
                                    "value": message['args']['pending_batches'],
                                    "inline": True
                                },
                                {
                                    "name": "Last Height Checked",
                                    "value": message['args']['last_height'],
                                    "inline": True
                                }
                            ],
                            footer=f"This message will be automatically deleted in {message['auto_delete']}s" if message['auto_delete'] != None else "",
                            color = 0xffd100
                        )
                    elif message['type'] == "nonce_mismatch":
                        msg = discord_client.compose_embed(
                            title = f"**{message['args']['moniker']}'s nonce is lagging behind!**",
                            fields = [
                                {
                                    "name": "Orchestrator Address",
                                    "value": message['args']['orchestrator'],
                                    "inline": True
                                },
                                {
                                    "name": "Last Observed Nonce",
                                    "value": message['args']['last_observed_nonce'],
                                    "inline": True
                                },
                                {
                                    "name": "Last Claimed Ethereum Event Nonce",
                                    "value": message['args']['last_claim_eth_event_nonce'],
                                    "inline": True
                                },
                                {
                                    "name": "Last Height Checked",
                                    "value": message['args']['last_height'],
                                    "inline": False
                                }
                            ],
                            footer=f"This message will be automatically deleted in {message['auto_delete']}s" if message['auto_delete'] != None else "",
                            color = 0xffd100
                        )
                    if discord_client.mode == "chain":
                        future = asyncio.run_coroutine_threadsafe(
                            discord_client.reply(
                                discord_client.channels["peggo"]["id"],
                                msg,
                                user,
                                auto_delete=message['auto_delete']
                            ),
                            discord_client.loop
                        )
                        # Optionally, wait for the coroutine to finish and handle exceptions
                        future.result()
                    elif discord_client.mode == "single":
                        for sub in subscriptions:
                            if sub["validator"] == message["args"]["validator"]:
                                future = asyncio.run_coroutine_threadsafe(
                                    discord_client.reply(
                                        discord_client.channels["peggo"]["id"],
                                        msg,
                                        auto_delete=message['auto_delete']
                                    ),
                                    discord_client.loop
                                )
                                # Optionally, wait for the coroutine to finish and handle exceptions
                                future.result()
                else:
                    self.logger.error("Discord client loop not ready.")
            else:
                self.logger.error("Discord client is not initialized.")

            # Slack client
            if self.app["slack"] is not None:
                slack_client = self.app["slack"]
                subscriptions = slack_client.subscriptions
                user = ""
                msg = None
                for sub in subscriptions:
                    if sub.get("validator") == message['args']['validator']:
                        user += f" <@{sub['user']}>"
                
                # for sub in subscriptions:
                #     if sub["validator"] == message["args"]["validator"]:
                if message['type'] == "pending_valsets":
                    msg = f"{user} *{message['args']['moniker']} has pending valsets!*\n" \
                        f"Pending Valsets: `{message['args']['pending_valsets']}`\n" \
                        f"Last Height Checked: `{message['args']['last_height']}`"
                elif message['type'] == "pending_batches":
                    msg = f"{user} *{message['args']['moniker']} has pending batches!*\n" \
                        f"Pending Batches: `{message['args']['pending_batches']}`\n" \
                        f"Last Height Checked: `{message['args']['last_height']}`"
                elif message['type'] == "nonce_mismatch":
                    msg = f"{user} *{message['args']['moniker']}'s nonce is lagging behind!*\n" \
                        f"Last Observed Nonce: `{message['args']['last_observed_nonce']}`\n" \
                        f"Last Claimed Ethereum Event Nonce: `{message['args']['last_claim_eth_event_nonce']}`\n" \
                        f"Last Height Checked: `{message['args']['last_height']}`"
                    
                slack_client.reply(
                        msg,
                        slack_client.channels["peggo"]["webhook_url"],
                )
            else:
                self.logger.error("Slack client is not initialized.")

            # Telegram client
            if self.app["telegram"] is not None:
                telegram_client = self.app["telegram"]
                if telegram_client.loop:
                    subscriptions = telegram_client.subscriptions
                    msg = None
                    for sub in subscriptions:
                        if "validator" in sub and sub["validator"] == message["args"]["validator"]:
                            if message['type'] == "pending_valsets":
                                msg = f"*{message['args']['moniker']} has pending valsets!*\n" \
                                    f"Pending Valsets: `{message['args']['pending_valsets']}`\n" \
                                    f"Last Height Checked: `{message['args']['last_height']}`"
                            elif message['type'] == "pending_batches":
                                msg = f"*{message['args']['moniker']} has pending batches!*\n" \
                                    f"Pending Batches: `{message['args']['pending_batches']}`\n" \
                                    f"Last Height Checked: `{message['args']['last_height']}`"
                            elif message['type'] == "nonce_mismatch":
                                msg = f"*{message['args']['moniker']}'s nonce is lagging behind!*\n" \
                                    f"Last Observed Nonce: `{message['args']['last_observed_nonce']}`\n" \
                                    f"Last Claimed Ethereum Event Nonce: `{message['args']['last_claim_eth_event_nonce']}`\n" \
                                    f"Last Height Checked: `{message['args']['last_height']}`"
                            
                            future = asyncio.run_coroutine_threadsafe(
                                telegram_client.reply(
                                    msg,
                                    sub["user"],
                                ),
                                telegram_client.loop
                            )
                            future.result()
                else:
                    self.logger.error("Telegram client loop not ready.")
            else:
                self.logger.error("Telegram client is not initialized.")
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")

    async def start_peggo_polling(self):
        while True:           
            time.sleep(30)
            self.logger.info("Fetching validators peggo status ...")
            with open('validators.json', 'r') as file:
                validators = json.load(file)
            
            for validator in validators:
                self.logger.debug(f"Checking {validator['moniker']} ...")
                valoper_address = validator['operator_address']
                try:
                    address = query.query(self.apis, path=f"/peggy/v1/query_delegate_keys_by_validator?validator_address={valoper_address}")
                    self.operators[valoper_address] = address
                    self.operators[valoper_address]["valoper_address"] = valoper_address
                    self.operators[valoper_address]["moniker"] = validator['moniker']
                    self.operators[valoper_address]["last_height"] = self.get_height()
                    self.operators[valoper_address]["last_observed_nonce"], self.operators[valoper_address]["valset_confirms"], self.operators[valoper_address]["batch_confirms"]= self.get_module_state()
                    self.operators[valoper_address]["last_claim_eth_event_nonce"] = self.get_lce(address["orchestrator_address"])
                    self.check(self.operators[valoper_address])
                    time.sleep(5) # Sleep for 5 seconds to prevent rate limiting
                except Exception as e:
                    self.logger.error(f"Error fetching operator status: {e}")

            self.operators = {}
            self.logger.info("Finished")
            time.sleep(self.params["interval"] - 30)


    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.start_peggo_polling())