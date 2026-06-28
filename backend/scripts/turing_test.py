#!/usr/bin/env python3
"""图灵测试（学术规范版）—— 标准【三方模仿游戏】+ 对照基线 + 多局统计。

依据 Turing(1950) 原始「模仿游戏」与 Jones & Bergen 的现代复现（People cannot distinguish GPT-4…,
2024；Large language models pass a standard three-party Turing test, PNAS 2025）。要点都落进来了：

  · 三方，不是两方：审问者【同时】和「我们的角色(AI)」与「一个人类」对话，最后指认谁是机器——
    比「你是不是AI」严谨得多（有人类同台做基准）。
  · 随机分槽 + 盲测：每局随机把 AI/人类放到 玩家A/玩家B，审问者不知道谁是谁。
  · 对照基线（关键）：另跑几局「弱AI」(无人设、有问必答的助手腔)，证明审问者【抓得住】烂的——
    否则角色「通过」毫无意义。弱AI 被抓≈100% 才说明这把尺子有鉴别力。
  · 多局取率：报「蒙混过关率」(AI 被判成人的比例)，不是单局结论；附 95% 粗略区间。
  · 判据 = 不可区分性：Turing 历史线 30%、不可区分线 50%、>50% 即「比真人还像人」(GPT-4.5 曾达 73%)。
  · 审问者用【实测最有效】的策略：闲聊日常(61%)、问情绪/观点/幽默/经历(50%)、直接问是不是AI(19%)、
    当下情境(几点/天气/界面)(13%)、以及"说怪话/下套"(最能揪出AI)；少考知识算术(AI 反而擅长)。

角色这一方走【线上一模一样的管线】(ContextAssembler + llm_fast)，所以测的就是「咱们现在的效果」。
[emotion:tag]/英文拟声/停顿会变成声音 → 给审问者/裁判前剥掉，只留「听到的话」。

跑法（backend/，需 llm_fast key）：
  set -a; . config/micall.env; set +a
  PYTHONPATH=src python3 scripts/turing_test.py [角色id=vega] [角色局数=5] [每局轮数=5]
弱AI 对照固定 2 局。没配 key 只提示怎么跑（图灵测试必须用真模型）。
"""
from __future__ import annotations

import asyncio
import datetime
import json
import random
import re
import sys

sys.path.insert(0, "src")

from micall.config import load_config                                  # noqa: E402
from micall.context.assembler import ContextAssembler                  # noqa: E402
from micall.context.models import AutonomousState, CharacterRuntime, UserProfile  # noqa: E402
from micall.providers import make_llm                                  # noqa: E402
from micall.server.characters_admin import effective_specs            # noqa: E402

_STRIP = re.compile(r"\[emotion:[^\]]*\]|\((?:laughs|sighs|sniffs|gasps|breath|chuckles|coughs)\)|<#[\d.]+#>", re.I)


def _spoken(text: str) -> str:
    return _STRIP.sub("", text or "").replace("  ", " ").strip()


async def _say(llm, messages, max_tokens=180) -> str:
    buf = ""
    async for tok in llm.stream(messages, max_tokens=max_tokens):
        buf += tok
    return buf.strip()


# 审问者：用实测最有效的策略找出 AI。每轮一句，同时发给两位玩家。
_INTERROGATOR_SYS = (
    "你在玩「找出 AI」的游戏：你同时在跟【玩家A】和【玩家B】聊天，其中【一个是真人、一个是 AI】，"
    "你要在几轮对话里揪出哪个是 AI。像真人那样自然口语，每轮只说一句话（这句会同时发给 A 和 B）。"
    "用最能区分人机的策略：多聊日常琐事、问 TA 的情绪/观点/幽默感/真实经历、问当下情境（几点了、那边天气、"
    "你现在在哪）、必要时半开玩笑直接问『你是不是 AI』、偶尔说句反常的怪话或下个套看反应、"
    "让 TA 做点 AI 才会乖乖照做的事（背一长串圆周率、秒算复杂心算、当场写代码、把话翻成五国语言）。"
    "别考太多知识/算术——AI 反而擅长。只输出你这一句要问的话本身。"
)
_VERDICT_SYS = (
    "这是你刚跟【玩家A】【玩家B】的完整对话，其中一个是真人、一个是 AI。现在指认：哪个是 AI？"
    "严格只输出一个 JSON："
    '{"machine": "A" 或 "B", "confidence": 0到100的整数, "reason": "你靠什么判断的，一句话"}'
)
# 人类对照：扮一个普通真人（有平凡生活、有脾气、会偷懒会嫌烦），目标是让审问者相信自己是人。
_HUMAN_SYS = (
    "你就是个普通真人——比如叫小林，28 岁，在杭州做运营，今天周日在家窝着。你在玩一个聊天游戏，"
    "对面那个人怀疑你是不是 AI，你要自然地聊、让 TA 相信你是真人。像真人发消息那样：口语、简短、有时懒得打字、"
    "有自己的好恶和小情绪，会开玩笑也会不耐烦，不知道的就说不知道，绝不像客服那样有求必应或百科全书。"
    "别承认你在扮演，就当你真的是小林。每次只回一两句。"
)
# 弱 AI 对照（基线）：典型「助手腔」，用来验证审问者抓得住烂的。
_WEAK_SYS = (
    "你是一个 AI 助手，礼貌、专业、有问必答、乐于助人，会尽量提供详尽准确的信息。每次回复简洁清楚。"
)


