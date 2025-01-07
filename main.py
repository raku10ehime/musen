import json
import os
import pathlib
import re
import shutil

import pandas as pd
import plotly.figure_factory as ff
import tweepy

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
}

rakuten4G = {
    # 1:免許情報検索  2: 登録情報検索
    "ST": 1,
    # 詳細情報付加 0:なし 1:あり
    "DA": 1,
    # スタートカウント
    "SC": 1,
    # 取得件数
    "DC": 1,
    # 出力形式 1:CSV 2:JSON 3:XML
    "OF": 2,
    # 無線局の種別
    "OW": "FB_H",
    # 所轄総合通信局
    "IT": "G",
    # 免許人名称/登録人名称
    "NA": "楽天モバイル",
}


def musen_api(d):

    d["IT"] = it

    r = requests.get("https://www.tele.soumu.go.jp/musen/list", params=d, headers=headers)
    r.raise_for_status()

    time.sleep(1)

    return r.json()


rakuten5G = {
    # 1:免許情報検索  2: 登録情報検索
    "ST": 1,
    # 詳細情報付加 0:なし 1:あり
    "DA": 0,
    # スタートカウント
    "SC": 1,
    # 取得件数
    "DC": 3,
    # 出力形式 1:CSV 2:JSON 3:XML
    "OF": 2,
    # 無線局の種別
    "OW": "FB",
    # 都道府県
    "HCV": 38000,
    # 免許人名称/登録人名称
    "NA": "楽天モバイル",
}


def select5G(d, start, end, unit):

    d["FF"] = start
    d["TF"] = end
    d["HZ"] = unit

    data = musen_api(d)

    df = pd.json_normalize(data, "musen").rename(columns={"listInfo.tdfkCd": "name"})

    se = df.value_counts("name")
    se.index = se.index.str.replace("愛媛県", "")

    return se, data["musenInformation"]["lastUpdateDate"]


def fetch_cities(s):

    lst = re.findall("(\S+)\s*\(([0-9,]+)\)", s)

    df0 = pd.DataFrame(lst, columns=["name", "count"])
    df0["count"] = df0["count"].str.strip().str.replace(",", "").astype(int)

    flag = df0["name"].str.endswith(("都", "道", "府", "県"))

    df0["pref"] = df0["name"].where(flag).ffill()

    df1 = df0[(df0["pref"] == "愛媛県") & (df0["name"] != "愛媛県")].copy().set_index("name")

    return df1["count"]


data4G = musen_api(rakuten4G)

update4G = data4G["musenInformation"]["lastUpdateDate"]

# マクロ局

macro = (
    data4G["musen"][0]["detailInfo"]["note"]
    .split("\\n", 2)[2]
    .replace("\\n", " ")
    .strip()
)

se_macro = fetch_cities(macro)

# フェムトセル

femto = (
    data4G["musen"][1]["detailInfo"]["note"]
    .split("\\n", 2)[2]
    .replace("\\n", " ")
    .strip()
)

se_femto = fetch_cities(femto)

# ミリ波

se_milli, update_mil = select5G(rakuten5G, 26.5, 29.5, 3)

# sub6

se_sub6, update_sub = select5G(rakuten5G, 3300, 4200, 2)

df0 = pd.concat(
    [
        se_macro.rename("マクロ"),
        se_femto.rename("フェムト"),
        se_milli.rename("ミリ波"),
        se_sub6.rename("sub6"),
    ],
    axis=1,
).rename_axis("市町村")

df1 = df0.fillna(0).astype(int)

if update4G == update_mil == update_sub:

    fromPath = pathlib.Path("csv", f"{update4G}.csv")
    fromPath.parent.mkdir(parents=True, exist_ok=True)

    # 上書き対策
    if not fromPath.exists():
        
        toPath = pathlib.Path("csv", "latest.csv")
        df2 = pd.read_csv(toPath, index_col=0).reindex(index=df1.index, fill_value=0)
        
        df3 = df1 - df2
        df3.index = df3.index.str.replace("^(越智郡|上浮穴郡|伊予郡|喜多郡|西宇和郡|北宇和郡|南宇和郡)", "", regex=True)
        
        text = "更新なし"

        if df3["マクロ"].sum() > 0:

            sr = df3.loc[df3["マクロ"] > 0, "マクロ"]

            cities = []

            for i, v in sr.items():
                cities.append(f"{i} {v:+}")

            text = "\n".join(cities)

            df1.to_csv(str(fromPath), encoding="utf_8_sig")

            shutil.copy(fromPath, toPath)

            # Twitter

            consumer_key = os.environ["CONSUMER_KEY"]
            consumer_secret = os.environ["CONSUMER_SECRET"]
            access_token = os.environ["ACCESS_TOKEN"]
            access_token_secret = os.environ["ACCESS_TOKEN_SECRET"]
            bearer_token = os.environ["BEARER_TOKEN"]

            twit = f"{update4G}現在\n\n愛媛県の楽天モバイルの基地局数\n\n{text}\n\nhttps://docs.google.com/spreadsheets/d/e/2PACX-1vTM3Ct_fcPG0JJIGu2ACn9XXws-RkY_lkbqT27-FNMC2n6w8HwCrvQVG0erSEOW0Gc0iMP2BnG4hR_T/pubhtml\n\n#楽天モバイル #愛媛 #基地局"

            client = tweepy.Client(
                bearer_token, consumer_key, consumer_secret, access_token, access_token_secret
            )
