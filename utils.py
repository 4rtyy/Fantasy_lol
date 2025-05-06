# utils.py

import pandas as pd
import numpy as np
from itertools import product
from collections import defaultdict


def calcular_estatisticas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula para cada jogador:
      - media_vitoria / media_derrota (brutas)
      - media_confronto (bruta, só exibição)
      - win_prob (probabilidade justa de vitória, sem juice)
      - base_exp = win_prob*media_vitoria + (1-win_prob)*media_derrota
      - weight_confronto = win_prob * (n_confrontos / (n_confrontos + avg_n_conf))
      - expectedScore = blend entre base_exp e media_confronto
      - custo_beneficio = expectedScore / price
    smoothing do peso de confronto usa avg_n_conf calculado a partir do próprio dataset,
    tornando o balanceamento data-driven.
    """
    df = df.copy()

    # 1) Juice removal
    odd_map = df.groupby("teamName")["teamOdd"].first().to_dict()

    # 2) Inicializa colunas
    for col in [
        "media_vitoria","media_derrota","media_confronto",
        "n_confrontos","win_prob","base_exp",
        "weight_confronto","expectedScore","oponente"
    ]:
        df[col] = 0.0 if col != "oponente" else None

    # 3) Passagem 1: médias brutas + win_prob
    for idx, row in df.iterrows():
        recent = row.get("recentMatches", []) or []
        games  = row.get("games", []) or []
        upc    = row.get("upcomingMatches", []) or []

        opponent = upc[0].get("opponentTeam",{}).get("name") if upc else None
        odd_t    = row.get("teamOdd", 2.0)
        odd_a    = odd_map.get(opponent)

        # win_prob justa
        if odd_a:
            p_t = 1/odd_t; p_a = 1/odd_a
            win_prob = p_t/(p_t+p_a)
        else:
            win_prob = min(max(1/odd_t,0.0),1.0)

        # coleta scores
        win_map = {g["matchId"]:g.get("win",False) for g in games if "matchId" in g}
        vit, der, conf = [], [], []
        for m in recent:
            mid = m.get("matchId")
            if mid not in win_map: continue
            pts = m.get("score",0)
            adv = m.get("opponentTeam",{}).get("name")
            if win_map[mid]:
                vit.append(pts)
            else:
                der.append(pts)
            if opponent and adv==opponent:
                conf.append(pts)

        media_v = sum(vit)/len(vit) if vit else 0.0
        media_d = sum(der)/len(der) if der else 0.0
        media_c = sum(conf)/len(conf) if conf else 0.0
        n_conf  = len(conf)
        base_exp = win_prob*media_v + (1-win_prob)*media_d

        # grava brutos
        df.at[idx,"media_vitoria"]   = round(media_v,2)
        df.at[idx,"media_derrota"]   = round(media_d,2)
        df.at[idx,"media_confronto"] = round(media_c,2)
        df.at[idx,"n_confrontos"]    = n_conf
        df.at[idx,"win_prob"]        = round(win_prob,3)
        df.at[idx,"base_exp"]        = round(base_exp,2)
        df.at[idx,"oponente"]        = opponent

    # 4) Cálculo data-driven do peso de confronto
    avg_n_conf = df["n_confrontos"].mean()

    # 5) Passagem 2: expectedScore
    for idx, row in df.iterrows():
        n_conf   = row["n_confrontos"]
        wp       = row["win_prob"]
        base     = row["base_exp"]
        media_c  = row["media_confronto"]

        weight_conf = wp * (n_conf / (n_conf + avg_n_conf)) if (n_conf + avg_n_conf) > 0 else 0.0
        expected    = (1 - weight_conf) * base + weight_conf * media_c

        df.at[idx,"weight_confronto"] = round(weight_conf,3)
        df.at[idx,"expectedScore"]    = round(expected,2)

    # 6) custo-benefício
    df["custo_beneficio"] = df.apply(
        lambda r: round(r["expectedScore"] / r["price"],3) if r["price"]>0 else 0.0,
        axis=1
    )

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
    """
    Monta o time ótimo mesmo se o orçamento for muito baixo,
    desde que cubra o jogador mais barato de cada posição.
    """
    df = df.copy()
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0)

    # 1) Prepara candidatos: top5 por criterio + jogador mais barato
    por_pos = {}
    cheapest_by_pos = {}
    sum_cheapest = 0.0
    for pos in ["top", "jungle", "mid", "bottom", "support"]:
        subset = df[df["role"] == pos]
        if subset.empty:
            return []
        top5 = subset.nlargest(5, criterio)
        cheapest = subset.nsmallest(1, "price")
        # adiciona o mais barato se não estiver no top5
        combined = pd.concat([top5, cheapest]).drop_duplicates(subset=["playerName"])
        por_pos[pos] = combined.to_dict("records")
        cheapest_by_pos[pos] = cheapest.iloc[0]
        sum_cheapest += cheapest.iloc[0]["price"]

    # 2) Gera combinações sob orçamento
    validos = []
    for combo in product(*por_pos.values()):
        time_ = list(combo)
        custo = sum(j["price"] for j in time_)
        if custo <= orcamento:
            pts = sum(j[criterio] for j in time_)
            eff = pts / custo if custo else 0
            validos.append((time_, custo, pts, eff))

    # 3) Se houver combos viáveis, retorna top5
    if validos:
        validos.sort(key=lambda x: x[2], reverse=True)
        return validos[:5]

    # 4) Sem combos sob orçamento,
    #    se orçamento < soma dos mais baratos, não dá pra montar
    if orcamento < sum_cheapest:
        return []

    # 5) Se orçamento >= soma dos mais baratos, retorna o combo de mais baratos
    time_cheapest = [cheapest_by_pos[pos].to_dict() for pos in ["top","jungle","mid","bottom","support"]]
    custo = sum(p["price"] for p in time_cheapest)
    pts   = sum(p[criterio] for p in time_cheapest)
    eff   = pts / custo if custo else 0
    return [(time_cheapest, custo, pts, eff)]


def montar_times(df: pd.DataFrame, orcamento: float) -> dict:
    return {
        "⭐ Maior Pontuação Esperada": montar_time_otimo(df, "expectedScore", orcamento),
        "🚀 Maior Teto de Pontuação":  montar_time_otimo(df, "maxRoundScore", orcamento)
    }