"""
Original: https://github.com/k141303/shinra_jp_scorer/blob/master/scoring.py
"""
import json
import csv
import argparse
import os
from collections import defaultdict

#属性名の修正リスト(shinra2020現在)
REPLACE_LIST = {
    "1.6.4.2": {"軍備": "DEL"},  # Facility:Castle
    "1.6.4.15": {"閉館年": "閉園年"},  # Facility:Zoo
    "1.1": {"職業": "地位職業"},  # JP-5:Person
    "1.6.6.0": {"停車場名": "停車場"}  # Facility:Line_Other
}

#アノテーション取得


def get_annotation(path):
    with open(path, "r", encoding="utf_8") as f:
        return [json.loads(line) for line in f.readlines()]

#wikipediaのデータ取得


def get_wiki(path, page_id, extension="txt"):
    try:
        with open("{}/{}.{}".format(path, page_id, extension), "r", encoding="utf_8") as f:
            return f.read()
    except FileNotFoundError:
        return None

#targetのリストを取得


def get_target(path):
    target = []
    with open(path, "r", encoding="utf_8") as f:
        reader = csv.reader(f)
        for row in reader:
            target += row
    return target


def out_csv(path, tables, name):
    """
    csvの書き出し
    """
    if not os.path.exists(path):
        os.mkdir(path)
    for offset_type, table in tables.items():
        with open("{}/{}_{}.csv".format(path, offset_type, name), "w") as f:
            writer = csv.writer(f, lineterminator="\n")  # 改行コード（\n）を指定しておく
            writer.writerows(table)  # 2次元配列も書き込める


def out_score(path, score):
    """
    スコアの書き出し
    """
    tables = {}
    for offset_type, item in score.items():
        table = [["attribute", "precision", "recall", "F1"]]
        for attribute, item_ in item.items():
            table.append([attribute, item_["precision"],
                         item_["recall"], item_["F1"]])
        tables[offset_type] = table
    out_csv(path, tables, "score")


def get_ene(one_liner_dict):
    """
    データのeneを特定
    """
    enes = set()
    for line in one_liner_dict:
        ene = line.get("ENE")
        if ene is not None:
            enes.add(ene)

    #1つ以上のENEが含まれる場合、もしくは1つも含まれない場合にエラー
    if len(enes) != 1:
        raise Exception("The test data must contain one type of ENE.")

    return list(enes)[0]


def attribute_corrector(ene, attr):
    """
    バージョン間での属性名の統一(修正)
    eneはカテゴリー特定のために必要
    """
    attr = attr.translate(str.maketrans(
        {chr(0x0021 + i): chr(0xFF01 + i) for i in range(94)}))
    attr = REPLACE_LIST.get(ene, {}).get(attr, attr)
    return attr


def liner2dict(one_liner_dict, ene):
    """
    ワンライナーjsonをpage_idと属性名で整理した辞書に変換します。
    同時にHTML、プレーンテキストのどちらのオフセットを保持しているかのフラグ、
    全ての属性名のリストを返します。
    """
    id_dict = defaultdict(lambda: defaultdict(lambda: []))
    html, plain = False, False
    attributes = set()
    for line in one_liner_dict:
        page_id = str(line["page_id"])

        attribute = line["attribute"]
        attribute = attribute_corrector(ene, attribute)
        attributes.add(attribute)

        #html_offsetを持っていればhtmlフラグを立てる
        if not html and line.get("html_offset") is not None:
            html = True
        #text_offsetを持っていればplainフラグを立てる
        if not plain and line.get("text_offset") is not None:
            plain = True

        id_dict[page_id][attribute].append(line)

    return id_dict, html, plain, sorted(attributes)


def clean(id_dict, offset_type):
    """
    採点のためにid_dict上の不要な情報の削除
    """
    cleaned = defaultdict(lambda: defaultdict(lambda: []))
    for page_id, item in id_dict.items():
        for attribute, item_ in item.items():
            for item__ in item_:
                offset = item__[offset_type]
                #タプル化したオフセットのみ残す
                offset_tuple = (offset["start"]["line_id"],
                                offset["start"]["offset"],
                                offset["end"]["line_id"],
                                offset["end"]["offset"]
                                )
                cleaned[page_id][attribute].append(offset_tuple)
    return cleaned


