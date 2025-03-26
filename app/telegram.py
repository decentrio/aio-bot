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
            commands=["help", "sub", "unsub"]
        )
    
    async def handle_command(self, message: telebot.types.Message):
        self.logger.info(f"Received command: {message.text}")

        command_name = message.text.split(" ")[0]
        commands = message.text.split(" ")[1:]

        if command_name == "/help":
            await self.send_message(
                message.chat.id,
                "This is a simple Telegram bot that listens for Bitcoin transactions and new blocks on the blockchain. You can subscribe to receive notifications for new blocks and transactions. Use the following commands to interact with the bot:\n\n"
                "* /subscribe block - Subscribe to receive notifications for new blocks\n"
                "* /subscribe tx - Subscribe to receive notifications for new transactions\n"
                "* /unsubscribe block - Unsubscribe from block notifications\n"
                "* /unsubscribe tx - Unsubscribe from transaction notifications\n"
                f"* /help - Display this help message"
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
                    f"Subscribed `{value}` for <@{message.from_user.id}>"
                )
                with open("config.json", "r") as f:
                    config = json.load(f)
                config["app"]["telegram"]["subscriptions"] = self.subscriptions
                with open("config.json", "w") as f:
                    json.dump(config, f, indent=4)
            elif (len(commands) == 1):
                if commands[0] == "help":
                    await self.send_message(
                        message.chat.id,
                        "Available commands:\n \
                                `/sub val <val-address>`: Get notification about validator/peggo operator\n \
                                `/sub balance <eth/inj-address>`: Get notification about low balance\n \
                                `/sub list`: List all your subscriptions"
                    )
                elif commands[0] == "list":
                    user_subs = [sub["validator"] if "validator" in sub else sub["address"] for sub in self.subscriptions if sub["user"] == message.chat.id]
                    sub_list = "\n".join(f"- {sub}" for sub in user_subs) if user_subs else "No subscriptions found."
                    await self.send_message(
                        message.chat.id,
                        "Your subscriptions:\n" + sub_list
                    )
                else:
                    await self.send_message(
                        message.chat.id,
                        "Invalid number of arguments for command `/sub`"
                    )
        elif command_name == "/unsub":
            value_to_remove = commands[0]
            self.subscriptions = [sub for sub in self.subscriptions if sub.get("validator") != value_to_remove and sub.get("address") != value_to_remove]
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