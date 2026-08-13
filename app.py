import streamlit as st
import fitz  # PyMuPDF
from PIL import Image
import io
import json
import time
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai

# ==========================================
# 1. CSS & テーマ設定 (POPに!)
# ==========================================
# Google FontsからPOPなフォントを読み込み、カスタムCSSを適用
POP_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Kosugi+Maru&display=swap" rel="stylesheet">

<style>
    /* 全体フォント (丸文字でPOP) */
    html, body, [class*="css"]  {
        font-family: 'Kosugi Maru', sans-serif;
    }

    /* メイン背景色 (ミルクホワイト) */
    .stApp {
        background-color: #FFFAF0;
    }

    /* タイトル (大きく、オレンジ、POPフォント) */
    .main-title {
        font-family: 'Kosugi Maru', sans-serif;
        color: #FF6F61;
        font-size: 3rem;
        font-weight: bold;
        text-align: center;
        margin-bottom: 0.5rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
    }
    .sub-title {
        color: #6c757d;
        font-size: 1.2rem;
        text-align: center;
        margin-bottom: 2rem;
    }

    /* サイドバー (薄いオレンジ) */
    [data-testid="stSidebar"] {
        background-color: #FFF3E0;
        border-right: 2px solid #FFCC80;
    }

    /* POPなコンテナボックス (角丸・影) */
    .pop-container {
        background-color: #FFFFFF;
        border-radius: 20px;
        padding: 25px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.05);
        margin-bottom: 25px;
        border: 1px solid #FFCC80;
    }

    /* ボタン (グラデーション、角丸、ホバー) */
    .stButton > button {
        background: linear-gradient(45deg, #FF6F61, #FF8A75);
        color: white;
        border: none;
        border-radius: 30px;
        padding: 15px 30px;
        font-size: 1.2rem;
        font-weight: bold;
        box-shadow: 0 5px 15px rgba(255,111,97,0.3);
        transition: all 0.3s ease;
        width: 100%;
    }
    .stButton > button:hover {
        background: linear-gradient(45deg, #FF8A75, #FF6F61);
        transform: translateY(-3px);
        box-shadow: 0 8px 20px rgba(255,111,97,0.5);
    }

    /* タブ (角丸、オレンジ) */
    .stTabs [data-baseweb="tab-list"] {
        background-color: transparent;
        border-radius: 15px 15px 0 0;
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #FFF3E0;
        color: #FF6F61;
        border-radius: 15px 15px 0 0;
        padding: 10px 20px;
        font-weight: bold;
        transition: all 0.2s ease;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background-color: #FFECB3;
    }
    .stTabs [aria-selected="true"] {
        background-color: #FF6F61 !important;
        color: white !important;
    }

    /* ファイルアップローダー (POPに) */
    .stFileUploader > div > button {
        background-color: #FFCC80 !important;
        color: #FF6F61 !important;
        border-radius: 20px !important;
    }
    
    /* データフレーム (角丸) */
    .stDataFrame {
        border-radius: 15px;
        overflow: hidden;
    }

    /* 警告/情報ボックス (POPな色) */
    .stWarning {
        background-color: #FFCDD2 !important;
        color: #B71C1C !important;
        border-radius: 15px;
        border: 1px solid #EF9A9A;
    }
    .stInfo {
        background-color: #E1F5FE !important;
        color: #01579B !important;
        border-radius: 15px;
        border: 1px solid #81D4FA;
    }
    .stSuccess {
        background-color: #C8E6C9 !important;
        color: #1B5E20 !important;
        border-radius: 15px;
        border: 1px solid #A5D6A7;
    }

    /* チャートのタイトルフォント */
    .gtitle {
        font-family: 'Kosugi Maru', sans-serif !important;
    }
</style>
"""

# ==========================================
# 2. アプリのメイン処理
# ==========================================
st.set_page_config(layout="wide", page_title="🍳 Smile Kitchen アンケート解析 🤖")
st.markdown(POP_CSS, unsafe_allow_html=True) # CSS適用

# タイトル
st.markdown('<div class="main-title">🍳 Smile Kitchen 🤖</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">AIアンケート一括自動集計アプリ</div>', unsafe_allow_html=True)

# 1. APIキーの設定 (サイドバー)
st.sidebar.markdown("## ⚙️ 設定")
st.sidebar.markdown('<div class="pop-container">', unsafe_allow_html=True) # コンテナ開始
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    st.sidebar.success("✅ APIキーは自動で読み込まれました")
else:
    api_key = st.sidebar.text_input("Gemini APIキーを入力してください", type="password")
    st.sidebar.markdown("[APIキーの無料取得はこちら(Google AI Studio)](https://aistudio.google.com/app/apikey)")
st.sidebar.markdown('</div>', unsafe_allow_html=True) # コンテナ終了

# 2. ファイルアップロード
st.markdown('<div class="pop-container">', unsafe_allow_html=True)
uploaded_files = st.file_uploader(
    "📄 アンケートのPDFファイルをアップロードしてください（複数選択可）", 
    type=["pdf"], 
    accept_multiple_files=True
)
st.markdown('</div>', unsafe_allow_html=True)

prompt_text = """
あなたはデータ入力のスペシャリストです。提供されたアンケート画像から、以下の項目を正確に読み取り、必ず指定されたJSONフォーマットのみで出力してください。
マークされていない、または無記入の項目は空文字 "" としてください。数値は数字のみを出力してください（例: "5"）。

【出力JSONフォーマット】
{
  "Q1_日時": "MM月DD日 HH時",
  "Q2_同伴者": "ご家族/友人知人/カップル/ひとり/その他 のいずれか。その他の場合は手書き内容",
  "Q3_来店回数": "はじめて/2回/3回以上 のいずれか",
  "Q4_来店きっかけ": "ホームページ/パークガイド/看板/口コミ/通りすがり/その他 のいずれか",
  "Q5_選んだ理由": "丸が囲まれている番号や理由をカンマ区切りで",
  "Q6_メニュー": "手書き内容",
  "Q7_料理評価": "5〜1の数字",
  "Q7_接客評価": "5〜1の数字",
  "Q7_店舗評価": "5〜1の数字",
  "Q8_距離感": "1〜3の数字",
  "Q9_再来店意向": "5〜1の数字",
  "Q10_推奨意向": "5〜1の数字",
  "Q11_満足度": "5〜1の数字",
  "Q12_求めるサービス": "1〜5の数字",
  "自由記述": "手書き内容をそのまま抽出",
  "自由記述_分類": "ポジティブ / ネガティブ・改善要望 / その他 / 無記入 のいずれかで分類してください"
}
"""

if uploaded_files and api_key:
    # 読み取り開始ボタン
    if st.button("🚀 一括読み取りを開始する"):
        genai.configure(api_key=api_key)
        
        # モデルの指定 (常に最新のFlashモデルを使用)
        model = genai.GenerativeModel(
            'gemini-flash-latest',
            generation_config={"response_mime_type": "application/json"}
        )
        
        all_results = []
        progress_text = "PDFを解析中..."
        progress_bar = st.progress(0, text=progress_text)
        
        total_pages = sum([fitz.open(stream=f.read(), filetype="pdf").page_count for f in uploaded_files])
        for f in uploaded_files:
            f.seek(0)
            
        current_page_num = 0
        
        for file in uploaded_files:
            pdf_document = fitz.open(stream=file.read(), filetype="pdf")
            
            for page_num in range(pdf_document.page_count):
                page = pdf_document.load_page(page_num)
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("jpeg")
                
                pil_image = Image.open(io.BytesIO(img_bytes))
                
                try:
                    response = model.generate_content([prompt_text, pil_image])
                    result_json = json.loads(response.text)
                    result_json["元ファイル名"] = f"{file.name} (P.{page_num+1})"
                    all_results.append(result_json)
                    
                except Exception as e:
                    st.error(f"{file.name} の {page_num+1}ページ目でエラーが発生しました: {e}")
                
                current_page_num += 1
                progress_bar.progress(current_page_num / total_pages, text=f"処理中... ({current_page_num}/{total_pages}ページ完了)")
                
                # 無料枠のスピード制限（エラー429）を回避するため、4秒間の一時停止を入れる
                time.sleep(4)
        
        progress_bar.empty()
        st.success("🎉 すべての読み取りが完了しました！")
        
        # セッション状態にデータを保存 (画面更新で消えないように)
        st.session_state['survey_df'] = pd.DataFrame(all_results)

# 3. 結果表示 (データがあれば)
if 'survey_df' in st.session_state and not st.session_state['survey_df'].empty:
    df = st.session_state['survey_df']
    cols = df.columns.tolist()
    cols = cols[-1:] + cols[:-1]
    df = df[cols]
    
    if "Q1_日時" in df.columns:
        df['抽出日付'] = df['Q1_日時'].astype(str).str.extract(r'(\d{1,2}月\d{1,2}日)')
        df['抽出日付'] = df['抽出日付'].fillna('日付不明')
    
    # POPなタブ
    tab1, tab2, tab3 = st.tabs(["📊 データ一覧表", "📈 日別・傾向グラフ分析", "⚠️ ご意見・改善要望まとめ"])
    
    with tab1:
        st.markdown('<div class="pop-container">', unsafe_allow_html=True)
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 データをCSV（Excel用）でダウンロード",
            data=csv,
            file_name='smile_kitchen_survey_data.csv',
            mime='text/csv',
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    with tab2:
        st.markdown('<div class="pop-container">', unsafe_allow_html=True)
        st.subheader("📅 日別のアンケート回収数")
        if "抽出日付" in df.columns:
            date_counts = df[df['抽出日付'] != '日付不明']['抽出日付'].value_counts().reset_index()
            date_counts.columns = ['日付', '件数']
            date_counts = date_counts.sort_values('日付')
            
            if not date_counts.empty:
                fig_date = px.bar(date_counts, x='日付', y='件数', title='日別回収数 (件)', text_auto=True, color_discrete_sequence=['#FF6F61'])
                fig_date.update_layout(plot_bgcolor='white', title_font_size=20)
                st.plotly_chart(fig_date, use_container_width=True)
            else:
                st.info("日付データが読み取れませんでした。")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="pop-container">', unsafe_allow_html=True)
        st.subheader("主要な回答の傾向")
        col1, col2 = st.columns(2)
        
        # POPな色相 (Pastel, Rainbow)
        pop_colors = px.colors.qualitative.Pastel
        
        with col1:
            if "Q3_来店回数" in df.columns:
                q3_counts = df["Q3_来店回数"].value_counts().reset_index()
                q3_counts.columns = ['来店回数', '件数']
                fig_q3 = px.pie(q3_counts, names='来店回数', values='件数', title='ご来店回数の割合', color_discrete_sequence=pop_colors)
                fig_q3.update_layout(title_font_size=18)
                st.plotly_chart(fig_q3, use_container_width=True)
        
        with col2:
            if "Q2_同伴者" in df.columns:
                q2_counts = df["Q2_同伴者"].value_counts().reset_index()
                q2_counts.columns = ['同伴者', '件数']
                fig_q2 = px.pie(q2_counts, names='同伴者', values='件数', title='ご同伴者の割合', color_discrete_sequence=pop_colors)
                fig_q2.update_layout(title_font_size=18)
                st.plotly_chart(fig_q2, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="pop-container">', unsafe_allow_html=True)
        st.subheader("各評価の平均スコア (5点満点)")
        
        metrics = ["Q7_料理評価", "Q7_接客評価", "Q7_店舗評価", "Q9_再来店意向", "Q10_推奨意向", "Q11_満足度"]
        metrics_icons = ["🍔", "👩‍🍳", "🏪", "🔁", "📢", "😊"]
        metrics_names = ["料理", "接客", "店舗", "再来店", "推奨", "満足度"]
        avg_data = []
        for i, m in enumerate(metrics):
            if m in df.columns:
                numeric_s = pd.to_numeric(df[m].astype(str).str.extract(r'(\d+)')[0], errors='coerce')
                avg_val = numeric_s.mean()
                if pd.notna(avg_val):
                    avg_data.append({"評価項目": f"{metrics_icons[i]} {metrics_names[i]}", "平均スコア": round(avg_val, 2)})
        
        if avg_data:
            df_avg = pd.DataFrame(avg_data)
            fig_avg = px.bar(df_avg, x='評価項目', y='平均スコア', range_y=[0, 5], text='平均スコア', color='平均スコア', color_continuous_scale='Reds')
            fig_avg.update_layout(plot_bgcolor='white', title_font_size=18)
            st.plotly_chart(fig_avg, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with tab3:
        st.markdown('<div class="pop-container">', unsafe_allow_html=True)
        st.subheader("👨‍👩‍👧‍👦 お客様からの自由記述・ご意見")
        
        if "自由記述" in df.columns and "自由記述_分類" in df.columns:
            df_opinions = df[df["自由記述"].str.strip() != ""]
            
            st.markdown("### ⚠️ 改善要望・ネガティブなご意見")
            negatives = df_opinions[df_opinions["自由記述_分類"].str.contains("ネガティブ|改善", na=False)]
            if not negatives.empty:
                for idx, row in negatives.iterrows():
                    st.warning(f"**⏰ {row['Q1_日時']}** (ファイル: {row['元ファイル名']})\n\n> {row['自由記述']}")
            else:
                st.success("✨ ネガティブなご意見や改善要望はありませんでした！")
            
            st.divider()
            
            st.markdown("### 🥰 ポジティブ・その他のご意見")
            positives = df_opinions[~df_opinions["自由記述_分類"].str.contains("ネガティブ|改善", na=False)]
            if not positives.empty:
                for idx, row in positives.iterrows():
                    st.info(f"**⏰ {row['Q1_日時']}** (ファイル: {row['元ファイル名']})\n\n> {row['自由記述']}")
        else:
            st.info("自由記述のデータがありません。")
        st.markdown('</div>', unsafe_allow_html=True)

elif uploaded_files and not api_key:
    st.warning("サイドバーの設定欄にGemini APIキーを入力してください。")
