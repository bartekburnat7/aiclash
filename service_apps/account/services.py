from mnemonic import Mnemonic
from solders.keypair import Keypair
from config import load_data, save_data

def create_wallet():
    """Generate a new Solana wallet from a 12-word mnemonic phrase."""
    mnemo = Mnemonic("english")
    mnemonic_phrase = mnemo.generate(strength=128)

    seed = mnemo.to_seed(mnemonic_phrase)
    keypair = Keypair.from_seed(seed[:32])

    return keypair, mnemonic_phrase

def load_wallet(mnemonic_phrase):
    """Load an existing wallet from a 12-word mnemonic phrase."""
    mnemo = Mnemonic("english")
    seed = mnemo.to_seed(mnemonic_phrase)
    keypair = Keypair.from_seed(seed[:32])

    return keypair