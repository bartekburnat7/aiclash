import secrets
import base58
import base64

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET



from .models import CustomUser


# ── Nonce ───────────────────────────────────────────────────────────────────

@require_GET
def wallet_nonce(request):

    pubkey = request.GET.get('pubkey', '').strip()
    if not pubkey:
        return JsonResponse({'error': 'pubkey required'}, status=400)
    nonce = secrets.token_hex(32)
    request.session['wallet_nonce'] = nonce
    request.session['wallet_nonce_pubkey'] = pubkey
    message = f'Sign in to AIclash.fun\nNonce: {nonce}'
    return JsonResponse({'nonce': nonce, 'message': message})


def _verify_phantom_signature(pubkey_b58: str, message: str, signature_b64: str) -> bool:
    from nacl.signing import VerifyKey
    from nacl.exceptions import BadSignatureError
    try:
        verify_key = VerifyKey(base58.b58decode(pubkey_b58))
        sig_bytes = base64.b64decode(signature_b64)
        verify_key.verify(message.encode('utf-8'), sig_bytes)
        return True
    except (BadSignatureError, Exception):
        return False


# ── Login ────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    error = None

    if request.method == 'POST':
        pubkey = request.POST.get('pubkey', '').strip()
        signature = request.POST.get('signature', '').strip()
        nonce = request.session.get('wallet_nonce', '')
        nonce_pubkey = request.session.get('wallet_nonce_pubkey', '')
        message = f'Sign in to AIclash.fun\nNonce: {nonce}'

        if not pubkey or not signature or not nonce:
            error = 'Wallet connection incomplete. Please try again.'
        elif pubkey != nonce_pubkey:
            error = 'Wallet address mismatch.'
        elif not _verify_phantom_signature(pubkey, message, signature):
            error = 'Signature verification failed.'
        else:
            request.session.pop('wallet_nonce', None)
            request.session.pop('wallet_nonce_pubkey', None)
            try:
                user = CustomUser.objects.get(public_wallet_address=pubkey)
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                return redirect(request.GET.get('next') or 'home    ')
            except CustomUser.DoesNotExist:
                error = 'No account found for this wallet. Please register first.'

    return render(request, 'service_apps/account/templates/login.html', {'error': error})


# ── Register ─────────────────────────────────────────────────────────────────

def register(request):
    if request.user.is_authenticated:
        return redirect('home')

    error = None

    if request.method == 'POST':
        pubkey = request.POST.get('pubkey', '').strip()
        signature = request.POST.get('signature', '').strip()
        username = request.POST.get('username', '').strip()
        nonce = request.session.get('wallet_nonce', '')
        nonce_pubkey = request.session.get('wallet_nonce_pubkey', '')
        message = f'Sign in to AIclash.fun\nNonce: {nonce}'

        if not pubkey or not signature or not nonce:
            error = 'Wallet connection incomplete. Please try again.'
        elif pubkey != nonce_pubkey:
            error = 'Wallet address mismatch.'
        elif not _verify_phantom_signature(pubkey, message, signature):
            error = 'Signature verification failed.'
        elif not username:
            error = 'Username is required.'
        elif len(username) > 30:
            error = 'Username must be 30 characters or less.'
        elif not username.replace('_', '').replace('-', '').isalnum():
            error = 'Username can only contain letters, digits, hyphens and underscores.'
        elif CustomUser.objects.filter(username__iexact=username).exists():
            error = 'That username is already taken.'
        elif CustomUser.objects.filter(public_wallet_address=pubkey).exists():
            error = 'An account already exists for this wallet. Please log in instead.'
        else:
            request.session.pop('wallet_nonce', None)
            request.session.pop('wallet_nonce_pubkey', None)
            user = CustomUser.objects.create_user(username=username, public_wallet_address=pubkey)
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('home')

    return render(request, 'service_apps/account/templates/register.html', {'error': error})


# ── Logout ───────────────────────────────────────────────────────────────────

@login_required(login_url='/account/login')
def logout_view(request):
    logout(request)
    return redirect('home')