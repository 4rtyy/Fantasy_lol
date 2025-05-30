import streamlit as st
import pandas as pd
import json
import os
import plotly.express as px
from api_config import integrate_data
from utils import calcular_estatisticas, montar_time_otimo
from sklearn.cluster import KMeans # type: ignore
from sklearn.preprocessing import StandardScaler # type: ignore
from sklearn.decomposition import PCA # type: ignore
from datetime import datetime

# Configuração da página
st.set_page_config(page_title="Cartola LoL", layout="wide")
st.title("📊 Cartola FC - League of Legends")

# Carrega dados e configurações
SETTINGS_FILE = "settings.json"
@st.cache_data(ttl=3600)
def carregar_dados():
    return integrate_data()

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_settings(orcamento, odds):
    settings = load_settings()
    historico = settings.get("historico", [])
    historico.append({
        "timestamp": datetime.now().isoformat(timespec='seconds'),
        "orcamento": orcamento,
        "odds": odds
    })
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "orcamento": orcamento,
            "odds": odds,
            "historico": historico
        }, f, indent=2)


# Inicialização dos dados
if "df" not in st.session_state:
    df_raw, _ = carregar_dados()
    if df_raw.empty:
        st.error("Nenhum dado disponível.")
        st.stop()
    settings = load_settings()
    st.session_state.orcamento = settings.get("orcamento", 25.0)
    for col, default in [("teamOdd", 2.0), ("region", "Outra"), ("teamName", "Desconhecido")]:
        df_raw[col] = df_raw.get(col, default)
    st.session_state.odds = settings.get("odds") or {team: 2.0 for team in df_raw["teamName"].unique()}
    st.session_state.regioes = {
        team: df_raw[df_raw["teamName"] == team]["region"].iloc[0]
        for team in df_raw["teamName"].unique()
    }
    df_raw["teamOdd"] = df_raw["teamName"].map(st.session_state.odds)
    st.session_state.df = calcular_estatisticas(df_raw)
    st.session_state.df["Chance de Vitória"] = st.session_state.df["win_prob"].apply(lambda x: f"{x * 100:.1f}%")

def validar_odd_digitada(valor_str, nome_time, default=2.0):
    try:
        val = float(valor_str.replace(",", "."))
        if val < 1.01:
            st.warning(f"⚠️ Odd mínima para **{nome_time}** é 1.01. Valor ajustado.")
            return 1.01
        return round(val, 2)
    except:
        st.warning(f"❌ Odd inválida para **{nome_time}**. Usando valor padrão ({default:.2f}).")
        return default

def validar_orcamento_digitado(valor_str, default=st.session_state.orcamento):
    try:
        val = float(valor_str.replace(",", "."))
        if val <= 0:
            st.warning("⚠️ O orçamento deve ser maior que zero. Usando valor padrão.")
            return default
        return round(val, 2)
    except:
        st.warning("❌ Orçamento inválido. Usando valor padrão.")
        return default


with st.sidebar:
    st.markdown("## ⚙️ Parâmetros")

    input_orc = st.text_input(
        "Orçamento (💰)", value=f"{st.session_state.orcamento:.2f}", key="orcamento_input"
    )
    novo_orc = validar_orcamento_digitado(input_orc)

    st.markdown("---")
    st.markdown("### 🤝 Ajuste de Odds por Confronto")

    novas_odds = {}
    df_local = st.session_state.df
    opp_map = df_local.groupby("teamName")["oponente"].first().to_dict()

    matchups = {}
    for team, opp in opp_map.items():
        if opp:
            key = tuple(sorted([team, opp]))
            matchups.setdefault(key, []).append(team)

    for region_label in ["Norte", "Sul"]:
        with st.expander(f"Confrontos {region_label}", expanded=False):
            for t1, t2 in sorted(matchups.keys()):
                if st.session_state.regioes.get(t1) == region_label or st.session_state.regioes.get(t2) == region_label:
                    st.markdown(f"**{t1}** vs **{t2}**")
                    col1, col2 = st.columns(2)
                    with col1:
                        input_1 = st.text_input(
                            f"{t1} (odd)", value=f"{st.session_state.odds.get(t1, 2.0):.2f}",
                            key=f"txt_odd_{t1}"
                        )
                        odd1 = validar_odd_digitada(input_1, t1, default=st.session_state.odds.get(t1, 2.0))
                    with col2:
                        input_2 = st.text_input(
                            f"{t2} (odd)", value=f"{st.session_state.odds.get(t2, 2.0):.2f}",
                            key=f"txt_odd_{t2}"
                        )
                        odd2 = validar_odd_digitada(input_2, t2, default=st.session_state.odds.get(t2, 2.0))

                    novas_odds[t1] = odd1
                    novas_odds[t2] = odd2

    if st.button("Aplicar Ajustes"):
        st.session_state.orcamento = novo_orc
        st.session_state.odds.update(novas_odds)
        df_upd = st.session_state.df.copy()
        df_upd["teamOdd"] = df_upd["teamName"].map(st.session_state.odds)
        st.session_state.df = calcular_estatisticas(df_upd)
        save_settings(st.session_state.orcamento, st.session_state.odds)

