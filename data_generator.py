import argparse
import copy
import io
import json
import os
import random
from contextlib import redirect_stdout
from datetime import timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


DEFAULT_CONFIG_PATH = "generator_config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "random_seed": 42,
    "output": {
        "dir": "data",
        "encoding": "utf-8-sig",
    },
    "observation": {
        "start": "2025-10-01",
        "end": "2026-01-31",
        "user_registration_end": "2025-12-31",
    },
    "population": {
        "n_users": 2500,
    },
    "dimensions": {
        "personas": ["whale", "engaged_nonpayer", "casual", "at_risk"],
        "countries": ["SG", "MY", "ID", "PH"],
        "devices": ["ios", "android"],
        "channels": ["organic", "ads", "referral", "influencer"],
        "event_types": ["login", "play", "mission_complete", "level_up", "quit"],
        "product_types": ["starter_bundle", "battle_pass", "gem_pack", "vip_bundle"],
    },
    "sampling_probs": {
        "personas": {
            "whale": 0.08,
            "engaged_nonpayer": 0.27,
            "casual": 0.45,
            "at_risk": 0.20,
        },
        "countries": {
            "SG": 0.45,
            "MY": 0.20,
            "ID": 0.20,
            "PH": 0.15,
        },
        "devices": {
            "ios": 0.40,
            "android": 0.60,
        },
        "channels": {
            "organic": 0.35,
            "ads": 0.40,
            "referral": 0.15,
            "influencer": 0.10,
        },
    },
    "labels": {
        "personas": {
            "whale": "高价值付费用户",
            "engaged_nonpayer": "高活跃非付费用户",
            "casual": "休闲用户",
            "at_risk": "流失风险用户",
        },
        "countries": {
            "SG": "新加坡",
            "MY": "马来西亚",
            "ID": "印度尼西亚",
            "PH": "菲律宾",
        },
        "channels": {
            "organic": "自然流量",
            "ads": "广告投放",
            "referral": "推荐裂变",
            "influencer": "达人推广",
        },
    },
    "channel_effects": {
        "organic": {"activity_mult": 1.00, "payment_mult": 1.00, "retention_mult": 1.05},
        "ads": {"activity_mult": 0.92, "payment_mult": 0.85, "retention_mult": 0.85},
        "referral": {"activity_mult": 1.08, "payment_mult": 1.12, "retention_mult": 1.12},
        "influencer": {"activity_mult": 1.12, "payment_mult": 0.95, "retention_mult": 0.90},
    },
    "country_effects": {
        "SG": {"activity_mult": 1.00, "payment_prob_mult": 1.15, "payment_amt_mult": 1.30, "session_mult": 1.10},
        "MY": {"activity_mult": 0.98, "payment_prob_mult": 1.00, "payment_amt_mult": 1.00, "session_mult": 1.00},
        "ID": {"activity_mult": 1.03, "payment_prob_mult": 0.88, "payment_amt_mult": 0.80, "session_mult": 0.95},
        "PH": {"activity_mult": 1.01, "payment_prob_mult": 0.90, "payment_amt_mult": 0.82, "session_mult": 0.96},
    },
    "behavior_rules": {
        "activity_prob_min": 0.01,
        "activity_prob_max": 0.98,
        "new_user_boost_days": 7,
        "new_user_activity_mult": 1.15,
        "session_stddev": 8.0,
        "at_risk_decay_min": 0.10,
    },
    "payment_rules": {
        "payment_prob_min": 0.0,
        "payment_prob_max": 0.99,
        "event_lookback_count": 10,
        "fallback_payment_days_after_reg": 14,
        "event_boost_payment_threshold": 1.20,
        "event_boost_avg_payments_mult": 1.15,
        "promo_amount_boost_probability": 0.35,
        "promo_amount_boost_mult": 1.10,
        "whale_amount_bonus_probability": 0.25,
        "whale_amount_bonus_choices": [1.5, 2.0],
    },
    "persona_params": {
        "whale": {
            "day_active_prob": 0.75,
            "avg_events_per_active_day": 5.0,
            "session_mean": 42.0,
            "pay_prob_base": 0.35,
            "avg_payments": 4.0,
            "payment_activity_divisor": 300,
            "payment_prob_cap": 0.95,
            "amount_scale": [12, 25, 60, 120],
            "event_type_probs": {"login": 0.20, "play": 0.45, "mission_complete": 0.18, "level_up": 0.12, "quit": 0.05},
        },
        "engaged_nonpayer": {
            "day_active_prob": 0.65,
            "avg_events_per_active_day": 4.0,
            "session_mean": 35.0,
            "pay_prob_base": 0.03,
            "avg_payments": 1.0,
            "payment_activity_divisor": 1000,
            "payment_prob_cap": 0.25,
            "amount_scale": [3, 5, 8, 15],
            "event_type_probs": {"login": 0.22, "play": 0.48, "mission_complete": 0.18, "level_up": 0.08, "quit": 0.04},
        },
        "casual": {
            "day_active_prob": 0.32,
            "avg_events_per_active_day": 2.0,
            "session_mean": 18.0,
            "pay_prob_base": 0.05,
            "avg_payments": 1.0,
            "payment_activity_divisor": 1200,
            "payment_prob_cap": 0.30,
            "amount_scale": [3, 6, 12, 20],
            "event_type_probs": {"login": 0.30, "play": 0.40, "mission_complete": 0.12, "level_up": 0.08, "quit": 0.10},
        },
        "at_risk": {
            "day_active_prob": 0.50,
            "avg_events_per_active_day": 3.0,
            "session_mean": 20.0,
            "pay_prob_base": 0.02,
            "avg_payments": 1.0,
            "payment_activity_divisor": 1500,
            "payment_prob_cap": 0.12,
            "amount_scale": [2, 4, 6, 10],
            "event_type_probs": {"login": 0.32, "play": 0.38, "mission_complete": 0.12, "level_up": 0.06, "quit": 0.12},
        },
    },
    "product_type_rules": [
        {"max_amount": 6, "probs": {"starter_bundle": 0.55, "battle_pass": 0.10, "gem_pack": 0.30, "vip_bundle": 0.05}},
        {"max_amount": 20, "probs": {"starter_bundle": 0.25, "battle_pass": 0.35, "gem_pack": 0.30, "vip_bundle": 0.10}},
        {"max_amount": None, "probs": {"starter_bundle": 0.10, "battle_pass": 0.20, "gem_pack": 0.30, "vip_bundle": 0.40}},
    ],
    "special_events": [
        {"name": "festival_event", "start": "2026-01-10", "end": "2026-01-14", "activity_mult": 1.15, "payment_mult": 1.10, "session_mult": 1.08, "quit_mult": 0.90, "target_personas": None, "target_channels": None, "target_countries": None},
        {"name": "starter_bundle_campaign", "start": "2026-01-15", "end": "2026-01-20", "activity_mult": 1.05, "payment_mult": 1.80, "session_mult": 1.00, "quit_mult": 1.00, "target_personas": ["engaged_nonpayer"], "target_channels": None, "target_countries": None},
        {"name": "server_incident", "start": "2026-01-22", "end": "2026-01-22", "activity_mult": 0.55, "payment_mult": 0.70, "session_mult": 0.80, "quit_mult": 1.35, "target_personas": None, "target_channels": None, "target_countries": None},
        {"name": "reactivation_campaign", "start": "2026-01-24", "end": "2026-01-28", "activity_mult": 1.25, "payment_mult": 1.05, "session_mult": 1.00, "quit_mult": 0.95, "target_personas": ["at_risk"], "target_channels": None, "target_countries": None},
    ],
    "campaigns": [
        {"campaign_id": "C001", "start_date": "2026-01-05", "end_date": "2026-01-12", "target_segment": "new_user", "reward": "starter_mission_pack"},
        {"campaign_id": "C002", "start_date": "2026-01-15", "end_date": "2026-01-20", "target_segment": "active_nonpayer", "reward": "first_purchase_bundle"},
        {"campaign_id": "C003", "start_date": "2026-01-22", "end_date": "2026-01-22", "target_segment": "all_users", "reward": "incident_compensation_pack"},
        {"campaign_id": "C004", "start_date": "2026-01-24", "end_date": "2026-01-28", "target_segment": "churn_risk", "reward": "return_login_bonus"},
        {"campaign_id": "C005", "start_date": "2026-01-20", "end_date": "2026-01-27", "target_segment": "high_value", "reward": "vip_exclusive_bundle"},
    ],
}


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def set_random_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def weighted_choice(items: List[str], probs: List[float]) -> str:
    return str(np.random.choice(items, p=probs))


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))


