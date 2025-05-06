# api_config.py

import os
import json
import pandas as pd
from pathlib import Path

CACHE_DIR = "cache"
Path(CACHE_DIR).mkdir(exist_ok=True)

def carregar_json_cache(nome_arquivo):
    caminho = os.path.join(CACHE_DIR, nome_arquivo)
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)

def carregar_todos_os_players_cache():
    players = []
    for nome_arquivo in os.listdir(CACHE_DIR):
        if nome_arquivo.startswith("player-") and nome_arquivo.endswith(".json"):
            caminho = os.path.join(CACHE_DIR, nome_arquivo)
            with open(caminho, "r", encoding="utf-8") as f:
                try:
                    player_data = json.load(f)
                    players.append(player_data.get("data", {}))  # <- Aqui já pegamos direto "data"
                except Exception as e:
                    print(f"[ERRO] Falha ao carregar {nome_arquivo}: {e}")
    return players

def integrate_data():
    market_raw = carregar_json_cache("market.json")
    season_raw = carregar_json_cache("season.json")

    market = market_raw.get("data", {})
    season = season_raw.get("data", {})

    round_players = market.get("roundPlayers", [])
    teams_data = market.get("teams", [])
    stats_data = season.get("players", [])

    print(">> market_raw keys:", market_raw.keys())
    print(">> market_data keys:", market.keys())
    print(">> Tamanho de roundPlayers:", len(round_players))

    players_detalhes = carregar_todos_os_players_cache()
    print(">> Total de players_detalhes:", len(players_detalhes))
    for i, p in enumerate(players_detalhes[:3]):
        print(f"Detalhe {i}: keys ->", p.keys())

    stats_map = {p["proPlayerId"]: p for p in stats_data if p.get("proPlayerId")}
    detalhes_map = {p.get("player", {}).get("id"): p for p in players_detalhes if p.get("player", {}).get("id")}

    rows = []
    for jogador in round_players:
        pro_id = jogador.get("proPlayerId")
        estat = stats_map.get(pro_id, {})
        detalhes = detalhes_map.get(pro_id)

        if not detalhes:
            print(f"[AVISO] Sem detalhes para jogador {pro_id}")
            continue

        player_info = detalhes.get("player", {})
        recent_matches = detalhes.get("recentMatches", [])
        upcoming_matches = detalhes.get("upcomingMatches", [])
        games = detalhes.get("games", [])

        team_id = jogador.get("teamId")
        team_name = next((t["name"] for t in teams_data if t.get("id") == team_id), "Desconhecido")

        region = "Sul" if any(r in team_name for r in ["FURIA", "Isurus", "Fluxo", "paiN", "LOUD", "Vivo", "Leviatán", "RED"]) else "Norte"

        row = {
            "proPlayerId": pro_id,
            "playerName": jogador.get("summonerName") or player_info.get("name", "Desconhecido"),
            "teamName": team_name,
            "price": jogador.get("price", 0),
            "role": jogador.get("role", ""),
            "teamId": team_id,
            "teamOdd": None,
            "region": region,
            "averageRoundScore": estat.get("averageRoundScore", 0),
            "maxRoundScore": estat.get("maxRoundScore", 0),
            "minRoundScore": estat.get("minRoundScore", 0),
            "lastRoundScore": estat.get("lastRoundScore", 0),
            "lastRoundPrice": estat.get("lastRoundPrice", 0),
            "recentMatches": recent_matches,
            "upcomingMatches": upcoming_matches,
            "games": games,
        }

        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        print("[ERRO] DataFrame final está vazio! Verifique os dados de entrada.")
    else:
        print("[DEBUG] Colunas do DataFrame final:", df.columns.tolist())

    return df, market
