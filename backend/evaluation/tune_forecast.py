"""Hyperparameter and feature comparison for the demand forecast, with a time split.

Run from backend:

    .venv/Scripts/python.exe evaluation/tune_forecast.py

Same seeded histories and weekly folds as backtest_forecast.py (5 seeds x 6 weeks), split
in time so the choice is never made on the weeks it is judged on:

  tuning weeks    the 3 older weeks of each seed (15 weeks): every candidate is scored here
                  and the best setting of each model family is kept
  report weeks    the 3 most recent weeks of each seed (15 weeks): only those kept settings,
                  the app's current forest and the baselines are scored here

Families: the app's random forest (a small grid of tree settings, then extra features with
the best settings), gradient boosting with a Poisson loss, and a Poisson regression on
hour-of-day and day-of-week indicators with an optional linear trend.
Results are printed and saved to evaluation/results/forecast-tuning.json.
"""
import itertools
import json
import statistics
from datetime import datetime, timedelta

from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import PoissonRegressor

from backtest_forecast import RESULTS, expected_rate, mae, seeded_history, week_scores
from app.ai.forecast import RF_PARAMS, features, seasonal

SEEDS = [2026, 1, 2, 3, 4]
WEEKS = 6
TUNING_WEEKS = 3  # the older half


def app_features(at, values, start):
    return features(at, values)


def with_trend(at, values, start):
    return features(at, values) + [(at - start).days]


def with_lag_mean(at, values, start):
    return features(at, values) + [seasonal(at, values)]


def calendar(at, values, start, trend=True):
    """Indicators for the hour and the weekday: a multiplicative profile under a log link."""
    row = [0.0] * 31
    row[at.hour] = 1.0
    row[24 + at.weekday()] = 1.0
    return row + ([(at - start).days / 100] if trend else [])


def calendar_no_trend(at, values, start):
    return calendar(at, values, start, trend=False)


def candidate(name, family, make_model, featurize):
    return {"name": name, "family": family, "make": make_model, "featurize": featurize}


def candidates():
    found = []
    for trees, depth, leaf in itertools.product([80, 200], [5, 10, None], [3, 10, 30]):
        params = {**RF_PARAMS, "n_estimators": trees, "max_depth": depth, "min_samples_leaf": leaf}
        found.append({**candidate(f"forest trees={trees} depth={depth} leaf={leaf}", "random_forest",
                                  lambda p=params: RandomForestRegressor(**p), app_features), "params": params})
    for rate, leaves in itertools.product([0.05, 0.1], [7, 15]):
        found.append(candidate(f"boosting poisson lr={rate} leaves={leaves}", "gradient_boosting",
                               lambda r=rate, l=leaves: HistGradientBoostingRegressor(loss="poisson", learning_rate=r, max_leaf_nodes=l,
                                                                                       max_iter=200, min_samples_leaf=20, random_state=42),
                               app_features))
    for alpha, featurize in itertools.product([1e-4, 1e-3, 1e-2], [calendar, calendar_no_trend]):
        found.append(candidate(f"poisson regression alpha={alpha} {'trend' if featurize is calendar else 'no trend'}",
                               "poisson_regression", lambda a=alpha: PoissonRegressor(alpha=a, max_iter=1000), featurize))
    return found


def forest_variants(params):
    """Extra features for the forest, with the tree settings that won the grid."""
    return [candidate(f"forest + {label}", "random_forest_features", lambda p=params: RandomForestRegressor(**p), featurize)
            for label, featurize in [("trend", with_trend), ("lag mean", with_lag_mean)]]


def predict(spec, fold):
    visible, start = fold["visible"], fold["start"]
    train = fold["train"]
    model = spec["make"]()
    model.fit([spec["featurize"](at, visible, start) for at in train], [visible[at] for at in train])
    return [max(0.0, float(v)) for v in model.predict([spec["featurize"](at, visible, start) for at in fold["target"]])]


