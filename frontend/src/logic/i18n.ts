// 英语 UI 包（多语言生效·界面文字）。
//
// 设计：渲染期「按短语查表翻译」——compile.tsx 在产出文本节点 / 插值字符串 / placeholder /
// aria-label 时，若当前 uiLang 非中文，就拿【去空白后的原文】查 EN 表，命中则换英文、保留两侧空白；
// 未命中原样返回（优雅降级＝保持中文，绝不空白）。
// 好处：① 中文默认零改动（模板一字未动 → lint:bindings/smoke 基线不变）；
//       ② 一张表同时覆盖「模板里的固定文案」与「TS 里算出来再插值的固定文案（如 toast）」；
//       ③ 角色名/邮箱/用户输入等动态值不在表里 → 自动保持原样。
// 带数字/名字拼接的复合句（如「剩余 X 分钟」）在 MiCallLogic 里用 tt() 直接给英文，不走查表。

// uiLang：跟随语言选择器。中文＝zh（界面中文）；其余任何语言＝en（国际英文包）。
export function uiLangOf(lang: string): "zh" | "en" {
  return (lang || "").trim() === "中文" || !lang ? "zh" : "en";
}

// Chinese → English。键＝模板/TS 里【去空白后】的原文，必须逐字节匹配（标点也要一致）。
const EN: Record<string, string> = {
  // —— 顶部导航 / 菜单 ——
  "账单": "Billing",
  "邀请好友": "Invite friends",
  "深色模式": "Dark mode",
  "联系我们": "Contact us",
  "设置": "Settings",
  "登录 / 注册": "Log in / Sign up",
  "点此退出登录": "Tap to log out",
  "退出": "Log out",
  "退出登录？": "Log out?",
  "登录后这段对话和时长都会保留": "Log in to keep this chat and your minutes",
  "注册": "Sign up",
  // —— 主屏 ——
  "正在为你接通": "Connecting you",
  "回忆": "Memories",
  "发现": "Discover",
  "状态": "Status",
  "静音": "Mute",
  "文字": "Text",
  "更多": "More",
  "完成": "Done",
  "跳过": "Skip",
  "在线": "Online",
  "正在聆听": "Listening",
  "正在思考": "Thinking",
  "正在说话": "Speaking",
  "这次聊得怎么样？": "How was this call?",
  "已保存": "Saved",
  "轻点呼叫": "Tap to call",
  "取消": "Cancel",
  "挂断": "Hang up",
  "再次呼叫": "Call again",
  "想对 TA 说点什么…（可选）": "Say something to them… (optional)",
  // —— 收藏 ——
  "我的收藏": "My favorites",
  "还没有收藏的角色": "No favorite characters yet",
  "在角色资料里点 ♥ 收藏喜欢的 TA": "Tap ♥ on a character's profile to add them",
  "新回复": "New reply",
  // —— 语言 / 自动挂断 ——
  "语言": "Language",
  "自动挂断": "Auto hang-up",
  "读取中…": "Loading…",
  // —— 引导 ——
  "轻点下方按钮开始通话": "Tap the button below to start a call",
  "选好角色和场景,绿色按钮拨给 TA,像打电话一样聊天。": "Pick a character and a scene, tap the green button, and chat like a phone call.",
  "知道了": "Got it",
  // —— 通话「更多」/确认弹层 ——
  "撤回上一句": "Undo last line",
  "移除 TA 刚说的最近一句": "Remove the last thing they said",
  "重置记忆": "Reset memory",
  "让 TA 忘记这段对话,重新开始": "Make them forget this chat and start over",
  "重置这段记忆？": "Reset this memory?",
  "重置": "Reset",
  // —— 角色资料 ——
  "她还记得的一些事": "A few things she remembers",
  "修改密码": "Change password",
  "取消订阅": "Cancel subscription",
  "关于 载思": "About zsky",
  "TA 的原声": "Their original voice",
  "音色 · 描述你想要的声音": "Voice · Describe the voice you want",
  "再听": "Replay",
  "用这个": "Use this",
  "职业": "Occupation",
  "现居": "Lives in",
  "星座": "Zodiac",
  "身高": "Height",
  "体重": "Weight",
  "生日": "Birthday",
  "国籍": "Nationality",
  "种族": "Ethnicity",
  "外貌": "Appearance",
  "性子": "Temperament",
  "兴趣爱好": "Interests",
  "口头禅": "Catchphrase",
  "小习惯": "Little habits",
  "背景故事": "Backstory",
  "喜欢": "Likes",
  "不喜欢": "Dislikes",
  // —— 角色 / 场景选择 ——
  "选择角色": "Choose a character",
  "推荐": "For you",
  "热门": "Popular",
  "收藏": "Favorites",
  "选择场景": "Choose a scene",
  "自定义": "Custom",
  "应用场景": "Scenes",
  "试试这些": "Try these",
  "最近使用": "Recent",
  // —— 账单 / 充值 / 邀请 ——
  "账户余额": "Account balance",
  "分钟剩余": "minutes left",
  "充值": "Top up",
  "交易记录": "Transactions",
  "每邀请一位好友,双方各得": "For each friend you invite, you both get",
  "通话时长": "Call minutes",
  "复制": "Copy",
  "分享给好友": "Share with friends",
  "邀请记录": "Invite history",
  "会员套餐（即将上线）": "Membership plans (coming soon)",
  "兑换": "Redeem",
  // —— 通话记录 ——
  "通话记录": "Call history",
  "删除": "Delete",
  // —— 切换 / 失败弹层 ——
  "挂断切换": "Hang up & switch",
  "接通失败": "Call failed",
  "网络似乎不太稳定,没能接通。要再试一次吗?": "The network seems unstable and the call didn't connect. Try again?",
  "重试": "Retry",
  "以后再说": "Maybe later",
  // —— 工单 ——
  "问题类型": "Issue type",
  "提交工单": "Submit",
  "我的工单": "My tickets",
  // —— 隐私 / 协议 ——
  "隐私政策与用户协议": "Privacy Policy & Terms",
  "隐私政策": "Privacy Policy",
  "我们非常重视你的隐私。载思 仅在通话进行时采集你的语音用于实时对话,": "We take your privacy seriously. zsky only captures your voice during a call for real-time conversation,",
  "不会保存或用于训练": "never stored or used for training",
  ";通话结束即丢弃。": "; it is discarded when the call ends.",
  "账户信息仅包含邮箱与加密后的密码,用于登录与时长管理,绝不出售或分享给第三方。": "Account info contains only your email and an encrypted password, used for login and minute management — never sold or shared with third parties.",
  "我们使用必要的 Cookie 维持登录状态与基本偏好(主题、语言),不用于跨站追踪或广告。": "We use essential cookies to keep you signed in and remember basic preferences (theme, language) — not for cross-site tracking or ads.",
  "你可以随时在设置中退出登录、修改密码或注销账户,届时相关数据将被删除。": "You can log out, change your password, or delete your account anytime in Settings; related data will be removed.",
  "用户协议": "Terms of Service",
  "注册或使用即表示你已阅读并同意以下条款。": "By signing up or using the service, you confirm you have read and agree to the following terms.",
  "服务内容": "The service",
  ":载思 提供与 AI 角色的语音通话服务。AI 生成的内容仅供陪伴与娱乐,不构成任何专业(医疗、法律、心理等)建议。": ": zsky provides voice calls with AI characters. AI-generated content is for companionship and entertainment only and is not professional (medical, legal, psychological, etc.) advice.",
  "账户": "Account",
  ":你需对账户与密码安全负责。请勿将账户用于违法或骚扰用途。": ": You are responsible for the security of your account and password. Do not use your account for unlawful or harassing purposes.",
  "时长与计费": "Minutes & billing",
  ":免费时长与会员时长按实际通话扣减;会员可随时取消,已消耗时长不退。": ": Free and membership minutes are deducted by actual call time; membership can be canceled anytime, and used minutes are non-refundable.",
  "行为规范": "Conduct",
  ":禁止利用本服务生成违法、仇恨或侵犯他人权益的内容,我们有权暂停违规账户。": ": Using the service to generate unlawful, hateful, or infringing content is prohibited; we may suspend violating accounts.",
  "最近更新:2026 年 6 月": "Last updated: June 2026",
  "我们使用必要的 Cookie 维持登录与基本偏好,不用于广告追踪。继续使用即表示同意我们的隐私政策。": "We use essential cookies to keep you signed in and remember basic preferences — not for ad tracking. By continuing, you agree to our Privacy Policy.",
  "同意": "Agree",
  "确认修改": "Confirm",
  // —— 弹层标题（在 MiCallLogic 里有同名固定串时也复用）——
  "账户信息": "Account info",
  "账单与充值": "Billing & top-up",
  // —— 通话中状态条 ——
  "已撤回上一句": "Last line undone",
  "记忆已重置": "Memory reset",
  // —— placeholder ——
  "邮箱": "Email",
  "密码（至少 6 位）": "Password (at least 6 characters)",
  "新密码（至少 6 位）": "New password (at least 6 characters)",
  "确认新密码": "Confirm new password",
  "搜索角色": "Search characters",
  "输入兑换码": "Enter redeem code",
  "详细描述你的问题或建议…": "Describe your issue or suggestion in detail…",
  "描述你想聊的场景，TA 会照着和你聊…": "Describe the scene you want, and they'll play along…",
  "如：温柔的成熟女声 / 低沉磁性的大叔": "e.g. a gentle mature female voice / a deep, magnetic man",
  // —— aria-label ——
  "拨打电话": "Call",
  "发现·切换角色": "Discover · switch character",
  "状态·TA的近况": "Status · their latest",
  "有客服回复": "New support reply",
  "有新回忆": "New memories",
  "有新近况": "New status",
  // —— 复合句的可拼接片段（与数字/名字拼接，分段翻译仍通顺）——
  "分钟": "min",
  "现在": "now",
  "删除选中的": "Delete selected",
  "条记录？": "records?",
  // —— 常见 toast / 提示（TS 里算出来经 {{ toast }} 插值 → 同样查表翻译）——
  "处理中…": "Processing…",
  "兑换中…": "Redeeming…",
  "登录成功": "Logged in",
  "已退出登录": "Logged out",
  "密码已修改": "Password changed",
  "两次密码不一致": "Passwords don't match",
  "新密码至少 6 位": "New password must be at least 6 characters",
  "请输入有效邮箱和至少 6 位密码": "Enter a valid email and a password of at least 6 characters",
  "请先登录": "Please log in first",
  "请先登录再提交": "Please log in before submitting",
  "请先登录再兑换": "Please log in before redeeming",
  "请先描述你的问题": "Please describe your issue first",
  "请输入兑换码": "Enter a redeem code",
  "已提交，回复会显示在下方": "Submitted — replies will appear below",
  "已删除所选通话记录": "Selected call records deleted",
  "删除失败，请重试": "Delete failed, please retry",
  "通话中不能换音色": "Can't change voice during a call",
  "没匹配上，换个说法再试试": "No match — try describing it differently",
  "邀请链接已复制，发给好友即可": "Invite link copied — send it to a friend",
  "需要麦克风权限才能通话，请在浏览器允许后重试": "Microphone access is required to call. Please allow it in your browser and retry.",
  "音色库加载失败，请稍后重试": "Failed to load voices, please retry later",
  "长时间无人说话，已自动挂断": "No one spoke for a while — auto hung up",
  "信号断了，重新拨入就能接着聊": "Connection dropped — call again to keep chatting",
  "语音识别中断，可用文字继续对话": "Speech recognition stopped — you can continue by text",
  "时长仅剩 1 分钟": "Only 1 minute left",
  "登录后可查看你们的回忆": "Log in to see your shared memories",
  "🎧 戴耳机体验最佳：随时打断、无回声": "🎧 Best with headphones: interrupt anytime, no echo",
  "演示模式：接入后端后兑换码即可生效": "Demo mode: redeem codes work once the backend is connected",
  "会员套餐即将上线，当前请用兑换码充值": "Membership plans are coming soon — use a redeem code to top up for now",
  "订阅将在本周期结束后取消": "Your subscription will cancel at the end of this period",
  "接入后端后可用": "Available once the backend is connected",
  "需接入后端": "Backend required",
  // —— 场景名 + 简介（pillLabel/场景列表插值出来，查表英文化）——
  "随便聊聊": "Just chat",
  "想到什么说什么": "Say whatever comes to mind",
  "心情树洞": "Vent space",
  "我会认真听你说": "I'll really listen",
  "模拟面试": "Mock interview",
  "我陪你一起准备": "Let's prep together",
  "英语陪练": "English practice",
  "快和我用英语聊吧": "Let's chat in English",
  "成语接龙": "Idiom chain",
  "测试你的成语储备": "Test your idiom knowledge",
  // —— 其它固定标签 / CTA ——
  "注册领免费时长": "Get free minutes",
  "你好呀": "Hello",
  "全部已读": "Mark all read",
  // —— buildScenarios 生成的 20 个场景名 + 简介 ——
  "睡前故事": "Bedtime story", "伴你慢慢入睡": "Drift off slowly",
  "解压冥想": "Calm meditation", "一起深呼吸放松": "Breathe and relax together",
  "哄睡晚安": "Lull to sleep", "轻声陪你入眠": "Softly see you to sleep",
  "早安叫醒": "Morning wake-up", "元气满满开启一天": "Start the day energized",
  "情感倾诉": "Heart-to-heart", "说说你的心事": "Share what's on your mind",
  "学习监督": "Study buddy", "陪你专注一小时": "Focus together for an hour",
  "旅行规划": "Trip planning", "聊聊下一趟去哪": "Plan where to go next",
  "美食推荐": "Food picks", "今天吃点什么好": "What to eat today",
  "历史漫谈": "History talk", "听段有趣的过往": "An intriguing bit of the past",
  "哲学夜谈": "Late-night philosophy", "深夜聊聊人生": "Talk life, late at night",
  "诗词鉴赏": "Poetry appreciation", "读一首给你听": "I'll read you a poem",
  "职场吐槽": "Work venting", "下班来吐吐槽": "Vent after work",
  "恋爱模拟": "Romance sim", "体验一段心动": "Feel a little flutter",
  "方言练习": "Dialect practice", "换个口音聊聊": "Chat in another accent",
  "辩论练习": "Debate practice", "来场观点交锋": "A clash of views",
  "脱口秀": "Stand-up", "听个段子乐一乐": "A joke to lighten up",
  "星座运势": "Horoscope", "今天的你怎么样": "How are you today",
  "读书分享": "Book sharing", "聊聊最近在读的": "Talk about your latest read",
  "育儿陪聊": "Parenting chat", "带娃路上不孤单": "Not alone in raising kids",
  "减压陪伴": "Unwind together", "卸下今天的疲惫": "Shed today's fatigue",
  // —— 会员 / 充值 ——
  "轻享会员": "Lite", "畅聊会员": "Plus", "无限会员": "Unlimited",
  "每月 300 分钟": "300 min / month", "每月 1500 分钟": "1500 min / month", "每月不限时": "Unlimited minutes",
  "月付": "Monthly", "季付": "Quarterly", "年付": "Yearly",
  "省20%": "Save 20%", "省30%": "Save 30%", "最受欢迎": "Most popular",
  "选择会员": "Choose a plan", "支付": "Pay",
  // —— 回忆 / 状态 面板项标签 ——
  "你们的关系": "Your relationship", "上次聊到": "Last talked about", "上次的心情": "Last mood",
  "你们的梗": "Your inside jokes", "还没聊完的": "Unfinished threads",
  "心情": "Mood", "最近在经历": "Going through", "此刻精力": "Energy now", "在期待": "Looking forward to",
  // —— 杂项可见标签 ——
  "关闭": "Off", "展开": "Expand", "收起": "Collapse",
  "通话结束": "Call ended", "账号": "Account",
  "试听声音": "Preview voice", "正在试听…": "Previewing…",
  "匹配声音": "Match a voice", "匹配中…": "Matching…",
  "从全部音色里挑": "Pick from all voices",
  "浅色": "Light", "深色": "Dark",
  "已注册": "Registered",
  // —— 工单问题类型 ——
  "建议反馈": "Feedback", "功能异常": "Bug report", "账号/支付": "Account / payment", "其他": "Other",
};

/** 渲染期查表翻译：uiLang 非中文且去空白后命中 → 换英文并保留两侧空白；否则原样返回。 */
export function tr(uiLang: string, text: string): string {
  if (uiLang === "zh" || !text) return text;
  const key = text.trim();
  if (!key) return text;
  const en = EN[key];
  if (en === undefined) return text;
  // 保留原文两侧空白：把前导/尾随空白包回英文（复合句里" 分钟"→" min"靠这个）
  const m = text.match(/^(\s*)[\s\S]*?(\s*)$/);
  return m ? m[1] + en + m[2] : en;
}
