import os
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponseForbidden, HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import models
from openai import OpenAI
from openai import RateLimitError, AuthenticationError, APIConnectionError

from .models import Battle
from .sol_utils import generate_battle_keypair, get_balance_lamports, get_signature_status, send_sol, sol_to_lamports


def _get_openai_client():
    return OpenAI(api_key=os.environ.get('chatgpt_api'))


def _run_ai_judge(battle: Battle):
    client = _get_openai_client()

    # Generate player_a AI response from their prompt + topic
    player_a_result = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[
            {
                'role': 'system',
                'content': (
                    'You are an AI competing in a battle. '
                    'Answer the topic using the player\'s instructions. '
                    'Be compelling and concise (max 200 words).'
                ),
            },
            {
                'role': 'user',
                'content': f'Topic: {battle.topic}\n\nInstructions: {battle.player_a_prompt}',
            },
        ],
        max_tokens=300,
    )
    battle.player_a_response = player_a_result.choices[0].message.content.strip()

    # Generate player_b AI response from their prompt + topic
    player_b_result = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[
            {
                'role': 'system',
                'content': (
                    'You are an AI competing in a battle. '
                    'Answer the topic using the player\'s instructions. '
                    'Be compelling and concise (max 200 words).'
                ),
            },
            {
                'role': 'user',
                'content': f'Topic: {battle.topic}\n\nInstructions: {battle.player_b_prompt}',
            },
        ],
        max_tokens=300,
    )
    battle.player_b_response = player_b_result.choices[0].message.content.strip()

    # AI judge evaluates both responses
    judge_prompt = f"""You are an impartial AI judge for a 1v1 AI battle.

Topic: {battle.topic}

Player A ({battle.player_a.username}) Answer:
{battle.player_a_response}

Player B ({battle.player_b.username}) Answer:
{battle.player_b_response}

Evaluate both answers fairly on accuracy, clarity, creativity, and persuasiveness.
Respond ONLY in this exact format:
WINNER: [A or B]
REASONING: [1-3 sentence explanation]"""

    judge_result = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[
            {
                'role': 'system',
                'content': 'You are a fair, concise AI judge. Follow the exact response format.',
            },
            {'role': 'user', 'content': judge_prompt},
        ],
        max_tokens=200,
    )
    verdict = judge_result.choices[0].message.content.strip()

    winner_line = next((l for l in verdict.split('\n') if l.startswith('WINNER:')), '')
    reasoning_line = next((l for l in verdict.split('\n') if l.startswith('REASONING:')), '')
    winner_letter = winner_line.replace('WINNER:', '').strip().upper()

    battle.judge_reasoning = reasoning_line.replace('REASONING:', '').strip()
    battle.winner = battle.player_a if winner_letter == 'A' else battle.player_b
    battle.status = Battle.STATUS_FINISHED
    battle.save()

    _send_payout(battle)


def _send_payout(battle: Battle):
    """Send 95% of the pot to the winner, 5% to the house wallet."""
    if not battle.battle_pubkey or not battle.battle_secret:
        return

    winner_pubkey = (
        battle.winner.public_wallet_address
        if battle.winner and battle.winner.public_wallet_address
        else ''
    )
    house_pubkey = os.environ.get('house_pubkey', '')

    if not winner_pubkey or not house_pubkey:
        return

    try:
        total = get_balance_lamports(battle.battle_pubkey)
        if total < 10_000:  # dust / unfunded battle
            return

        winner_lamports = int(total * 0.95) - 5_000  # subtract estimated tx fee
        house_lamports  = int(total * 0.05) - 5_000

        if winner_lamports > 0:
            send_sol(battle.battle_secret, winner_pubkey, winner_lamports)
        if house_lamports > 0:
            send_sol(battle.battle_secret, house_pubkey, house_lamports)
    except Exception as exc:
        # Payout failure must never break the battle result
        print(f'[Payout] Battle #{battle.pk} payout failed: {exc}')


TOPIC_CATEGORIES = [
    'Philosophy',
    'Science & Technology',
    'History',
    'Arts & Culture',
    'Politics & Society',
    'Mathematics & Logic',
    'Nature & Environment',
    'Sports & Competition',
    'Business & Economics',
    'Pop Culture',
    'Ethics & Morality',
    'Space & The Universe',
]


# ── Views ────────────────────────────────────────────────────────────────────

def battle_list(request):
    battles = Battle.objects.select_related('posted_by', 'player_a', 'player_b', 'winner').all()
    return render(request, 'service_apps/battles/templates/battles/list.html', {'battles': battles})


