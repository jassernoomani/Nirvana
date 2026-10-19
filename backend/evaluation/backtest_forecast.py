"""Rolling backtest of the demand forecast (app/ai/forecast.py) on seeded order histories.

Run from backend (no Ollama needed, the forecast does not use the LLM):

    .venv/Scripts/python.exe evaluation/backtest_forecast.py
    .venv/Scripts/python.exe evaluation/backtest_forecast.py --seeds 2026 1 2 --weeks 4

For each seed, a fresh temporary database is filled by seed_data.build (90 days, as in the
demo). Then, for each of the last N weeks, every method is trained only on the hours before
that week and predicts the whole week, as the app does for the week after today:

  random_forest    the app's RandomForestRegressor (forecast.RF_PARAMS, forecast.features)
  weekly_baseline  mean of the same hour 1, 2 and 3 weeks earlier (forecast.seasonal)
  last_week        the same hour one week earlier
  app_policy       what the app publishes: the forest or the baseline, whichever had the
                   lower error on the week before (a single 7-day holdout)
  oracle           the generator's true expected rate; not a method, it shows the error left
                   by chance alone (Poisson noise) that no model can remove

Results are printed and saved to evaluation/results/forecast-backtest.json.
"""
import argparse
import json
import statistics
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from sklearn.ensemble import RandomForestRegressor  # noqa: E402

import seed_data  # noqa: E402
from app import database  # noqa: E402
from app.ai.forecast import RF_PARAMS, features, hourly_history, seasonal  # noqa: E402

RESULTS = Path(__file__).with_name("results")
NOW = datetime(2026, 10, 19, 12, 0)  # fixed, so every run sees the same history
HISTORY_DAYS = 90
METHODS = ["random_forest", "weekly_baseline", "last_week", "app_policy", "oracle"]


def seeded_history(seed):
    """A new database filled by the demo seed, read back exactly as the app reads it."""
    folder = tempfile.TemporaryDirectory()
    database.DATABASE_PATH = Path(folder.name) / "backtest.db"
    database.initialize_database()
    today = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    with database.get_connection() as connection:
        seed_data.build(connection, days=HISTORY_DAYS, rng_seed=seed, now=NOW)
        _, hours, observed = hourly_history(connection, today)
    folder.cleanup()
    return today, hours, observed


def expected_rate(at, today):
    """The generator's mean: hourly rate x weekday factor x trend, minus the 2% cancelled."""
    day_index = (at.replace(hour=0) - (today - timedelta(days=HISTORY_DAYS))).days
    trend = 0.9 + 0.2 * day_index / HISTORY_DAYS
    return seed_data.HOURLY_RATE.get(at.hour, 0) * seed_data.WEEKDAY_FACTOR[at.weekday()] * trend * 0.98


def forest_predictions(training, target, observed, cutoff, params):
    """Train on the hours before cutoff and predict target, seeing only values before cutoff."""
    visible = {at: value for at, value in observed.items() if at < cutoff}
    train = [at for at in training if at < cutoff]
    model = RandomForestRegressor(**params)
    model.fit([features(at, visible) for at in train], [visible[at] for at in train])
    return [max(0.0, float(value)) for value in model.predict([features(at, visible) for at in target])], visible


def mae(predicted, actual):
    return statistics.mean(abs(p - a) for p, a in zip(predicted, actual))


def week_scores(predicted, actual, target):
    """Hourly error, daily-total error, total bias and peak-hour hits for one predicted week."""
    days = [(predicted[i:i + 24], actual[i:i + 24], target[i]) for i in range(0, len(target), 24)]
    daily_errors = [abs(sum(p) - sum(a)) for p, a, _ in days]
    peak_hits = [abs(max(range(24), key=p.__getitem__) - max(range(24), key=a.__getitem__)) <= 1 for p, a, _ in days]
    return {"hourly_mae": round(mae(predicted, actual), 3),
            "daily_mae": round(statistics.mean(daily_errors), 2),
            "daily_mape": round(statistics.mean(e / sum(a) for e, (_, a, _) in zip(daily_errors, days)), 4),
            "week_bias": round((sum(predicted) - sum(actual)) / sum(actual), 4),
            "peak_hour_within_1h": round(sum(peak_hits) / len(peak_hits), 3)}