def random_date(start: pd.Timestamp, end: pd.Timestamp) -> pd.Timestamp:
    delta = end - start
    seconds = random.randint(0, int(delta.total_seconds()))
    return start + pd.Timedelta(seconds=seconds)


def localize_series(series: pd.Series, mapping: Dict[str, str]) -> pd.Series:
    return series.rename(index=mapping)


def ordered_prob_values(keys: List[str], prob_map: Dict[str, float], section_name: str) -> List[float]:
    missing = [key for key in keys if key not in prob_map]
    if missing:
        raise ValueError(f"{section_name} 缺少以下键的概率配置: {missing}")
    return [float(prob_map[key]) for key in keys]


def load_config(config_path: str) -> Dict[str, Any]:
    config = copy.deepcopy(DEFAULT_CONFIG)
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        config = deep_merge(config, user_config)
    return config


def save_default_config(config_path: str) -> None:
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)


def event_applies(
    event_cfg: Dict[str, Any],
    current_day: pd.Timestamp,
    persona: str,
    channel: str,
    country: str,
) -> bool:
    start = pd.to_datetime(event_cfg["start"])
    end = pd.to_datetime(event_cfg["end"])

    if not (start <= current_day <= end):
        return False
    if event_cfg.get("target_personas") is not None and persona not in event_cfg["target_personas"]:
        return False
    if event_cfg.get("target_channels") is not None and channel not in event_cfg["target_channels"]:
        return False
    if event_cfg.get("target_countries") is not None and country not in event_cfg["target_countries"]:
        return False
    return True


