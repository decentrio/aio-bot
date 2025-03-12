import hashlib
import base64
from bech32 import bech32_encode, convertbits

def convert(pubkey_base64, prefix):
    """
    Generates a Bech32-encoded address by directly hashing the public key.
    """
    pubkey_bytes = base64.b64decode(pubkey_base64)
    sha256_hash = hashlib.sha256(pubkey_bytes).digest()
    address_bytes = sha256_hash[:20]
    converted_bits = convertbits(address_bytes, 8, 5)
    if converted_bits is None:
        raise ValueError("Error in converting bits for Bech32 encoding.")

    bech32_address = bech32_encode(prefix, converted_bits)
    hex_address = address_bytes.hex()

    return  hex_address.upper(), bech32_address

# if __name__ == "__main__":
#     prefix = "onomyvalcons"
#     consensus_pubkey = { 
#         "@type": "/cosmos.crypto.ed25519.PubKey",
#         "key": "Z78utMFhMjee0HZVQSjfmHOYFXTrGhIXVVBJKzTU+ic="
#     }
       
#     try:
#         hex_address, valcons_address = convert(consensus_pubkey["key"], prefix)
#         print(f"Hex Address (valcons): {hex_address}")
#         print(f"Validator Consensus Address (valcons): {valcons_address}")
#     except Exception as e:
#         print(f"Error generating valcons address: {e}")