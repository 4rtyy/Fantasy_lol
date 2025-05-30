import pandas as pd
import numpy as np
from itertools import product
from collections import defaultdict
from datetime import datetime


def calcular_estatisticas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    odd_map = df.groupby("teamName")["teamOdd"].first().to_dict()

    for col in [
        "media_vitoria", "media_derrota", "media_confronto",
        "std_vitoria", "std_derrota", "std_confronto",
        "n_confrontos", "win_prob", "base_exp",
        "weight_confronto", "expectedScore", "oponente"
    ]:
        df[col] = 0.0 if col != "oponente" else None

    for idx, row in df.iterrows():
        recent = row.get("recentMatches", []) or []
        games = row.get("games", []) or []
        upc = row.get("upcomingMatches", []) or []

        opponent = upc[0].get("opponentTeam", {}).get("name") if upc else None
        odd_t = row.get("teamOdd", 2.0)
        odd_a = odd_map.get(opponent)

        if odd_a and odd_t:
            inv_t = 1 / odd_t
            inv_a = 1 / odd_a
            total = inv_t + inv_a
            win_prob = inv_t / total
        else:
            win_prob = 1 / odd_t if odd_t else 0.5

        win_map = {g["matchId"]: g.get("win", False) for g in games if "matchId" in g}

        vit, der, conf = [], [], []
        for m in sorted(recent, key=lambda x: x.get("startsAt", ""), reverse=True):
            mid = m.get("matchId")
            if mid not in win_map:
                continue
            pts = m.get("score", 0)
            adv = m.get("opponentTeam", {}).get("name")
            i = len(recent) - recent.index(m)  # posição invertida
            decay = 0.9 ** (i - 1)  # mais recente, maior peso

            if win_map[mid]:
                vit.extend([pts] * int(decay * 10))  # simula peso
            else:
                der.extend([pts] * int(decay * 10))
            if opponent and adv == opponent:
                conf.append(pts)

        def safe_avg(arr):
            return sum(arr) / len(arr) if arr else 0.0

        def safe_std(arr):
            return float(np.std(arr)) if arr else 0.0

        media_v = safe_avg(vit)
        media_d = safe_avg(der)
        media_c = safe_avg(conf)

        std_v = safe_std(vit)
        std_d = safe_std(der)
        std_c = safe_std(conf)

        n_conf = len(conf)
        base_exp = win_prob * media_v + (1 - win_prob) * media_d

        df.at[idx, "media_vitoria"] = round(media_v, 2)
        df.at[idx, "media_derrota"] = round(media_d, 2)
        df.at[idx, "media_confronto"] = round(media_c, 2)

        df.at[idx, "std_vitoria"] = round(std_v, 2)
        df.at[idx, "std_derrota"] = round(std_d, 2)
        df.at[idx, "std_confronto"] = round(std_c, 2)

        df.at[idx, "n_confrontos"] = n_conf
        df.at[idx, "win_prob"] = round(win_prob, 3)
        df.at[idx, "base_exp"] = round(base_exp, 2)
        df.at[idx, "oponente"] = opponent

    avg_n_conf = df["n_confrontos"].mean()

    for idx, row in df.iterrows():
        n_conf = row["n_confrontos"]
        wp = row["win_prob"]
        base = row["base_exp"]
        media_c = row["media_confronto"]

        # Novo modelo de weight usando função logística suavizada
        ratio = n_conf / avg_n_conf if avg_n_conf > 0 else 0
        weight_conf = wp * (ratio / (1 + ratio))  # logistic-like

        expected = (1 - weight_conf) * base + weight_conf * media_c

        df.at[idx, "weight_confronto"] = round(weight_conf, 3)
        df.at[idx, "expectedScore"] = round(expected, 2)

    df["custo_beneficio"] = df.apply(
        lambda r: round(r["expectedScore"] / r["price"], 3) if r["price"] > 0 else 0.0,
        axis=1
    )

    df["teto_esperado"] = df["expectedScore"] + df["std_vitoria"]
    return df


def top_jogadores_por_posicao(df: pd.DataFrame,
                              criterio: str = "expectedScore",
                              top_n: int = 5) -> dict:
    resultado = {}
    for pos in ["top", "jungle", "mid", "bottom", "support"]:
        resultado[pos] = (
            df[df["role"] == pos]
              .nlargest(top_n, criterio)
              .to_dict("records")
        )
    return resultado


def montar_time_otimo(df: pd.DataFrame,
                      criterio: str,
                      orcamento: float) -> list:
    df = df.copy()
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0)

    por_pos = {}
    cheapest_by_pos = {}
    sum_cheapest = 0.0
    for pos in ["top", "jungle", "mid", "bottom", "support"]:
        subset = df[df["role"] == pos]
        if subset.empty:
            return []
        top5 = subset.nlargest(5, criterio)
        cheapest = subset.nsmallest(1, "price")
        combined = pd.concat([top5, cheapest]).drop_duplicates(subset=["playerName"])
        por_pos[pos] = combined.to_dict("records")
        cheapest_by_pos[pos] = cheapest.iloc[0]
        sum_cheapest += cheapest.iloc[0]["price"]

    validos = []
    for combo in product(*por_pos.values()):
        time_ = list(combo)
        custo = sum(j["price"] for j in time_)
        if custo <= orcamento:
            pts = sum(j[criterio] for j in time_)
            eff = pts / custo if custo else 0
            validos.append((time_, custo, pts, eff))

    if validos:
        validos.sort(key=lambda x: x[2], reverse=True)
        return validos[:5]

    if orcamento < sum_cheapest:
        return []

    time_cheapest = [cheapest_by_pos[pos].to_dict() for pos in ["top", "jungle", "mid", "bottom", "support"]]
    custo = sum(p["price"] for p in time_cheapest)
    pts = sum(p[criterio] for p in time_cheapest)
    eff = pts / custo if custo else 0
    return [(time_cheapest, custo, pts, eff)]


def montar_times(df: pd.DataFrame, orcamento: float) -> dict:
    return {
        "⭐ Maior Pontuação Esperada": montar_time_otimo(df, "expectedScore", orcamento),
        "🚀 Maior Teto de Pontuação": montar_time_otimo(df, "teto_esperado", orcamento)
    }