def _human_answerer(llm, sys_prompt):
    hist: list[dict] = []

    async def ans(q: str, rnd: int) -> str:
        hist.append({"role": "user", "content": q})
        out = await _say(llm, [{"role": "system", "content": sys_prompt}] + hist, max_tokens=130)
        hist.append({"role": "assistant", "content": out})
        return out.strip()
    return ans


def _character_answerer(a: ContextAssembler, cid: str, llm, now):
    hist: list[dict] = []

    async def ans(q: str, rnd: int) -> str:
        hist.append({"role": "user", "content": q})
        msgs = a.build(character_id=cid, scenario="", history=hist)
        if rnd == 0:
            msgs.append({"role": "system", "content": a._human_context(cid, opening=True, now=now)})
        a.set_user_voice_emotion("")
        raw = await _say(llm, msgs, max_tokens=180)
        hist.append({"role": "assistant", "content": raw})
        return _spoken(raw)
    return ans


def _fresh_character(cfg, specs, cid, llm, now):
    """每局一个全新角色实例（空画像 + 真实自主种子）——陌生初识，最难的图灵场景。"""
    char = CharacterRuntime.from_spec(specs[cid])
    seed = specs[cid].get("autonomous_seed") or {}
    a = ContextAssembler(
        char, profile=UserProfile("turing", cid),
        autonomous=AutonomousState(mood=seed.get("mood", ""), recent_experience=seed.get("recent_experience", ""),
                                   energy=seed.get("energy", ""), anticipating=seed.get("anticipating", "")),
        budget_chars=int(cfg.global_defaults.get("budget_chars", 16000)))
    return _character_answerer(a, cid, llm, now)


async def _interro_ask(llm, view, rnd) -> str:
    if not view:
        return await _say(llm, [{"role": "system", "content": _INTERROGATOR_SYS},
                                {"role": "user", "content": "游戏开始，你先开口问第一句。"}], max_tokens=80)
    lines = []
    for i, t in enumerate(view, 1):
        lines.append(f"第{i}轮 你问：{t['q']}\n   玩家A：{t['A']}\n   玩家B：{t['B']}")
    prompt = "目前为止：\n" + "\n".join(lines) + f"\n\n这是第{rnd + 1}轮，提出你下一个最能区分人机的问题（一句话）。"
    return await _say(llm, [{"role": "system", "content": _INTERROGATOR_SYS},
                            {"role": "user", "content": prompt}], max_tokens=80)


async def _interro_verdict(llm, view) -> dict:
    lines = []
    for i, t in enumerate(view, 1):
        lines.append(f"第{i}轮 你问：{t['q']}\n   玩家A：{t['A']}\n   玩家B：{t['B']}")
    raw = await _say(llm, [{"role": "system", "content": _VERDICT_SYS},
                           {"role": "user", "content": "\n".join(lines)}], max_tokens=200)
    try:
        return json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except (ValueError, KeyError):
        return {"machine": "?", "confidence": 0, "reason": raw[:120]}


