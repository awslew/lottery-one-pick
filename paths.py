# -*- coding: utf-8 -*-
"""路径与数据源统一解析 —— 所有脚本只从这里拿路径，不写死绝对路径。

数据表查找顺序（第一个存在的即被采用）：
    ① 环境变量 DLT_DATA 指向的文件
    ② <仓库根>/data/大乐透历史开奖数据.xlsx
    ③ <当前工作目录>/大乐透历史开奖数据.xlsx

克隆仓库后无需任何配置即可直接运行；把表放在别处时，设 DLT_DATA 即可：
    Windows :  set DLT_DATA=D:\\我的数据\\开奖.xlsx
    macOS/Linux :  export DLT_DATA=~/我的数据/开奖.xlsx
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# 全项目唯一「主开关」的宿主文件名：各脚本的默认期号都从它读取
MAIN_SWITCH_FILE_NAME = "dlt_pick_one.py"

DEFAULT_DATA_NAME = "大乐透历史开奖数据.xlsx"


def find_data_file():
    """按顺序解析数据表路径，找不到时给出可操作的提示。"""
    env = os.environ.get("DLT_DATA", "").strip()
    candidates = []
    if env:
        candidates.append(os.path.abspath(os.path.expanduser(env)))
    candidates.append(os.path.join(DATA_DIR, DEFAULT_DATA_NAME))
    candidates.append(os.path.join(os.getcwd(), DEFAULT_DATA_NAME))

    for path in candidates:
        if os.path.isfile(path):
            return path

    raise SystemExit(
        "✗ 找不到历史开奖数据表，按以下任一方式提供：\n"
        f"    ① 设环境变量 DLT_DATA 指向你的表（当前值：{env or '未设置'}）\n"
        f"    ② 把表放到 {os.path.join(DATA_DIR, DEFAULT_DATA_NAME)}\n"
        f"    ③ 把表放到当前工作目录：{os.path.join(os.getcwd(), DEFAULT_DATA_NAME)}\n"
        "  首次使用可先跑 python update_excel.py 生成数据表。"
    )


def read_main_switch():
    """读主开关 dlt_pick_one.py 顶部的 CURRENT_PERIOD。

    注意：这里是**读文件源码**（正则取常量），不是 import —— 该文件带执行主体，
    import 它会把整期出号流程跑一遍。
    """
    import re

    path = os.path.join(BASE_DIR, MAIN_SWITCH_FILE_NAME)
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        raise SystemExit(f"✗ 读不到主开关文件：{path}（{e}）")
    m = re.search(r'^CURRENT_PERIOD\s*=\s*"(\d+)"', src, re.M)
    if not m:
        raise SystemExit(f'✗ 主开关文件里找不到 CURRENT_PERIOD = "NNNNN"：{path}')
    return m.group(1)
