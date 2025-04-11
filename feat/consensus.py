import utils.query as query
import logging
import re
import json

def get_consensus(rpcs):
    """
    Fetching the current consensus state
    """
    consensus_info = {}
    with open("validators.json", "r") as f:
        validators = json.load(f)
        f.close()

    try:
        data = query.query(rpcs, path=f"/consensus_state")
        consensus_state = data.get("result", {}).get("round_state", {})
        logging.info(f"Consensus state: {consensus_state}") 
        data = query.query(rpcs, path=f"/validators?per_page=300")
        valset = data.get("result", {}).get("validators", [])
        height_round_step = consensus_state.get("height/round/step", "")
        if height_round_step:
            height, round_num, step = height_round_step.split("/")
            consensus_info["height"] = int(height)
            consensus_info["round"] = int(round_num)
            consensus_info["step"] = int(step)
        height_vote_set = consensus_state.get("height_vote_set", [])
        current_round_state = height_vote_set[-1] if height_vote_set else {}
        prevotes_bit_array = current_round_state.get("prevotes_bit_array", "")
        precommits_bit_array = current_round_state.get("precommits_bit_array", "")
        consensus_info["prevotes_percent"] = prevotes_bit_array.split("=")[-1].strip()
        consensus_info["precommits_percent"] = precommits_bit_array.split("=")[-1].strip()
        consensus_info["proposer"] = consensus_state.get("proposer", {}).get("index", -1) 
        prevotes = re.search(r":([^}]+)}", prevotes_bit_array).group(1)
        precommits = re.search(r":([^}]+)}", precommits_bit_array).group(1)
        consensus_info["validator"] = [] 
        for id in range(len(prevotes)):
            address = valset[id].get("address")
            for val in validators:
                if address == val.get("hex"):
                    consensus_info["validator"].append({
                        "moniker": val.get("moniker"),
                        "prevotes": "✅" if prevotes[id] == "x" else "❌",
                        "precommits": "✅" if precommits[id] == "x" else "❌",
                        "address": address
                    })
                    break
        return consensus_info
    except Exception as e:
        logging.error(f"Error fetching consensus: {e}")
        return {
            "error": f"Error fetching consensus: {e}",
        }
