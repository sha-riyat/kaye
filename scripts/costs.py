"""Real model cost per merchant, from the `model_call` table.

    uv run python -m scripts.costs            # uses DATABASE_URL
    uv run python -m scripts.costs --days 7

Prints, per model, the number of calls, the total and the average cost, then the cost of one
active merchant-day and a 30-day projection. Transcription is logged per audio minute.
"""

import argparse
import asyncio
from datetime import timedelta

from sqlalchemy import func
from sqlmodel import select

from app.config import get_settings
from app.db.engine import Database
from app.db.models import ModelCall
from app.db.queries import utcnow

USD_TO_FCFA = 600  # rounded; XOF is pegged to the euro, check the day's rate before quoting


async def main(days: int) -> None:
    db = Database(get_settings().database_url)
    since = utcnow() - timedelta(days=days)
    async with db.session() as s:
        per_model = (
            await s.exec(
                select(ModelCall.model, func.count(), func.sum(ModelCall.cost_usd), func.avg(ModelCall.cost_usd))
                .where(ModelCall.created_at >= since)
                .group_by(ModelCall.model)
            )
        ).all()
        day = func.date_trunc("day", ModelCall.created_at)
        shop_days = (
            await s.exec(
                select(ModelCall.shop_id, day, func.sum(ModelCall.cost_usd), func.count())
                .where(ModelCall.created_at >= since, ModelCall.shop_id.is_not(None))  # type: ignore[union-attr]
                .group_by(ModelCall.shop_id, day)
            )
        ).all()
    await db.dispose()

    print(f"Last {days} day(s)\n")
    print(f"{'model':28} {'calls':>6} {'total $':>10} {'avg $':>9}")
    for model, n, total, avg in per_model:
        print(f"{model:28} {n:6d} {float(total):10.4f} {float(avg):9.5f}")
    if not shop_days:
        print("\nNo merchant activity yet.")
        return
    costs = sorted(float(c) for _, _, c, _ in shop_days)
    messages = sorted(n for *_, n in shop_days)
    median_cost, median_msgs = costs[len(costs) // 2], messages[len(messages) // 2]
    print(f"\nActive merchant-days: {len(shop_days)}")
    print(f"Median merchant-day: {median_msgs} model calls, ${median_cost:.4f}")
    print(f"30 active days: ${median_cost * 30:.2f} ≈ {median_cost * 30 * USD_TO_FCFA:,.0f} FCFA".replace(",", " "))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=30)
    asyncio.run(main(parser.parse_args().days))
