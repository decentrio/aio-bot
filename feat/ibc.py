import logging
import json
import utils.query as query
import asyncio
from datetime import datetime
import time

def getIBCList(apis):
    with open("ibc.json", "r") as ibc_file:
        ibc_list = json.load(ibc_file)
    try:
        injective_detail = query.query(apis, path=f"/injective/chain.json")
        injective_apis = injective_detail["apis"]["rest"]
        for ibc in ibc_list:
            if "api-1" not in ibc.keys() or ibc["api-1"] is None:
                chain_detail = query.query(apis, path=f"/{ibc['chain-1']}/chain.json")
                chain1_apis = chain_detail["apis"]["rest"]
                ibc["api-1"] = [
                    api["address"]
                    if api["address"].startswith("https://") or api["address"].startswith("http://")
                    else "https://" + api["address"]
                    for api in chain1_apis]
            if "api-2" not in ibc.keys() or ibc["api-2"] is None:
                ibc["api-2"] = [
                    api["address"]
                    if api["address"].startswith("https://") or api["address"].startswith("http://")
                    else "https://" + api["address"]
                    for api in injective_apis]
        with open("ibc.json", "w") as ibc_file:
            json.dump(ibc_list, ibc_file, indent=4)
        return ibc_list
    except Exception as e:
        logging.error(f"Error getting IBC list: {e}")
        return []

class IBC:
    def __init__(self, app, params):
        self.app = app
        self.params = params
        self.api = params["registry_api"]
        self.client_update_threshold = params["client_update_threshold"]
        self.stuck_packets_threshold = params["stuck_packets_threshold"]
        self.ibcs = getIBCList(self.api)

        self.logger = logging.getLogger("IBC")
        self.logger.setLevel(logging.INFO)

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
            for ibc in self.ibcs:
                try:
                    if ibc["client-1"] != "":
                        self.checkClient(ibc["client-1"], ibc["api-1"], ibc["api-2"], ibc["chain-1"], ibc["chain-2"])
                    data = query.query(ibc["api-1"], path=f"/ibc/core/channel/v1/channels/{ibc['channel-1']}/ports/{ibc['port-1']}/packet_commitments")
                    packet_1 = data["commitments"]
                    ibc["packet-1"] = len(packet_1)
                    if len(packet_1):
                        self.notify({
                            "type": "packets",
                            "args": {
                                "quantity": len(packet_1),
                                "chain-1": ibc["chain-1"],
                                "chain-2": ibc["chain-2"],
                                "port": ibc["port-1"],
                                "channel": ibc["channel-1"]
                            },
                            "auto_delete": None
                        })

                    self.logger.debug(f"{ibc['chain-1']}-{ibc['chain-2']} queried.")
                except Exception as e:
                    self.logger.error(f"Error querying {ibc['chain-1']}-{ibc['chain-2']}: {e}")

                try:
                    if ibc["client-2"] != "":
                        self.checkClient(ibc["client-2"], ibc["api-2"], ibc["api-1"], ibc["chain-2"], ibc["chain-1"])
                    data = query.query(ibc["api-2"], path=f"/ibc/core/channel/v1/channels/{ibc['channel-2']}/ports/{ibc['port-2']}/packet_commitments")
                    packet_2 = data["commitments"]
                    ibc["packet-2"] = len(packet_2)
                    if len(packet_2) >= self.stuck_packets_threshold:
                        self.notify({
                            "type": "packets",
                            "args": {
                                "quantity": len(packet_2),
                                "chain-1": ibc["chain-2"],
                                "chain-2": ibc["chain-1"],
                                "port": ibc["port-2"],
                                "channel": ibc["channel-2"]
                            },
                            "auto_delete": None
                        })

                    self.logger.debug(f"{ibc['chain-2']}-{ibc['chain-1']} queried.")
                except Exception as e:
                    self.logger.error(f"Error querying {ibc['chain-2']}-{ibc['chain-1']}: {e}")

            with open("ibc.json", "w") as ibc_file:
                json.dump(self.ibcs, ibc_file, indent=4)
            self.logger.info("All IBC queried.")
            time.sleep(1200)

    def notify(self, message):
        try:
            # Discord client
            if self.app["discord"] is not None:
                discord_client = self.app["discord"]
                if discord_client.loop:
                    if message["type"] == "client":
                        msg = discord_client.compose_embed(
                            title=f"**Client {message['args']['client']} is about to expire!**",
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
                            color=0x75ffd1
                        )
                    elif message["type"] == "packets":
                        msg = discord_client.compose_embed(
                            title=f"**Uncommitted packets from {message['args']['chain-1']} to {message['args']['chain-2']}**",
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
                            color=0x75ffd1
                        )
                    future = asyncio.run_coroutine_threadsafe(
                        discord_client.reply(
                            discord_client.channels["ibc"]["id"],
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

            # Slack client
            if self.app["slack"] is not None:
                slack_client = self.app["slack"]
                if message["type"] == "client":
                    msg = f"*Client {message['args']['client']} is about to expired!*\n" \
                        f"From: {message['args']['chain-1']}\n" \
                        f"To: {message['args']['chain-2']}\n" \
                        f"Last Updated: {message['args']['last_updated']}\n" \
                        f"Time Left: {message['args']['time_left']}\n"
                elif message["type"] == "packets":
                    msg = f"*Uncommitted packets from {message['args']['chain-1']} to {message['args']['chain-2']}*\n" \
                        f"From: {message['args']['chain-1']}\n" \
                        f"To: {message['args']['chain-2']}\n" \
                        f"Port: {message['args']['port']}\n" \
                        f"Channel: {message['args']['channel']}\n" \
                        f"Missed: {message['args']['quantity']}\n"
                slack_client.reply(
                    msg,
                    slack_client.channels[0]["id"],
                )
            else:
                self.logger.error("Slack client is not initialized.")

            # Telegram client
            if self.app["telegram"] is not None:
                telegram_client = self.app["telegram"]
                if telegram_client.loop:
                    if message["type"] == "client":
                        msg = f"*Client {message['args']['client']} is about to expired!*\n" \
                        f"From: {message['args']['chain-1']}\n" \
                        f"To: {message['args']['chain-2']}\n" \
                        f"Last Updated: {message['args']['last_updated']}\n" \
                        f"Time Left: {message['args']['time_left']} \n"
                    elif message["type"] == "packets":
                        msg = f"*Uncommitted packets from {message['args']['chain-1']} to {message['args']['chain-2']}*\n" \
                            f"From: {message['args']['chain-1']}\n" \
                            f"To: {message['args']['chain-2']}\n" \
                            f"Port: {message['args']['port']}\n" \
                            f"Channel: {message['args']['channel']}\n" \
                            f"Missed: {message['args']['quantity']}\n"
                    future = asyncio.run_coroutine_threadsafe(
                        telegram_client.reply(
                            msg,
                            telegram_client.channels[0]["id"]
                        ),
                        telegram_client.loop
                    )

                    # Optionally, wait for the coroutine to finish and handle exceptions
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