# Layout em Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Jogadores", "Times Ideais", "Monte Seu Time", "Base Completa", "Análise Avançada"
])

with tab1:
    st.header("🏆 Top 20 por Posição")
    cols = st.columns(2)
    for i, pos in enumerate(["top", "jungle", "mid", "bottom", "support"]):
        dfp = st.session_state.df[st.session_state.df.role == pos].copy()
        dfp["Chance de Vitória"] = dfp["win_prob"].apply(lambda x: f"{x * 100:.1f}%")
        top = dfp.nlargest(20, "expectedScore").rename(columns={
            "playerName": "Jogador", "price": "Preço", "expectedScore": "Pts Esperados",
            "custo_beneficio": "Pts/Preço", "media_confronto": "Média Confronto",
            "teto_esperado": "Teto Esperado"
        })
        with cols[i % 2].expander(pos.capitalize(), expanded=True):
            st.dataframe(
                top[["Jogador", "Preço", "Chance de Vitória", "Pts Esperados", "Teto Esperado", "Pts/Preço", "Média Confronto"]],
                height=212, hide_index=True
            )

with tab2:
    st.header("⭐ Times Ideais")
    geral = montar_time_otimo(st.session_state.df, "expectedScore", st.session_state.orcamento)[0]
    df_g = pd.DataFrame(geral[0]).copy()
    df_g["Chance de Vitória"] = df_g["win_prob"].apply(lambda x: f"{x * 100:.1f}%")
    df_g["Teto Esperado"] = df_g["expectedScore"] + df_g["std_vitoria"]
    df_g = df_g.rename(columns={
        "playerName": "Jogador", "teamName": "Time", "role": "Posição",
        "price": "Preço", "expectedScore": "Pts Esperados", "custo_beneficio": "Pts/Preço"
    })
    with st.expander("Time Ideal Geral", expanded=True):
        st.dataframe(
            df_g[["Jogador", "Time", "Posição", "Preço", "Chance de Vitória", "Pts Esperados", "Teto Esperado", "Pts/Preço"]],
            height=212, hide_index=True
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Custo", f"{geral[1]:.2f}")
        c2.metric("Pts Esperados", f"{geral[2]:.2f}")
        c3.metric("Eficiência", f"{geral[3]:.2f}")

    for region_label in ["Norte", "Sul"]:
        sub = st.session_state.df[st.session_state.df.region == region_label]
        if sub.empty: continue
        best = montar_time_otimo(sub, "expectedScore", st.session_state.orcamento)[0]
        df_r = pd.DataFrame(best[0]).copy()
        df_r["Chance de Vitória"] = df_r["win_prob"].apply(lambda x: f"{x * 100:.1f}%")
        df_r["Teto Esperado"] = df_r["expectedScore"] + df_r["std_vitoria"]
        df_r = df_r.rename(columns={
            "playerName": "Jogador", "teamName": "Time", "role": "Posição",
            "price": "Preço", "expectedScore": "Pts Esperados", "custo_beneficio": "Pts/Preço"
        })
        with st.expander(f"Time Ideal {region_label}", expanded=False):
            st.dataframe(
                df_r[["Jogador", "Time", "Posição", "Preço", "Chance de Vitória", "Pts Esperados", "Teto Esperado", "Pts/Preço"]],
                height=212, hide_index=True
            )
            rc1, rc2, rc3 = st.columns(3)
            rc1.metric("Custo", f"{best[1]:.2f}")
            rc2.metric("Pts", f"{best[2]:.2f}")
            rc3.metric("Eff", f"{best[3]:.2f}")

with tab3:
    st.header("🛠 Monte Seu Time")
    cols3 = st.columns(5)
    roles = ["top", "jungle", "mid", "bottom", "support"]
    picks = {}
    for i, pos in enumerate(roles):
        opts = sorted(
            st.session_state.df[st.session_state.df.role == pos].playerName.unique(),
            key=lambda x: x.lower()
        )
        picks[pos] = cols3[i].selectbox(
            pos.capitalize(), [None] + list(opts),
            format_func=lambda x: x if x else "Selecione...",
            key=f"pick_{pos}"
        )
    if all(picks.values()):
        df_c = st.session_state.df[
            st.session_state.df.playerName.isin(picks.values())
        ].copy()
        df_c["Chance de Vitória"] = df_c["win_prob"].apply(lambda x: f"{x * 100:.1f}%")
        df_c["Teto Esperado"] = df_c["expectedScore"] + df_c["std_vitoria"]
        df_c = df_c.rename(columns={
            "playerName": "Jogador", "teamName": "Time", "role": "Posição",
            "price": "Preço", "expectedScore": "Pts Esperados", "custo_beneficio": "Pts/Preço"
        })
        with st.expander("Seu Time Customizado", expanded=True):
            st.dataframe(
                df_c[["Jogador", "Time", "Posição", "Preço", "Chance de Vitória", "Pts Esperados", "Teto Esperado", "Pts/Preço"]],
                height=212, hide_index=True
            )
            total_c = df_c.Preço.sum()
            total_p = df_c["Pts Esperados"].sum()
            total_e = total_p / total_c if total_c > 0 else 0
            m1, m2, m3 = st.columns(3)
            m1.metric("Custo", f"{total_c:.2f}")
            m2.metric("Pts", f"{total_p:.2f}")
            m3.metric("Eff", f"{total_e:.2f}")
    else:
        st.info("Escolha um jogador para cada posição.")

with tab4:
    st.header("📋 Base Completa")
    df_full = st.session_state.df.copy()
    df_full["Chance de Vitória"] = df_full["win_prob"].apply(lambda x: f"{x * 100:.1f}%")
    df_full["Teto Esperado"] = df_full["expectedScore"] + df_full["std_vitoria"]
    df_full = df_full.rename(columns={
        "playerName": "Jogador", "role": "Posição", "teamName": "Time",
        "price": "Preço", "expectedScore": "Pts Esperados", "custo_beneficio": "Pts/Preço",
        "maxRoundScore": "Máx Histórico", "media_vitoria": "Média Vitórias",
        "media_derrota": "Média Derrotas", "media_confronto": "Média Confronto"
    })
    st.dataframe(
        df_full[[
            "Jogador", "Posição", "Time", "Preço", "Chance de Vitória",
            "Pts Esperados", "Teto Esperado", "Pts/Preço", "Máx Histórico",
            "Média Vitórias", "Média Derrotas", "Média Confronto"
        ]], height=212, hide_index=True
    )

with tab5:
    st.header("📊 Análise Avançada e Insights")
    df = st.session_state.df.copy()

    # 0) Ranking por Eficiência (Expected / Price)
    top_eff = df.nlargest(10, 'custo_beneficio')[['playerName', 'role', 'teamName', 'expectedScore', 'price', 'custo_beneficio']]
    top_eff = top_eff.rename(columns={
        'playerName': 'Jogador', 'role': 'Posição', 'teamName': 'Time',
        'expectedScore': 'Pts Esperados', 'price': 'Preço', 'custo_beneficio': 'Pts/Preço'
    })
    st.subheader("🏅 Top 10 Jogadores Mais Eficientes")
    st.dataframe(top_eff, use_container_width=True, hide_index=True)

    # 1) Top 10 Teto Esperado
    top_ceiling = df.nlargest(10, 'teto_esperado')[['playerName', 'role', 'teamName', 'expectedScore', 'teto_esperado']]
    top_ceiling = top_ceiling.rename(columns={
        'playerName': 'Jogador', 'role': 'Posição', 'teamName': 'Time',
        'expectedScore': 'Pts Esperados', 'teto_esperado': 'Teto Esperado'
    })
    st.subheader("🚀 Top 10 Jogadores com Maior Teto de Pontuação")
    st.dataframe(top_ceiling, use_container_width=True, hide_index=True)

    # 2) Dispersão: Preço vs ExpectedScore
    st.subheader("💸 Relação entre Preço e Pontuação Esperada")
    fig = px.scatter(
        df, x='price', y='expectedScore', color='role', hover_name='playerName',
        size='custo_beneficio',
        labels={'price': 'Preço', 'expectedScore': 'Pts Esperados'},
        title='Dispersão: Preço vs Pontuação Esperada'
    )
    st.plotly_chart(fig, use_container_width=True)

    # 3) Boxplot: Pts Esperados por Região
    st.subheader("🌍 Pontuação Esperada por Região")
    fig_box = px.box(
        df, x='region', y='expectedScore', color='region',
        points='all',
        title='Distribuição de Pontuação por Região'
    )
    st.plotly_chart(fig_box, use_container_width=True)

    # 4) Matriz de Correlação (Principais Métricas)
    st.subheader("🔗 Correlação entre Métricas")
    corr_metrics = ['expectedScore', 'teto_esperado', 'media_vitoria', 'media_derrota', 'media_confronto']
    corr = df[corr_metrics].corr()
    fig_corr = px.imshow(
        corr, text_auto=True, aspect='auto',
        title='Matriz de Correlação'
    )
    st.plotly_chart(fig_corr, use_container_width=True)

    # 5) Sumário Estatístico
    st.subheader("📈 Estatísticas Resumidas das Métricas")
    desc = df[corr_metrics].describe().T[['mean','std','min','max']]
    st.dataframe(desc.rename(columns={
        'mean': 'Média', 'std': 'Desvio', 'min': 'Mínimo', 'max': 'Máximo'
    }), use_container_width=True)