# -*- coding: utf-8 -*-
import logging
from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.project_service import state
from backend.api_models import err, ErrorCode

logger = logging.getLogger(__name__)

templates_router = APIRouter(prefix="/api/templates")


# -- 内置网文模板 --
# 每个模板包含 id / name / genre / description / chapters(标题+摘要列表)

_TEMPLATES = [
    {
        "id": "xuanhuan",
        "name": "玄幻升级流",
        "genre": "玄幻",
        "description": "金手指->宗门->秘境->渡劫->飞升，经典修仙升级路线，20章骨架",
        "chapters": [
            {"title": "废柴觉醒", "summary": "主角遭族人欺辱，濒死之际意外觉醒神秘传承金手指，命运转折"},
            {"title": "初露锋芒", "summary": "利用金手指快速修炼，在家族比武中一鸣惊人，扬眉吐气"},
            {"title": "离乡入世", "summary": "告别家族，怀揣修仙之志踏上广阔天地，结识同道中人"},
            {"title": "拜入宗门", "summary": "通过层层考核加入修仙大宗，成为外门弟子，初窥修真门径"},
            {"title": "外门风云", "summary": "在外门脱颖而出，结交挚友亦树立强敌，暗流涌动"},
            {"title": "内门试炼", "summary": "闯过内门试炼晋升内门弟子，接触更高深功法与资源"},
            {"title": "师承机缘", "summary": "得到宗门长老青睐，获传核心功法，实力突飞猛进"},
            {"title": "灵脉秘境", "summary": "宗门百年秘境开启，主角随队进入寻宝，危机四伏"},
            {"title": "秘境奇遇", "summary": "秘境深处获得上古传承，实力暴涨，却也引来觊觎"},
            {"title": "突破筑基", "summary": "借秘境收获一举突破筑基期，奠定修仙根基"},
            {"title": "宗门大比", "summary": "代表宗门参加修仙界青年大比，与各路天骄争锋"},
            {"title": "名震一方", "summary": "大比夺魁扬名修仙界，成为新生代领军人物"},
            {"title": "仙魔之战", "summary": "魔道突袭，主角被卷入仙魔两道旷世纷争"},
            {"title": "深入魔渊", "summary": "为救同门单闯魔渊，力挽狂澜，尽显英雄本色"},
            {"title": "结丹大成", "summary": "血战中突破瓶颈，结成金丹，踏入修仙新境界"},
            {"title": "渡劫之劫", "summary": "修为圆满引发天劫，九死一生渡劫成功"},
            {"title": "仇家上门", "summary": "旧日仇家联合围攻，主角陷入十死无生之局"},
            {"title": "绝地反击", "summary": "以一敌众浴血奋战，反杀强敌，威震四方"},
            {"title": "巅峰之战", "summary": "与幕后黑手展开宿命决战，了结所有恩怨"},
            {"title": "飞升仙界", "summary": "大道圆满，白日飞升，开启仙界新篇章"},
        ],
    },
    {
        "id": "urban_system",
        "name": "都市系统流",
        "genre": "都市",
        "description": "系统激活->新手任务->商城->排行榜->终极任务，爽文升级节奏，15章",
        "chapters": [
            {"title": "系统降临", "summary": "主角人生跌入谷底，神秘系统突然激活，发布首个任务"},
            {"title": "新手任务", "summary": "完成新手任务，获得第一桶金与初始技能点"},
            {"title": "初尝甜头", "summary": "用系统奖励改善生活，惊艳周围众人"},
            {"title": "技能获取", "summary": "商城解锁，兑换第一个特殊技能，实力质变"},
            {"title": "崭露头角", "summary": "凭技能在职场/校园强势逆袭，打脸众人"},
            {"title": "暗流涌动", "summary": "出众表现引来他人觊觎，遭人暗中算计"},
            {"title": "反杀逆袭", "summary": "利用系统洞察先机化解危机，漂亮反杀"},
            {"title": "排行榜现", "summary": "系统排行榜开启，主角发现众多隐藏竞争者"},
            {"title": "巅峰对决", "summary": "与排行榜顶尖高手正面交锋，险胜晋级"},
            {"title": "隐藏任务", "summary": "触发隐藏剧情，逐步揭开系统背后秘密"},
            {"title": "势力扩张", "summary": "整合资源建立自己的势力版图，影响力倍增"},
            {"title": "商城升级", "summary": "解锁高级商城，获得逆天道具与传承"},
            {"title": "终极危机", "summary": "系统发布终极任务，失败即被抹杀，生死倒计时"},
            {"title": "绝境破局", "summary": "集结所有资源与人脉应对终极考验，破局而出"},
            {"title": "登顶封神", "summary": "完成终极任务，登顶排行榜第一，掌控系统"},
        ],
    },
    {
        "id": "rebirth_revenge",
        "name": "重生复仇流",
        "genre": "重生",
        "description": "重生->布局->收服->复仇->新局，步步为营的复仇爽文，18章",
        "chapters": [
            {"title": "含恨重生", "summary": "主角被害家破人亡，重生回到十年前命运转折点"},
            {"title": "重整旗鼓", "summary": "利用前世记忆重新规划人生，避开前世覆辙"},
            {"title": "暗中布局", "summary": "提前布局关键产业与人脉，埋下复仇棋子"},
            {"title": "初次交锋", "summary": "与前世的仇人首次正面过招，小试牛刀"},
            {"title": "收服旧将", "summary": "收拢前世忠诚却遭排挤的部下，组建班底"},
            {"title": "商战初胜", "summary": "在商战中精准打击仇人羽翼，初战告捷"},
            {"title": "招揽人才", "summary": "挖角仇人核心团队，釜底抽薪削弱对手"},
            {"title": "设局诱敌", "summary": "精心设下陷阱，引诱仇人入彀"},
            {"title": "釜底抽薪", "summary": "切断仇人资金命脉，令其陷入困局"},
            {"title": "离间之计", "summary": "施离间计瓦解仇人内部联盟，分而治之"},
            {"title": "旧情难断", "summary": "与前世恋人重逢，情感纠葛牵动布局"},
            {"title": "危机反扑", "summary": "仇人察觉反扑，主角陷入前世重演的危机"},
            {"title": "绝处逢生", "summary": "凭前世记忆预判先机，化险为夷"},
            {"title": "全面反击", "summary": "多线并进全面反攻，仇人节节败退"},
            {"title": "仇人末路", "summary": "主要仇人接连落网落败，大势已定"},
            {"title": "终极对决", "summary": "与幕后主使展开终极对决，了结宿怨"},
            {"title": "真相大白", "summary": "揭开前世被害的全部真相，沉冤得雪"},
            {"title": "新局开启", "summary": "复仇完成，主角开启全新人生格局"},
        ],
    },
    {
        "id": "palace_intrigue",
        "name": "女频宫斗流",
        "genre": "女频宫斗",
        "description": "入宫->初斗->结盟->危机->翻盘，深宫权谋步步惊心，16章",
        "chapters": [
            {"title": "选秀入宫", "summary": "主角选秀入宫，初识后宫波谲云诡的险恶"},
            {"title": "初承恩宠", "summary": "因偶然机缘承宠，却引来众妃嫉妒"},
            {"title": "第一次暗算", "summary": "遭人设计陷害，险些失宠获罪"},
            {"title": "化解危机", "summary": "凭机智与细心化解危机，初显心机"},
            {"title": "结识盟友", "summary": "与其他同样受压的低位妃嫔结成同盟"},
            {"title": "培植势力", "summary": "暗中收服宫女太监，编织自己的情报网"},
            {"title": "对抗贵妃", "summary": "与宠冠六宫的贵妃正面交锋，不落下风"},
            {"title": "借刀杀人", "summary": "巧妙借皇后之手打压对手，藏锋守拙"},
            {"title": "步步晋升", "summary": "位份渐升，对贵妃地位形成威胁"},
            {"title": "盟友反水", "summary": "盟友被重利收买，背后捅刀陷害"},
            {"title": "跌入低谷", "summary": "被构陷禁足冷宫，失去恩宠与自由"},
            {"title": "韬光养晦", "summary": "在冷宫隐忍筹谋，寻找翻盘契机"},
            {"title": "抓住把柄", "summary": "掌握对手致命把柄，时机成熟"},
            {"title": "一击必杀", "summary": "借力打力连环出手，扳倒主要对手"},
            {"title": "登顶后位", "summary": "击败所有对手，登上母仪天下的后位"},
            {"title": "盛世承平", "summary": "稳固后位整顿后宫，开启太平盛世"},
        ],
    },
    {
        "id": "infinite_flow",
        "name": "无限流",
        "genre": "无限流",
        "description": "进入->首局->队友->规则->通关，生死副本智斗求生，12章",
        "chapters": [
            {"title": "诡异邀请", "summary": "主角收到神秘邀请，被卷入无限轮回空间"},
            {"title": "首局游戏", "summary": "被投入第一个恐怖副本，险象环生"},
            {"title": "生死一线", "summary": "在副本中几度濒死，摸索求生之道"},
            {"title": "破局通关", "summary": "发现规则漏洞，艰难通关首局副本"},
            {"title": "结识队友", "summary": "遇到其他轮回者，组队共御强敌"},
            {"title": "团队磨合", "summary": "在第二个副本中磨合团队，建立信任"},
            {"title": "规则解析", "summary": "逐渐掌握副本规则体系，化被动为主动"},
            {"title": "队友牺牲", "summary": "副本中队友为掩护主角慷慨赴死"},
            {"title": "单人副本", "summary": "独自面对高难度单人副本，挑战极限"},
            {"title": "隐藏真相", "summary": "发现无限空间背后的惊天真相"},
            {"title": "终极副本", "summary": "挑战最终副本，直面幕后黑手"},
            {"title": "通关自由", "summary": "通关所有副本，赢得自由与新生"},
        ],
    },
    {
        "id": "farming",
        "name": "种田文流",
        "genre": "种田",
        "description": "穿越->基建->经商->争霸->盛世，温馨升级到争霸天下，15章",
        "chapters": [
            {"title": "穿越异世", "summary": "主角穿越到古代贫苦农家，一穷二白"},
            {"title": "白手起家", "summary": "利用现代知识改善生活，初见成效"},
            {"title": "第一桶金", "summary": "发明小物什赚到第一笔钱，生活转机"},
            {"title": "开荒种田", "summary": "改良农耕技术，粮食大丰收，温饱无忧"},
            {"title": "兴修水利", "summary": "带领村民修筑水利，声名鹊起"},
            {"title": "经商之道", "summary": "开办作坊打通商路，富甲乡里"},
            {"title": "遭遇豪强", "summary": "地方豪强觊觎产业，强取豪夺"},
            {"title": "智斗豪强", "summary": "凭智慧与官府背景挫败豪强，保住家业"},
            {"title": "扩大版图", "summary": "产业不断扩张，成为一方巨贾"},
            {"title": "遇乱世", "summary": "天下大乱烽烟四起，流民涌入乡里"},
            {"title": "组建民团", "summary": "为保境安民组建武装民团，自保一方"},
            {"title": "逐鹿中原", "summary": "被迫卷入诸侯争霸，左右天下大势"},
            {"title": "运筹帷幄", "summary": "以雄厚经济实力为后盾，运筹帷幄决胜千里"},
            {"title": "一统天下", "summary": "辅佐明主平定天下，终结乱世"},
            {"title": "盛世繁华", "summary": "开创太平盛世，造福万民青史留名"},
        ],
    },
]

