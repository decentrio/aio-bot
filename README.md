# AIO Bot - All-in-one services bot for Injective/other Cosmos chains

The bot has fundamental features:
- Notify user when a validator miss blocks/low signing performance
- Notify user when a validator is active/inactive/jailed
- New proposal on chain
- Peggo performance (Injective)
- Check balance (Injective/Ethereum, useful for peggo operators)
- IBC packets tracking
- Upgrades on chain

The bot supports on 3 platforms: Slack, Discord, and Telegram.

![image](https://github.com/user-attachments/assets/509d4235-3541-451b-a81c-4e116c522a60)
![image](https://github.com/user-attachments/assets/ac22bbed-cdcc-4a2b-9f08-5570b8f7f617)


## Setup
To setup bot for messaging platforms, refer to 

## Configuration
This configuration file is used to set up the AIO Bot for various platforms and features. The file also contains subscriptions detail for each platform, so it should not be removed/renamed. (todo: make a proper db)

Below is an explanation of each section:
### `app`
- **slack**: Configuration for Slack integration.
    - `enable`: Boolean to enable/disable Slack integration.
    - `oAuth-token`: OAuth token for Slack API.
    - `signing-secret`: Signing secret for Slack.
    - `port`: Port number for the Slack bot.
    - `channels`: List of Slack channels the bot will interact with.
        - `id`: Channel ID.
        - `name`: Channel name, for easy management.
    - `subscriptions`: List of user subscriptions to validators. This will store all subscriptions information so the file must not be deleted.

- **discord**: Configuration for Discord integration.
    - `enable`: Boolean to enable/disable Discord integration.
    - `bot-token`: Bot token for Discord API.
    - `channels`: List of Discord channels the bot will interact with.
        - `id`: Channel ID.
        - `name`: Channel name.
    - `subscriptions`: List of user subscriptions to validators. This will store all subscriptions information so the file must not be deleted.

- **telegram**: Configuration for Telegram integration.
    - `enable`: Boolean to enable/disable Telegram integration.
    - `bot`: Bot token for Telegram API.
    - `subscriptions`: List of user subscriptions to validators. This will store all subscriptions information so the file must not be deleted.

### `chain`
- **chain**: Chain pretty name.

### `rpcs`
- **rpcs**: List of RPC endpoints for the blockchain network. The websocket module will connect to these rpcs and will try next ones when an URL is failed to connect.

### `api`
- **api**: API endpoint for the blockchain network.

### `features`
- **faucet**: Boolean to enable/disable faucet feature.
- **gov**: Configuration for governance features.
    - `enable`: Boolean to enable/disable governance features.
    - `params`: Parameters for governance.
        - `voting_period`: Voting period duration.
        - `min_deposit`: Minimum deposit required.
        - `threshold`: Threshold for passing proposals.
        - `veto`: Veto threshold.

- **validators**: Configuration for validator monitoring.
    - `enable`: Boolean to enable/disable validator monitoring.
    - `mode`: Mode of operation (e.g., "chain").
    - `params`: Parameters for validator monitoring.
        - `threshold`: Threshold for alerts.
        - `signing_window`: Signing window duration.
        - `min_signed_per_window`: Minimum signed blocks per window.
        - `jailed_duration`: Duration for which a validator is jailed.
        - `prefix`: Prefix for validator addresses.

- **peggo**: Configuration for Peggo performance monitoring.
    - `enable`: Boolean to enable/disable Peggo monitoring.
    - `mode`: Mode of operation (e.g., "chain").
    - `params`: Parameters for Peggo monitoring (currently empty).

- **ibc**: Boolean to enable/disable IBC packets tracking.
- **consensus**: Boolean to enable/disable consensus monitoring.
- **wallet**: Configuration for wallet monitoring.
    - `mode`: Mode of operation (e.g., "chain").
    - `enable`: Boolean to enable/disable wallet monitoring.
    - `params`: Parameters for wallet monitoring (currently empty).


## Run
```bash
python3 -m venv .aio
source .aio/bin/activate
pip3 install -r requirements.txt
python3 main.py
```
