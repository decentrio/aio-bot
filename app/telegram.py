import logging
import json
import asyncio
import telebot
import telebot.async_telebot

class TelegramClient(telebot.async_telebot.AsyncTeleBot):
    def __init__(self, config):
        self.token: str = config["app"]["telegram"]["token"]
        self.subscriptions: list = config["app"]["telegram"]["subscriptions"]
        self.channels: list = config["app"]["telegram"]["channels"]
        self.mode: str = config["app"]["telegram"]["mode"]
        
        self.logger = logging.getLogger("TelegramClient")
        self.logger.setLevel(logging.INFO)
        self.loop = None

        super().__init__(token=self.token, parse_mode="Markdown")
        self.register_commands()

    def register_commands(self):
        self.register_message_handler(
            callback=self.handle_command,
            commands=["help", "sub", "unsub", "start"]
        )
    
    async def handle_command(self, message: telebot.types.Message):
        self.logger.info(f"Received command: {message.text}")

        command_name = message.text.split(" ")[0]
        commands = message.text.split(" ")[1:]

        if command_name == "/help" or command_name == "/start":
            await self.send_message(
                message.chat.id,
                """
                **AIO Bot for Injective!**\n
- `/sub val <valoper-address>`: Valoper address subscription will notify you of validator uptime, peggo performance and low balance on your validator operator and peggo orchestrator addresses
- `/sub ibc`: Subscribe to IBC monitoring notifications
- `/sub gov`: Subscribe to governance notifications
- `/sub list`: List all your subscriptions
- `/unsub <valoper-address>`: Unsubscribe from a subscription
- `/help`: Show this help menu
                """
            )
        elif command_name == "/sub":
            if (len(commands) == 2):
                sub_type = commands[0]
                value = commands[1]
                if sub_type == "val":
                    self.subscriptions.append({
                        "user": message.chat.id,
                        "validator": value
                    })
                elif sub_type == "balance":
                    self.subscriptions.append({
                        "user": message.chat.id,
                        "address": value
                    })
                else:
                    await self.send_message(
                        message.chat.id,
                        f"Invalid subscription type: {sub_type}"
                    )
                    return
                await self.send_message(
                    message.chat.id,
                    f"Subscribed `{value}`"
                )
                with open("config.json", "r") as f:
                    config = json.load(f)
                config["app"]["telegram"]["subscriptions"] = self.subscriptions
                with open("config.json", "w") as f:
                    json.dump(config, f, indent=4)
            elif (len(commands) == 1):
                if commands[0] == "list":
                    user_subs = [sub["validator"] if "validator" in sub else sub["address"] if "address" in sub else sub["sub"] for sub in self.subscriptions if sub["user"] == message.chat.id]
                    sub_list = "\n".join(f"- {sub}" for sub in user_subs) if user_subs else "No subscriptions found."
                    await self.send_message(
                        message.chat.id,
                        "Your subscriptions:\n" + sub_list
                    )
                elif commands[0] == "ibc":
                    self.subscriptions.append({
                        "user": message.chat.id,
                        "sub": "ibc"
                    })
                    with open("config.json", "r") as f:
                        config = json.load(f)
                    config["app"]["telegram"]["subscriptions"] = self.subscriptions
                    with open("config.json", "w") as f:
                        json.dump(config, f, indent=4)
                    await self.send_message(
                        message.chat.id,
                        "Subscribed to receive IBC monitoring notifications."
                    )
                elif commands[0] == "gov":
                    self.subscriptions.append({
                        "user": message.chat.id,
                        "sub": "gov"
                    })
                    with open("config.json", "r") as f:
                        config = json.load(f)
                    config["app"]["telegram"]["subscriptions"] = self.subscriptions
                    with open("config.json", "w") as f:
                        json.dump(config, f, indent=4)
                    await self.send_message(
                        message.chat.id,
                        "Subscribed to receive governance notifications."
                    )
                else:
                    await self.send_message(
                        message.chat.id,
                        "Invalid number of arguments for command `/sub`"
                    )
        elif command_name == "/unsub":
            value_to_remove = commands[0]
            self.subscriptions = [
                sub for sub in self.subscriptions
                if not (
                    sub.get("user") == message.chat.id and (
                        sub.get("validator") == value_to_remove or
                        sub.get("address") == value_to_remove or
                        sub.get("sub") == value_to_remove
                    )
                )
            ]
            await self.send_message(
                message.chat.id,
                f"Unsubscribed: `{value_to_remove}`"
            )
            with open("config.json", "r") as config_file:
                config = json.load(config_file)
            config["app"]["telegram"]["subscriptions"] = self.subscriptions
            with open("config.json", "w") as config_file:
                json.dump(config, config_file, indent=4)
    
    async def reply(self, message, channel):
        try:
            asyncio.create_task(
                self.send_message(
                    channel,
                    message
            ))
            self.logger.info(f"Message sent to channel: {channel}")
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")

    def start(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.create_task(super().infinity_polling())
            self.loop.run_forever()
        except Exception as e:
            self.logger.error(f"Error starting Telegram client: {e}")