def backtest(seed, weeks, params):
    today, hours, observed = seeded_history(seed)
    training = hours[504:]  # the first three weeks only provide lag values, as in the app
    folds = []
    for week in range(weeks, 0, -1):
        cutoff = today - timedelta(days=7 * week)
        target = [cutoff + timedelta(hours=i) for i in range(7 * 24)]
        actual = [observed[at] for at in target]
        forest, visible = forest_predictions(training, target, observed, cutoff, params)
        predictions = {"random_forest": forest,
                       "weekly_baseline": [seasonal(at, visible) for at in target],
                       "last_week": [visible.get(at - timedelta(hours=168), 0) for at in target],
                       "oracle": [expected_rate(at, today) for at in target]}
        # The app's choice: both candidates scored on the week before the cutoff.
        holdout = [cutoff - timedelta(days=7) + timedelta(hours=i) for i in range(7 * 24)]
        held_forest, held_visible = forest_predictions(training, holdout, observed, holdout[0], params)
        held_actual = [observed[at] for at in holdout]
        chose_forest = mae(held_forest, held_actual) <= mae([seasonal(at, held_visible) for at in holdout], held_actual)
        predictions["app_policy"] = forest if chose_forest else predictions["weekly_baseline"]
        scores = {method: week_scores(predictions[method], actual, target) for method in METHODS}
        better_forest = scores["random_forest"]["hourly_mae"] <= scores["weekly_baseline"]["hourly_mae"]
        folds.append({"seed": seed, "week_from": cutoff.date().isoformat(),
                      "training_days": len([at for at in training if at < cutoff]) // 24,
                      "actual_orders": sum(actual), "app_chose": "random_forest" if chose_forest else "weekly_baseline",
                      "app_choice_was_better": chose_forest == better_forest, "scores": scores})
    return folds


def average(folds, method, metric):
    return round(statistics.mean(fold["scores"][method][metric] for fold in folds), 4)


def main():
    parser = argparse.ArgumentParser(description="Rolling backtest of the demand forecast.")
    parser.add_argument("--seeds", type=int, nargs="+", default=[2026, 1, 2, 3, 4], help="seed_data random seeds")
    parser.add_argument("--weeks", type=int, default=6, help="number of most recent weeks to predict, one at a time")
    parser.add_argument("--label", default="forecast-backtest", help="name of the results file")
    args = parser.parse_args()

    folds = []
    for seed in args.seeds:
        seed_folds = backtest(seed, args.weeks, RF_PARAMS)
        folds += seed_folds
        print(f"seed {seed:>4}: " + "  ".join(f"{f['week_from']} RF {f['scores']['random_forest']['hourly_mae']:.3f} "
                                               f"base {f['scores']['weekly_baseline']['hourly_mae']:.3f}" for f in seed_folds))

    metrics = ["hourly_mae", "daily_mae", "daily_mape", "week_bias", "peak_hour_within_1h"]
    summary = {method: {metric: average(folds, method, metric) for metric in metrics} for method in METHODS}
    forest_wins = sum(f["scores"]["random_forest"]["hourly_mae"] <= f["scores"]["weekly_baseline"]["hourly_mae"] for f in folds)
    result = {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "history_days": HISTORY_DAYS, "seeds": args.seeds,
              "weeks": args.weeks, "rf_params": RF_PARAMS, "summary": summary,
              "forest_beats_baseline": f"{forest_wins}/{len(folds)}",
              "app_choice_was_better": f"{sum(f['app_choice_was_better'] for f in folds)}/{len(folds)}",
              "app_chose_forest": f"{sum(f['app_chose'] == 'random_forest' for f in folds)}/{len(folds)}",
              "folds": folds}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{args.label}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"\n{len(folds)} predicted weeks ({len(args.seeds)} seeds x {args.weeks} weeks), averages:")
    print(f"{'method':16} {'hourly MAE':>10} {'daily MAE':>10} {'daily MAPE':>10} {'week bias':>10} {'peak +-1h':>10}")
    for method in METHODS:
        s = summary[method]
        print(f"{method:16} {s['hourly_mae']:>10.3f} {s['daily_mae']:>10.2f} {s['daily_mape']:>10.1%} {s['week_bias']:>+10.1%} {s['peak_hour_within_1h']:>10.0%}")
    print(f"Forest beats the baseline in {result['forest_beats_baseline']} weeks; the app chose the forest in "
          f"{result['app_chose_forest']}; its choice was the better one in {result['app_choice_was_better']}.")
    print(f"Saved evaluation/results/{args.label}.json")


if __name__ == "__main__":
    main()