def get_active_event_effects(
    config: Dict[str, Any],
    current_day: pd.Timestamp,
    persona: str,
    channel: str,
    country: str,
) -> Dict[str, Any]:
    effects = {
        "activity_mult": 1.0,
        "payment_mult": 1.0,
        "session_mult": 1.0,
        "quit_mult": 1.0,
        "active_events": [],
    }
    for event_cfg in config["special_events"]:
        if event_applies(event_cfg, current_day, persona, channel, country):
            effects["activity_mult"] *= event_cfg["activity_mult"]
            effects["payment_mult"] *= event_cfg["payment_mult"]
            effects["session_mult"] *= event_cfg["session_mult"]
            effects["quit_mult"] *= event_cfg["quit_mult"]
            effects["active_events"].append(event_cfg["name"])
    return effects


def get_persona_params(config: Dict[str, Any], persona: str) -> Dict[str, Any]:
    return config["persona_params"][persona]


def get_event_type_probs(config: Dict[str, Any], persona: str, quit_mult: float) -> List[float]:
    event_types = config["dimensions"]["event_types"]
    probs = np.array(
        ordered_prob_values(
            event_types,
            get_persona_params(config, persona)["event_type_probs"],
            f"persona_params.{persona}.event_type_probs",
        ),
        dtype=float,
    )
    quit_idx = event_types.index("quit")
    probs[quit_idx] *= quit_mult
    probs = probs / probs.sum()
    return probs.tolist()


def choose_product_type(config: Dict[str, Any], amount: float) -> str:
    product_types = config["dimensions"]["product_types"]
    for rule in config["product_type_rules"]:
        max_amount = rule["max_amount"]
        if max_amount is None or amount <= float(max_amount):
            probs = ordered_prob_values(product_types, rule["probs"], "product_type_rules.probs")
            return weighted_choice(product_types, probs)
    raise ValueError("product_type_rules 配置无效，未匹配到任何金额区间。")


