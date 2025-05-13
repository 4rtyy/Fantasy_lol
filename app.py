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
    for col, default in [("teamOdd",2.0),("region","Outra"),("teamName","Desconhecido")]:
        df_raw[col] = df_raw.get(col, default)
    st.session_state.odds = settings.get("odds") or {team:2.0 for team in df_raw["teamName"].unique()}
    st.session_state.regioes = {
        team: df_raw[df_raw["teamName"]==team]["region"].iloc[0]
        for team in df_raw["teamName"].unique()
    }
    df_raw["teamOdd"] = df_raw["teamName"].map(st.session_state.odds)
    st.session_state.df = calcular_estatisticas(df_raw)

# Sidebar: Parâmetros e Odds
with st.sidebar:
    st.markdown("## ⚙️ Parâmetros")
    novo_orc = st.number_input(
        "Orçamento (💰)", 1.0, 100.0,
        value=st.session_state.orcamento, step=0.1, format="%.2f"
    )
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
    for region_label in ["Norte","Sul"]:
        with st.expander(f"Confrontos {region_label}", expanded=False):
            for t1, t2 in sorted(matchups.keys()):
                if st.session_state.regioes.get(t1) == region_label or st.session_state.regioes.get(t2) == region_label:
                    st.write(f"**{t1}** vs **{t2}**")
                    odd1 = st.number_input(f"{t1} odd", 1.01, 10.0,
                                            st.session_state.odds.get(t1,2.0), 0.01,
                                            format="%.2f", key=f"odd_{t1}")
                    odd2 = st.number_input(f"{t2} odd", 1.01, 10.0,
                                            st.session_state.odds.get(t2,2.0), 0.01,
                                            format="%.2f", key=f"odd_{t2}")
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
    for i, pos in enumerate(["top","jungle","mid","bottom","support"]):
        dfp = st.session_state.df[st.session_state.df.role == pos]
        top = dfp.nlargest(20, "expectedScore").rename(columns={
            "playerName":"Jogador","price":"Preço","teamOdd":"Odds",
            "expectedScore":"Pts Esperados","custo_beneficio":"Pts/Preço",
            "media_confronto":"Média Confronto"
        })
        with cols[i%2].expander(pos.capitalize(), expanded=True):
            st.dataframe(
                top[["Jogador","Preço","Odds","Pts Esperados","Pts/Preço","Média Confronto"]],
                height=212, hide_index=True
            )

