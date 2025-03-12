from slack_bolt import App, Ack, Say, Respond
import asyncio
import json
import re

class SlackClient(App):
    def __init__(self, config):
        self.token: str = config["app"]["slack"]["oAuth-token"]
        self.port: str = config["app"]["slack"]["port"]
        self.channels: list = config["app"]["slack"]["channels"]
        self.signing_secret: str = config["app"]["slack"]["signing-secret"]
        self.subscriptions: list = config["app"]["slack"]["subscriptions"]
        self.mode: str = config["app"]["slack"]["mode"]

        super().__init__(
            token=config["app"]["slack"]["oAuth-token"],
            signing_secret=config["app"]["slack"]["signing-secret"]
        )
        self.register_commands()

    def register_commands(self):
        self.command("/help")(self.handle_command)
        self.command("/sub")(self.handle_command)
        self.command("/unsub")(self.handle_command)
    
    def handle_command(self, ack, respond, command):
        ack()
        command_name = command["command"]
        commands = command.get("text", "").split(" ")
        self.logger.info(f" {commands}")
        if command_name == "/help":
            respond({
                "response_type": "in_channel",
                "text": "This is a simple Slack bot that listens for Bitcoin transactions and new blocks on the blockchain. You can subscribe to receive notifications for new blocks and transactions. Use the following commands to interact with the bot:\n\n"
                        "* /subscribe block - Subscribe to receive notifications for new blocks\n"
                        "* /subscribe tx - Subscribe to receive notifications for new transactions\n"
                        "* /unsubscribe block - Unsubscribe from block notifications\n"
                        "* /unsubscribe tx - Unsubscribe from transaction notifications\n"
                        f"* /help - Display this help message"
            })
        elif command_name == "/sub":
            if (len(commands) == 2):
                sub_type = commands[0]
                value = commands[1]
                if sub_type == "val":
                    self.subscriptions.append({
                            "user": command["user_id"],
                            "validator": value
                    })
                elif sub_type == "balance":
                    self.subscriptions.append({
                        "user": command["user_id"],
                        "address": value
                    })
                else:
                    respond({
                        "response_type": "in_channel",
                        "text": f"Invalid subscription type: {sub_type}"
                    })
                    return
                respond({
                    "response_type": "in_channel",
                    "text": f"Subscribed `{value}` for <@{command['user_id']}>"
                })
                with open("config.json", "r") as config_file:
                    config = json.load(config_file)
                config["app"]["slack"]["subscriptions"] = self.subscriptions
                with open("config.json", "w") as config_file:
                    json.dump(config, config_file, indent=4)
            elif (len(commands) == 1):
                if commands[0] == "help":
                    respond({
                        "response_type": "in_channel",
                        "text": "Available commands:\n \
                                `/sub val <val-address>`: Get notification about validator/peggo operator\n \
                                `/sub balance <eth/inj-address>`: Get notification about low balance\n \
                                `/sub list`: List all your subscriptions",
                    })
                elif commands[0] == "list":
                    user_subs = [sub["validator"] if "validator" in sub else sub["address"] for sub in self.subscriptions if sub["user"] == command["user_id"]]
                    sub_list = "\n".join(f"- {sub}" for sub in user_subs) if user_subs else "No subscriptions found."
                    respond({
                        "response_type": "in_channel",
                        "text": "Your subscriptions:\n" + sub_list
                    })
                else:
                    respond({
                        "response_type": "in_channel",
                        "text": f"Invalid command: {commands}"
                    })
        elif command_name == "/unsub":
            value_to_remove = commands[0]
            self.subscriptions = [sub for sub in self.subscriptions if sub.get("validator") != value_to_remove and sub.get("address") != value_to_remove]
            respond({
                "response_type": "in_channel",
                "text": f"Unsubscribed: `{value_to_remove}` for <@{command['user_id']}>"
            })
            with open("config.json", "r") as config_file:
                config = json.load(config_file)
            config["app"]["slack"]["subscriptions"] = self.subscriptions
            with open("config.json", "w") as config_file:
                json.dump(config, config_file, indent=4)
            
    def reply(self, message, channel, thread_ts = None):
        try:
            if type(message) is str:
                self.client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=message
                )
            elif type(message) is list:
                self.client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    attachments=message
                )
            self.logger.info(f"Message sent")
        except Exception as e:
            self.logger.error(f"Error replying to Slack message: {e}")

    def start(self):
        """
        Start Slack bot
        """
        try:
            super().start(
                port=int(self.port),
                path="/slack/events"
            )

        except Exception as e:
            self.logger.error(f"Error starting Slack bot: {e}")
