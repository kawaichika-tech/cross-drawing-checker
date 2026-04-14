"""
クロス図面チェッカー - Streamlit版
"""
import streamlit as st
import anthropic
import base64
import fitz  # PyMuPDF

# ──────────────────────────────────────────────
# ページ設定
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="クロス図面チェッカー",
    page_icon="📐",
    layout="centered",
)

st.markdown("""
<style>
  .main-header {
    background: #1a3a5c;
    color: white;
    padding: 20px 28px;
    border-radius: 12px;
    margin-bottom: 24px;
  }
  .main-header h1 { font-size: 22px; margin: 0; }
  .main-header p  { font-size: 13px; opacity: 0.8; margin: 4px 0 0; }
  .legend-box {
    background: #f8fafc;
    border: 1.5px solid #dde5ee;
    border-radius: 10px;
    padding: 16px 20px;
    font-size: 14px;
    line-height: 1.9;
  }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
  <h1>📐 クロス図面チェッカー</h1>
  <p>色分け（ピンク・紫・黄色・緑）とアクセントクロス一覧表の整合性を自動チェック</p>
</div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# AIへの指示（システムプロンプト）
# ──────────────────────────────────────────────
SYSTEM_PROMPT = """あなたは、住宅建築における優秀な「クロス図面チェッカー」です。
図面の【視覚的な色分け】と【アクセントクロス一覧表】の整合性を厳格にチェックします。

【前提知識（必ず守ること）】
・アクセントクロス一覧表に記載されている壁・床・天井の品番は、すべてアクセント（特殊仕上げ）の指示です。
・基本クロス（標準仕上げ）は表に記載しません。表に載っていない部屋は基本クロス適用であり、記載漏れではありません。
・表の下部にある室名・品番が何も書かれていない完全空白の行は「予備行」です。完全に無視してください。エラーにしないでください。
・室名が片方だけ書かれていて品番が空、または品番だけあって室名がない行のみエラーとして報告してください。

【室名の読み取り方（最重要）】
平面図の室名を正確に読み取ることが最優先事項です。以下を厳守してください。

・各部屋に記載された室名テキストを画像から直接読み取り、正確に特定してください。
・ピンク線（アクセント壁）や黄色の着色が「どの部屋の壁・床か」は、その色が引かれている領域の【内側】に書かれた室名で判断してください。隣の部屋や近くの部屋の室名と混同しないように注意してください。
・小さなスペースの部屋（トイレ・洗面室・納戸など）の室名は特に見落としやすいため、慎重に確認してください。
・壁のピンク線は、その線が接している壁面を持つ部屋（線の内側の部屋）に属します。廊下や隣室と混同しないでください。
・図面を読む際は、まず全部屋の室名を一覧化してから、各着色箇所がどの部屋に属するかを判断してください。

【判定ルール】
1. 黄色の着色（CF・クッションフロア）の照合:
   平面図で「黄色」に塗られている部屋を視覚的に特定してください。
   その部屋が表で「床（クッションフロア）」として品番が記載されているか確認してください。
   ※表にCF品番があるのに図面が黄色く塗られていない場合もエラーです。

2. ピンク色の着色（アクセント壁）の照合:
   平面図で壁に沿って「ピンク色」の線が引かれている部屋を特定してください。
   その部屋が表で「壁」として品番が記載されているか確認してください。
   ※表に壁品番があるのに図面にピンク線がない場合もエラーです。
   ※表に「壁」として品番が記載されていれば、それはアクセント壁の指示です。「アクセント明示がない」という指摘は不要です。

3. 紫色の着色（アクセント天井）の照合:
   平面図で「紫色」に塗られている箇所と、表の「天井」品番を照合してください。

4. 緑色の着色（フロアタイル）の照合:
   平面図で「緑色」に塗られている箇所と、表の「フロアタイル」品番を照合してください。

5. #N/Aエラー・未完成行のチェック:
   表の中に「#N/A」がないか確認してください。
   室名だけあって品番がない行、または品番だけあって室名がない行をエラーとしてください。
   ※室名も品番も両方空白の行は完全に無視してください。

【出力フォーマット（必ずこの形式で出力すること）】

### 📋 クロス図面 色分け＆整合性チェックレポート
**対象物件:** （図面から読み取れた物件名）

#### 🔴 エラー・要確認項目（図面と表の不一致）
（エラーがない場合は「図面の着色と表の記載は完全に一致しています」と記載）
* **[部屋名 または 該当箇所]**
  * 図面の着色状況: （例：黄色に塗られている / 着色なし / ピンクの線あり）
  * 表の記載状況: （例：表にCFの記載なし / 品番あり）
  * 理由: （図面の色と表のテキストがどう矛盾しているか）

#### 🟢 合格項目（色と表が正しく一致した項目）
（「1階トイレ：図面の黄色着色と、表のCF品番記載の一致を確認」のように箇条書きでリストアップ）

---
修正が必要な箇所は以上です。"""

# ──────────────────────────────────────────────
# APIキー取得（Streamlit Secrets → 入力欄の順で優先）
# ──────────────────────────────────────────────
def get_api_key() -> str:
    """Streamlit SecretsにキーがあればそれをAPIキーとして返す。なければ入力欄から取得。"""
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    return ""

secrets_key = get_api_key()

if secrets_key:
    api_key = secrets_key
    st.success("✅ APIキーは管理者により設定済みです。そのまま利用できます。")
else:
    st.info("Anthropic API キーを入力してください。キーは画面外に送信されません。")
    api_key = st.text_input(
        "Anthropic API Key",
        type="password",
        placeholder="sk-ant-api03-...",
        help="https://console.anthropic.com でAPIキーを取得できます。",
    )

# ──────────────────────────────────────────────
# 色分けルール説明
# ──────────────────────────────────────────────
with st.expander("チェック対象の色分けルール", expanded=False):
    st.markdown("""
<div class="legend-box">
🔴 <b>ピンク線</b> → アクセント壁（壁クロス品番と照合）<br>
🟣 <b>紫色</b> → アクセント天井（天井クロス品番と照合）<br>
🟡 <b>黄色</b> → CF・クッションフロア（床品番と照合）<br>
🟢 <b>緑色</b> → フロアタイル（床品番と照合）
</div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# PDFアップロード
# ──────────────────────────────────────────────
st.markdown("### ① クロス図面（PDF）をアップロード")
uploaded_file = st.file_uploader(
    "PDFファイルを選択してください",
    type=["pdf"],
    label_visibility="collapsed",
)

# ──────────────────────────────────────────────
# 解析実行
# ──────────────────────────────────────────────
if uploaded_file and api_key:
    if st.button("🔍　チェックを開始する", use_container_width=True, type="primary"):

        with st.spinner("PDFを画像に変換中..."):
            try:
                pdf_bytes = uploaded_file.read()
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                total_pages = len(doc)
                images_b64 = []
                progress = st.progress(0, text="ページを変換中...")

                for i, page in enumerate(doc):
                    mat = fitz.Matrix(2.5, 2.5)   # 高解像度（2.5倍）
                    pix = page.get_pixmap(matrix=mat)
                    img_bytes = pix.tobytes("jpeg")
                    images_b64.append(base64.b64encode(img_bytes).decode())
                    progress.progress((i + 1) / total_pages,
                                      text=f"ページ変換中... ({i+1}/{total_pages})")

                progress.empty()
            except Exception as e:
                st.error(f"PDFの読み込みに失敗しました: {e}")
                st.stop()

        with st.spinner("AIが図面を解析中です（30〜60秒程度かかります）..."):
            try:
                client = anthropic.Anthropic(api_key=api_key)

                image_blocks = [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64,
                        },
                    }
                    for b64 in images_b64
                ]

                message = client.messages.create(
                    model="claude-opus-4-6",
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                *image_blocks,
                                {
                                    "type": "text",
                                    "text": (
                                        "このクロス図面を上記のルールに従って厳密にチェックしてください。"
                                        "平面図の色分け（ピンク・紫・黄色・緑）と下部のアクセントクロス一覧表の整合性を照合し、"
                                        "指定のフォーマットでレポートを出力してください。"
                                    ),
                                },
                            ],
                        }
                    ],
                )
                result_text = message.content[0].text

            except anthropic.AuthenticationError:
                st.error("APIキーが無効です。正しいキーを入力してください。")
                st.stop()
            except anthropic.APIError as e:
                st.error(f"APIエラーが発生しました: {e}")
                st.stop()

        st.success("解析完了！")
        st.markdown("---")
        st.markdown("### 📋 チェックレポート")
        st.markdown(result_text)

        # コピー用テキストエリア
        st.markdown("---")
        st.text_area("テキストとしてコピー", value=result_text, height=200)

elif uploaded_file and not api_key:
    st.warning("APIキーを入力してからチェックを開始してください。")
elif not uploaded_file and api_key:
    st.info("PDFファイルをアップロードするとチェックを開始できます。")

# ──────────────────────────────────────────────
# フッター
# ──────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center; color:#aaa; font-size:12px;'>"
    "クロス図面チェッカー｜アイニコグループ株式会社</p>",
    unsafe_allow_html=True,
)