def calc_score(count):
    """
    TP, FP, FNから再現率、精度、F値を計算
    """
    if count["TP"] == 0:
        #ZeroDivisionErrorを防ぐ
        return {"recall": 0, "precision": 0, "F1": 0}
    score = {}
    score["recall"] = count["TP"] / count["TPFN"]
    score["precision"] = count["TP"] / count["TPFP"]
    score["F1"] = 2 * score["recall"] * score["precision"] / \
        (score["recall"] + score["precision"])
    return score


def calc_macro(score):
    """
    属性名ごとのスコアからマクロ平均を計算
    """
    if len(score) == 0:
        return {"recall": 0, "precision": 0, "F1": 0}

    total = defaultdict(lambda: [])
    for item in score.values():
        for indicator, num in item.items():
            total[indicator].append(num)
    macro = {}
    for indicator, item in total.items():
        if len(item) == 0:
            macro[indicator] = 0
        else:
            macro[indicator] = sum(item)/len(item)
    return macro


def calc_micro(counter):
    """
    属性名ごとのTP,FN,FPからマクロ平均を計算
    """
    if len(counter) == 0:
        return {"recall": 0, "precision": 0, "F1": 0}

    total = defaultdict(lambda: [])
    for item in counter.values():
        for key, count in item.items():
            total[key].append(count)
    return calc_score({key: sum(item) for key, item in total.items()})


def scoring(answer, result, target, attributes, offset_type):
    """
    完全一致でスコアを計算
    """
    #採点のため答えと採点対象を簡略化
    answer = clean(answer, offset_type)
    result = clean(result, offset_type)

    #TP,FP,FNをカウント
    counter = defaultdict(lambda: {"TP": 0, "TPFP": 0, "TPFN": 0})
    for page_id, item in answer.items():
        if page_id not in target:
            #対象でない場合はスキップ
            continue
        for attribute in attributes:
            if result.get(page_id) is None or result[page_id].get(attribute) is None:
                res = []
            else:
                res = result[page_id][attribute]
            if item.get(attribute) is None:
                ans = []
            else:
                ans = item[attribute]
            counter[attribute]["TP"] += len(set(ans) & set(res))
            counter[attribute]["TPFP"] += len(set(res))
            counter[attribute]["TPFN"] += len(set(ans))

    #再現率、精度、F値を計算
    score = {attribute: calc_score(count)
             for attribute, count in counter.items()}

    #マクロ平均を計算
    score["macro_ave"] = calc_macro(score)

    #マイクロ平均を計算
    score["micro_ave"] = calc_micro(counter)

    return score


def diff(text, offsets, offset_type):
    """
    オフセット(リスト)からテキストを取得
    抽出されたテキストと保持しているテキストを比較
    違う場合はエラーログで返す
    """
    splitext = text.split("\n")
    error = []
    for offset in offsets:
        accum = ""
        for idx, line_id in enumerate(range(offset[offset_type]["start"]["line_id"], offset[offset_type]["end"]["line_id"]+1)):
            sol, eol = 0, len(splitext[line_id])
            if idx == 0:
                sol = offset[offset_type]["start"]["offset"]
            else:
                accum += "\n"
            if idx == offset[offset_type]["end"]["line_id"] - offset[offset_type]["start"]["line_id"]:
                eol = offset[offset_type]["end"]["offset"]
            accum += splitext[line_id][sol:eol]
        if accum != offset[offset_type]["text"]:
            error.append([offset["page_id"], "Different offset", offset["title"],
                          offset[offset_type]["start"]["line_id"],
                          offset[offset_type]["start"]["offset"],
                          offset[offset_type]["end"]["line_id"],
                          offset[offset_type]["end"]["offset"],
                          offset[offset_type]["text"],
                          accum])
    return error


