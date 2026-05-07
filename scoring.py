"""
scoring.py — Shared seal scoring logic.

Used by:
  - cogs/confirm_seals.py     (evaluate + write to DB)
  - cogs/view_seal_progress.py (evaluate + display only)
"""

import os
import discord
from google_services import GoogleServices

# ---------------------------------------------------------------------------
# Scoring Configuration
# ---------------------------------------------------------------------------

# Minimum number of submitted reviews required to be eligible for a Seal.
MIN_REVIEWS = 1 if os.getenv("ENVIRONMENT") == "test" else 5

# Percentage of reviews (>=) that must score >= PASS_SCORE to earn the Seal.
PASS_RATE_THRESHOLD = 0.70

# A single review must reach this weighted score to count as a "passing" review.
PASS_SCORE = 80.0  # out of 100

# Category weights (must sum to 1.0).
# Keys are lowercase substrings matched against Google Form question titles.
# Real form titles confirmed from Cycle 10 exports:
#   AESTHETICS | THEME | MATERIALS | MECHANICS | BALANCE | FUN FACTOR
CATEGORY_WEIGHTS = {
    "aesthetics": 0.10,
    "theme":      0.10,
    "materials":  0.10,
    "fun factor": 0.20,
    "mechanics":  0.25,
    "balance":    0.25,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _match_weight(question_title: str) -> float | None:
    """
    Return the weight for a question based on a case-insensitive substring
    match against CATEGORY_WEIGHTS keys, or None if not a scored category.
    """
    lower = question_title.lower()
    for keyword, weight in CATEGORY_WEIGHTS.items():
        if keyword in lower:
            return weight
    return None


def _parse_numeric(raw: str) -> float | None:
    """Parse '8', '8 - Great', '8-Great' etc. into a float, or None."""
    try:
        return float(raw.strip().split()[0].split("-")[0].strip())
    except (ValueError, IndexError, AttributeError):
        return None


def _score_response(answers: dict, question_map: dict) -> float | None:
    """
    Calculate the weighted score (0–100) for a single form response.

    question_map: { question_id -> question_title }
    answers:      { question_id -> Google Forms answer dict }

    Returns None if no scored questions could be found.
    """
    weighted_sum = 0.0
    total_weight = 0.0

    for q_id, title in question_map.items():
        weight = _match_weight(title)
        if weight is None:
            continue

        answer_data = answers.get(q_id)
        if not answer_data:
            continue

        for ta in answer_data.get("textAnswers", {}).get("answers", []):
            val = _parse_numeric(ta.get("value", ""))
            if val is not None:
                # Form scores are 1–10; normalise to 0–100.
                weighted_sum += (val / 10.0) * weight * 100
                total_weight += weight
                break  # one answer per question

    if total_weight == 0:
        return None

    # Scale proportionally in case some categories were unanswered.
    return weighted_sum / total_weight


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_set(form_id: str, entry: dict, gs: GoogleServices) -> dict:
    """
    Fetch responses for one Google Form and evaluate the Seal criteria.

    Parameters
    ----------
    form_id : str
        The Google Form ID.
    entry : dict
        The Spotlight roster entry (needs at least ``set_name`` and
        ``category``).
    gs : GoogleServices
        An already-initialised GoogleServices instance.

    Returns
    -------
    dict with keys:
        set_name, category, form_id,
        num_reviews (int),
        weighted_scores (list[float]),
        passing_reviews (int),
        pass_rate (float 0–1),
        avg_score (float | None),
        category_averages (dict[title, float | None]),
        sealed (bool),
        failure_reasons (list[str])
    """
    set_name = entry.get("set_name", "Unknown")
    category = entry.get("category", "Unknown")

    # Fetch form structure to build question_id → title map
    form_structure = gs.get_form(form_id)
    items = form_structure.get("items", [])

    question_map: dict[str, str] = {}
    for item in items:
        q_item = item.get("questionItem")
        if not q_item:
            continue
        q = q_item.get("question", {})
        if not q or "questionId" not in q:
            continue
        # Only include scale questions (numerical scores), skip text/comment fields
        if "scaleQuestion" not in q and "choiceQuestion" not in q:
            continue
        question_map[q["questionId"]] = item.get("title", "Unknown")

    # Fetch all responses
    responses = gs.get_form_responses(form_id)

    # Accumulate per-category raw scores for the breakdown display
    category_accumulators: dict[str, list[float]] = {
        title: []
        for title in question_map.values()
        if _match_weight(title) is not None
    }

    weighted_scores: list[float] = []

    for response in responses:
        answers = response.get("answers", {})

        # Per-category accumulation
        for q_id, title in question_map.items():
            if _match_weight(title) is None:
                continue
            answer_data = answers.get(q_id)
            if not answer_data:
                continue
            for ta in answer_data.get("textAnswers", {}).get("answers", []):
                val = _parse_numeric(ta.get("value", ""))
                if val is not None:
                    category_accumulators[title].append(val)
                    break

        score = _score_response(answers, question_map)
        if score is not None:
            weighted_scores.append(score)

    num_reviews = len(weighted_scores)
    passing_reviews = sum(1 for s in weighted_scores if s >= PASS_SCORE)
    pass_rate = passing_reviews / num_reviews if num_reviews > 0 else 0.0
    avg_score = sum(weighted_scores) / num_reviews if num_reviews > 0 else None

    is_withdrawn = entry.get("withdrawn", False)

    # Determine pass/fail and collect explicit failure reasons
    failure_reasons: list[str] = []
    if is_withdrawn:
        failure_reasons.append("Set was withdrawn from the Seal process by the creator")
    if num_reviews < MIN_REVIEWS:
        failure_reasons.append(
            f"Insufficient reviews: {num_reviews} submitted, {MIN_REVIEWS} required"
        )
    if num_reviews > 0 and pass_rate < PASS_RATE_THRESHOLD:
        failure_reasons.append(
            f"Pass rate too low: {pass_rate * 100:.1f}% scored ≥ {PASS_SCORE:.0f} "
            f"(requires {PASS_RATE_THRESHOLD * 100:.0f}%)"
        )

    sealed = len(failure_reasons) == 0

    category_averages = {
        title: (sum(vals) / len(vals)) if vals else None
        for title, vals in category_accumulators.items()
    }

    return {
        "set_name": set_name,
        "category": category,
        "form_id": form_id,
        "num_reviews": num_reviews,
        "weighted_scores": weighted_scores,
        "passing_reviews": passing_reviews,
        "pass_rate": pass_rate,
        "avg_score": avg_score,
        "category_averages": category_averages,
        "sealed": sealed,
        "failure_reasons": failure_reasons,
    }


def build_result_embed(result: dict, cycle_number: int,
                       *, show_seal_status: bool = True) -> discord.Embed:
    """
    Build a Discord Embed from an ``evaluate_set`` result dict.

    Parameters
    ----------
    result : dict
        Output of ``evaluate_set``.
    cycle_number : int
        Used in the embed description.
    show_seal_status : bool
        If True (default), colours the embed and labels it SEALED/NOT SEALED.
        Set to False for the progress view where no decision has been made yet.
    """
    set_name = result["set_name"]
    sealed = result["sealed"]
    num_reviews = result["num_reviews"]

    if show_seal_status:
        color = discord.Color.green() if sealed else discord.Color.red()
        status_icon = "✅" if sealed else "❌"
        status_text = "**SEALED**" if sealed else "**NOT SEALED**"
        title = f"{status_icon} {set_name} ({result['category']})"
        description = f"Cycle {cycle_number} — {status_text}"
    else:
        # Progress view — use a neutral colour and no pass/fail verdict
        color = discord.Color.blurple()
        title = f"📊 {set_name} ({result['category']})"
        description = f"Cycle {cycle_number} — In Progress"

    embed = discord.Embed(title=title, description=description, color=color)

    # Review count
    min_label = f" / {MIN_REVIEWS} required" if num_reviews < MIN_REVIEWS else " ✅"
    embed.add_field(
        name="Reviews",
        value=f"{num_reviews}{min_label}",
        inline=True
    )

    # Average weighted score
    if result["avg_score"] is not None:
        embed.add_field(
            name="Avg Weighted Score",
            value=f"{result['avg_score']:.1f} / 100",
            inline=True
        )
    else:
        embed.add_field(name="Avg Weighted Score", value="No data yet", inline=True)

    # Pass rate
    if num_reviews > 0:
        threshold_label = f"≥ {PASS_SCORE:.0f}"
        embed.add_field(
            name=f"Reviews Scoring {threshold_label}",
            value=(
                f"{result['passing_reviews']}/{num_reviews} "
                f"({result['pass_rate'] * 100:.1f}%)"
                f" — need {PASS_RATE_THRESHOLD * 100:.0f}%"
            ),
            inline=False
        )

    # Per-category breakdown (only categories with data)
    if result["category_averages"]:
        lines = []
        for title, avg in sorted(result["category_averages"].items()):
            if avg is None:
                continue
            weight = _match_weight(title)
            w_pct = f"{weight * 100:.0f}%" if weight else "?"
            lines.append(f"• **{title}** (weight {w_pct}): {avg:.2f}/10")
        if lines:
            embed.add_field(
                name="Category Breakdown",
                value="\n".join(lines),
                inline=False
            )

    # Failure reasons (only shown when show_seal_status=True)
    if show_seal_status and not sealed:
        embed.add_field(
            name="Failure Reason(s)",
            value="\n".join(f"• {r}" for r in result["failure_reasons"]),
            inline=False
        )

    return embed