def generate_users(config: Dict[str, Any]) -> pd.DataFrame:
    obs_cfg = config["observation"]
    dims = config["dimensions"]
    probs = config["sampling_probs"]
    n_users = int(config["population"]["n_users"])

    start = pd.to_datetime(obs_cfg["start"])
    end = pd.to_datetime(obs_cfg["user_registration_end"])

    persona_probs = ordered_prob_values(dims["personas"], probs["personas"], "sampling_probs.personas")
    country_probs = ordered_prob_values(dims["countries"], probs["countries"], "sampling_probs.countries")
    device_probs = ordered_prob_values(dims["devices"], probs["devices"], "sampling_probs.devices")
    channel_probs = ordered_prob_values(dims["channels"], probs["channels"], "sampling_probs.channels")

    rows = []
    for i in range(1, n_users + 1):
        rows.append(
            {
                "user_id": f"U{i:05d}",
                "register_date": random_date(start, end),
                "country": weighted_choice(dims["countries"], country_probs),
                "device": weighted_choice(dims["devices"], device_probs),
                "channel": weighted_choice(dims["channels"], channel_probs),
                "persona": weighted_choice(dims["personas"], persona_probs),
            }
        )
    return pd.DataFrame(rows).sort_values("user_id").reset_index(drop=True)


def generate_events(config: Dict[str, Any], users_df: pd.DataFrame) -> pd.DataFrame:
    obs_end_dt = pd.to_datetime(config["observation"]["end"])
    behavior_rules = config["behavior_rules"]
    dims = config["dimensions"]
    rows = []

    for _, user in users_df.iterrows():
        user_id = user["user_id"]
        reg_date = pd.to_datetime(user["register_date"])
        persona = user["persona"]
        channel = user["channel"]
        country = user["country"]

        base = get_persona_params(config, persona)
        channel_fx = config["channel_effects"][channel]
        country_fx = config["country_effects"][country]
        active_days = max((obs_end_dt - reg_date).days, 1)

        for d in range(active_days + 1):
            current_day = reg_date + timedelta(days=d)
            if current_day > obs_end_dt:
                break

            event_fx = get_active_event_effects(config, current_day, persona, channel, country)
            activity_prob = base["day_active_prob"]
            activity_prob *= channel_fx["activity_mult"]
            activity_prob *= channel_fx["retention_mult"]
            activity_prob *= country_fx["activity_mult"]
            activity_prob *= event_fx["activity_mult"]

            if persona == "at_risk":
                decay_factor = max(behavior_rules["at_risk_decay_min"], 1.0 - d / max(active_days, 1))
                activity_prob *= decay_factor

            if d <= int(behavior_rules["new_user_boost_days"]):
                activity_prob *= behavior_rules["new_user_activity_mult"]

            activity_prob = clamp(
                activity_prob,
                behavior_rules["activity_prob_min"],
                behavior_rules["activity_prob_max"],
            )

            if random.random() < activity_prob:
                lam = base["avg_events_per_active_day"] * event_fx["activity_mult"]
                n_events = max(1, int(np.random.poisson(lam)))
                event_probs = get_event_type_probs(config, persona, event_fx["quit_mult"])
                session_mean = base["session_mean"] * country_fx["session_mult"] * event_fx["session_mult"]

                for _ in range(n_events):
                    event_time = current_day + timedelta(
                        hours=random.randint(0, 23),
                        minutes=random.randint(0, 59),
                        seconds=random.randint(0, 59),
                    )
                    rows.append(
                        {
                            "user_id": user_id,
                            "event_time": pd.to_datetime(event_time),
                            "event_type": weighted_choice(dims["event_types"], event_probs),
                            "session_length": max(1, int(np.random.normal(session_mean, behavior_rules["session_stddev"]))),
                        }
                    )

    events_df = pd.DataFrame(rows)
    if events_df.empty:
        return pd.DataFrame(columns=["user_id", "event_time", "event_type", "session_length"])
    return events_df.sort_values(["user_id", "event_time"]).reset_index(drop=True)


