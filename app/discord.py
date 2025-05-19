import logging
import discord
import asyncio
import json
from discord.ext import commands, tasks
from feat.consensus import get_consensus

class DiscordClient(commands.Bot):
    def __init__(self, config):
        self.token: int | str = config["app"]["discord"]["bot-token"]
        self.channels: dict = config["app"]["discord"]["channels"]
        self.subscriptions: list = config["app"]["discord"]["subscriptions"]
        self.mode: str = config["app"]["discord"]["mode"]
        self.rpcs: list = config["rpcs"] # for /consensus command only

        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True

        super().__init__(command_prefix='/', intents=intents)

        self.logger = logging.getLogger("DiscordClient")
        self.logger.setLevel(logging.DEBUG)

        self.loop = None

    def compose_embed(self, title="", description="", author="", fields=[], footer="", color=0x29fffb):
        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        embed.set_author(name=author)
        for field in fields:
            embed.add_field(
                name=field["name"],
                value=field["value"],
                inline=field["inline"]
            )
        embed.set_footer(text=footer)
        return embed

    async def on_ready(self):
        """
        Gets called when the Discord client logs in
        """
        self.logger.info(
            f'Logged into Discord as {self.user} (ID: {self.user.id})')
        for guild in self.guilds:
            print(f"Guild: {guild.name} (ID: {guild.id})")
            print("Channels:")
            for channel in guild.text_channels:
                self.logger.info(
                    f"  Text Channel: {channel.name} (ID: {channel.id})")
            for channel in guild.voice_channels:
                self.logger.info(
                    f"  Voice Channel: {channel.name} (ID: {channel.id})")
            for channel in guild.stage_channels:
                self.logger.info(
                    f"  Stage Channel: {channel.name} (ID: {channel.id})")
            self.logger.info("")

        self.loop = asyncio.get_running_loop()

    async def on_message(self, message):
        if message.author == self.user:
            return
        self.logger.info(
            f"{message.channel.name} | {message.author} | {message.content}")
        if message.content.startswith('/'):
            await self.handle_command(message)

    async def handle_command(self, message):
        command = message.content[1:].split(' ')[0]
        match command:
            case "help":
                msg = self.compose_embed(
                    title="**AIO Bot for Injective!**",
                    description="""
                        Available commands: \n
                        - `/sub val <valoper-address>`: Valoper address subscription will notify you of validator uptime, peggo performance and low balance on your validator operator and peggo orchestrator addresses \n
                        - `/sub list`: List all your subscriptions \n
                        - `/unsub <valoper-address>`: Unsubscribe from a subscription \n
                        - `/consensus`: Show current block's consensus state (useful in upgrade events) \n
                        - `/help`: Show this help menu
                    """
                )
                await self.reply(message.channel.id, msg)
            case "sub":
                commands = message.content[1:].split(' ')
                print(commands)
                if (len(commands) == 3):
                    sub_type = commands[1]
                    value = commands[2]
                    if sub_type == "val":
                        self.subscriptions.append({
                            "user": message.author.id,
                            "validator": value
                        })

                    msg = self.compose_embed(
                        description=f"Subscribed `{value}` for <@{message.author.id}>",
                    )
                    await self.reply(message.channel.id, msg)
                    with open("config.json", "r") as config_file:
                        config = json.load(config_file)
                    config["app"]["discord"]["subscriptions"] = self.subscriptions
                    with open("config.json", "w") as config_file:
                        json.dump(config, config_file, indent=4)
                elif (len(commands) == 2):
                    if commands[1] == "list":
                        user_subs = [sub["validator"] if "validator" in sub else sub["address"]
                                     for sub in self.subscriptions if sub["user"] == message.author.id]
                        sub_list = "\n".join(
                            f"- {sub}" for sub in user_subs) if user_subs else "No subscriptions found."
                        msg = self.compose_embed(
                            title=f"**Your subscriptions:**",
                            description=sub_list
                        )
                        await self.reply(message.channel.id, msg)
                    else:
                        msg = self.compose_embed(
                            title=f"**Invalid command!**",
                            description=f"Invalid command: `{commands}`",
                        )
                        await self.reply(message.channel.id, msg)
            case "unsub":
                value_to_remove = message.content[1:].split(' ')[1]
                self.subscriptions = [
                    sub for sub in self.subscriptions
                    if not (
                        sub.get("user") == message.author.id and (
                            sub.get("validator") == value_to_remove or
                            sub.get("address") == value_to_remove 
                        )
                    )
                ]
                msg = self.compose_embed(
                    description=f"Unsubscribed `{value_to_remove}` for <@{message.author.id}>",
                )
                await self.reply(message.channel.id, msg)
                with open("config.json", "r") as config_file:
                    config = json.load(config_file)
                config["app"]["discord"]["subscriptions"] = self.subscriptions
                with open("config.json", "w") as config_file:
                    json.dump(config, config_file, indent=4)
            case "consensus":
                commands = message.content[1:].split(' ')
                self.logger.debug(f"Commands: {commands}")
                if (len(commands) <= 2):
                    custom_rpc = commands[1] if len(commands) == 2 else self.rpcs
                    consensus_state = get_consensus(custom_rpc)
                    if consensus_state == {}:
                        msg = self.compose_embed(
                            title=f"**Error fetching consensus state!**"
                        )
                        await self.reply(message.channel.id, msg, auto_delete=60)
                    else:
                        msg_1 = self.compose_embed(
                            title=f"**Consensus state (1/3)**",
                            description=f"Height/Round/Step: `{consensus_state['height']}/{consensus_state['round']}/{consensus_state['step']}`\n \
                                       Prevotes/Precommits: `{consensus_state['prevotes_percent']}%/{consensus_state['precommits_percent']}%`\n \
                                        Proposer: `{consensus_state['validator'][consensus_state['proposer']]['moniker']}`",
                            fields=[
                                {
                                    "name":consensus_state["validator"][i]['moniker'],
                                    "value": f"{consensus_state["validator"][i]['prevotes']} {consensus_state["validator"][i]['precommits']}",
                                    "inline": True
                                } for i in range(24)
                            ],
                            footer=f"This message will be automatically deleted in 60s"
                        )
                        msg_2 = self.compose_embed(
                            title=f"**Consensus state (2/3)**",
                            description=f"Height/Round/Step: `{consensus_state['height']}/{consensus_state['round']}/{consensus_state['step']}`\n \
                                        Prevotes/Precommits: `{consensus_state['prevotes_percent']}%/{consensus_state['precommits_percent']}%`\n \
                                            Proposer: `{consensus_state['validator'][consensus_state['proposer']]['moniker']}`",
                            fields=[
                                {
                                    "name":consensus_state["validator"][i]['moniker'],
                                    "value": f"{consensus_state["validator"][i]['prevotes']} {consensus_state["validator"][i]['precommits']}",
                                    "inline": True
                                } for i in range(24, 48)
                            ],
                            footer=f"This message will be automatically deleted in 60s"
                        )
                        msg_3 = self.compose_embed(
                            title=f"**Consensus state (3/3)**",
                            description=f"Height/Round/Step: `{consensus_state['height']}/{consensus_state['round']}/{consensus_state['step']}`\n \
                                        Prevotes/Precommits: `{consensus_state['prevotes_percent']}%/{consensus_state['precommits_percent']}%`\n \
                                            Proposer: `{consensus_state['validator'][consensus_state['proposer']]['moniker']}`",
                            fields=[
                                {
                                    "name":consensus_state["validator"][i]['moniker'],
                                    "value": f"{consensus_state["validator"][i]['prevotes']} {consensus_state["validator"][i]['precommits']}",
                                    "inline": True
                                } for i in range(48, len(consensus_state["validator"]))
                            ],
                            footer=f"This message will be automatically deleted in 60s"
                        )
                        self.logger.debug(f"Consensus state: {consensus_state}")
                        await self.reply(message.channel.id, msg_1, auto_delete=60)
                        await self.reply(message.channel.id, msg_2, auto_delete=60)
                        await self.reply(message.channel.id, msg_3, auto_delete=60)
                else:
                    msg = self.compose_embed(
                        title=f"**Invalid command!**",
                        description=f"Invalid command: `{commands}`",
                    )
                    await self.reply(message.channel.id, msg)
            case _:
                self.logger.error(f"Invalid command: {command}")
                msg = self.compose_embed(
                    title=f"**Invalid command!**",
                    description=f"Invalid command: `{commands}`",
                )
                await self.reply(message.channel.id, msg)

    async def reply(self, channel_id, content, mention = "", auto_delete = 60):
        """
        Sends a message to a specified channel
        """
        await self.wait_until_ready()
        channel = self.get_channel(channel_id)
        if channel:
            try:
                asyncio.create_task(self.send_message(channel, mention, content, auto_delete))
                self.logger.info(f"Message sent to {channel.name}")
            except asyncio.TimeoutError:
                self.logger.error(
                    'Timeout: Failed to send message to channel %s', channel_id)
            except discord.Forbidden:
                self.logger.error(
                    'Bot does not have permission to send messages in channel %s', channel_id)
            except discord.HTTPException as e:
                self.logger.error(f"HTTP error occurred: {e}")
        else:
            self.logger.error('Channel with ID %s not found', channel_id)

    async def send_message(self, channel, mention, content, auto_delete):
        await channel.send(
            content=mention, 
            embed=content, 
            delete_after=auto_delete
        )

    def run(self):
        """
        Starts the Discord bot.
        """
        try:
            super().run(self.token)
        except Exception as e:
            self.logger.error(f"Error running the bot: {e}")
