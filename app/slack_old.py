from slack_bolt import App, Ack, Say, Respond
import asyncio
import json
import re
import requests 

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
                "text": "*AIO Bot for Injective!*\n\n"
                        "- `/sub val <valoper-address>`: Valoper address subscription will notify you of validator uptime, peggo performance and low balance on your validator operator and peggo orchestrator addresses\n"
                        "- `/sub list`: List all your subscriptions\n"
                        "- `/unsub <valoper-address>`: Unsubscribe from a subscription\n"
                        "- `/help`: Show this help menu"
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
                if commands[0] == "list":
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
            
    def reply(self, message, channel, thread_ts=None):
        try:
            if isinstance(message, str):
                payload = {
                    "text": message
                }
            elif isinstance(message, list):
                payload = {
                    "attachments": message
                }

            # Send the POST request to the webhook URL (which is 'channel' here)
            response = requests.post(
                channel,  # Using 'channel' as the webhook URL
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload)
            )

            # Check if the response from the webhook is successful
            if response.status_code == 200:
                self.logger.info("Message sent successfully")
            else:
                self.logger.error(f"Failed to send message. Status code: {response.status_code}")
                self.logger.error(f"Response: {response.text}")

        except Exception as e:
            self.logger.error(f"Error sending message to webhook: {e}")

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