def _build_outline_text(tpl: dict) -> str:
    """根据模板构建大纲文本，格式：# 书名\n第1章 标题: 摘要\n..."""
    lines = [f"# {tpl['name']}"]
    for i, ch in enumerate(tpl["chapters"], 1):
        lines.append(f"第{i}章 {ch['title']}: {ch['summary']}")
    return "\n".join(lines)


# -- 请求模型 --

class TemplateApplyRequest(BaseModel):
    template_id: str


# -- 路由 --

@templates_router.get("/list")
def list_templates():
    """返回预置模板列表"""
    items = []
    for tpl in _TEMPLATES:
        items.append({
            "id": tpl["id"],
            "name": tpl["name"],
            "genre": tpl["genre"],
            "description": tpl["description"],
            "chapter_count": len(tpl["chapters"]),
            "chapters": [
                {"title": c["title"], "summary": c["summary"]}
                for c in tpl["chapters"]
            ],
        })
    return {"ok": True, "templates": items, "count": len(items)}

@templates_router.post("/apply")
def apply_template(data: TemplateApplyRequest):
    """将指定模板的大纲写入当前项目。
    - 写入 outline.txt（通过 save_outline_text）
    - 同时保存结构化大纲（通过 set_novel_outline）
    返回 {ok, outline}
    """
    if not state.project:
        return err(ErrorCode.PROJECT_NOT_OPEN, "未打开项目")

    tpl = None
    for t in _TEMPLATES:
        if t["id"] == data.template_id:
            tpl = t
            break
    if not tpl:
        return err(ErrorCode.NOT_FOUND, f"未找到模板: {data.template_id}")

    try:
        outline_text = _build_outline_text(tpl)

        # 1. 写入 outline.txt（项目大纲文件）
        state.project.save_outline_text(outline_text)

        # 2. 保存结构化全书大纲（dict 格式）
        #    从模板的章节列表提炼出概括性的全书大纲
        chapters_data = tpl["chapters"]
        # story_arc: 把章节标题串成一段叙述
        story_lines = []
        for i, ch in enumerate(chapters_data, 1):
            story_lines.append(f"第{i}阶段({ch['title']}): {ch['summary']}")
        story_arc = "\n".join(story_lines)

        # theme: 用模板描述的前半部分
        theme = tpl.get("description", "")[:30]

        # character_arcs: 暂时为空，等用户后续完善
        structured = {
            "theme": theme,
            "core_conflict": "",
            "story_arc": story_arc,
            "world_anchor": "",
            "character_arcs": [],
            "key_hooks": [],
            "ending": chapters_data[-1]["summary"] if chapters_data else "",
            "tone": ""
        }
        state.project.set_novel_outline(structured)

        logger.info(
            f"[Templates] 应用模板 {tpl['name']}({tpl['id']})，"
            f"{len(tpl['chapters'])} 章，已写入 outline.txt"
        )
        return {"ok": True, "outline": outline_text}
    except Exception as e:
        logger.exception("[Templates] 应用模板失败")
        return err(ErrorCode.INTERNAL_ERROR, f"应用失败: {e}")


# ═══════════════════════════════════════════════════════════════════
# 正向创作增强路由 - /api/creative/*  (参考 Sudowrite Describe/Expand/Rewrite/Feedback)
# ═══════════════════════════════════════════════════════════════════