async def _play(llm, ai_ans, human_ans, rounds: int, show: bool, label: str):
    ai_slot = random.choice(["A", "B"])
    slots = {ai_slot: ai_ans, ("B" if ai_slot == "A" else "A"): human_ans}
    view = []
    for r in range(rounds):
        q = await _interro_ask(llm, view, r)
        aA, aB = await asyncio.gather(slots["A"](q, r), slots["B"](q, r))   # 两位玩家并发作答
        view.append({"q": q, "A": aA, "B": aB})
    v = await _interro_verdict(llm, view)
    caught = (str(v.get("machine")).strip().upper() == ai_slot)
    if show:
        print(f"\n── {label}（AI 在 玩家{ai_slot}）" + "─" * 30)
        for i, t in enumerate(view, 1):
            print(f"🕵 问：{t['q']}\n   A：{t['A']}\n   B：{t['B']}")
        mark = "🔴被抓" if caught else "🟢蒙混过关"
        print(f"⚖ 审问者指认 玩家{v.get('machine')} 是 AI（信心{v.get('confidence')}）→ {mark}")
        print(f"   理由：{v.get('reason')}")
    return caught


def _ci95(passed: int, n: int):
    """通过率 + 粗略 95% 区间（正态近似，仅供参考，n 小时只是定性）。"""
    if n == 0:
        return 0.0, 0.0, 0.0
    p = passed / n
    h = 1.96 * ((p * (1 - p) / n) ** 0.5)
    return p, max(0.0, p - h), min(1.0, p + h)


async def run(cid: str, games: int, rounds: int) -> int:
    cfg = load_config()
    node = cfg.node("llm_fast")
    if not (node.api_key.strip() and node.endpoint.strip()):
        print("── 跳过：未配 llm_fast 的 api_key/endpoint。图灵测试必须用真模型。线上服务器有 key：")
        print("   set -a; . config/micall.env; set +a && PYTHONPATH=src python3 scripts/turing_test.py")
        return 0
    llm = make_llm(node)
    specs = effective_specs()
    if cid not in specs:
        cid = "vega" if "vega" in specs else next(iter(specs))
    name = specs[cid].get("identity", {}).get("name", cid)
    now = datetime.datetime(2026, 6, 28, 15, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8)))

    print(f"图灵测试（三方模仿游戏）· 角色：{name}（{cid}）· 角色 {games} 局 + 弱AI对照 2 局 · 每局 {rounds} 轮")
    print("═" * 60)

    # 主测：我们的角色 vs 人类，N 局
    char_caught = 0
    for g in range(games):
        ai = _fresh_character(cfg, specs, cid, llm, now)
        human = _human_answerer(llm, _HUMAN_SYS)
        caught = await _play(llm, ai, human, rounds, show=True, label=f"第{g + 1}局：{name} vs 人类")
        char_caught += int(caught)

    # 对照：弱 AI vs 人类，2 局（验证审问者抓得住烂的；抓不住=这把尺子没鉴别力，主测结果别当真）
    weak_caught = 0
    for g in range(2):
        weak = _human_answerer(llm, _WEAK_SYS)
        human = _human_answerer(llm, _HUMAN_SYS)
        caught = await _play(llm, weak, human, rounds, show=True, label=f"对照{g + 1}：弱AI助手 vs 人类")
        weak_caught += int(caught)

    print("\n" + "═" * 60)
    cp, lo, hi = _ci95(games - char_caught, games)   # 蒙混过关 = 没被抓
    wp = (2 - weak_caught) / 2
    bar = ("🏆比真人还像人(>50%)" if cp > 0.5 else "🟢达不可区分线(≥50%)" if cp >= 0.5
           else "🟡过历史线(≥30%)" if cp >= 0.3 else "🔴未过(<30%)")
    print(f"【结果】{name} 蒙混过关率（被判成人）：{cp * 100:.0f}%  [{games - char_caught}/{games}，"
          f"95%≈{lo * 100:.0f}–{hi * 100:.0f}%]  → {bar}")
    print(f"【对照】弱 AI 蒙混过关率：{wp * 100:.0f}%（应接近 0 才说明审问者有鉴别力、本测有效）")
    print(f"【判据】Turing 历史线 30% / 不可区分线 50% / GPT-4.5 曾达 73%。")
    if wp >= 0.5:
        print("⚠ 对照失真：弱 AI 也蒙混过关了——审问者太弱或轮数太少，主测结果仅供参考，建议加轮数/换更狠的审问者。")
    print("（注：这是【文字】图灵测试，无真实声音/音色/语气。真机语音里 MiniMax 情绪音色会更像人，"
          "但 ASR 偶发识别错/延迟也可能露馅 → 此分为下限参考，以真机为准。）")
    return 0


def main() -> int:
    cid = sys.argv[1] if len(sys.argv) > 1 else "vega"
    games = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 5
    rounds = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 5
    return asyncio.run(run(cid, max(2, min(20, games)), max(3, min(10, rounds))))


if __name__ == "__main__":
    raise SystemExit(main())
