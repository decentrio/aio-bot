import json
import asyncio
import logging
import time
import threading
import utils.query as query
import utils.pubkey as pubkey

# Chain mode
class Validators:
    def __init__(self, app, block_queue, params, chain, apis, mode):
        self.logger = logging.getLogger("Validators")
        self.logger.setLevel(logging.INFO)
        self.prefix = params["prefix"] + "valcons"
        self.missed = {
            "height": 0,
            "missed": []
        }
        self.mode = mode
        self.block_queue = block_queue
        self.app = app
        self.apis = apis
        self.chain = chain
        self.params = self.getSlashingParams()
        self.params.update(params)
        self.validators = self.getValidators(params["prefix"] + "valcons")


    def getValidators(self, prefix) -> list:
        validators = []
        try:
            data = query.query(self.apis, path=f"/cosmos/staking/v1beta1/validators?status=BOND_STATUS_BONDED&pagination.limit=200&pagination.count_total=true")
            for val in data["validators"]:
                hex_address, valcons_address = pubkey.convert(
                    val["consensus_pubkey"]["key"], prefix)
                validators.append({
                    "moniker": val["description"]["moniker"],
                    "operator_address": val["operator_address"],
                    "valcons_address": valcons_address,
                    "hex": hex_address,
                    "missed": 0,
                    "missed_percentage": 0,
                    "warning_level": 0
                })
            with open("validators.json", "w") as f:
                json.dump(validators, f, indent=4)
            return validators
        except Exception as e:
            raise e

    # Val not appear in current valset (new val)
    def findValbyPubkey(self, pub_key) -> dict:
        try:
            data = query.query(self.apis, path=f"/cosmos/staking/v1beta1/validators?pagination.limit=200&pagination.count_total=true")
            for val in data["validators"]:
                if val["consensus_pubkey"]["key"] == pub_key:
                    hex_address, valcons_address = pubkey.convert(
                        val["consensus_pubkey"]["key"], self.prefix)
                    return {
                        "moniker": val["description"]["moniker"],
                        "operator_address": val["operator_address"],
                        "valcons_address": valcons_address,
                        "hex": hex_address,
                        "missed": 0,
                        "missed_percentage": 0,
                        "warning_level": 0
                    }
            return None
        except Exception:
            return None

    def getSlashingParams(self) -> dict:
        try: 
            data = query.query(self.apis, path=f"/cosmos/slashing/v1beta1/params")
            result = {
                "signed_blocks_window": int(data["params"]["signed_blocks_window"]),
                "min_signed_per_window": float(data["params"]["min_signed_per_window"]),
                "jailed_duration": data["params"]["downtime_jail_duration"]
            }
            return result
        except Exception:
            self.logger.error("Error getting slashing params.")
            return None
    
    def checkSigningPerformance(self) -> dict:
        try:
            block = query.query(self.apis, path=f"/cosmos/base/tendermint/v1beta1/blocks/latest")
            self.missed["height"] = int(block["block"]["header"]["height"])
            data = query.query(self.apis, path=f"/cosmos/slashing/v1beta1/signing_infos?pagination.limit=200&pagination.count_total=true")
            for val in data["info"]:
                validator = next(filter(lambda x: x["valcons_address"] == val["address"], self.validators), None)
                if validator is None:
                    continue

                missed_percentage = int(val["missed_blocks_counter"]) / (self.params["signed_blocks_window"] * (1 - self.params["min_signed_per_window"]))
                current_warning_level = validator["warning_level"]
                
                if missed_percentage > self.params["threshold"][3]["value"]: # CRITICAL
                    validator["warning_level"] = 3
                elif missed_percentage > self.params["threshold"][2]["value"]: # WARNING
                    validator["warning_level"] = 2
                elif missed_percentage > self.params["threshold"][1]["value"]: # ATTENTION
                    validator["warning_level"] = 1
                else:
                    validator["warning_level"] = 0

                if missed_percentage > self.params["threshold"][1]["value"]: # ATTENTION
                    if int(val["missed_blocks_counter"]) < validator["missed"] and missed_percentage < self.params["threshold"][current_warning_level]["value"]:
                        self.notify({
                            "type": "recovering",
                            "args": {
                                "validator": validator["operator_address"],
                                "moniker": validator["moniker"],
                                "missed_percentage": missed_percentage
                            },
                            "auto_delete": None
                        })
                    elif int(val["missed_blocks_counter"]) > validator["missed"] and current_warning_level < 3 and missed_percentage >= self.params["threshold"][current_warning_level + 1]["value"]:
                        self.notify({
                            "type": "miss_block",
                            "args": {
                                "validator": validator["operator_address"],
                                "moniker": validator["moniker"],
                                "window_missed": int(val["missed_blocks_counter"]),
                                "missed_percentage": missed_percentage,
                                "warning_level": self.params["threshold"][validator["warning_level"]]["label"]
                            },
                            "auto_delete": None
                        })
                    validator["missed"] = int(val["missed_blocks_counter"])
                    validator["missed_percentage"] = missed_percentage
                    self.missed["missed"].append(validator["moniker"])
                elif missed_percentage < self.params["threshold"][0]["value"]: # ACTIVE
                    if validator["missed_percentage"] > self.params["threshold"][1]["value"]: # ATTENTION
                        self.logger.debug(f"Validator {validator['moniker']} is active after misses blocks!")
                        self.notify({
                            "type": "active",
                            "args": {
                                "validator": validator["operator_address"],
                                "moniker": validator["moniker"],
                            },
                            "auto_delete": None
                        })
                    validator["missed"] = int(val["missed_blocks_counter"])
                    validator["missed_percentage"] = missed_percentage
                    validator["warning_level"] = 0
            self.logger.debug(self.missed)
            self.missed["missed"] = []
        except Exception as e:
            self.logger.error(f"Error getting signing performance: {e}")

    def start_check_valset(self):
        while True:
            if not self.block_queue.empty():
                data = self.block_queue.get()
                if data and "result" in data:
                    msg_type = data["result"]["query"]
                    if msg_type == "tm.event='ValidatorSetUpdates'":
                        valset = data["result"]["data"]["value"]["validator_updates"]
                        self.checkValset(valset)

    def checkValset(self, valset):
        self.logger.debug(f"Checking valset: {valset}")
        for val in valset:
            validator = next(filter(lambda x: x["hex"] == val["address"], self.validators), None)
            if validator and int(val["voting_power"]) == 0:  # inactive
                if validator["warning_level"] != 3:  # out active set
                    self.notify({
                        "type": "inactive",
                        "args": {
                            "validator": validator["operator_address"],
                            "moniker": validator["moniker"],
                        },
                        "auto_delete": None
                    })
                else:  # likely to be jailed
                    try:
                        check_jailed = query.query(self.apis, path=f"/cosmos/staking/v1beta1/validators/{validator['operator_address']}")
                        if check_jailed["validator"]["jailed"]:
                            data = query.query(self.apis, path=f"/cosmos/slashing/v1beta1/signing_infos/{validator['valcons_address']}")
                            self.notify({
                                "type": "jailed",
                                "args": {
                                    "validator": validator["operator_address"],
                                    "moniker": validator["moniker"],
                                    "jailed_until": data["val_signing_info"]["jailed_until"],
                                    "last_height": f"{self.missed["height"] - validator["missed"]:,}",
                                    "jailed_duration": self.params["jailed_duration"]
                                },
                                "auto_delete": None
                            })
                        else:
                            self.notify({
                                "type": "inactive",
                                "args": {
                                    "validator": validator["operator_address"],
                                    "moniker": validator["moniker"],
                                },
                                "auto_delete": None
                            })
                    except Exception as e:
                        self.logger.error(f"Error getting jailed info: {e}")
                self.validators.remove(validator)
            elif not validator and int(val["voting_power"]) > 0:
                new_validator = self.findValbyPubkey(val["pub_key"]["value"])
                if new_validator is not None:
                    self.validators.append(new_validator)
                    self.logger.debug(f"Validator {new_validator['moniker']} is new to active set!")
                    self.notify({
                        "type": "active",
                        "args": {
                            "validator": new_validator["operator_address"],
                            "moniker": new_validator["moniker"],
                        },
                        "auto_delete": None
                    })
                else:
                    self.logger.error(f"Validator not found: {val['address']}")

    async def start_block_polling(self): 
        valset_thread = threading.Thread(target=self.start_check_valset)
        valset_thread.daemon = True
        valset_thread.start()

        while True:
            time.sleep(self.params["interval"])
            self.checkSigningPerformance()
            with open("validators.json", "w") as f:
                json.dump(self.validators, f, indent=4)

    def notify(self, message):
        try:
            # Discord client, single + chain mode
            if self.app["discord"] is not None:
                discord_client = self.app["discord"]
                if discord_client.loop:
                    subscriptions = discord_client.subscriptions
                    msg = None
                    user = ""
                    for sub in subscriptions:
                        if sub.get("validator") == message['args']['validator']:
                            user += f" <@{sub['user']}>"

                    if message['type'] == "miss_block":
                        if message['args']['missed_percentage'] <= self.params["threshold"][2]["value"]: # WARNING
                            color = 0xfff942
                        elif message['args']['missed_percentage'] <= self.params["threshold"][3]["value"]: # CRITICAL
                            color = 0xff941a
                        else:
                            color = 0xff4d4d
                        msg = discord_client.compose_embed(
                            title=f"**[{message['args']['warning_level']}] {message['args']['moniker']} has missed more than {message['args']['missed_percentage'] * 100:.2f}% of the allowed missed blocks!**",
                            description=f"Last Signed Block: `{message['args']['last_height']}`" if "last_height" in message['args'] else "",
                            fields=[
                                {
                                    "name": "Blocks to JAILED",
                                    "value": int(self.params["signed_blocks_window"] * (1 - self.params["min_signed_per_window"]) - message['args']['window_missed']),
                                    "inline": True
                                },
                                {
                                    "name": "Window Signing Percentage",
                                    "value": f"{(self.params["signed_blocks_window"] - message['args']['window_missed'])} / {self.params["signed_blocks_window"]} ({((self.params["signed_blocks_window"] - message['args']['window_missed']) / self.params["signed_blocks_window"] * 100):.2f}%)",
                                    "inline": True
                                },
                                {
                                    "name": "Signing window",
                                    "value": self.params["signed_blocks_window"],
                                    "inline": True
                                }
                            ],
                            footer=f"This message will be automatically deleted in {message['auto_delete']}s" if message['auto_delete'] != None else "",
                            color=color
                        )
                    elif message['type'] == "recovering":
                        if message['args']['missed_percentage'] <= self.params["threshold"][2]["value"]: # WARNING
                            color = 0xfff942
                        elif message['args']['missed_percentage'] <= self.params["threshold"][3]["value"]: # CRITICAL
                            color = 0xff941a
                        else:
                            color = 0xff4d4d
                        msg = discord_client.compose_embed(
                            title=f"**[RECOVERING] {message['args']['moniker']} is recovering!**",
                            description="",
                            fields=[
                                {
                                    "name": "Window Signing Percentage",
                                    "value": f"{(1 - message['args']['missed_percentage']) * 100}%",
                                    "inline": True
                                }
                            ],
                            footer=f"This message will be automatically deleted in {message['auto_delete']}s" if message['auto_delete'] != None else "",
                            color=color
                        )
                    elif message['type'] == "active":
                        msg = discord_client.compose_embed(
                            title=f"**{message['args']['moniker']} is active again!**",
                            description="",
                            fields=[],
                            footer=f"This message will be automatically deleted in {message['auto_delete']}s" if message['auto_delete'] != None else "",
                            color=0x75ffd1,
                        )
                    elif message['type'] == "inactive":
                        msg = discord_client.compose_embed(
                            title=f"**{message['args']['moniker']} is inactive!**",
                            description="",
                            fields=[],
                            footer=f"This message will be automatically deleted in {message['auto_delete']}s" if message['auto_delete'] != None else "",
                            color=0x545454
                        )
                    elif message['type'] == "jailed":
                        msg = discord_client.compose_embed(
                            title=f"**{message['args']['moniker']} is JAILED!**",
                            description="",
                            fields=[
                                {
                                    "name": "Last Signed Block",
                                    "value": message['args']['last_height'],
                                    "inline": True
                                },
                                {
                                    "name": "Jailed Until",
                                    "value": message['args']['jailed_until'],
                                    "inline": True
                                },
                                {
                                    "name": "Jailed Duration",
                                    "value": message['args']['jailed_duration'],
                                    "inline": True
                                }
                            ],
                            footer=f"This message will be automatically deleted in {message['auto_delete']}s" if message['auto_delete'] != None else "",
                            color=0xde1212
                        )

                    if discord_client.mode == "chain" and self.mode == "chain":
                        future = asyncio.run_coroutine_threadsafe(
                            discord_client.reply(
                                discord_client.channels["validators"]["id"],
                                msg,
                                user,
                                message['auto_delete']
                            ),
                            discord_client.loop
                        )
                        future.result()
                    elif discord_client.mode == "single":
                        for sub in subscriptions:
                            if sub["validator"] == message['args']['validator']:
                                future = asyncio.run_coroutine_threadsafe(
                                    discord_client.reply(
                                        discord_client.channels["validators"]["id"],
                                        msg,
                                        auto_delete=message['auto_delete']
                                    ),
                                    discord_client.loop
                                )
                                future.result()
                else:
                    self.logger.error("Discord client loop not ready.")
            else:
                self.logger.error("Discord client is not initialized.")

            # Slack client, single + chain mode
            if self.app["slack"] is not None:
                slack_client = self.app["slack"]
                subscriptions = slack_client.subscriptions
                user = ""
                msg = None
                for sub in subscriptions:
                    if sub.get("validator") == message['args']['validator']:
                        user += f" <@{sub['user']}>"

                if message['type'] == "miss_block":
                    msg = f"""
{user} *[{message['args']['warning_level']}] {message['args']['moniker']} has missed more than {message['args']['missed_percentage'] * 100:.2f}% of the allowed missed blocks!*\n
Blocks to JAILED: `{int(self.params["signed_blocks_window"] * (1 - self.params["min_signed_per_window"]) - message['args']['window_missed'])}`\n
Window Signing Percentage: `{(self.params['signed_blocks_window'] - message['args']['window_missed'])} / {self.params['signed_blocks_window']} ({((self.params['signed_blocks_window'] - message['args']['window_missed']) / self.params['signed_blocks_window'] * 100):.2f}%)`\n
Signing window: `{self.params['signed_blocks_window']}`\n
Min signed per window: `{self.params['min_signed_per_window'] * 100}%`
                    """
                elif message['type'] == "recovering":
                    msg = f"""
{user} *[RECOVERING] {message['args']['moniker']} is recovering!*\n
Window Signing Percentage: `{(1 - message['args']['missed_percentage']) * 100}%`
                    """
                elif message['type'] == "active":
                    msg = f"{user} *{message['args']['moniker']} is active again!*"
                elif message['type'] == "inactive":
                    msg = f"{user} *{message['args']['moniker']} is inactive!**"
                elif message['type'] == "jailed":
                    msg = f"{user} *{message['args']['moniker']} is JAILED!*\n" \
                        f"Last Signed Block: `{message['args']['last_height']}`\n" \
                        f"Jailed Until: `{message['args']['jailed_until']}`\n" \
                        f"Jailed Duration: `{message['args']['jailed_duration']}`"
                    
                slack_client.reply(
                    msg,
                    slack_client.channels["validator"]["webhook_url"],
                )
            else:
                self.logger.error("Slack client is not initialized.")

            # Telegram client, single mode only
            if self.app["telegram"] is not None and len(self.app["telegram"].subscriptions):
                telegram_client = self.app["telegram"]
                if telegram_client.loop:
                    subscriptions = telegram_client.subscriptions
                    msg = None
                    for sub in subscriptions:
                        if "validator" in sub and sub["validator"] == message['args']['validator']:
                            if message['type'] == "miss_block":
                                msg = f"""
*[{message['args']['warning_level']}] {message['args']['moniker']} has missed more than {message['args']['missed_percentage'] * 100:.2f}% of the allowed missed blocks!*
Blocks to JAILED: `{int(self.params["signed_blocks_window"] * (1 - self.params["min_signed_per_window"]) - message['args']['window_missed'])}`
Window Signing Percentage: `{(self.params['signed_blocks_window'] - message['args']['window_missed'])} / {self.params['signed_blocks_window']} ({((self.params['signed_blocks_window'] - message['args']['window_missed']) / self.params['signed_blocks_window'] * 100):.2f}%)`
Signing window: `{self.params['signed_blocks_window']}`
Min signed per window: `{self.params['min_signed_per_window'] * 100}%`
                                """
                            elif message['type'] == "recovering":
                                msg = f"""
*[RECOVERING] {message['args']['moniker']} is recovering!*
Window Signing Percentage: `{(1 - message['args']['missed_percentage']) * 100}%`
                                """
                            elif message['type'] == "active":
                                msg = f"*{message['args']['moniker']} is active again!*"
                            elif message['type'] == "inactive":
                                msg = f"*{message['args']['moniker']} is inactive!**"
                            elif message['type'] == "jailed":
                                msg = f"""
*{message['args']['moniker']} is JAILED!*
Last Signed Block: `{message['args']['last_height']}`
Jailed Until: `{message['args']['jailed_until']}`
Jailed Duration: `{message['args']['jailed_duration']}`
                                """
                                
                            future = asyncio.run_coroutine_threadsafe(
                                telegram_client.reply(
                                    msg,
                                    sub["user"]
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

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.start_block_polling())