def folds():
    """Every (seed, week) fold, with what may be seen before the predicted week."""
    found = []
    for seed in SEEDS:
        today, hours, observed = seeded_history(seed)
        for week in range(WEEKS, 0, -1):
            cutoff = today - timedelta(days=7 * week)
            target = [cutoff + timedelta(hours=i) for i in range(7 * 24)]
            visible = {at: value for at, value in observed.items() if at < cutoff}
            found.append({"seed": seed, "week_from": cutoff.date().isoformat(), "tuning": week > WEEKS - TUNING_WEEKS,
                          "start": hours[0], "train": [at for at in hours[504:] if at < cutoff], "target": target,
                          "visible": visible, "actual": [observed[at] for at in target], "today": today})
    return found


def score(spec, chosen_folds):
    return statistics.mean(mae(predict(spec, fold), fold["actual"]) for fold in chosen_folds)


def full_scores(predictions_by_fold, chosen_folds):
    weeks = [week_scores(predictions, fold["actual"], fold["target"]) for predictions, fold in zip(predictions_by_fold, chosen_folds)]
    return {metric: round(statistics.mean(w[metric] for w in weeks), 4) for metric in weeks[0]}


def main():
    all_folds = folds()
    tuning = [f for f in all_folds if f["tuning"]]
    report = [f for f in all_folds if not f["tuning"]]
    print(f"{len(tuning)} tuning weeks (from {min(f['week_from'] for f in tuning)}), "
          f"{len(report)} report weeks (from {min(f['week_from'] for f in report)})")

    tuning_results = []
    for spec in candidates():
        spec["tuning_mae"] = round(score(spec, tuning), 4)
        tuning_results.append(spec)
        print(f"  tuning MAE {spec['tuning_mae']:.4f}  {spec['name']}")
    best_forest = min((s for s in tuning_results if s["family"] == "random_forest"), key=lambda s: s["tuning_mae"])
    for spec in forest_variants(best_forest["params"]):
        spec["tuning_mae"] = round(score(spec, tuning), 4)
        tuning_results.append(spec)
        print(f"  tuning MAE {spec['tuning_mae']:.4f}  {spec['name']}")

    kept = {}
    for spec in tuning_results:
        if spec["family"] not in kept or spec["tuning_mae"] < kept[spec["family"]]["tuning_mae"]:
            kept[spec["family"]] = spec
    app_forest = next(s for s in tuning_results if s.get("params") == RF_PARAMS)

    rows = [("app forest (current settings)", app_forest["tuning_mae"], [predict(app_forest, f) for f in report])]
    rows += [(f"{spec['name']} [best {family}]", spec["tuning_mae"], [predict(spec, f) for f in report]) for family, spec in kept.items()]
    rows += [("weekly baseline", round(statistics.mean(mae([seasonal(at, f["visible"]) for at in f["target"]], f["actual"]) for f in tuning), 4),
              [[seasonal(at, f["visible"]) for at in f["target"]] for f in report]),
             ("oracle (true rate)", None, [[expected_rate(at, f["today"]) for at in f["target"]] for f in report])]
    reported = [{"name": name, "tuning_hourly_mae": tuning_mae, "report": full_scores(predictions, report)} for name, tuning_mae, predictions in rows]

    print(f"\nReport weeks ({len(report)}), settings chosen on the tuning weeks only:")
    print(f"{'candidate':58} {'tuning':>7} {'hourly MAE':>10} {'daily MAE':>9} {'MAPE':>6} {'bias':>7} {'peak':>5}")
    for row in reported:
        r = row["report"]
        tuned = f"{row['tuning_hourly_mae']:.3f}" if row["tuning_hourly_mae"] is not None else "-"
        print(f"{row['name'][:58]:58} {tuned:>7} {r['hourly_mae']:>10.3f} {r['daily_mae']:>9.2f} {r['daily_mape']:>6.1%} {r['week_bias']:>+7.1%} {r['peak_hour_within_1h']:>5.0%}")

    RESULTS.mkdir(exist_ok=True)
    result = {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "seeds": SEEDS, "weeks": WEEKS, "tuning_weeks_per_seed": TUNING_WEEKS,
              "tuning": [{"name": s["name"], "family": s["family"], "hourly_mae": s["tuning_mae"]} for s in sorted(tuning_results, key=lambda s: s["tuning_mae"])],
              "report": reported}
    (RESULTS / "forecast-tuning.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("Saved evaluation/results/forecast-tuning.json")


if __name__ == "__main__":
    main()
