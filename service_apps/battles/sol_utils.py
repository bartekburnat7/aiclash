"""
Minimal Solana utilities: keypair generation, balance check, SOL transfer.
Uses direct JSON-RPC HTTP calls + solders for signing.
"""
import os
import base64
import base58
import requests

from solders.keypair import Keypair as SoldersKeypair
from solders.pubkey import Pubkey
from solders.hash import Hash
from solders.transaction import Transaction
from solders.system_program import transfer, TransferParams


def _rpc_url():
    return os.environ.get('solana_rpc', 'https://api.mainnet-beta.solana.com')


def generate_battle_keypair():
    """Generate a fresh Solana keypair. Returns (pubkey_str, secret_b58)."""
    kp = SoldersKeypair()
    secret_b58 = base58.b58encode(bytes(kp)).decode()
    return str(kp.pubkey()), secret_b58


def get_balance_lamports(pubkey_str):
    """Return the confirmed SOL balance of an address in lamports."""
    resp = requests.post(
        _rpc_url(),
        json={
            'jsonrpc': '2.0', 'id': 1,
            'method': 'getBalance',
            'params': [pubkey_str, {'commitment': 'confirmed'}],
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()['result']['value']


def sol_to_lamports(sol_amount):
    return int(float(sol_amount) * 1_000_000_000)


def get_signature_status(signature_str):
    """Return the confirmationStatus string for a tx signature, or None if not found."""
    resp = requests.post(
        _rpc_url(),
        json={
            'jsonrpc': '2.0', 'id': 1,
            'method': 'getSignatureStatuses',
            'params': [[signature_str], {'searchTransactionHistory': True}],
        },
        timeout=10,
    )
    resp.raise_for_status()
    value = resp.json()['result']['value']
    if not value or value[0] is None:
        return None
    if value[0].get('err'):
        raise ValueError(f'Transaction failed on-chain: {value[0]["err"]}')
    return value[0].get('confirmationStatus')


def send_sol(from_secret_b58, to_pubkey_str, lamports):
    """
    Sign and broadcast a SOL transfer from a keypair to a destination.
    Returns the transaction signature string.
    Raises on RPC or network errors.
    """
    rpc = _rpc_url()
    kp = SoldersKeypair.from_bytes(base58.b58decode(from_secret_b58))
    dest = Pubkey.from_string(to_pubkey_str)

    # Get latest blockhash
    bh = requests.post(rpc, json={
        'jsonrpc': '2.0', 'id': 1,
        'method': 'getLatestBlockhash',
        'params': [{'commitment': 'finalized'}],
    }, timeout=10)
    bh.raise_for_status()
    blockhash = Hash.from_string(bh.json()['result']['value']['blockhash'])

    # Build and sign transaction
    ix = transfer(TransferParams(
        from_pubkey=kp.pubkey(),
        to_pubkey=dest,
        lamports=lamports,
    ))
    tx = Transaction.new_signed_with_payer([ix], kp.pubkey(), [kp], blockhash)

    # Send
    payload = base64.b64encode(bytes(tx)).decode()
    result = requests.post(rpc, json={
        'jsonrpc': '2.0', 'id': 1,
        'method': 'sendTransaction',
        'params': [payload, {'encoding': 'base64', 'preflightCommitment': 'confirmed'}],
    }, timeout=30)
    result.raise_for_status()
    data = result.json()
    if 'error' in data:
        raise RuntimeError(f"Solana RPC error: {data['error']}")
    return data['result']  # tx signature
