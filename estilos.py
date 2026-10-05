"""Estilos de la app (CSS)."""
import streamlit as st

CSS = """
<style>
  .block-container {padding-top: 1.1rem; padding-bottom: 1rem; max-width: 1320px;}
  header[data-testid="stHeader"] {height: 0; background: transparent;}
  [data-testid="stSidebarCollapsedControl"] {display: none;}
  div[data-testid="stVerticalBlock"] {gap: 1rem;}
  div[data-testid="stWidgetLabel"] p {font-size: .82rem; font-weight: 600; color: var(--text-2);}
  :root {--text-2: #52514e; --line: #e4e3df; --soft: #f5f5f2; --accent: #1f7a4d;}
  @media (prefers-color-scheme: dark) {:root {--text-2: #c3c2b7; --line: #3a3a37; --soft: #232322;}}

  .app-title {display:flex; flex-direction:column; gap:.05rem; margin:0;}
  .app-title .t {font-size:1.4rem; line-height:1.2; font-weight:700; letter-spacing:-.01em; white-space:nowrap;}
  .app-title span {font-size:.8rem; color:var(--text-2);}

  .chips {display:flex; flex-wrap:wrap; gap:.35rem; margin:-.35rem 0 0;}
  .chip {font-size:.76rem; padding:.12rem .55rem; border-radius:999px;
         background:var(--soft); border:1px solid var(--line); white-space:nowrap;}
  .chip b {font-weight:600;}
  .chip.muted {opacity:.75;}

  .totales {display:flex; gap:1.6rem; padding:.45rem .8rem; border:1px solid var(--line);
            border-radius:10px; background:var(--soft); align-items:baseline;}
  .totales div {display:flex; flex-direction:column;}
  .totales small {font-size:.72rem; color:var(--text-2); text-transform:uppercase; letter-spacing:.03em;}
  .totales strong {font-size:1.15rem; font-variant-numeric: tabular-nums;}

  .kpis {display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:.6rem;}
  @media (max-width: 700px) {.kpis {grid-template-columns:repeat(2, minmax(0,1fr));}}
  .kpi {border:1px solid var(--line); border-radius:10px; padding:.55rem .8rem;}
  .kpi small {font-size:.72rem; color:var(--text-2); text-transform:uppercase; letter-spacing:.03em;}
  .kpi div {font-size:1.25rem; font-weight:700; font-variant-numeric: tabular-nums;}
  .kpi span.sub {display:block; font-size:.74rem; font-weight:500; color:var(--text-2);}

  .presu {border:1px solid var(--line); border-radius:10px; padding:.6rem .75rem .55rem; margin-bottom:.2rem;}
  .presu-top {display:flex; flex-direction:column; gap:.15rem;}
  .presu-prog {font-size:.8rem; font-weight:600; line-height:1.25;}
  .presu-est {font-size:.74rem; white-space:nowrap; display:flex; align-items:center; gap:.3rem;}
  .dot {width:.6rem; height:.6rem; border-radius:50%; display:inline-block; flex:none;}
  .presu-saldo {display:flex; flex-direction:column; margin:.35rem 0 .35rem;}
  .presu-saldo div {display:flex; align-items:baseline; gap:.4rem; flex-wrap:wrap;}
  .presu-saldo small {font-size:.7rem; color:var(--text-2); text-transform:uppercase; letter-spacing:.03em;}
  .presu-saldo strong {font-size:1.2rem; font-variant-numeric:tabular-nums;}
  .presu-saldo strong.neg, .neg {color:#d03b3b;}
  .presu-saldo span {font-size:.74rem; color:var(--text-2);}
  .meter {position:relative; height:12px; border-radius:4px; background:var(--soft);
          border:1px solid var(--line); display:flex; overflow:visible;}
  .meter.chico {height:8px;}
  .meter > b {height:100%; display:block;}
  .meter > b:first-child {border-radius:4px 0 0 4px;}
  .meter i {position:absolute; top:-4px; bottom:-4px; width:0; border-left:2px solid var(--text-1, #0b0b0b);}
  .meter i.dash {border-left:2px dashed #d03b3b;}
  /* Escenario mínimo: triángulo debajo de la barra */
  .meter u {position:absolute; bottom:-9px; width:0; height:0; margin-left:-5px; text-decoration:none;
            border-left:5px solid transparent; border-right:5px solid transparent; border-bottom:7px solid #52514e;}
  .presu-ley {display:flex; flex-wrap:wrap; gap:.15rem .7rem; font-size:.72rem; color:var(--text-2); margin-top:.55rem;}
  .presu-ley span {display:flex; align-items:center; gap:.25rem; white-space:nowrap;}
  .presu-min {font-size:.74rem; margin-top:.35rem; padding-top:.35rem; border-top:1px dashed var(--line);}
  .sq {width:.6rem; height:.6rem; border-radius:2px; display:inline-block;}
  .presu-mini {display:grid; grid-template-columns:1fr auto; gap:.1rem .6rem; align-items:center;
               font-size:.74rem; padding:.3rem 0; border-bottom:1px solid var(--line);}
  .presu-mini .meter {grid-column:1 / -1;}
  .panel-titulo {font-size:.8rem; font-weight:700; color:var(--text-2);
                 text-transform:uppercase; letter-spacing:.04em; margin:.1rem 0 0;}
  .panel-titulo span {font-weight:400; text-transform:none; letter-spacing:0;}
</style>
"""


def aplicar() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
