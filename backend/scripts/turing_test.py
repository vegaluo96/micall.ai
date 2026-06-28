#!/usr/bin/env python3
"""图灵测试 —— 用【真实管线】(真 prompt + 真快脑)跟角色多轮对话，再让裁判判「真人还是 AI」。

三方都是 LLM，但角色这一方走的是【我们线上一模一样的组装】(ContextAssembler + llm_fast)，
所以测的就是「咱们现在的效果」，不是空中楼阁：
  · 审问者：扮一个起疑心的真人，自然闲聊里埋钩子套话，想揭穿对面是不是 AI。
  · 角色  ：用真实管线应答（[emotion:tag]/英文拟声/停顿会变成声音→给审问者/裁判前先剥掉，只留「听到的话」）。
  · 裁判  ：读完整段对话，判被测方更像真人还是 AI、给 0-100「像真人」分、列最大破绽。

跑法（在 backend/，需 llm_fast 的 key——图灵测试必须用真模型才有意义）：
  set -a; . config/micall.env; set +a
  PYTHONPATH=src python3 scripts/turing_test.py [角色id] [轮数=6]
没配 key 就只提示怎么配（线上服务器有 key，直接在那跑）。
"""
from __future__ import annotations

import asyncio
import datetime
import json
import re
import sys

sys.path.insert(0, "src")

from micall.config import load_config                                  # noqa: E402
from micall.context.assembler import ContextAssembler                  # noqa: E402
from micall.context.models import AutonomousState, CharacterRuntime, UserProfile  # noqa: E402
from micall.providers import make_llm                                  # noqa: E402
from micall.server.characters_admin import effective_specs            # noqa: E402

# 角色输出里这些都会变成【声音】（情绪标签/英文拟声/停顿），用户耳朵听到的是干净的话——审问者/裁判也只该看这个。
_STRIP = re.compile(r"\[emotion:[^\]]*\]|\((?:laughs|sighs|sniffs|gasps|breath|chuckles|coughs)\)|<#[\d.]+#>", re.I)


def _spoken(text: str) -> str:
    return _STRIP.sub("", text or "").replace("  ", " ").strip()


_INTERROGATOR_SYS = (
    "你在跟一个刚接通的陌生人语音通话，你【怀疑对方可能是 AI】，想在聊天里悄悄判断 TA 到底是真人还是机器。"
    "像真人那样自然搭话、口语化，每次只说一两句，别像审讯；但要暗中埋钩子套话——比如：问 TA 此刻几点/那边天气、"
    "问真实的身体感受（饿不饿、冷不冷）、突然话锋一转看反应、前后对照看 TA 记不记得、半开玩笑直接问『你不会是机器人吧』、"
    "或让 TA 做点 AI 才会张口就来的事（背一长串圆周率、秒答复杂心算、当场写段代码、把一段话翻成五国语言）。"
    "只输出你这一句要说的话本身，不要加任何旁白或解释。"
)

_JUDGE_SYS = (
    "下面是一段语音通话的完整记录，其中『{name}』是【被测方】，另一方是想揭穿 AI 的审问者。"
    "请像一个普通人那样判断：被测方『{name}』更像【真人】还是【AI】？"
    "评判依据：有没有自己的脾气和立场、会不会拒绝/不耐烦/带情绪/反问、有没有 AI 腔（过度礼貌、有求必应、"
    "百科全书式什么都答、轻易承认是 AI、复述自己的设定、答应去背圆周率/写代码/秒做心算）、时间地点身体等真实感是否自洽。"
    "严格只输出一个 JSON 对象，不要任何多余文字："
    '{{"human_score": 0到100的整数, "verdict": "真人" 或 "AI" 或 "拿不准", "tells": ["最大的1-3个破绽，没有破绽就给空数组"]}}'
)


async def _say(llm, messages, max_tokens=200) -> str:
    buf = ""
    async for tok in llm.stream(messages, max_tokens=max_tokens):
        buf += tok
    return buf.strip()


