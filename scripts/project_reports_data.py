"""Shared planning baseline for the fictional InterviewAgent project."""

AUTHORS = ["王明哲", "江悦铭", "周士斌"]

TEAM = {
    "陈昊": {"role": "项目经理", "rate": 220, "planned_hours": 800},
    "赵宁": {"role": "产品经理/业务分析师", "rate": 180, "planned_hours": 600},
    "林泽宇": {"role": "系统架构师/AI 技术负责人", "rate": 260, "planned_hours": 800},
    "孙博": {"role": "Agent/GraphRAG 工程师", "rate": 220, "planned_hours": 800},
    "郭嘉怡": {"role": "Agent/算法工程师", "rate": 220, "planned_hours": 800},
    "刘晨": {"role": "后端工程师", "rate": 190, "planned_hours": 760},
    "唐宇": {"role": "后端工程师", "rate": 190, "planned_hours": 760},
    "许婧": {"role": "前端工程师", "rate": 180, "planned_hours": 680},
    "何嘉": {"role": "前端工程师", "rate": 180, "planned_hours": 680},
    "郑凯": {"role": "测试工程师", "rate": 160, "planned_hours": 520},
    "马琳": {"role": "测试/质量工程师", "rate": 160, "planned_hours": 520},
    "蒋欣": {"role": "UI/UX 设计师", "rate": 160, "planned_hours": 320},
    "韩磊": {"role": "DevOps/安全工程师", "rate": 200, "planned_hours": 400},
}

PHASES = [
    {"code": "1.0", "name": "立项与启动", "weeks": "1", "hours": 320, "labor_cost": 70_000},
    {"code": "2.0", "name": "需求分析与原型", "weeks": "2-3", "hours": 760, "labor_cost": 143_200},
    {"code": "3.0", "name": "架构设计与技术验证", "weeks": "4-5", "hours": 920, "labor_cost": 190_000},
    {"code": "4.0", "name": "核心功能迭代开发", "weeks": "6-11", "hours": 3340, "labor_cost": 680_000},
    {"code": "5.0", "name": "语音与系统集成", "weeks": "12-15", "hours": 1280, "labor_cost": 250_000},
    {"code": "6.0", "name": "系统测试与验收准备", "weeks": "16-18", "hours": 1280, "labor_cost": 220_000},
    {"code": "7.0", "name": "部署移交与项目收尾", "weeks": "19-20", "hours": 540, "labor_cost": 122_000},
]

NON_LABOR_COSTS = {
    "大模型与语音服务预算": 90_000,
    "云主机、数据库、存储与监控": 60_000,
    "测试设备、域名证书与安全测评": 35_000,
}

LABOR_COST = sum(item["labor_cost"] for item in PHASES)
DIRECT_COST = LABOR_COST + sum(NON_LABOR_COSTS.values())
MANAGEMENT_RESERVE_RATE = 0.12
MANAGEMENT_RESERVE = round(DIRECT_COST * MANAGEMENT_RESERVE_RATE)
BAC = DIRECT_COST + MANAGEMENT_RESERVE

PROJECT = {
    "name": "InterviewAgent 智能面试评估系统",
    "short_name": "InterviewAgent",
    "version": "V2.0（作业修订版）",
    "report_date": "2026年6月21日",
    "scenario_note": "软件项目管理虚拟案例；人员、工期和成本均为规划数据，不代表现实开发进度。",
    "planned_weeks": 20,
    "method": "阶段门控制下的两周迭代开发",
    "authors": AUTHORS,
    "team": TEAM,
    "phases": PHASES,
    "non_labor_costs": NON_LABOR_COSTS,
    "labor_cost": LABOR_COST,
    "direct_cost": DIRECT_COST,
    "management_reserve_rate": MANAGEMENT_RESERVE_RATE,
    "management_reserve": MANAGEMENT_RESERVE,
    "bac": BAC,
    "milestones": [
        ("M1", "项目章程批准", "第1周"),
        ("M2", "需求与原型基线确认", "第3周"),
        ("M3", "架构与关键技术验证评审", "第5周"),
        ("M4", "文本面试主流程版本", "第11周"),
        ("M5", "语音与端到端集成版本", "第15周"),
        ("M6", "系统测试与用户验收评审", "第18周"),
        ("M7", "部署移交与项目收尾评审", "第20周"),
    ],
    "quality_targets": [
        ("关键业务流程通过率", ">= 95%"),
        ("阶段流转正确率", ">= 98%"),
        ("评价报告结构化成功率", ">= 99%"),
        ("RAG Recall@5", ">= 0.80"),
        ("严重缺陷遗留数", "0"),
        ("API P95 响应时间（非 LLM）", "< 800 ms"),
        ("语音首包 P95 延迟", "< 2.5 s"),
    ],
    "risks": [
        ("R01", "LLM 输出不稳定或格式漂移", "高", "结构化输出、重试、降级模板", "林泽宇"),
        ("R02", "GraphRAG 检索相关性不足", "高", "评测集、混合检索、阈值与回退", "孙博"),
        ("R03", "第三方模型或语音接口中断", "高", "超时、熔断、文本降级与配额监控", "刘晨"),
        ("R04", "简历与面试数据泄露", "高", "最小化采集、访问控制、脱敏与保留期限", "韩磊"),
        ("R05", "语音链路延迟影响体验", "中高", "流式处理、首包指标和弱网测试", "何嘉"),
        ("R06", "核心 AI 人员形成单点依赖", "中高", "接口文档、结对评审、关键知识备份", "林泽宇"),
        ("R07", "范围持续扩张", "中", "需求基线、MoSCoW 与变更控制", "陈昊"),
        ("R08", "前后端与 Agent 接口反复变更", "中", "契约优先、Mock 与版本化接口", "刘晨"),
    ],
}


def money(value):
    return f"¥{value:,.0f}"


def percent(value, digits=1):
    return f"{value * 100:.{digits}f}%"
