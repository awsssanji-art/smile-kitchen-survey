import streamlit as st
import fitz  # PyMuPDF
from PIL import Image
import io
import json
import time
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import gspread

# ==========================================
# 1. CSS & テーマ設定 (POPデザイン)
# ==========================================
POP_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Kosugi+Maru&display=swap" rel="stylesheet">
<style>
    html, body, [class*="css"]  { font-family: 'Kosugi Maru', sans-serif; }
    .stApp { background-color: #FFFAF0; }
    .main-title { color: #FF6F61; font-size: 3rem; font-weight: bold; text-align: center; margin-bottom: 0.5rem; text-shadow: 2px 2px 4px rgba(0,0,0,0.1); }
    .sub-title { color: #6c757d; font-size: 1.2rem; text-align: center; margin-bottom: 2rem; }
    [data-testid="stSidebar"] { background-color: #FFF3E0; border-right: 2px solid #FFCC80; }
    .pop-container { background-color: #FFFFFF; border-radius: 20px; padding: 25px; box-shadow: 0 10px 20px rgba(0,0,0,0.05); margin-bottom: 25px; border: 1px solid #FFCC80; }
    .stButton > button { background: linear-gradient(45deg, #FF6F61, #FF8A75); color: white; border: none; border-radius: 30px; padding: 15px 30px; font-size: 1.2rem; font-weight: bold; box-shadow: 0 5px 15px rgba(255,111,97,0.3); transition: all 0.3s ease; width: 100%; }
    .stButton > button:hover { background: linear-gradient(45deg, #FF8A75, #FF6F61); transform: translateY(-3px); box-shadow: 0 8px 20px rgba(255,111,97,0.5); }
    .stTabs [data-baseweb="tab-list"] { background-color: transparent; border-radius: 15px 15px 0 0; gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #FFF3E0; color: #FF6F61; border-radius: 15px 15px 0 0; padding: 10px 20px; font-weight: bold; }
    .stTabs [aria-selected="true"] { background-color: #FF6F61 !important; color: white !important; }
    .stWarning { background-color: #FFCDD2 !important; color: #B71C1C !important; border-radius: 15px; border: 1px solid #EF9A9A; }
    .stInfo { background-color: #E1F5FE !important; color: #01579B !important; border-radius: 15px; border: 1px solid #81D4FA; }
    .stSuccess { background-color: #C8E6C9 !important; color: #1B5E20 !important; border-radius: 15px; border: 1px solid #A5D6A7; }
</style>
"""

st.set_page_config(layout="wide", page_title="🍳 Smile Kitchen アンケート解析 🤖")
st.markdown(POP_CSS, unsafe_allow_html=True)

# ==========================================
# 2. Googleスプレッドシート連携機能
# ==========================================
@st.cache_resource
def get_gspread_client():
    cred_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    return gspread.service_account_from_dict(cred_dict)

def save_to_spreadsheet(df):
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(st.secrets["SPREADSHEET_ID"])
        try:
            ws = sh.worksheet("データDB")
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title="データDB", rows="1000", cols="30")
            ws.append_row(df.columns.tolist()) # ヘッダーを追加
        
        # NaNなどを空文字に変換してエラーを防ぐ
        df_to_save = df.fillna("")
        ws.append_rows(df_to_save.values.tolist())
        return True
    except Exception as e:
        st.error(f"スプレッドシートの保存に失敗しました: {e}")
        return False

def load_from_spreadsheet():
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(st.secrets["SPREADSHEET_ID"])
        ws = sh.worksheet("データDB")
        data = ws.get_all_records()
        if data:
            return pd.DataFrame(data)
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

# ==========================================
# 3. アプリメイン画面
# ==========================================
st.markdown('<div class="main-title">🍳 Smile Kitchen 🤖</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">AIアンケート一括自動集計アプリ</div>', unsafe_allow_html=True)

# サイドバー設定
st.sidebar.markdown("## ⚙️ 設定")
st.sidebar.markdown('<div class="pop-container">', unsafe_allow_html=True)
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    st.sidebar.success("✅ APIキーは自動で読み込まれました")
else:
    st.sidebar.error("⚠️ APIキーが設定されていません")
    api_key = None
st.sidebar.markdown('</div>', unsafe_allow_html=True)

# メインモード切り替え
app_mode = st.radio("表示する画面を選んでください", ["🆕 新しいアンケートを読み込む", "📊 過去のデータを月別・一括で分析する"], horizontal=True)

if app_mode == "🆕 新しいアンケートを読み込む":
    st.markdown('<div class="pop-container">', unsafe_allow_html=True)
    uploaded_files = st.file_uploader("📄 アンケートのPDFファイルをアップロードしてください（複数選択可）", type=["pdf"], accept_multiple_files=True)
    st.markdown('</div>', unsafe_allow_html=True)

    prompt_text = """
    あなたはデータ入力のスペシャリストです。提供されたアンケート画像から、以下の項目を正確に読み取り、必ず指定されたJSONフォーマットのみで出力してください。
    マークされていない、または無記入の項目は空文字 "" としてください。数値は数字のみを出力してください（例: "5"）。

    【出力JSONフォーマット】
    {
      "Q1_日時": "MM月DD日 HH時",
      "Q2_同伴者": "ご家族/友人知人/カップル/ひとり/その他 のいずれか",
      "Q3_来店回数": "はじめて/2回/3回以上 のいずれか",
      "Q4_来店きっかけ": "ホームページ/パークガイド/看板/口コミ/通りすがり/その他",
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
      "自由記述_分類": "ポジティブ / ネガティブ・改善要望 / その他 / 無記入"
    }
    """

    if uploaded_files and api_key:
        if st.button("🚀 一括読み取り＆データベース保存を開始する"):
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-flash-latest', generation_config={"response_mime_type": "application/json"})
            
            all_results = []
            progress_bar = st.progress(0, text="PDFを解析中...")
            total_pages = sum([fitz.open(stream=f.read(), filetype="pdf").page_count for f in uploaded_files])
            for f in uploaded_files: f.seek(0)
                
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
                        
                        # 登録月を抽出（月別管理用）
                        month_str = "不明"
                        if "Q1_日時" in result_json and "月" in result_json["Q1_日時"]:
                            month_str = result_json["Q1_日時"].split("月")[0] + "月"
                            
                        result_json["登録月"] = month_str
                        result_json["元ファイル名"] = f"{file.name} (P.{page_num+1})"
                        all_results.append(result_json)
                    except Exception as e:
                        st.error(f"{file.name} (P.{page_num+1}) でエラー: {e}")
                    
                    current_page_num += 1
                    progress_bar.progress(current_page_num / total_pages, text=f"処理中... ({current_page_num}/{total_pages}ページ完了)")
                    time.sleep(4) # スピード制限回避
            
            progress_bar.empty()
            
            if all_results:
                df = pd.DataFrame(all_results)
                # 列の並び替え（登録月と元ファイル名を先頭付近に）
                cols = df.columns.tolist()
                cols = ['登録月', 'Q1_日時', '元ファイル名'] + [c for c in cols if c not in ['登録月', 'Q1_日時', '元ファイル名']]
                df = df[cols]
                
                # スプレッドシートへ自動保存
                with st.spinner('データベースに保存しています...'):
                    success = save_to_spreadsheet(df)
                
                if success:
                    st.success("🎉 読み取りとデータベースへの保存が完了しました！")
                    st.info("上の「表示する画面を選んでください」から「📊 過去のデータを月別・一括で分析する」を選ぶと、今まで保存したすべてのデータが見られます。")

elif app_mode == "📊 過去のデータを月別・一括で分析する":
    st.markdown('<div class="pop-container">', unsafe_allow_html=True)
    st.subheader("📚 スプレッドシート・データベース")
    
    with st.spinner('過去のデータを取得しています...'):
        db_df = load_from_spreadsheet()
    
    if db_df.empty:
        st.warning("まだ保存されているデータがありません。「🆕 新しいアンケートを読み込む」からデータを追加してください。")
    else:
        # 月別絞り込み機能
        months = ["すべての月"] + sorted(list(db_df["登録月"].unique()))
        selected_month = st.selectbox("📅 分析する月を選んでください", months)
        
        if selected_month != "すべての月":
            db_df = db_df[db_df["登録月"] == selected_month]
            
        st.success(f"総データ数: {len(db_df)}件 のアンケートを表示しています")
        
        tab1, tab2, tab3 = st.tabs(["📊 データ一覧表", "📈 グラフ分析", "⚠️ ご意見まとめ"])
        
        with tab1:
            st.dataframe(db_df, use_container_width=True)
            csv = db_df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button("📥 表示中のデータをCSVでダウンロード", data=csv, file_name='smile_kitchen_db.csv', mime='text/csv')
        
        with tab2:
            col1, col2 = st.columns(2)
            pop_colors = px.colors.qualitative.Pastel
            with col1:
                if "Q3_来店回数" in db_df.columns:
                    q3_counts = db_df["Q3_来店回数"].value_counts().reset_index()
                    q3_counts.columns = ['来店回数', '件数']
                    fig_q3 = px.pie(q3_counts, names='来店回数', values='件数', title='ご来店回数の割合', color_discrete_sequence=pop_colors)
                    st.plotly_chart(fig_q3, use_container_width=True)
            with col2:
                if "Q2_同伴者" in db_df.columns:
                    q2_counts = db_df["Q2_同伴者"].value_counts().reset_index()
                    q2_counts.columns = ['同伴者', '件数']
                    fig_q2 = px.pie(q2_counts, names='同伴者', values='件数', title='ご同伴者の割合', color_discrete_sequence=pop_colors)
                    st.plotly_chart(fig_q2, use_container_width=True)

            st.divider()
            st.subheader("各評価の平均スコア (5点満点)")
            metrics = ["Q7_料理評価", "Q7_接客評価", "Q7_店舗評価", "Q9_再来店意向", "Q10_推奨意向", "Q11_満足度"]
            metrics_icons = ["🍔 料理", "👩‍🍳 接客", "🏪 店舗", "🔁 再来店", "📢 推奨", "😊 満足度"]
            avg_data = []
            for i, m in enumerate(metrics):
                if m in db_df.columns:
                    numeric_s = pd.to_numeric(db_df[m].astype(str).str.extract(r'(\d+)')[0], errors='coerce')
                    avg_val = numeric_s.mean()
                    if pd.notna(avg_val):
                        avg_data.append({"評価項目": metrics_icons[i], "平均スコア": round(avg_val, 2)})
            
            if avg_data:
                df_avg = pd.DataFrame(avg_data)
                fig_avg = px.bar(df_avg, x='評価項目', y='平均スコア', range_y=[0, 5], text='平均スコア', color='平均スコア', color_continuous_scale='Reds')
                st.plotly_chart(fig_avg, use_container_width=True)

        with tab3:
            st.markdown("### ⚠️ 改善要望・ネガティブなご意見")
            if "自由記述_分類" in db_df.columns:
                negatives = db_df[db_df["自由記述_分類"].astype(str).str.contains("ネガティブ|改善", na=False)]
                if not negatives.empty:
                    for idx, row in negatives.iterrows():
                        st.warning(f"**⏰ {row['Q1_日時']}** \n\n> {row['自由記述']}")
                else:
                    st.success("✨ ネガティブなご意見や改善要望はありませんでした！")
                
                st.divider()
                st.markdown("### 🥰 ポジティブ・その他のご意見")
                positives = db_df[~db_df["自由記述_分類"].astype(str).str.contains("ネガティブ|改善", na=False)]
                positives = positives[positives["自由記述"].astype(str).str.strip() != ""]
                if not positives.empty:
                    for idx, row in positives.iterrows():
                        st.info(f"**⏰ {row['Q1_日時']}** \n\n> {row['自由記述']}")
    st.markdown('</div>', unsafe_allow_html=True)