def checker(path, result, extension="txt"):
    """
    オフセットとテキストのズレを確認
    """
    error = [["page_id", "error_type", "title", "start_lineid",
              "start_offset", "end_lineid", "end_offset", "text", "extracted_string"]]
    for page_id, item in result.items():
        text = get_wiki(path, page_id, extension=extension)
        if text is None:
            error.append([page_id, "Not Found"])
            continue
        offset_type = "text_offset" if extension == "txt" else "html_offset"
        offsets = []
        for attribute, item_ in item.items():
            offsets += item_
        error += diff(text, offsets, offset_type)
    return error


def print_score(score):
    print("System result score")
    for offset_type, item in score.items():
        print("({})".format(offset_type))
        print("|属性名|精度|再現率|F値|")
        print("|-|-|-|-|")
        for attribute, item_ in item.items():
            print("|{}|{:.3f}|{:.3f}|{:.3f}|".format(attribute,
                                                     item_["precision"],
                                                     item_["recall"],
                                                     item_["F1"]))


def get_score(answer, result, target=None, html_path=None, plain_path=None, error_path=None, score_path=None):
    """
    スコアを計算します。
    引数
      answer, result ,target(任意) ,html_path(任意) ,plain_path(任意)
        answer : 正答のリスト(ワンライナーjsonをリストとして読み込んだものと等価)
                 pathでも可
        result : システム結果のリスト
                 pathでも可
        target : 採点の対象とするpage_idのリスト(入力しない場合はresultに含まれるpage_idが対象になります。)
        html_path : HTMLファイルの場所(入力するとオフセットが合っているかを確認します)
        plain_path : プレーンテキストファイルの場所(同上)
        error_path : エラーログを指定したpathに書き出します。(任意)
        score_path : スコアログを指定したpathに書き出します。(任意)
    戻り値
      score
        score : スコア(html、プレーンでそれぞれのスコア格納した辞書)
      (HTML or プレーンテキストのパスが指定された場合)
      score, error
        score : 同上
        error : オフセットが間違っていた場合のエラー(html、プレーンでそれぞれのエラーを格納した辞書)
    """
    #正答とシステム結果の取得(answer,resultがファイルパスの場合)
    if isinstance(answer, str):
        answer = get_annotation(answer)
    if isinstance(result, str):
        result = get_annotation(result)
    if isinstance(target, str):
        if target[0] == "[":
            target = json_loads(target)
        else:
            target = get_target(target)

        target = [str(t) for t in target]

    #正答データのeneを取得
    ene = get_ene(answer)

    #辞書形式に変換(+属性名の統一・修正)
    answer, _, _, attributes = liner2dict(answer, ene)
    result, html_flag, plain_flag, _ = liner2dict(result, ene)

    #採点対象のpage_idを取得
    if target is None:
        target = list(answer.keys())

    if __name__ == "__main__":
        print("Number of scoring targets : {}".format(len(target)))
        print("Target : {}".format(("HTML" if html_flag else "")
                                   + (" & " if html_flag & plain_flag else "")
                                   + ("PLAIN" if plain_flag else "")))

    score = {}
    error = {}
    if html_flag:
        #スコアの計算
        score["html"] = scoring(answer, result, target,
                                attributes, "html_offset")
        if html_path is not None:
            #オフセットが合っているか確認
            error["html"] = checker(html_path, result, "html")
            if __name__ == "scoring":
                print("HTML annotation errors : {}".format(len(error["html"])))

    if plain_flag:
        #スコアの計算
        score["text"] = scoring(answer, result, target,
                                attributes, "text_offset")
        if plain_path is not None:
            #オフセットが合っているか確認
            error["text"] = checker(plain_path, result, "txt")
            if __name__ == "scoring":
                print("Text annotation errors : {}".format(len(error["text"])))

    # if __name__ == "scoring":
    #     print_score(score)

    # if score_path is not None:
    #     #スコアの書き出し
    #     out_score(score_path, score)

    if not error:  # オフセットの確認を行わない場合(html or plainのパスが指定されていない)
        return score

    if error_path is not None:
        #エラーログの書き出し
        out_csv(error_path, error, "error_log")

    return score, error