def generate_payments(config: Dict[str, Any], users_df: pd.DataFrame, events_df: pd.DataFrame) -> pd.DataFrame:
    if events_df.empty:
        return pd.DataFrame(columns=["user_id", "payment_time", "amount", "product_type"])

    payment_rules = config["payment_rules"]
    event_summary = (
        events_df.groupby("user_id")
        .agg(activity_count=("event_type", "count"), last_event_time=("event_time", "max"))
        .reset_index()
    )
    merged = users_df.merge(event_summary, on="user_id", how="left")
    merged["activity_count"] = merged["activity_count"].fillna(0)

    rows = []
    for _, user in merged.iterrows():
        user_id = user["user_id"]
        persona = user["persona"]
        channel = user["channel"]
        country = user["country"]
        reg_date = pd.to_datetime(user["register_date"])
        activity_count = int(user["activity_count"])

        base = get_persona_params(config, persona)
        channel_fx = config["channel_effects"][channel]
        country_fx = config["country_effects"][country]

        pay_prob = min(base["payment_prob_cap"], base["pay_prob_base"] + activity_count / base["payment_activity_divisor"])
        pay_prob *= channel_fx["payment_mult"]
        pay_prob *= country_fx["payment_prob_mult"]

        user_events = events_df.loc[events_df["user_id"] == user_id, "event_time"].sort_values()
        event_payment_boost = 1.0
        if not user_events.empty:
            for event_time in user_events.tail(min(int(payment_rules["event_lookback_count"]), len(user_events))):
                day = pd.to_datetime(event_time).normalize()
                fx = get_active_event_effects(config, day, persona, channel, country)
                event_payment_boost = max(event_payment_boost, fx["payment_mult"])

        pay_prob *= event_payment_boost
        pay_prob = clamp(pay_prob, payment_rules["payment_prob_min"], payment_rules["payment_prob_max"])

        if random.random() < pay_prob:
            avg_payments = base["avg_payments"]
            if event_payment_boost > payment_rules["event_boost_payment_threshold"]:
                avg_payments *= payment_rules["event_boost_avg_payments_mult"]

            n_payments = max(1, int(np.random.poisson(avg_payments)))
            for _ in range(n_payments):
                if not user_events.empty:
                    payment_time = user_events.sample(1, random_state=random.randint(1, 10_000_000)).iloc[0]
                    pay_day = pd.to_datetime(payment_time).normalize()
                    pay_event_fx = get_active_event_effects(config, pay_day, persona, channel, country)
                else:
                    payment_time = reg_date + timedelta(days=random.randint(0, int(payment_rules["fallback_payment_days_after_reg"])))
                    pay_event_fx = {"payment_mult": 1.0, "activity_mult": 1.0, "session_mult": 1.0, "quit_mult": 1.0, "active_events": []}

                amount = float(np.random.choice(base["amount_scale"]))
                if persona == "whale" and random.random() < payment_rules["whale_amount_bonus_probability"]:
                    amount *= random.choice(payment_rules["whale_amount_bonus_choices"])
                amount *= country_fx["payment_amt_mult"]

                if pay_event_fx["payment_mult"] > payment_rules["event_boost_payment_threshold"] and random.random() < payment_rules["promo_amount_boost_probability"]:
                    amount *= payment_rules["promo_amount_boost_mult"]

                amount = round(amount, 2)
                rows.append(
                    {
                        "user_id": user_id,
                        "payment_time": pd.to_datetime(payment_time),
                        "amount": amount,
                        "product_type": choose_product_type(config, amount),
                    }
                )

    payments_df = pd.DataFrame(rows)
    if payments_df.empty:
        return pd.DataFrame(columns=["user_id", "payment_time", "amount", "product_type"])
    return payments_df.sort_values(["user_id", "payment_time"]).reset_index(drop=True)


