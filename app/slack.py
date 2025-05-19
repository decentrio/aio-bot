from flask import Flask, request, jsonify
import logging
import json 
import requests

class SlackServer(Flask):
    def __init__(self, config):
        super().__init__(__name__)
        self.port: int = config["app"]["slack"]["port"]
        self.channels: list = config["app"]["slack"]["channels"]
        self.subscriptions: list = config["app"]["slack"]["subscriptions"]
        self.mode: str = config["app"]["slack"]["mode"]
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

    def handle_sub(self, args, user_id):
        if (len(args) == 2):
            sub_type = args[0]
            value = args[1]
            if sub_type == "val":
                self.subscriptions.append({
                    "user": user_id,
                    "validator": value
                })
                with open("config.json", "r") as config_file:
                    config = json.load(config_file)
                config["app"]["slack"]["subscriptions"] = self.subscriptions
                with open("config.json", "w") as config_file:
                    json.dump(config, config_file, indent=4)
                return f"Subscribed `{value}` for <@{user_id}>"
            else:
                return f"Invalid subscription type: {sub_type}"
        elif (len(args) == 1):
            if args[0] == "list":
                user_subs = [sub["validator"] if "validator" in sub else sub["address"] for sub in self.subscriptions if sub["user"] == user_id]
                sub_list = "\n".join(f"- {sub}" for sub in user_subs) if user_subs else "No subscriptions found."
                return f"Your subscriptions:\n{sub_list}"
            else:
                return f"Invalid command: {args[0]}"
        return "You have successfully subscribed!"

    def handle_unsub(self, args, user_id):
        value_to_remove = args
        self.subscriptions = [
            sub for sub in self.subscriptions
            if not (
                sub.get("user") == user_id and (
                    sub.get("validator") == value_to_remove or
                    sub.get("address") == value_to_remove
                )
            )
        ]

        with open("config.json", "r") as config_file:
            config = json.load(config_file)
        config["app"]["slack"]["subscriptions"] = self.subscriptions
        with open("config.json", "w") as config_file:
            json.dump(config, config_file, indent=4)

        return f"Unsubscribed: `{value_to_remove}` for <@{user_id}>"

    def handle_help(self):
        help_message = """
        *AIO Bot for Injective!*\n
        - `/sub val <valoper-address>`: Valoper address subscription will notify you of validator uptime, peggo performance and low balance on your validator operator and peggo orchestrator addresses\n
        - `/sub list`: List all your subscriptions\n
        - `/unsub <valoper-address>`: Unsubscribe from a subscription\n
        - `/help`: Show this help menu
        """
        return help_message

    def register_routes(self):
        @self.route('/api/slash_command', methods=['POST'])
        def slash_command():
            token = request.form.get('token')
            team_id = request.form.get('team_id')
            team_domain = request.form.get('team_domain')
            enterprise_id = request.form.get('enterprise_id')
            enterprise_name = request.form.get('enterprise_name')
            channel_id = request.form.get('channel_id')
            channel_name = request.form.get('channel_name')
            user_id = request.form.get('user_id')
            user_name = request.form.get('user_name')
            command = request.form.get('command')
            text = request.form.get('text')
            response_url = request.form.get('response_url')
            trigger_id = request.form.get('trigger_id')
            api_app_id = request.form.get('api_app_id')
            args = text.split(" ")

            self.logger.info(f"Received command: {command} with text: {args}")

            if command == "/sub":
                response = self.handle_sub(args, user_id)
            elif command == "/unsub":
                response = self.handle_unsub(args, user_id)
            elif command == "/help":
                response = self.handle_help()
            else:
                response = "Invalid command. Type `/help` for available commands."

            return jsonify({
                "response_type": "ephemeral",
                "text": response
            })

    def reply(self, message, channel):
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
        try:
            self.register_routes()
            self.logger.info("Starting Slack server...")
            from waitress import serve
            serve(self, host='0.0.0.0', port=self.port)
        except Exception as e:
            self.logger.error(f"Error starting Slack server: {e}")
            raise