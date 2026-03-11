import os
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponseForbidden, HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from openai import OpenAI
from openai import RateLimitError, AuthenticationError, APIConnectionError

from .models import Battle


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

        battle = Battle.objects.create(
            posted_by=request.user,
            topic=topic,
            stake=stake_val,
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

    can_join = (
        user.is_authenticated
        and battle.status == Battle.STATUS_WAITING
        and not is_player_a
        and not is_player_b
    )
    player_a_needs_prompt = is_player_a and not battle.player_a_prompt and battle.status == Battle.STATUS_PENDING
    player_b_needs_prompt = is_player_b and not battle.player_b_prompt and battle.status == Battle.STATUS_PENDING

    context = {
        'battle': battle,
        'is_player_a': is_player_a,
        'is_player_b': is_player_b,
        'can_join': can_join,
        'player_a_needs_prompt': player_a_needs_prompt,
        'player_b_needs_prompt': player_b_needs_prompt,
    }
    return render(request, 'service_apps/battles/templates/battles/detail.html', context)


@login_required(login_url='/account/login')
@require_POST
def join_battle(request, pk):
    battle = get_object_or_404(Battle, pk=pk)
    if battle.status != Battle.STATUS_WAITING:
        return HttpResponseBadRequest('Battle is not open for joining.')

    user = request.user
    if battle.player_a == user or battle.player_b == user:
        return HttpResponseForbidden('You have already joined this battle.')

    # Enforce max 2 active battles per user (as a player)
    active_as_a = Battle.objects.filter(
        player_a=user,
        status__in=[Battle.STATUS_WAITING, Battle.STATUS_PENDING, Battle.STATUS_JUDGING]
    ).count()
    active_as_b = Battle.objects.filter(
        player_b=user,
        status__in=[Battle.STATUS_WAITING, Battle.STATUS_PENDING, Battle.STATUS_JUDGING]
    ).count()
    if active_as_a + active_as_b >= 2:
        return HttpResponseForbidden('You already have 2 active battles. Finish them before joining another.')

    if battle.player_a is None:
        # Take slot A — battle still waiting for player B
        battle.player_a = user
    else:
        # Take slot B — both players ready, move to pending
        battle.player_b = user
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
