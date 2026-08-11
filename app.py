import streamlit as st
import fitz  # PyMuPDF
from PIL import Image
import io
import json
import pandas as pd
import plotly.express as px
import google.generativeai as genai

st.set_page_config(layout="wide", page_title="アンケート一括集計アプリ")
st.title("Smile Kitchen アンケート一括自動集計アプリ")

# 1. APIキーの設定
st.sidebar.header("設定")
# Streamlitのシステムに保存されたキーがあればそれを使い、無ければ入力欄を表示する
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    st.sidebar.success("✅ APIキーは自動で読み込まれました")
else:
    api_key = st.sidebar.text_input("Gemini APIキーを入力してください", type="password")
    st.sidebar.markdown("[APIキーの無料取得はこちら(Google AI Studio)](https://aistudio.google.com/app/apikey)")
# 2. 複数PDFのアップロード
uploaded_files = st.file_uploader(
    "アンケートのPDFファイルをアップロードしてください（複数選択可）", 
    type=["pdf"], 
    accept_multiple_files=True
)

# 【変更点】自由記述の「感情分類」をAIに判定させるよう指示を追加
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
    if st.button("一括読み取りを開始する"):
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
        
        progress_bar.empty()
        st.success("すべての読み取りが完了しました！")
        
        if all_results:
            df = pd.DataFrame(all_results)
            cols = df.columns.tolist()
            cols = cols[-1:] + cols[:-1]
            df = df[cols]
            
            # 【変更点】Q1_日時から「〇月〇日」の部分だけを抽出して新しい列を作る
            if "Q1_日時" in df.columns:
                df['抽出日付'] = df['Q1_日時'].astype(str).str.extract(r'(\d{1,2}月\d{1,2}日)')
                df['抽出日付'] = df['抽出日付'].fillna('日付不明')
            
            tab1, tab2, tab3 = st.tabs(["📊 データ一覧表", "📈 日別・傾向グラフ分析", "⚠️ ご意見・改善要望まとめ"])
            
            with tab1:
                st.dataframe(df)
                csv = df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 データをCSV（Excel用）でダウンロード",
                    data=csv,
                    file_name='smile_kitchen_survey_data.csv',
                    mime='text/csv',
                )
            
            with tab2:
                # 【変更点】日別集計グラフの追加
                st.subheader("📅 日別のアンケート回収数")
                if "抽出日付" in df.columns:
                    date_counts = df[df['抽出日付'] != '日付不明']['抽出日付'].value_counts().reset_index()
                    date_counts.columns = ['日付', '件数']
                    date_counts = date_counts.sort_values('日付')
                    
                    if not date_counts.empty:
                        fig_date = px.bar(date_counts, x='日付', y='件数', title='日別回収数', text_auto=True)
                        st.plotly_chart(fig_date, use_container_width=True)
                    else:
                        st.info("日付データが読み取れませんでした。")

                st.divider()
                
                st.subheader("主要な回答の傾向")
                col1, col2 = st.columns(2)
                
                with col1:
                    if "Q3_来店回数" in df.columns:
                        q3_counts = df["Q3_来店回数"].value_counts().reset_index()
                        q3_counts.columns = ['来店回数', '件数']
                        fig_q3 = px.pie(q3_counts, names='来店回数', values='件数', title='ご来店回数の割合')
                        st.plotly_chart(fig_q3, use_container_width=True)
                
                with col2:
                    if "Q2_同伴者" in df.columns:
                        q2_counts = df["Q2_同伴者"].value_counts().reset_index()
                        q2_counts.columns = ['同伴者', '件数']
                        fig_q2 = px.pie(q2_counts, names='同伴者', values='件数', title='ご同伴者の割合')
                        st.plotly_chart(fig_q2, use_container_width=True)

                st.divider()
                st.subheader("各評価の平均スコア (5点満点)")
                
                metrics = ["Q7_料理評価", "Q7_接客評価", "Q7_店舗評価", "Q9_再来店意向", "Q10_推奨意向", "Q11_満足度"]
                avg_data = []
                for m in metrics:
                    if m in df.columns:
                        numeric_s = pd.to_numeric(df[m].astype(str).str.extract(r'(\d+)')[0], errors='coerce')
                        avg_val = numeric_s.mean()
                        if pd.notna(avg_val):
                            avg_data.append({"評価項目": m, "平均スコア": round(avg_val, 2)})
                
                if avg_data:
                    df_avg = pd.DataFrame(avg_data)
                    fig_avg = px.bar(df_avg, x='評価項目', y='平均スコア', range_y=[0, 5], text='平均スコア', color='平均スコア', color_continuous_scale='Blues')
                    st.plotly_chart(fig_avg, use_container_width=True)

            with tab3:
                # 【変更点】ネガティブな意見とポジティブな意見を分類して表示
                st.subheader("お客様からの自由記述・ご意見")
                
                if "自由記述" in df.columns and "自由記述_分類" in df.columns:
                    # 空欄を除外
                    df_opinions = df[df["自由記述"].str.strip() != ""]
                    
                    # ネガティブ・改善要望を抽出して赤・黄色系のボックスで表示
                    negatives = df_opinions[df_opinions["自由記述_分類"].str.contains("ネガティブ|改善", na=False)]
                    st.markdown("### ⚠️ 改善要望・ネガティブなご意見")
                    if not negatives.empty:
                        for idx, row in negatives.iterrows():
                            # Q1_日時も合わせて表示して、いつの意見か分かりやすくする
                            st.warning(f"**{row['Q1_日時']}** (ファイル: {row['元ファイル名']})\n\n> {row['自由記述']}")
                    else:
                        st.success("ネガティブなご意見や改善要望はありませんでした！")
                    
                    st.divider()
                    
                    # ポジティブ・その他の意見を抽出して青系のボックスで表示
                    positives = df_opinions[~df_opinions["自由記述_分類"].str.contains("ネガティブ|改善", na=False)]
                    st.markdown("### ✨ ポジティブ・その他のご意見")
                    if not positives.empty:
                        for idx, row in positives.iterrows():
                            st.info(f"**{row['Q1_日時']}** (ファイル: {row['元ファイル名']})\n\n> {row['自由記述']}")
                else:
                    st.info("自由記述のデータがありません。")

elif uploaded_files and not api_key:
    st.warning("左側のサイドバーにGemini APIキーを入力してください。")