with tab2:
    st.header("⭐ Times Ideais")
    geral = montar_time_otimo(
        st.session_state.df, "expectedScore", st.session_state.orcamento
    )[0]
    df_g = pd.DataFrame(geral[0]).rename(columns={
        "playerName":"Jogador","teamName":"Time","role":"Posição",
        "price":"Preço","expectedScore":"Pts Esperados","custo_beneficio":"Pts/Preço"
    })
    with st.expander("Time Ideal Geral", expanded=True):
        st.dataframe(
            df_g[["Jogador","Time","Posição","Preço","Pts Esperados","Pts/Preço"]],
            height=212, hide_index=True
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Custo", f"{geral[1]:.2f}")
        c2.metric("Pts Esperados", f"{geral[2]:.2f}")
        c3.metric("Eficiência", f"{geral[3]:.2f}")
    for region_label in ["Norte","Sul"]:
        sub = st.session_state.df[st.session_state.df.region == region_label]
        if sub.empty: continue
        best = montar_time_otimo(sub, "expectedScore", st.session_state.orcamento)[0]
        df_r = pd.DataFrame(best[0]).rename(columns={
            "playerName":"Jogador","teamName":"Time","role":"Posição",
            "price":"Preço","expectedScore":"Pts Esperados","custo_beneficio":"Pts/Preço"
        })
        with st.expander(f"Time Ideal {region_label}", expanded=False):
            st.dataframe(
                df_r[["Jogador","Time","Posição","Preço","Pts Esperados","Pts/Preço"]],
                height=212, hide_index=True
            )
            rc1, rc2, rc3 = st.columns(3)
            rc1.metric("Custo", f"{best[1]:.2f}")
            rc2.metric("Pts", f"{best[2]:.2f}")
            rc3.metric("Eff", f"{best[3]:.2f}")

with tab3:
    st.header("🛠 Monte Seu Time")
    cols3 = st.columns(5)
    roles = ["top","jungle","mid","bottom","support"]
    picks = {}
    for i, pos in enumerate(roles):
        opts = sorted(
            st.session_state.df[st.session_state.df.role==pos].playerName.unique(),
            key=lambda x: x.lower()
        )
        picks[pos] = cols3[i].selectbox(
            pos.capitalize(), [None]+opts,
            format_func=lambda x: x if x else "Selecione...",
            key=f"pick_{pos}"
        )
    if all(picks.values()):
        df_c = st.session_state.df[
            st.session_state.df.playerName.isin(picks.values())
        ].rename(columns={
            "playerName":"Jogador","teamName":"Time","role":"Posição",
            "price":"Preço","expectedScore":"Pts Esperados","custo_beneficio":"Pts/Preço"
        })
        with st.expander("Seu Time Customizado", expanded=True):
            st.dataframe(
                df_c[["Jogador","Time","Posição","Preço","Pts Esperados","Pts/Preço"]],
                height=212, hide_index=True
            )
            total_c = df_c.Preço.sum()
            total_p = df_c["Pts Esperados"].sum()
            total_e = total_p/total_c if total_c>0 else 0
            m1, m2, m3 = st.columns(3)
            m1.metric("Custo", f"{total_c:.2f}")
            m2.metric("Pts", f"{total_p:.2f}")
            m3.metric("Eff", f"{total_e:.2f}")
    else:
        st.info("Escolha um jogador para cada posição.")

with tab4:
    st.header("📋 Base Completa")
    df_full = st.session_state.df.rename(columns={
        "playerName":"Jogador","role":"Posição","teamName":"Time",
        "price":"Preço","teamOdd":"Odds","expectedScore":"Pts Esperados",
        "custo_beneficio":"Pts/Preço","maxRoundScore":"Máx Histórico",
        "media_vitoria":"Média Vitórias","media_derrota":"Média Derrotas",
        "media_confronto":"Média Confronto"
    })
    st.dataframe(
        df_full[[
            "Jogador","Posição","Time","Preço","Odds",
            "Pts Esperados","Pts/Preço","Máx Histórico","Média Vitórias",
            "Média Derrotas","Média Confronto"
        ]], height=212, hide_index=True
    )

with tab5:
    st.header("📊 Análise Avançada e Insights")
    df = st.session_state.df.copy()

    # 0) Sharpe ratio simplificado
    df['sharpe'] = df['expectedScore'] / (df['media_derrota'] + 1e-6)

    # 1) Bolha: Preço vs ExpectedScore (custo-benefício como tamanho)
    col1, col2 = st.columns(2)
    fig1 = px.scatter(
        df, x='price', y='expectedScore', size='custo_beneficio', color='role',
        hover_name='playerName',
        title='Preço vs ExpectedScore (bolha ~ Custo-benefício)'
    )
    col1.plotly_chart(fig1, use_container_width=True)

    # 2) Top 10 por Custo-benefício
    top_cb = df.nlargest(10, 'custo_beneficio')
    fig2 = px.bar(
        top_cb, x='playerName', y='custo_beneficio', color='role',
        hover_data=['teamName'],
        title='Top 10 Jogadores por Custo-benefício'
    )
    col2.plotly_chart(fig2, use_container_width=True)

    # 3) Radar Chart (métricas do jogador)
    metrics = ['expectedScore','media_vitoria','media_derrota','media_confronto','sharpe']
    player_sel = st.selectbox(
        "Selecione um Jogador para Radar Chart:",
        [''] + df['playerName'].sort_values(key=lambda x: x.str.lower()).unique().tolist(),
        key='radar'
    )
    if player_sel:
        row = df[df['playerName']==player_sel].iloc[0]
        values = [row[m] for m in metrics]
        fig3 = px.line_polar(
            r=values, theta=metrics, line_close=True, markers=True,
            title=f'Métricas de {player_sel}'
        )
        st.plotly_chart(fig3, use_container_width=True)

    # 4) PCA 2D das métricas
    PCA_feats = metrics
    pca = PCA(n_components=2)
    coords = pca.fit_transform(df[PCA_feats].fillna(0))
    df['PC1'], df['PC2'] = coords[:,0], coords[:,1]
    fig4 = px.scatter(
        df, x='PC1', y='PC2', color='role', hover_name='playerName',
        title='PCA 2D das Métricas Principais'
    )
    st.plotly_chart(fig4, use_container_width=True)

    # 5) Heatmap de correlação
    corr = df[PCA_feats].corr()
    fig5 = px.imshow(
        corr, text_auto=True, aspect='auto',
        title='Matriz de Correlação das Métricas'
    )
    st.plotly_chart(fig5, use_container_width=True)

    # 6) Estatísticas descritivas resumidas
    st.markdown("### Estatísticas Descritivas")
    desc = df[PCA_feats].describe().T[['mean','std','min','max']]
    st.dataframe(desc, use_container_width=True)

    # 7) Boxplot por Região e Posição
    fig6 = px.box(
        df, x='region', y='expectedScore', color='role',
        title='ExpectedScore por Região e Posição'
    )
    st.plotly_chart(fig6, use_container_width=True)

    # 8) Sunburst (Região -> Posição)
    region_role = df.groupby(['region','role'])['expectedScore'].mean().reset_index()
    fig7 = px.sunburst(
        region_role, path=['region','role'], values='expectedScore',
        title='ExpectedScore Médio por Região e Posição'
    )
    st.plotly_chart(fig7, use_container_width=True)

    # 9) Treemap Top 20
    top20 = df.nlargest(20,'expectedScore')
    fig8 = px.treemap(
        top20, path=['region','teamName','playerName'], values='expectedScore',
        title='Top 20 Jogadores por Região/Time'
    )
    st.plotly_chart(fig8, use_container_width=True)

    st.markdown("---")
    st.markdown(
        "## Insights Estatísticos Aprofunados:"  
        "\n- **Custo-benefício**: identifica quem rende mais por preço."
        "\n- **Radar Chart**: destaca pontos fortes e fracos individuais."
        "\n- **PCA**: revela padrões latentes em métricas."
        "\n- **Correlação**: identifica relações fortes entre variáveis."
        "\n- **Análise Regional**: compara consistência Norte vs Sul."
        "\n- **Sunburst/Treemap**: hierarquia e variabilidade de top performers."
    )