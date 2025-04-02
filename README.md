# All-in-one validator services bot for Injective & other Cosmos-SDK based blockchains

The bot supports the following alerts:
- Missed blocks (signing performance)
- Validator status (active/inactive/jailed)
- Governance proposals
- Peggo performance (Injective)
- Balance checks (Injective/Ethereum)
- IBC packets tracking
- Network upgrades

The bot supports 3 platforms: Slack, Discord and Telegram.

![image](https://github.com/user-attachments/assets/509d4235-3541-451b-a81c-4e116c522a60)
![image](https://github.com/user-attachments/assets/ac22bbed-cdcc-4a2b-9f08-5570b8f7f617)

## Configuration
The configuration file is used to set up the AIO Bot for various platforms. It also contains subscription details to receive alerts on each platform, ensure the file is valid and present.

Below is an explanation of each section:
### `app`
- **slack**: Configuration for Slack integration.
    - `enable`: Boolean to enable/disable Slack integration.
    - `oAuth-token`: OAuth token for Slack API.
    - `signing-secret`: Signing secret for Slack.
    - `port`: Port number for Slack.
    - `channels`: List of Slack channels the bot will interact with.
        - `id`: Channel ID.
        - `name`: Channel name.
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
- **rpcs**: List of RPC endpoints for the network, set multiple endpoints for redundancy.

### `apis`
- **api**: List of API endpoints for the network, set multiple endpoints for redundancy.

### `features`
- **faucet**: Boolean to enable/disable the faucet feature.
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

- **peggo**: Configuration for Injective Peggo performance monitoring.
    - `enable`: Boolean to enable/disable Peggo monitoring.
    - `mode`: Mode of operation (e.g., "chain").
    - `params`: Parameters for Peggo monitoring.

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


## Message format:
### Validators
```
[WARNING_LEVEL] VALIDATOR has missed more than MISS_PERCENT of the allowed signing window!
Blocks to Jail: Consecutive missed blocks to be jailed
Window Signing Percentage: Current signing window / Minimum signing window
Signing window: Signing window params
```

```
[RECOVERING] VALIDATOR is recovering!
Window Signing Percentage: Current signing window / minimum signing window
```

```
VALIDATOR is active!
```

```
VALIDATOR is inactive!
```

```
VALIDATOR is JAILED!
Last Signed Block: Last signed block
Jailed Until: Time to be unjailed 
Jailed Duration: Jail duration param
```

### Balance:
```
Low balance!
Address: Address
Balance: Balance of the address
```
```
Invalid address!
Address: Address
```

### IBC:
```
Client CLIENT is about to expire!
From: Source chain
To: Destination chain
Last Updated: Last client update time
Time Left: Time left to be expired
```
```
Uncommited packets from SOURCE_CHAIN to DESTINATION_CHAIN!
From: Source chain
To: Destination chain
Port: Channel port
Channel: Channel ID
Missed: Number of missed packets
```
### Peggo:
```
VALIDATOR has pending valsets!
Pending Valsets: Length of pending valsets
Last Height Checked: Last height checked
```
```
VALIDATOR's nonce is lagging behind!
Last Observed Nonce: Chain latest nonce
Last Claimed Ethereum Event Nonce: Operator nonce
Last Height Checked: Last height checked
```

### Gov:
```
New Proposal PROPOSAL_ID!
Description: Summary
Type: Proposal type
Title: Proposal name
```

