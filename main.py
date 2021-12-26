import os
import pathlib
import re
import shutil
import urllib.parse

import pandas as pd
import plotly.figure_factory as ff
import requests
import tweepy

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

    parm = urllib.parse.urlencode(d, encoding="shift-jis")
    r = requests.get("https://www.tele.soumu.go.jp/musen/list", parm)

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

    lst = re.findall("(\S+)\(([0-9,]+)\)", s)

    df0 = pd.DataFrame(lst, columns=["name", "count"])
    df0["count"] = df0["count"].str.strip().str.replace(",", "").astype(int)

    flag = df0["name"].str.endswith(("都", "道", "府", "県"))

    df0["pref"] = df0["name"].where(flag).fillna(method="ffill")

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

df1 = df0.fillna(0).astype(int).reset_index()

if update4G == update_mil == update_sub:

    fromPath = pathlib.Path("csv", f"{update4G}.csv")
    fromPath.parent.mkdir(parents=True, exist_ok=True)

    # 上書き対策
    if not fromPath.exists():

        imgPath = pathlib.Path("img", "table.png")
        imgPath.parent.mkdir(parents=True, exist_ok=True)

        fig = ff.create_table(df1)
        fig.write_image(str(imgPath), engine="kaleido", scale=10)

        df1.to_csv(str(fromPath), encoding="utf_8_sig")

        toPath = pathlib.Path("csv", "latest.csv")
        shutil.copy(fromPath, toPath)

        # Twitter

        consumer_key = os.environ["CONSUMER_KEY"]
        consumer_secret = os.environ["CONSUMER_SECRET"]
        access_token = os.environ["ACCESS_TOKEN"]
        access_token_secret = os.environ["ACCESS_TOKEN_SECRET"]
        bearer_token = os.environ["BEARER_TOKEN"]

        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_token_secret)

        api = tweepy.API(auth)

        image_id = api.media_upload("ehime.png").media_id

        twit = f"{update4G}現在\n\n愛媛県の楽天モバイルの基地局数"

        api.update_status(status=twit, media_ids=[image_id])
