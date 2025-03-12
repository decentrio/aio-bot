import asyncio
import utils.query as query
import logging

class Proposal:
    def __init__(self, app, tx_queue, params, api, chain):
        self.app = app
        self.api = api
        self.params = params
        self.tx_queue = tx_queue    
        self.chain = chain

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def queryProposal(self, id):
        try:
            proposal = query.query(f"{self.api}/cosmos/gov/v1/proposals/{id}")
            return proposal
        except Exception as e:
            self.logger.error(f"Error querying proposal: {e}")
            return None
        
    def notify(self, message):
        try:
            # Discord client
            if self.app["discord"] is not None:
                discord_client = self.app["discord"]
                if discord_client.loop:
                    msg = discord_client.compose_embed(
                        title = f"**New Proposal {message['args']['proposal_id']}**",
                        description = message['args']['summary'],
                        fields = [
                            {
                                "name": "Type",
                                "value": message['args']['type'],
                            }
                        ],
                        footer = "This message will be automatically deleted in 60s",
                        color = 0x75ffd1
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

            # Slack client
            if self.app["slack"] is not None:
                slack_client = self.app["slack"]
                msg = f"New Proposal {message['args']['proposal_id']}\n" \
                    f"Description: `{message['args']['summary']}`"
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
                    msg = f"New Proposal {message['args']['proposal_id']}\n" \
                        f"Description: `{message['args']['summary']}`"
                    future = asyncio.run_coroutine_threadsafe(
                        telegram_client.reply(
                            msg,
                            discord_client.channels[0]["id"]
                        ),
                        discord_client.loop
                    )
                    # Optionally, wait for the coroutine to finish and handle exceptions
                    future.result()
                else:
                    self.logger.error("Telegram client loop not ready.")
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
    
    async def start_tx_polling(self):
        while True:
            if not self.tx_queue.empty():
                tx = self.tx_queue.get()
                if tx and "result" in tx:
                    msg_type = tx["result"]["query"]
                    if msg_type == "tm.event='Tx' AND message.action CONTAINS 'MsgSubmitProposal'":
                        events = tx["result"]["events"]
                        print(events)
                        proposal_id = events["submit_proposal.proposal_id"][0]
                        deposit = events["proposal_deposit.amount"][0][:-5]
                        if int(deposit) >= int(self.params["min_deposit"]):
                            proposal = self.queryProposal(proposal_id)
                            title = proposal["proposal"]["title"]
                            type = events["submit_proposal.proposal_messages"][0]
                            summary = proposal["proposal"]["summary"]
                            voting_end_time = proposal["proposal"]["voting_end_time"]
                            messages = proposal["proposal"]["messages"]
                            proposer = events["submit_proposal.proposal_proposer"][0]
                            self.notify({
                                "type": "new_proposal",
                                "args": {
                                    "proposal_id": proposal_id,
                                    "title": title,
                                    "proposer": proposer,
                                    "type": type,
                                    "status": "Voting Period",
                                    "summary": summary,
                                    "voting_end_time": voting_end_time,
                                }
                            })


    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.start_tx_polling())