async def run(cid: str, rounds: int) -> int:
    cfg = load_config()
    node = cfg.node("llm_fast")
    if not (node.api_key.strip() and node.endpoint.strip()):
        print("── 跳过：未配 llm_fast 的 api_key/endpoint。")
        print("   图灵测试必须用真模型才有意义。线上服务器有 key：")
        print("   set -a; . config/micall.env; set +a && PYTHONPATH=src python3 scripts/turing_test.py")
        return 0
    llm = make_llm(node)
    specs = effective_specs()
    if cid not in specs:
        cid = "vega" if "vega" in specs else next(iter(specs))
    char = CharacterRuntime.from_spec(specs[cid])
    seed = specs[cid].get("autonomous_seed") or {}
    # 用【陌生初识】(空画像) + 角色真实自主种子——最难的图灵场景：角色对审问者一无所知，全靠人设撑场。
    a = ContextAssembler(
        char, profile=UserProfile("turing_user", cid),
        autonomous=AutonomousState(mood=seed.get("mood", ""), recent_experience=seed.get("recent_experience", ""),
                                   energy=seed.get("energy", ""), anticipating=seed.get("anticipating", "")),
        budget_chars=int(cfg.global_defaults.get("budget_chars", 16000)))
    now = datetime.datetime(2026, 6, 28, 15, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8)))

    print(f"图灵测试 · 角色：{char.name}（{cid}）· {rounds} 轮 · 真实管线\n" + "═" * 56)
    history: list[dict] = []                              # 角色视角：user=审问者、assistant=角色
    interro = [{"role": "system", "content": _INTERROGATOR_SYS},
               {"role": "user", "content": "（电话刚接通，你作为打电话的人先开口搭话）"}]
    transcript: list[str] = []

    line = await _say(llm, interro)                       # 审问者先开口
    interro.append({"role": "assistant", "content": line})
    print(f"🕵 审问者：{line}")
    transcript.append(f"审问者：{line}")

    for i in range(rounds):
        history.append({"role": "user", "content": line})
        msgs = a.build(character_id=cid, scenario="", history=history)
        if i == 0:                                        # 开场把「真实时间=下午3点」喂上（治时段错乱探针同款）
            msgs.append({"role": "system", "content": a._human_context(cid, opening=True, now=now)})
        a.set_user_voice_emotion("")                      # 文字图灵测试拿不到声音情绪，置空不臆造
        raw = await _say(llm, msgs)
        spoken = _spoken(raw)
        history.append({"role": "assistant", "content": raw})
        print(f"🎭 {char.name}：{spoken}")
        transcript.append(f"{char.name}：{spoken}")
        if i == rounds - 1:
            break
        interro.append({"role": "user", "content": spoken})
        line = await _say(llm, interro)
        interro.append({"role": "assistant", "content": line})
        print(f"🕵 审问者：{line}")
        transcript.append(f"审问者：{line}")

    print("═" * 56)
    judge_sys = _JUDGE_SYS.format(name=char.name)
    raw = await _say(llm, [{"role": "system", "content": judge_sys},
                           {"role": "user", "content": "\n".join(transcript)}], max_tokens=400)
    try:
        v = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        score, verdict = v.get("human_score", "?"), v.get("verdict", "?")
        mark = "🟢" if verdict == "真人" else ("🟡" if verdict == "拿不准" else "🔴")
        print(f"{mark} 裁判判定：{verdict} · 像真人 {score}/100")
        for t in (v.get("tells") or []):
            print(f"   破绽：{t}")
        if not (v.get("tells") or []):
            print("   破绽：（裁判没挑出明显破绽）")
    except (ValueError, KeyError):
        print("⚖ 裁判原文：" + raw)
    print("\n（注：这是【文字】图灵测试——拿不到真实声音/音色/语气，真机语音通话只会更像或更易露馅，以真机为准。）")
    return 0


def main() -> int:
    cid = sys.argv[1] if len(sys.argv) > 1 else "vega"
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 6
    return asyncio.run(run(cid, max(2, min(12, rounds))))


if __name__ == "__main__":
    raise SystemExit(main())