@login_required(login_url='/account/login')
def get_blockhash(request):
    """Return a recent blockhash from the server-side RPC (avoids browser 403)."""
    import requests as http_requests
    rpc = os.environ.get('solana_rpc', 'https://api.mainnet-beta.solana.com')
    try:
        resp = http_requests.post(rpc, json={
            'jsonrpc': '2.0', 'id': 1,
            'method': 'getLatestBlockhash',
            'params': [{'commitment': 'confirmed'}],
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()['result']['value']
        return JsonResponse({
            'blockhash': data['blockhash'],
            'lastValidBlockHeight': data['lastValidBlockHeight'],
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=502)


@login_required(login_url='/account/login')
def generate_question(request):
    """AJAX endpoint: given a category, return an AI-generated battle question."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        body = json.loads(request.body)
        category = body.get('category', '').strip()
    except (json.JSONDecodeError, AttributeError):
        category = request.POST.get('category', '').strip()

    if not category:
        return JsonResponse({'error': 'category required'}, status=400)

    try:
        client = _get_openai_client()
        result = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'You generate short, provocative, debate-worthy questions for 1v1 AI battles. '
                        'The question should be open-ended so AI can argue different perspectives. '
                        'Reply with ONLY the question text — no quotes, no prefixes, no explanation. '
                        'Max 120 characters.'
                    ),
                },
                {
                    'role': 'user',
                    'content': f'Generate one battle question for the category: {category}',
                },
            ],
            max_tokens=60,
        )
        question = result.choices[0].message.content.strip().strip('"').strip("'")
        return JsonResponse({'question': question})
    except RateLimitError:
        return JsonResponse(
            {'error': 'OpenAI quota exceeded. Please add credits at platform.openai.com/settings/billing.'},
            status=402,
        )
    except AuthenticationError:
        return JsonResponse(
            {'error': 'OpenAI API key is invalid or missing.'},
            status=401,
        )
    except APIConnectionError:
        return JsonResponse(
            {'error': 'Could not reach OpenAI. Check your internet connection and try again.'},
            status=503,
        )
    except Exception as e:
        return JsonResponse({'error': f'Generation failed: {e}'}, status=500)


@login_required(login_url='/account/login')
def create_battle(request):
    ctx = {'categories': TOPIC_CATEGORIES}
    if request.method == 'POST':
        # Enforce max 2 posted battles per user
        active_count = Battle.objects.filter(
            posted_by=request.user,
            status__in=[Battle.STATUS_WAITING, Battle.STATUS_PENDING, Battle.STATUS_JUDGING]
        ).count()
        if active_count >= 2:
            ctx['error'] = 'You already have 2 active battles. Finish them before creating a new one.'
            return render(request, 'service_apps/battles/templates/battles/create.html', ctx)

        topic = request.POST.get('topic', '').strip()
        category = request.POST.get('category', '').strip()
        stake = request.POST.get('stake', '0.1').strip()

        if not topic:
            ctx['error'] = 'Please generate a question first.'
            ctx.update({'post_category': category, 'post_stake': stake})
            return render(request, 'service_apps/battles/templates/battles/create.html', ctx)
        try:
            stake_val = float(stake)
            if stake_val <= 0:
                raise ValueError
        except ValueError:
            ctx['error'] = 'Stake must be a positive number.'
            ctx.update({'post_topic': topic, 'post_category': category})
            return render(request, 'service_apps/battles/templates/battles/create.html', ctx)

        pubkey, secret = generate_battle_keypair()
        battle = Battle.objects.create(
            posted_by=request.user,
            topic=topic,
            stake=stake_val,
            battle_pubkey=pubkey,
            battle_secret=secret,
        )
        return redirect('battles:detail', pk=battle.pk)

    return render(request, 'service_apps/battles/templates/battles/create.html', ctx)


def battle_detail(request, pk):
    battle = get_object_or_404(
        Battle.objects.select_related('posted_by', 'player_a', 'player_b', 'winner'), pk=pk
    )
    user = request.user
    is_player_a = user.is_authenticated and battle.player_a == user
    is_player_b = user.is_authenticated and battle.player_b == user

    is_creator = user.is_authenticated and battle.posted_by == user
    creator_needs_pay = is_creator and not is_player_a and battle.status == Battle.STATUS_WAITING

    can_join = (
        user.is_authenticated
        and battle.status == Battle.STATUS_WAITING
        and not is_player_a
        and not is_player_b
        and not is_creator
    )
    player_a_needs_prompt = is_player_a and not battle.player_a_prompt and battle.status == Battle.STATUS_PENDING
    player_b_needs_prompt = is_player_b and not battle.player_b_prompt and battle.status == Battle.STATUS_PENDING

    context = {
        'battle': battle,
        'is_player_a': is_player_a,
        'is_player_b': is_player_b,
        'is_creator': is_creator,
        'creator_needs_pay': creator_needs_pay,
        'can_join': can_join,
        'player_a_needs_prompt': player_a_needs_prompt,
        'player_b_needs_prompt': player_b_needs_prompt,
        'rpc_url': os.environ.get('solana_rpc', 'https://api.mainnet-beta.solana.com'),
    }
    return render(request, 'service_apps/battles/templates/battles/detail.html', context)


@login_required(login_url='/account/login')
def join_battle(request, pk):
    """
    POST with a Phantom tx signature → assign player slot, advance status.
    GET  → fallback payment instructions page.
    """
    battle = get_object_or_404(Battle, pk=pk)
    user = request.user

    if battle.status != Battle.STATUS_WAITING:
        return redirect('battles:detail', pk=pk)
    if battle.player_a == user or battle.player_b == user:
        return redirect('battles:detail', pk=pk)

    # Lazy-generate keypair for battles created before Solana integration
    if not battle.battle_pubkey:
        pubkey, secret = generate_battle_keypair()
        battle.battle_pubkey = pubkey
        battle.battle_secret = secret
        battle.save(update_fields=['battle_pubkey', 'battle_secret'])

    taking_slot_a = battle.player_a is None

    if request.method == 'GET':
        stake_lamports = sol_to_lamports(battle.stake)
        required_lamports = stake_lamports if taking_slot_a else 2 * stake_lamports
        return render(request, 'service_apps/battles/templates/battles/payment.html', {
            'battle': battle,
            'taking_slot_a': taking_slot_a,
            'stake_lamports': stake_lamports,
            'required_lamports': required_lamports,
        })

    # ── POST: verify Phantom tx signature before assigning the slot ───
    signature = request.POST.get('signature', '').strip()
    if not signature:
        return HttpResponseBadRequest('Missing transaction signature.')

    # Verify the transaction was confirmed on-chain
    import time
    confirmed = False
    for _attempt in range(8):  # poll up to ~8 seconds
        try:
            status = get_signature_status(signature)
            if status in ('confirmed', 'finalized'):
                confirmed = True
                break
        except ValueError:
            return HttpResponseBadRequest('Transaction failed on-chain.')
        except Exception:
            pass
        time.sleep(1)

    if not confirmed:
        return HttpResponseBadRequest('Could not confirm your transaction. Please try again.')

    # Verify the escrow wallet received enough funds
    stake_lamports = sol_to_lamports(battle.stake)
    try:
        balance = get_balance_lamports(battle.battle_pubkey)
    except Exception:
        return HttpResponseBadRequest('Could not verify escrow balance. Please try again.')

    expected_min = stake_lamports if taking_slot_a else 2 * stake_lamports
    # Allow 5% tolerance for rounding / fees
    if balance < int(expected_min * 0.95):
        return HttpResponseBadRequest('Insufficient funds received in the battle escrow. Payment may still be processing — please refresh and try again.')

    # Enforce max 2 active battles per user
    active_count = Battle.objects.filter(
        status__in=[Battle.STATUS_WAITING, Battle.STATUS_PENDING, Battle.STATUS_JUDGING]
    ).filter(
        models.Q(player_a=user) | models.Q(player_b=user)
    ).count()
    if active_count >= 2:
        return HttpResponseBadRequest('You already have 2 active battles. Finish one before joining another.')

    if taking_slot_a:
        battle.player_a = user
        battle.player_a_paid = True
    else:
        battle.player_b = user
        battle.player_b_paid = True
        battle.status = Battle.STATUS_PENDING
    battle.save()

    return redirect('battles:detail', pk=battle.pk)


@login_required(login_url='/account/login')
@require_POST
def submit_prompt(request, pk):
    battle = get_object_or_404(Battle, pk=pk)
    user = request.user

    is_player_a = battle.player_a == user
    is_player_b = battle.player_b == user

    if not is_player_a and not is_player_b:
        return HttpResponseForbidden('You are not a participant in this battle.')
    if battle.status not in (Battle.STATUS_WAITING, Battle.STATUS_PENDING):
        return HttpResponseBadRequest('Prompts can no longer be submitted for this battle.')
    if is_player_a and battle.player_a_prompt:
        return HttpResponseBadRequest('You have already submitted your prompt.')
    if is_player_b and battle.player_b_prompt:
        return HttpResponseBadRequest('You have already submitted your prompt.')

    prompt = request.POST.get('prompt', '').strip()
    if not prompt:
        return redirect('battles:detail', pk=battle.pk)

    if is_player_a:
        battle.player_a_prompt = prompt
    else:
        battle.player_b_prompt = prompt
    battle.save()

    # If both prompts are in, start judging
    if battle.player_a_prompt and battle.player_b_prompt:
        battle.status = Battle.STATUS_JUDGING
        battle.save()
        try:
            _run_ai_judge(battle)
        except Exception:
            pass

    return redirect('battles:detail', pk=battle.pk)