def generate_campaigns(config: Dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(config["campaigns"])


def generate_event_calendar(config: Dict[str, Any]) -> pd.DataFrame:
    rows = []
    for event_cfg in config["special_events"]:
        rows.append(
            {
                "event_name": event_cfg["name"],
                "start_date": event_cfg["start"],
                "end_date": event_cfg["end"],
                "activity_mult": event_cfg["activity_mult"],
                "payment_mult": event_cfg["payment_mult"],
                "session_mult": event_cfg["session_mult"],
                "quit_mult": event_cfg["quit_mult"],
                "target_personas": ",".join(event_cfg["target_personas"]) if event_cfg["target_personas"] else "all",
                "target_channels": ",".join(event_cfg["target_channels"]) if event_cfg["target_channels"] else "all",
                "target_countries": ",".join(event_cfg["target_countries"]) if event_cfg["target_countries"] else "all",
            }
        )
    return pd.DataFrame(rows)


def summarize_generated_data(config: Dict[str, Any], users_df: pd.DataFrame, events_df: pd.DataFrame, payments_df: pd.DataFrame) -> None:
    labels = config["labels"]

    print("\n=== 基础统计 ===")
    print(f"用户数: {len(users_df):,}")
    print(f"事件数: {len(events_df):,}")
    print(f"支付数: {len(payments_df):,}")

    print("\n=== 用户画像分布 ===")
    print(localize_series(users_df["persona"].value_counts(normalize=True).round(3), labels["personas"]))

    print("\n=== 国家分布 ===")
    print(localize_series(users_df["country"].value_counts(normalize=True).round(3), labels["countries"]))

    print("\n=== 渠道分布 ===")
    print(localize_series(users_df["channel"].value_counts(normalize=True).round(3), labels["channels"]))

    if not events_df.empty:
        daily_dau = (
            events_df.groupby(events_df["event_time"].dt.date)["user_id"]
            .nunique()
            .sort_index()
        )
        print("\n=== 最近 10 天 DAU 快照 ===")
        print(daily_dau.tail(10))
        quit_rate = (events_df["event_type"] == "quit").mean()
        print(f"\n退出事件占比: {quit_rate:.4f}")

    if not payments_df.empty:
        revenue_by_country = (
            payments_df.merge(
                users_df[["user_id", "country", "channel", "persona"]],
                on="user_id",
                how="left",
            )
            .groupby("country")["amount"]
            .mean()
            .round(2)
        )
        print("\n=== 各国家平均支付金额 ===")
        print(localize_series(revenue_by_country, labels["countries"]))

        top10_share = payments_df.groupby("user_id")["amount"].sum().sort_values(ascending=False)
        if len(top10_share) > 0:
            top_n = max(1, int(len(top10_share) * 0.10))
            pareto_share = top10_share.head(top_n).sum() / top10_share.sum()
            print(f"\nTop 10% 用户收入占比: {pareto_share:.3f}")


def save_dataframes(output_dir: str, encoding: str, dfs: Dict[str, pd.DataFrame]) -> None:
    ensure_dir(output_dir)
    for name, df in dfs.items():
        df.to_csv(os.path.join(output_dir, f"{name}.csv"), index=False, encoding=encoding)


def build_summary_text(
    config: Dict[str, Any],
    users_df: pd.DataFrame,
    events_df: pd.DataFrame,
    payments_df: pd.DataFrame,
) -> str:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        summarize_generated_data(config, users_df, events_df, payments_df)
    return buffer.getvalue().strip()


def save_run_summary(output_dir: str, summary_text: str) -> str:
    ensure_dir(output_dir)
    summary_path = os.path.join(output_dir, "run_summary.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_text)
        f.write("\n")
    return summary_path


def validate_probability_map(keys: List[str], prob_map: Dict[str, float], section_name: str) -> None:
    probs = ordered_prob_values(keys, prob_map, section_name)
    total = sum(probs)
    if not np.isclose(total, 1.0, atol=1e-6):
        raise ValueError(f"{section_name} 概率之和必须为 1，当前为 {total:.6f}")


def validate_config(config: Dict[str, Any]) -> None:
    obs_cfg = config["observation"]
    dims = config["dimensions"]
    probs = config["sampling_probs"]

    obs_start = pd.to_datetime(obs_cfg["start"])
    obs_end = pd.to_datetime(obs_cfg["end"])
    user_reg_end = pd.to_datetime(obs_cfg["user_registration_end"])

    if int(config["population"]["n_users"]) <= 0:
        raise ValueError("population.n_users 必须大于 0。")
    if obs_start > obs_end:
        raise ValueError("observation.start 不能晚于 observation.end。")
    if user_reg_end < obs_start:
        raise ValueError("observation.user_registration_end 不能早于 observation.start。")

    validate_probability_map(dims["personas"], probs["personas"], "sampling_probs.personas")
    validate_probability_map(dims["countries"], probs["countries"], "sampling_probs.countries")
    validate_probability_map(dims["devices"], probs["devices"], "sampling_probs.devices")
    validate_probability_map(dims["channels"], probs["channels"], "sampling_probs.channels")

    event_types = dims["event_types"]
    product_types = dims["product_types"]
    if "quit" not in event_types:
        raise ValueError("dimensions.event_types 必须包含 quit。")

    for persona in dims["personas"]:
        if persona not in config["persona_params"]:
            raise ValueError(f"persona_params 缺少画像配置: {persona}")
        persona_cfg = config["persona_params"][persona]
        validate_probability_map(event_types, persona_cfg["event_type_probs"], f"persona_params.{persona}.event_type_probs")
        if len(persona_cfg["amount_scale"]) == 0:
            raise ValueError(f"persona_params.{persona}.amount_scale 不能为空。")

    for channel in dims["channels"]:
        if channel not in config["channel_effects"]:
            raise ValueError(f"channel_effects 缺少渠道配置: {channel}")

    for country in dims["countries"]:
        if country not in config["country_effects"]:
            raise ValueError(f"country_effects 缺少国家配置: {country}")

    for rule in config["product_type_rules"]:
        validate_probability_map(product_types, rule["probs"], "product_type_rules.probs")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="基于配置文件生成游戏模拟数据。")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="配置文件路径，默认 generator_config.json。")
    parser.add_argument("--init-config", action="store_true", help="在当前路径生成默认配置文件并退出。")
    parser.add_argument("--seed", type=int, default=None, help="覆盖配置中的随机种子。")
    parser.add_argument("--output-dir", default=None, help="覆盖配置中的输出目录。")
    parser.add_argument("--obs-start", default=None, help="覆盖配置中的观察期开始日期。")
    parser.add_argument("--obs-end", default=None, help="覆盖配置中的观察期结束日期。")
    parser.add_argument("--user-reg-end", default=None, help="覆盖配置中的用户注册截止日期。")
    parser.add_argument("--n-users", type=int, default=None, help="覆盖配置中的用户数量。")
    return parser


