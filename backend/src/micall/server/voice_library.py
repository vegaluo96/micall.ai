"""MiniMax 系统（免费）音色库 —— 真实可用的 voice_id 清单，后台「音色」页据此展示与试听。

这些是 MiniMax T2A（speech-2.x 系列）的系统预置音色：调用 TTS 时可直接作为 voice_id 使用，
无需声音克隆/额外授权，属「免费」系统音色。运营在后台试听后，把某个 voice_id 填进角色的
「默认音色」即可启用。清单作为内置基础数据；若个别 ID 随供应商版本调整，可在此增删。

字段：voice_id（传给 TTS 的真实 ID）/ name（中文名）/ gender（性别）/ group（分组，便于检索）。
"""
from __future__ import annotations

# (voice_id, 中文名, 性别, 分组)
_SYSTEM: list[tuple[str, str, str, str]] = [
    # 青年 / 成熟（基础版）
    ("male-qn-qingse", "青涩青年", "男声", "青年"),
    ("male-qn-jingying", "精英青年", "男声", "青年"),
    ("male-qn-badao", "霸道青年", "男声", "青年"),
    ("male-qn-daxuesheng", "青年大学生", "男声", "青年"),
    ("female-shaonv", "少女", "女声", "少女"),
    ("female-yujie", "御姐", "女声", "御姐"),
    ("female-chengshu", "成熟女性", "女声", "成熟"),
    ("female-tianmei", "甜美女性", "女声", "甜美"),
    # 精品版（音质更佳）
    ("male-qn-qingse-jingpin", "青涩青年·精品", "男声", "青年"),
    ("male-qn-jingying-jingpin", "精英青年·精品", "男声", "青年"),
    ("male-qn-badao-jingpin", "霸道青年·精品", "男声", "青年"),
    ("male-qn-daxuesheng-jingpin", "青年大学生·精品", "男声", "青年"),
    ("female-shaonv-jingpin", "少女·精品", "女声", "少女"),
    ("female-yujie-jingpin", "御姐·精品", "女声", "御姐"),
    ("female-chengshu-jingpin", "成熟女性·精品", "女声", "成熟"),
    ("female-tianmei-jingpin", "甜美女性·精品", "女声", "甜美"),
    # 主持 / 有声书
    ("presenter_male", "男性主持人", "男声", "主持"),
    ("presenter_female", "女性主持人", "女声", "主持"),
    ("audiobook_male_1", "男性有声书 1", "男声", "有声书"),
    ("audiobook_male_2", "男性有声书 2", "男声", "有声书"),
    ("audiobook_female_1", "女性有声书 1", "女声", "有声书"),
    ("audiobook_female_2", "女性有声书 2", "女声", "有声书"),
    # 童声
    ("clever_boy", "聪明男童", "男声", "童声"),
    ("cute_boy", "可爱男童", "男声", "童声"),
    ("lovely_girl", "萌萌女童", "女声", "童声"),
    ("cartoon_pig", "卡通猪小琪", "中性", "童声"),
    # 剧情角色
    ("junlang_nanyou", "俊朗男友", "男声", "剧情"),
    ("bingjiao_didi", "病娇弟弟", "男声", "剧情"),
    ("chunzhen_xuedi", "纯真学弟", "男声", "剧情"),
    ("lengdan_xiongzhang", "冷淡学长", "男声", "剧情"),
    ("badao_shaoye", "霸道少爷", "男声", "剧情"),
    ("tianxin_xiaoling", "甜心小玲", "女声", "剧情"),
    ("qiaopi_mengmei", "俏皮萌妹", "女声", "剧情"),
    ("wumei_yujie", "妩媚御姐", "女声", "剧情"),
    ("diadia_xuemei", "嗲嗲学妹", "女声", "剧情"),
    ("danya_xuejie", "淡雅学姐", "女声", "剧情"),
]


def system_voice_library() -> list[dict]:
    """返回 MiniMax 系统（免费）音色清单（新列表，调用方可安全改）。"""
    return [
        {"voice_id": vid, "name": name, "gender": gender, "group": group, "lang": "中文", "engine": "MiniMax"}
        for (vid, name, gender, group) in _SYSTEM
    ]


def voice_ids() -> set[str]:
    return {vid for (vid, *_rest) in _SYSTEM}
