import logging
import asyncio
import json
import time
from datetime import datetime

import requests
from requests.exceptions import RequestException

import utils.query as query

class IBC:
    def __init__(self, app, params):
        self.logger = logging.getLogger("IBC")
        self.logger.setLevel(logging.DEBUG)
        self.app = app
        self.params = params
        self.client_update_threshold = params["client_update_threshold"]
        self.stuck_packets_threshold = params["stuck_packets_threshold"]
        self.alert_confirmation_seconds = params.get("alert_confirmation_seconds", 180)
        self.ibcs = []
        self.alert_candidates = {}

    def getIgnorePackets(self) -> list:
        try:
            with open("ibc_ignore.json", "r") as ignore_file:
                ignore_packets = json.load(ignore_file)
                self.logger.info("Loaded ignore packets list.")
                return ignore_packets
        except FileNotFoundError:
            self.logger.warning("ibc_ignore.json not found, returning empty list.")
            return []
        except json.JSONDecodeError as e:
            self.logger.error(f"Error decoding JSON from ibc_ignore.json: {e}")
            return []

    def _make_alert_key(self, alert_type, source_id, dest_id, channel, port, sequence=None):
        key = (
            alert_type,
            str(source_id),
            str(dest_id),
            str(channel),
            str(port),
        )
        if sequence is not None:
            return key + (str(sequence),)
        return key

    def _track_alert_candidate(self, key, payload):
        if self.alert_confirmation_seconds <= 0:
            return payload

        now = time.time()
        candidate = self.alert_candidates.get(key)
        if candidate:
            candidate["last_seen"] = now
            candidate["payload"] = payload
            if now - candidate["first_seen"] >= self.alert_confirmation_seconds:
                self.alert_candidates.pop(key, None)
                return payload
        else:
            self.alert_candidates[key] = {
                "first_seen": now,
                "last_seen": now,
                "payload": payload
            }
        return None

    def _clear_inactive_alerts(self, source_id, dest_id, channel, port, active_keys):
        for key in list(self.alert_candidates.keys()):
            if (
                len(key) >= 5
                and key[1] == str(source_id)
                and key[2] == str(dest_id)
                and key[3] == str(channel)
                and key[4] == str(port)
                and key not in active_keys
            ):
                self.alert_candidates.pop(key, None)

    def _is_api_active(self, api, chain_name):
        health_url = f"{api.rstrip('/')}/cosmos/base/tendermint/v1beta1/blocks/latest"
        try:
            response = requests.get(health_url, timeout=5)
            if response.status_code == 200:
                return True
            self.logger.warning(f"Health-check for {api} on {chain_name} returned {response.status_code}.")
        except RequestException as exc:
            self.logger.warning(f"Skipping inactive API {api} for {chain_name}: {exc}")
        except Exception as exc:
            self.logger.warning(f"Unexpected error probing {api} for {chain_name}: {exc}")
        return False

    def _filter_active_apis(self, apis, chain_name):
        active = []
        for api in apis:
            if self._is_api_active(api, chain_name):
                active.append(api)
        if not active:
            self.logger.error(f"No responsive REST endpoints found for {chain_name}.")
        return active

    def getIBCList(self) -> list:
        ibcs = []

        injective_detail = query.query(self.params["registry_api"], path="/injective/chain.json")
        apis = injective_detail["apis"]["rest"]
        chain_1_apis = [
            api["address"]
            if api["address"].startswith("https://") or api["address"].startswith("http://")
            else "https://" + api["address"]
            for api in apis
        ]

        chain_1_apis = self._filter_active_apis(chain_1_apis, "injective")
        if not chain_1_apis:
            return []

        # chain_1_apis = ["https://rest.cosmos.directory/injective"]

        try:
            notion_data = query.query(
                self.params["notion_api"], 
                method="POST",
                header= {
                    "Authorization": f"Bearer {self.params['notion_api_key']}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json"
                }
            )["results"]
        except Exception as e:
            self.logger.error(f"Error fetching data from Notion API: {e}")
            return []

        for property in notion_data:
            chain_2_name = property["properties"]["Chain"]["title"][0]["plain_text"]
            chain_2_id = property["properties"]["Chain-ID"]["rich_text"][0]["plain_text"]
            chain_2_channel = property["properties"]["Foreign\nChannel"]["rich_text"][0]["plain_text"]
            chain_2_port = property["properties"]["Foreign \nPort"]["rich_text"][0]["plain_text"]
            chain_1_channel = property["properties"]["Injective\nChannel"]["rich_text"][0]["plain_text"]
            chain_1_port = property["properties"]["Injective\nPort"]["rich_text"][0]["plain_text"]

            try:
                chain_2_detail = query.query(self.params["registry_api"], path=f"/{chain_2_name}/chain.json")
                apis = chain_2_detail["apis"]["rest"]
                chain_2_apis = [
                    api["address"]
                    if api["address"].startswith("https://") or api["address"].startswith("http://")
                    else "https://" + api["address"]
                    for api in apis
                ]

                chain_2_apis = self._filter_active_apis(chain_2_apis, chain_2_name)
                if not chain_2_apis:
                    continue
                # chain_2_apis = ["https://rest.cosmos.directory/" + chain_2_name]

                chain_1_client = query.query(chain_1_apis, path=f"/ibc/core/channel/v1/channels/{chain_1_channel}/ports/{chain_1_port}/client_state")
                chain_2_client = query.query(chain_2_apis, path=f"/ibc/core/channel/v1/channels/{chain_2_channel}/ports/{chain_2_port}/client_state")
                self.logger.debug(f"Fetched injective-{chain_2_name} IBC detail.")

                ibcs.append({
                    "chain-1": "injective",
                    "id-1": "injective-1",
                    "client-1": chain_1_client["identified_client_state"]["client_id"],
                    "channel-1": chain_1_channel,
                    "port-1": chain_1_port,
                    "api-1": chain_1_apis,
                    "chain-2": chain_2_name,
                    "id-2": chain_2_id,
                    "client-2": chain_2_client["identified_client_state"]["client_id"],
                    "channel-2": chain_2_channel,
                    "port-2": chain_2_port,
                    "api-2": chain_2_apis
                })
            except Exception as e:
                self.logger.error(f"Error fetching {chain_2_name} detail: {e}")
                continue

        self.logger.info("Fetched IBC list")
        with open("ibc.json", "w") as ibc_file:
            json.dump(ibcs, ibc_file, indent=4)
        return ibcs

    def checkClient(self, client, source_apis, dest_apis, chain_1, chain_2):
        try:
            client_state = query.query(source_apis, path=f"/ibc/core/client/v1/client_states/{client}")
        except Exception as e:
            self.logger.error(f"Error fetching client state for {client} on {source_apis}: {e}")
            return
        last_updated_height = client_state["client_state"]["latest_height"]["revision_height"]
        trusting_period = int(client_state["client_state"]["trusting_period"][:-1])
        try:
            block_detail = query.query(dest_apis, path=f"/cosmos/base/tendermint/v1beta1/blocks/{last_updated_height}")
            block_time = block_detail["block"]["header"]["time"]
            block_time = block_time.split(".")[0] + "Z"
            time_since_last_updated = (datetime.now() - datetime.strptime(block_time, "%Y-%m-%dT%H:%M:%SZ")).total_seconds()
            if trusting_period - time_since_last_updated <= self.client_update_threshold:
                self.notify({
                    "type": "client",
                    "args": {
                        "client": client,
                        "last_updated": block_time,
                        "chain-1": chain_1,
                        "chain-2": chain_2,
                        "time_left": trusting_period - time_since_last_updated if trusting_period >= time_since_last_updated else 0
                    },
                    "auto_delete": None
                })
        except Exception as e:
            self.logger.error(f"Error checking client {client} on {dest_apis}: {e}")


    async def queryIBCPackets(self):
        while True:
            self.ibcs = self.getIBCList()
            self.ibc_ignores = self.getIgnorePackets()
            for ibc in self.ibcs:
                try:
                    if ibc["client-1"] != "":
                        self.checkClient(ibc["client-1"], ibc["api-1"], ibc["api-2"], ibc["chain-1"], ibc["chain-2"])
                    data = query.query(ibc["api-1"], path=f"/ibc/core/channel/v1/channels/{ibc['channel-1']}/ports/{ibc['port-1']}/packet_commitments")
                    commitments_1 = data["commitments"]
                    ibc["packet-1"] = len(commitments_1)
                    ignore_packets = self.ibc_ignores[ibc["id-1"]][ibc["channel-1"]] if ibc["id-1"] in self.ibc_ignores and ibc["channel-1"] in self.ibc_ignores[ibc["id-1"]] else []
                    active_keys = set()

                    if len(commitments_1) >= self.stuck_packets_threshold:
                        if len(commitments_1) == 1:
                            sequence = commitments_1[0]["sequence"]
                            if sequence not in ignore_packets:
                                tx_detail = query.query([f"https://rpc.cosmos.directory/{ibc['chain-1']}"], path=f"/tx_search?query=%22send_packet.packet_sequence%3D{sequence}%22")
                                tx_block = int(tx_detail["result"]["txs"][0]["height"]) if tx_detail["result"] else None
                                current_block = int(query.query(ibc["api-1"], path="/cosmos/base/tendermint/v1beta1/blocks/latest")["block"]["header"]["height"])
                                pending_blocks = current_block - tx_block if tx_block else None
                                if pending_blocks is None or (pending_blocks is not None and pending_blocks <= 50000):
                                    payload = {
                                        "type": "packet",
                                        "args": {
                                            "chain-1": ibc["chain-1"],
                                            "chain-2": ibc["chain-2"],
                                            "port": ibc["port-1"],
                                            "channel": ibc["channel-1"],
                                            "sequence": sequence,
                                            "pending_blocks": pending_blocks,
                                            "url": f"https://rest.cosmos.directory/{ibc['chain-1']}/ibc/core/channel/v1/channels/{ibc['channel-1']}/ports/{ibc['port-1']}/packet_commitments/{sequence}"
                                        },
                                        "auto_delete": None
                                    }
                                    key = self._make_alert_key("packet", ibc["id-1"], ibc["id-2"], ibc["channel-1"], ibc["port-1"], sequence)
                                    active_keys.add(key)
                                    message = self._track_alert_candidate(key, payload)
                                    if message:
                                        self.notify(message)
                        else:
                            filtered_packets_1 = [p for p in commitments_1 if p["sequence"] not in ignore_packets]
                            if len(filtered_packets_1) > 0:
                                payload = {
                                    "type": "packets",
                                    "args": {
                                        "quantity": len(filtered_packets_1),
                                        "chain-1": ibc["chain-1"],
                                        "chain-2": ibc["chain-2"],
                                        "port": ibc["port-1"],
                                        "channel": ibc["channel-1"],
                                        "url": f"https://rest.cosmos.directory/{ibc['chain-1']}/ibc/core/channel/v1/channels/{ibc['channel-1']}/ports/{ibc['port-1']}/packet_commitments"
                                    },
                                    "auto_delete": None
                                }
                                key = self._make_alert_key("packets", ibc["id-1"], ibc["id-2"], ibc["channel-1"], ibc["port-1"])
                                active_keys.add(key)
                                message = self._track_alert_candidate(key, payload)
                                if message:
                                    self.notify(message)

                    self._clear_inactive_alerts(ibc["id-1"], ibc["id-2"], ibc["channel-1"], ibc["port-1"], active_keys)

                    self.logger.debug(f"{ibc['chain-1']}-{ibc['chain-2']} queried.")
                except Exception as e:
                    self.logger.error(f"Error querying {ibc['chain-1']}-{ibc['chain-2']}: {e}")

                try:
                    if ibc["client-2"] != "":
                        self.checkClient(ibc["client-2"], ibc["api-2"], ibc["api-1"], ibc["chain-2"], ibc["chain-1"])
                    data = query.query(ibc["api-2"], path=f"/ibc/core/channel/v1/channels/{ibc['channel-2']}/ports/{ibc['port-2']}/packet_commitments")
                    commitments_2 = data["commitments"]
                    ibc["packet-2"] = len(commitments_2)
                    ignore_packets = self.ibc_ignores[ibc["id-2"]][ibc["channel-2"]] if ibc["id-2"] in self.ibc_ignores and ibc["channel-2"] in self.ibc_ignores[ibc["id-2"]] else []
                    active_keys = set()

                    if len(commitments_2) >= self.stuck_packets_threshold:
                        if len(commitments_2) == 1:
                            sequence = commitments_2[0]["sequence"]
                            if sequence not in ignore_packets:
                                tx_detail = query.query([f"https://rpc.cosmos.directory/{ibc['chain-2']}"], path=f"/tx_search?query=%22send_packet.packet_sequence%3D{sequence}%22")
                                tx_block = int(tx_detail["result"]["txs"][0]["height"]) if tx_detail["result"] else None
                                current_block = int(query.query(ibc["api-2"], path="/cosmos/base/tendermint/v1beta1/blocks/latest")["block"]["header"]["height"])
                                pending_blocks = current_block - tx_block if tx_block else None
                                if pending_blocks is None or (pending_blocks is not None and pending_blocks <= 50000):
                                    payload = {
                                        "type": "packet",
                                        "args": {
                                            "chain-1": ibc["chain-2"],
                                            "chain-2": ibc["chain-1"],
                                            "port": ibc["port-2"],
                                            "channel": ibc["channel-2"],
                                            "sequence": sequence,
                                            "pending_blocks": pending_blocks,
                                            "url": f"https://rest.cosmos.directory/{ibc['chain-2']}/ibc/core/channel/v1/channels/{ibc['channel-2']}/ports/{ibc['port-2']}/packet_commitments/{sequence}"
                                        },
                                        "auto_delete": None
                                    }
                                    key = self._make_alert_key("packet", ibc["id-2"], ibc["id-1"], ibc["channel-2"], ibc["port-2"], sequence)
                                    active_keys.add(key)
                                    message = self._track_alert_candidate(key, payload)
                                    if message:
                                        self.notify(message)
                        else:
                            filtered_packets_2 = [p for p in commitments_2 if p["sequence"] not in ignore_packets]
                            if len(filtered_packets_2) > 0:
                                payload = {
                                    "type": "packets",
                                    "args": {
                                        "quantity": len(filtered_packets_2),
                                        "chain-1": ibc["chain-2"],
                                        "chain-2": ibc["chain-1"],
                                        "port": ibc["port-2"],
                                        "channel": ibc["channel-2"],
                                        "url": f"https://rest.cosmos.directory/{ibc['chain-2']}/ibc/core/channel/v1/channels/{ibc['channel-2']}/ports/{ibc['port-2']}/packet_commitments"
                                    },
                                    "auto_delete": None
                                }
                                key = self._make_alert_key("packets", ibc["id-2"], ibc["id-1"], ibc["channel-2"], ibc["port-2"])
                                active_keys.add(key)
                                message = self._track_alert_candidate(key, payload)
                                if message:
                                    self.notify(message)

                    self._clear_inactive_alerts(ibc["id-2"], ibc["id-1"], ibc["channel-2"], ibc["port-2"], active_keys)

                    self.logger.debug(f"{ibc['chain-2']}-{ibc['chain-1']} queried.")
                except Exception as e:
                    self.logger.error(f"Error querying {ibc['chain-2']}-{ibc['chain-1']}: {e}")

            with open("ibc.json", "w") as ibc_file:
                json.dump(self.ibcs, ibc_file, indent=4)
            self.logger.info("All IBC queried.")
            time.sleep(self.params["interval"])

    def notify(self, message):
        try:
            # Discord client
            if self.app["discord"] is not None:
                discord_client = self.app["discord"]
                if discord_client.loop:
                    if message["type"] == "client":
                        msg = discord_client.compose_embed(
                            title=f"**Client {message['args']['client']} is about to expire!**" if message['args']['time_left'] > 0 else f"**Client {message['args']['client']} was expired!**",
                            description="",
                            fields=[
                                {
                                    "name": "From",
                                    "value": message['args']['chain-1'],
                                    "inline": True
                                },
                                {
                                    "name": "To",
                                    "value": message['args']['chain-2'],
                                    "inline": True
                                },
                                {
                                    "name": "Last Updated",
                                    "value": message['args']['last_updated'],
                                    "inline": True
                                },
                                {
                                    "name": "Time Left",
                                    "value": message['args']['time_left'],
                                    "inline": True
                                }
                            ],
                            footer=f"This message will be automatically deleted in {message['auto_delete']}s" if message['auto_delete'] != None else "",
                            color=0xff941a
                        )
                    elif message["type"] == "packets":
                        msg = discord_client.compose_embed(
                            title=f"**Uncommitted packets from {message['args']['chain-1']} to {message['args']['chain-2']}**",
                            description=message['args']['url'],
                            fields=[
                                {
                                    "name": "From",
                                    "value": message['args']['chain-1'],
                                    "inline": True
                                },
                                {
                                    "name": "To",
                                    "value": message['args']['chain-2'],
                                    "inline": True
                                },
                                {
                                    "name": "Port",
                                    "value": message['args']['port'],
                                    "inline": True
                                },
                                {
                                    "name": "Channel",
                                    "value": message['args']['channel'],
                                    "inline": True
                                },
                                {
                                    "name": "Missed",
                                    "value": message['args']['quantity'],
                                    "inline": True
                                }
                            ],
                            footer=f"This message will be automatically deleted in {message['auto_delete']}s" if message['auto_delete'] != None else "",
                            color=0xfff942
                        )
                    elif message["type"] == "packet":
                        msg = discord_client.compose_embed(
                            title=f"**Pending packet `{message['args']['sequence']}` from {message['args']['chain-1']} to {message['args']['chain-2']}**",
                            description=message['args']['url'],
                            fields=[
                                {
                                    "name": "Port",
                                    "value": message['args']['port'],
                                    "inline": True
                                },
                                {
                                    "name": "Channel",
                                    "value": message['args']['channel'],
                                    "inline": True
                                },
                                {
                                    "name": "Sequence",
                                    "value": message['args']['sequence'],
                                    "inline": True
                                },
                                {
                                    "name": "Pending Blocks",
                                    "value": message['args']['pending_blocks'],
                                    "inline": True
                                } if "pending_blocks" in message['args'] else {}
                            ],
                            footer=f"This message will be automatically deleted in {message['auto_delete']}s" if message['auto_delete'] != None else "",
                            color=0xfff942
                        )
                    future = asyncio.run_coroutine_threadsafe(
                        discord_client.reply(
                            discord_client.channels["ibc"]["id"],
                            msg,
                            auto_delete=message["auto_delete"]
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
                if message["type"] == "client":
                    msg = f"""
{f"**Client {message['args']['client']} is about to expire!**" if message['args']['time_left'] > 0 else f"**Client {message['args']['client']} was expired!**"}
From: `{message['args']['chain-1']}`
To: `{message['args']['chain-2']}`
Last Updated: `{message['args']['last_updated']}`
Time Left: `{message['args']['time_left']}`
                                """
                elif message["type"] == "packets":
                    msg = f"""
*Uncommitted packets from {message['args']['chain-1']} to {message['args']['chain-2']}*
{message['args']['url']}
From: `{message['args']['chain-1']}`
To: `{message['args']['chain-2']}`
Port: `{message['args']['port']}`
Channel: `{message['args']['channel']}`
Missed: `{message['args']['quantity']}`
                                """
                elif message["type"] == "packet":
                    msg = f"""
*Pending packet `{message['args']['sequence']}` from {message['args']['chain-1']} to {message['args']['chain-2']}*
{message['args']['url']}
From: `{message['args']['chain-1']}`
To: `{message['args']['chain-2']}`
Port: `{message['args']['port']}`
Channel: `{message['args']['channel']}`
Sequence: `{message['args']['sequence']}`
{f"Pending Blocks: `{message['args']['pending_blocks']}`" if "pending_blocks" in message['args'] else ""}
"""
                slack_client.reply(
                    msg,
                    slack_client.channels["ibc"]["webhook_url"],
                )
            else:
                self.logger.error("Slack client is not initialized.")

            # Telegram client
            if self.app["telegram"] is not None and len(self.app["telegram"].subscriptions):
                telegram_client = self.app["telegram"]
                if telegram_client.loop:
                    subscriptions = telegram_client.subscriptions
                    for sub in subscriptions:
                        if "sub" in sub and sub["sub"] == "ibc":
                            if message["type"] == "client":
                                msg = f"""
{f"Client {message['args']['client']} is about to expire!" if message['args']['time_left'] > 0 else f"Client {message['args']['client']} was expired!"}
From: `{message['args']['chain-1']}`
To: `{message['args']['chain-2']}`
Last Updated: `{message['args']['last_updated']}`
Time Left: `{message['args']['time_left']}`
                                """
                            elif message["type"] == "packets":
                                msg = f"Uncommitted packets from {message['args']['chain-1']} to {message['args']['chain-2']}\n" + \
                                      f"`{message['args']['url']}`\n" + \
                                      f"From: `{message['args']['chain-1']}`\n" + \
                                      f"To: `{message['args']['chain-2']}`\n" + \
                                      f"Port: `{message['args']['port']}`\n" + \
                                      f"Channel: `{message['args']['channel']}`\n" + \
                                      f"Missed: `{message['args']['quantity']}`\n"
                            elif message["type"] == "packet":
                                msg = f"Pending packet `{message['args']['sequence']}` from {message['args']['chain-1']} to {message['args']['chain-2']}\n" + \
                                f"`{message['args']['url']}`\n" + \
                                f"From: `{message['args']['chain-1']}`\n" + \
                                f"To: `{message['args']['chain-2']}`\n" + \
                                f"Port: `{message['args']['port']}`\n" + \
                                f"Channel: `{message['args']['channel']}`\n" + \
                                f"Sequence: `{message['args']['sequence']}`\n" + \
                                (f"Pending Blocks: `{message['args']['pending_blocks']}`" if "pending_blocks" in message['args'] else "")
                                
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
        loop.run_until_complete(self.queryIBCPackets())