def apply_cli_overrides(config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    updated = copy.deepcopy(config)
    if args.seed is not None:
        updated["random_seed"] = args.seed
    if args.output_dir is not None:
        updated["output"]["dir"] = args.output_dir
    if args.obs_start is not None:
        updated["observation"]["start"] = args.obs_start
    if args.obs_end is not None:
        updated["observation"]["end"] = args.obs_end
    if args.user_reg_end is not None:
        updated["observation"]["user_registration_end"] = args.user_reg_end
    if args.n_users is not None:
        updated["population"]["n_users"] = args.n_users
    return updated


def run_generation(config: Dict[str, Any]) -> None:
    set_random_seed(int(config["random_seed"]))

    users_df = generate_users(config)
    events_df = generate_events(config, users_df)
    payments_df = generate_payments(config, users_df, events_df)
    campaigns_df = generate_campaigns(config)
    event_calendar_df = generate_event_calendar(config)

    save_dataframes(
        output_dir=config["output"]["dir"],
        encoding=config["output"]["encoding"],
        dfs={
            "users": users_df,
            "events": events_df,
            "payments": payments_df,
            "campaigns": campaigns_df,
            "event_calendar": event_calendar_df,
        },
    )
    summary_text = build_summary_text(config, users_df, events_df, payments_df)
    print(summary_text)
    summary_path = save_run_summary(config["output"]["dir"], summary_text)
    print(f"\nCSV 文件已保存到: {config['output']['dir']}{os.sep}")
    print(f"运行摘要已保存到: {summary_path}")


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.init_config:
        save_default_config(args.config)
        print(f"默认配置文件已生成: {args.config}")
        return

    config = load_config(args.config)
    config = apply_cli_overrides(config, args)
    validate_config(config)
    run_generation(config)


if __name__ == "__main__":
    main()
