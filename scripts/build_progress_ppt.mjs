import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const runtimeRoot = "C:/Users/wang/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/package.json";
const pptxRoot = "C:/Users/wang/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/.pnpm/pptxgenjs@4.0.1/node_modules/pptxgenjs/package.json";
const sharpRoot = "C:/Users/wang/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/.pnpm/sharp@0.34.5/node_modules/sharp/package.json";
const sharpRequire = createRequire(sharpRoot);
const pptxRequire = createRequire(pptxRoot);
const pptxgen = pptxRequire("pptxgenjs");
const sharp = sharpRequire("sharp");

const OUT_DIR = path.resolve("output/ppt");
const PREVIEW_DIR = path.join(OUT_DIR, "previews");
const PPTX_PATH = path.join(OUT_DIR, "InterviewAgent_progress_report.pptx");
const W = 13.333;
const H = 7.5;
const SVG_W = 1920;
const SVG_H = 1080;

fs.mkdirSync(PREVIEW_DIR, { recursive: true });

const C = {
  bg: "F7F4EE",
  bg2: "EFEAE1",
  bg3: "E8E3D8",
  ink: "1C1A16",
  muted: "5C5449",
  soft: "9C9488",
  line: "CDC6B8",
  accent: "C96214",
  accent2: "D9893A",
  green: "2E8B57",
  blue: "3A7CA5",
  white: "FFFFFF",
};

const FONT = "Microsoft YaHei";
const HEAD_FONT = "Microsoft YaHei";

const slides = [
  {
    kicker: "PROJECT PROGRESS REPORT",
    title: "InterviewAgent\n项目进度汇报",
    subtitle: "AI 虚拟面试官：技术面 + HR 面双模式",
    type: "cover",
    chips: ["LangGraph", "GraphRAG", "HR 面试", "ASR/TTS"],
  },
  {
    kicker: "01 / 项目背景",
    title: "从“刷题练习”到“真实面试模拟”",
    subtitle: "项目目标是构建一个可多轮追问、可结合简历和 JD、可生成反馈报告的 AI 面试训练系统。",
    type: "split",
    bullets: ["模拟真实面试压力与追问节奏", "结合简历和岗位要求进行个性化提问", "覆盖技术能力、表达能力和职业动机", "形成练习、反馈、复盘的完整闭环"],
    visualTitle: "训练闭环",
    visualItems: ["上传简历", "输入 JD", "AI 面试", "报告复盘"],
  },
  {
    kicker: "02 / 当前进展",
    title: "系统已形成完整面试闭环",
    subtitle: "本阶段不只补功能点，而是让系统从单一技术面扩展为可选择面试类型的综合训练平台。",
    type: "metrics",
    metrics: [
      ["2", "面试模式", "技术面 + HR 面"],
      ["8", "核心阶段", "覆盖提问、追问、总结"],
      ["5+", "关键技术", "LLM / RAG / 语音 / 状态机"],
    ],
  },
  {
    kicker: "03 / 功能总览",
    title: "面向候选人的端到端体验",
    subtitle: "用户从简历和岗位开始，完成实时对话式面试，最后得到结构化评估和历史记录。",
    type: "grid",
    cards: [
      ["简历上传与解析", "提取候选人经历，为追问提供上下文"],
      ["JD 输入与匹配", "根据岗位要求决定技术追问方向"],
      ["AI 多轮对话", "每轮只输出面试官话术，保持真实节奏"],
      ["语音交互", "支持语音输入、ASR 识别和 TTS 播报"],
      ["面试报告", "输出分数、优势、薄弱项和学习建议"],
      ["历史记录", "支持回看报告和完整对话记录"],
    ],
  },
  {
    kicker: "04 / 新增亮点",
    title: "新增 HR 面试选项",
    subtitle: "相对上次汇报，本阶段最大的变化是新增 HR 面试模式，并与技术面共用同一套会话与评估基础设施。",
    type: "hr",
    bullets: ["前端新增技术面 / HR 面模式选择", "后端新增 interview_mode 路由字段", "新增 HR 自我介绍、行为面试、职业规划三个节点", "行为面使用 STAR 法则追问，结合题库检索避免重复"],
  },
  {
    kicker: "05 / 流程对比",
    title: "同一状态机下的双路径面试流程",
    subtitle: "系统通过 LangGraph 统一调度，依据 interview_mode 进入技术面或 HR 面流程。",
    type: "flowCompare",
    tech: ["Greeting", "Resume Dive", "JD Tech", "Coding Test", "Wrap Up"],
    hr: ["Greeting", "Self Intro", "Behavioral", "Career", "Wrap Up"],
  },
  {
    kicker: "06 / 技术架构",
    title: "前后端、Agent、RAG 与语音模块协同",
    subtitle: "核心架构由 FastAPI 服务承接请求，LangGraph 编排面试流程，RAG/工具调用提供问题生成依据。",
    type: "architecture",
    layers: [
      ["前端交互层", "HTML / CSS / JS、WebSocket、音频采集"],
      ["服务接口层", "FastAPI、上传接口、会话接口、报告接口"],
      ["Agent 编排层", "LangGraph、阶段节点、工具调用、状态流转"],
      ["知识检索层", "GraphRAG、ChromaDB、Neo4j、HR 题库"],
      ["模型与语音层", "Qwen / DashScope、ASR、TTS"],
    ],
  },
  {
    kicker: "07 / Agent 编排",
    title: "每个面试阶段都是可扩展的 Node",
    subtitle: "Greeting、简历深挖、JD 技术追问、Coding Test、HR 节点和 Wrap Up 都作为独立节点维护。",
    type: "nodeMap",
    nodes: ["greeting", "resume_dive", "jd_tech", "coding_test", "hr_self_intro", "hr_behavioral", "hr_career", "wrap_up"],
  },
  {
    kicker: "08 / RAG 能力",
    title: "GraphRAG 与向量检索支撑个性化提问",
    subtitle: "技术面围绕 JD 技术实体和知识图谱追问，HR 面从行为题库中检索并去重。",
    type: "rag",
    bullets: ["GLiNER / 规则抽取 JD 技术实体", "BM25 + 向量检索 + RRF 融合召回", "Neo4j 技术知识图谱沿 LEADS_TO 链路展开", "ChromaDB 支持算法题和 HR 题库检索"],
  },
  {
    kicker: "09 / 语音与实时交互",
    title: "让模拟面试更接近真实交流",
    subtitle: "前端录制 PCM 音频并通过 WebSocket 流式传输，后端完成 ASR、LLM 对话和 TTS 播放。",
    type: "voice",
    steps: ["麦克风采集", "PCM 流传输", "ASR 转写", "LLM 回答", "TTS 播报"],
  },
  {
    kicker: "10 / 评估报告",
    title: "面试结束后自动生成结构化反馈",
    subtitle: "报告不仅给总分，还展示阶段表现、薄弱问题、优势项和后续学习建议。",
    type: "report",
    dims: [["技术深度", 8.0], ["编程能力", 7.2], ["沟通表达", 7.8], ["JD 匹配", 8.4], ["职业动机", 7.6]],
  },
  {
    kicker: "11 / 后续计划",
    title: "下一步：让面试更丰富、评估更细",
    subtitle: "围绕问题质量、评分维度、更多面试类型和部署稳定性继续推进。",
    type: "roadmap",
    items: [
      ["HR 题库扩展", "补充压力面、价值观、团队协作等题型"],
      ["评分细化", "区分技术、表达、动机、逻辑和匹配度"],
      ["更多模式", "扩展项目面、系统设计面、综合面"],
      ["工程完善", "部署、权限、稳定性和测试覆盖"],
    ],
  },
];

const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "InterviewAgent";
pptx.subject = "Project progress report";
pptx.title = "InterviewAgent 项目进度汇报";
pptx.company = "InterviewAgent";
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: HEAD_FONT,
  bodyFontFace: FONT,
  lang: "zh-CN",
};

function addBg(slide) {
  slide.background = { color: C.bg };
  slide.addShape(pptx.ShapeType.arc, {
    x: 8.3, y: -1.0, w: 5.8, h: 5.8,
    line: { color: C.bg3, transparency: 72, width: 1.2 },
    adjustPoint: 0.3,
  });
  slide.addShape(pptx.ShapeType.line, { x: 0.75, y: 6.95, w: 11.85, h: 0, line: { color: C.line, transparency: 35, width: 0.8 } });
  slide.addText("InterviewAgent", { x: 0.75, y: 6.97, w: 2.0, h: 0.18, fontFace: FONT, fontSize: 6.8, color: C.soft, margin: 0 });
}

function addHeader(slide, s, n) {
  slide.addText(s.kicker, { x: 0.75, y: 0.42, w: 3.0, h: 0.22, fontFace: FONT, fontSize: 8.5, bold: true, color: C.accent, charSpace: 1.2, margin: 0 });
  slide.addText(String(n).padStart(2, "0"), { x: 12.1, y: 0.42, w: 0.5, h: 0.22, fontFace: FONT, fontSize: 8.5, bold: true, color: C.soft, align: "right", margin: 0 });
}

function addTitle(slide, s) {
  slide.addText(s.title, { x: 0.75, y: 0.85, w: 7.6, h: 0.86, fontFace: HEAD_FONT, fontSize: 25, bold: true, color: C.ink, breakLine: false, fit: "shrink", margin: 0.02 });
  slide.addShape(pptx.ShapeType.line, { x: 0.75, y: 1.82, w: 1.2, h: 0, line: { color: C.accent, width: 2 } });
  slide.addText(s.subtitle, { x: 0.75, y: 1.98, w: 8.7, h: 0.48, fontFace: FONT, fontSize: 12.3, color: C.muted, breakLine: false, fit: "shrink", margin: 0.02 });
}

function chip(slide, text, x, y, w, color = C.accent) {
  slide.addShape(pptx.ShapeType.roundRect, { x, y, w, h: 0.33, rectRadius: 0.06, fill: { color: C.white, transparency: 8 }, line: { color, transparency: 42, width: 0.8 } });
  slide.addText(text, { x: x + 0.08, y: y + 0.07, w: w - 0.16, h: 0.12, fontFace: FONT, fontSize: 7.2, bold: true, color, align: "center", margin: 0 });
}

function panel(slide, x, y, w, h, fill = C.white) {
  slide.addShape(pptx.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.08, fill: { color: fill, transparency: fill === C.white ? 0 : 7 }, line: { color: C.line, transparency: 25, width: 0.8 } });
}

function addBulletList(slide, bullets, x, y, w) {
  bullets.forEach((b, i) => {
    const yy = y + i * 0.48;
    slide.addShape(pptx.ShapeType.ellipse, { x, y: yy + 0.06, w: 0.12, h: 0.12, fill: { color: i % 2 ? C.green : C.accent }, line: { color: i % 2 ? C.green : C.accent } });
    slide.addText(b, { x: x + 0.22, y: yy, w, h: 0.26, fontFace: FONT, fontSize: 11.2, color: C.ink, margin: 0, fit: "shrink" });
  });
}

function addCover(slide, s) {
  slide.background = { color: C.bg };
  slide.addShape(pptx.ShapeType.arc, { x: 7.2, y: -0.8, w: 5.4, h: 5.4, line: { color: C.accent, transparency: 74, width: 1.2 } });
  slide.addShape(pptx.ShapeType.arc, { x: 8.05, y: 0.15, w: 4.1, h: 4.1, line: { color: C.blue, transparency: 78, width: 1.0 } });
  slide.addText(s.kicker, { x: 0.75, y: 0.72, w: 3.3, h: 0.22, fontFace: FONT, fontSize: 8.5, bold: true, color: C.accent, charSpace: 1.2, margin: 0 });
  slide.addText(s.title, { x: 0.75, y: 1.4, w: 5.7, h: 1.55, fontFace: HEAD_FONT, fontSize: 34, bold: true, color: C.ink, breakLine: false, fit: "shrink", margin: 0 });
  slide.addShape(pptx.ShapeType.line, { x: 0.78, y: 3.15, w: 1.55, h: 0, line: { color: C.accent, width: 2.3 } });
  slide.addText(s.subtitle, { x: 0.75, y: 3.42, w: 5.8, h: 0.42, fontFace: FONT, fontSize: 13.3, color: C.muted, margin: 0 });
  s.chips.forEach((c, i) => chip(slide, c, 0.75 + i * 1.22, 4.18, 1.03, i === 2 ? C.green : C.accent));

  panel(slide, 7.05, 1.12, 4.8, 4.55, C.white);
  slide.addText("双模式面试流程", { x: 7.38, y: 1.43, w: 2.2, h: 0.24, fontFace: FONT, fontSize: 10.5, bold: true, color: C.ink, margin: 0 });
  const nodes = [
    ["简历", 7.45, 2.08, C.accent], ["JD", 9.15, 2.08, C.blue], ["Agent", 8.22, 3.1, C.ink],
    ["技术面", 7.35, 4.24, C.accent], ["HR 面", 9.25, 4.24, C.green], ["报告", 8.35, 5.05, C.blue],
  ];
  nodes.forEach(([label, x, y, color]) => {
    slide.addShape(pptx.ShapeType.ellipse, { x, y, w: 0.72, h: 0.72, fill: { color, transparency: 8 }, line: { color, transparency: 20 } });
    slide.addText(label, { x: x - 0.1, y: y + 0.25, w: 0.92, h: 0.12, fontFace: FONT, fontSize: 7.4, bold: true, color: C.white, align: "center", margin: 0 });
  });
  [[7.98, 2.44, 0.58, 0.55], [9.1, 2.44, -0.42, 0.55], [8.58, 3.82, -0.78, 0.34], [8.86, 3.82, 0.75, 0.34], [8.55, 4.82, 0.13, 0.25]].forEach(([x, y, w, h]) => {
    slide.addShape(pptx.ShapeType.line, { x, y, w, h, line: { color: C.line, width: 1.1, beginArrowType: "none", endArrowType: "triangle" } });
  });
}

function addSplit(slide, s) {
  addTitle(slide, s);
  addBulletList(slide, s.bullets, 0.9, 3.0, 5.2);
  panel(slide, 7.3, 2.72, 4.6, 2.75, C.white);
  slide.addText(s.visualTitle, { x: 7.62, y: 3.0, w: 2.4, h: 0.26, fontFace: FONT, fontSize: 12, bold: true, color: C.ink, margin: 0 });
  s.visualItems.forEach((it, i) => {
    const x = 7.65 + (i % 2) * 1.9;
    const y = 3.55 + Math.floor(i / 2) * 0.78;
    slide.addShape(pptx.ShapeType.roundRect, { x, y, w: 1.45, h: 0.42, rectRadius: 0.06, fill: { color: i % 2 ? C.bg2 : "FFF7EC" }, line: { color: i % 2 ? C.blue : C.accent, transparency: 45 } });
    slide.addText(it, { x: x + 0.08, y: y + 0.13, w: 1.29, h: 0.12, fontFace: FONT, fontSize: 7.8, bold: true, color: C.ink, align: "center", margin: 0 });
  });
}

function addMetrics(slide, s) {
  addTitle(slide, s);
  s.metrics.forEach(([num, label, desc], i) => {
    const x = 1.0 + i * 4.0;
    panel(slide, x, 3.08, 3.25, 1.9, C.white);
    slide.addText(num, { x: x + 0.28, y: 3.35, w: 1.4, h: 0.55, fontFace: HEAD_FONT, fontSize: 31, bold: true, color: i === 1 ? C.green : C.accent, margin: 0 });
    slide.addText(label, { x: x + 0.3, y: 4.03, w: 1.8, h: 0.22, fontFace: FONT, fontSize: 11.2, bold: true, color: C.ink, margin: 0 });
    slide.addText(desc, { x: x + 0.3, y: 4.42, w: 2.55, h: 0.24, fontFace: FONT, fontSize: 8.7, color: C.muted, margin: 0 });
  });
}

function addGrid(slide, s) {
  addTitle(slide, s);
  s.cards.forEach(([title, desc], i) => {
    const x = 0.85 + (i % 3) * 4.05;
    const y = 2.72 + Math.floor(i / 3) * 1.42;
    panel(slide, x, y, 3.55, 1.08, C.white);
    slide.addShape(pptx.ShapeType.ellipse, { x: x + 0.25, y: y + 0.25, w: 0.26, h: 0.26, fill: { color: i % 2 ? C.green : C.accent }, line: { color: i % 2 ? C.green : C.accent } });
    slide.addText(title, { x: x + 0.68, y: y + 0.2, w: 2.45, h: 0.2, fontFace: FONT, fontSize: 10.3, bold: true, color: C.ink, margin: 0 });
    slide.addText(desc, { x: x + 0.68, y: y + 0.52, w: 2.55, h: 0.25, fontFace: FONT, fontSize: 7.9, color: C.muted, fit: "shrink", margin: 0 });
  });
}

function addHr(slide, s) {
  addTitle(slide, s);
  addBulletList(slide, s.bullets, 0.9, 2.9, 5.9);
  panel(slide, 7.45, 2.75, 4.4, 2.9, C.white);
  ["自我介绍", "行为面试", "职业规划", "总结评估"].forEach((label, i) => {
    const y = 3.05 + i * 0.58;
    slide.addText(`0${i + 1}`, { x: 7.82, y: y + 0.02, w: 0.35, h: 0.15, fontFace: FONT, fontSize: 7.5, bold: true, color: C.accent, margin: 0 });
    slide.addShape(pptx.ShapeType.line, { x: 8.25, y: y + 0.12, w: 0.5, h: 0, line: { color: C.line, width: 1 } });
    slide.addText(label, { x: 8.92, y, w: 1.4, h: 0.2, fontFace: FONT, fontSize: 10.2, bold: true, color: C.ink, margin: 0 });
  });
  chip(slide, "STAR 法则追问", 8.0, 5.0, 1.55, C.green);
  chip(slide, "题库检索去重", 9.8, 5.0, 1.55, C.accent);
}

function addFlowCompare(slide, s) {
  addTitle(slide, s);
  const rowY = [3.05, 4.55];
  [["技术面", s.tech, C.accent], ["HR 面", s.hr, C.green]].forEach(([label, arr, color], r) => {
    slide.addText(label, { x: 0.95, y: rowY[r] + 0.12, w: 0.8, h: 0.22, fontFace: FONT, fontSize: 10.5, bold: true, color, margin: 0 });
    arr.forEach((it, i) => {
      const x = 2.05 + i * 1.95;
      slide.addShape(pptx.ShapeType.roundRect, { x, y: rowY[r], w: 1.35, h: 0.52, rectRadius: 0.06, fill: { color: C.white }, line: { color, transparency: 35 } });
      slide.addText(it, { x: x + 0.08, y: rowY[r] + 0.18, w: 1.19, h: 0.1, fontFace: FONT, fontSize: 7.1, bold: true, color: C.ink, align: "center", margin: 0 });
      if (i < arr.length - 1) slide.addShape(pptx.ShapeType.line, { x: x + 1.35, y: rowY[r] + 0.26, w: 0.48, h: 0, line: { color: C.line, width: 1, endArrowType: "triangle" } });
    });
  });
}

function addArchitecture(slide, s) {
  addTitle(slide, s);
  s.layers.forEach(([name, desc], i) => {
    const y = 2.72 + i * 0.68;
    const color = [C.accent, C.blue, C.ink, C.green, C.accent2][i];
    slide.addShape(pptx.ShapeType.roundRect, { x: 1.05, y, w: 10.75, h: 0.48, rectRadius: 0.05, fill: { color: i % 2 ? C.white : C.bg2, transparency: i % 2 ? 0 : 8 }, line: { color: C.line, transparency: 25 } });
    slide.addShape(pptx.ShapeType.rect, { x: 1.05, y, w: 0.16, h: 0.48, fill: { color }, line: { color } });
    slide.addText(name, { x: 1.42, y: y + 0.13, w: 1.6, h: 0.14, fontFace: FONT, fontSize: 8.8, bold: true, color, margin: 0 });
    slide.addText(desc, { x: 3.35, y: y + 0.13, w: 7.6, h: 0.14, fontFace: FONT, fontSize: 8.6, color: C.ink, margin: 0 });
  });
}

function addNodeMap(slide, s) {
  addTitle(slide, s);
  s.nodes.forEach((n, i) => {
    const x = 1.1 + (i % 4) * 2.8;
    const y = 2.75 + Math.floor(i / 4) * 1.12;
    panel(slide, x, y, 2.2, 0.64, C.white);
    slide.addText(n, { x: x + 0.16, y: y + 0.22, w: 1.86, h: 0.12, fontFace: FONT, fontSize: 8.2, bold: true, color: i >= 4 && i <= 6 ? C.green : C.ink, align: "center", margin: 0 });
  });
  slide.addText("扩展方式：新增节点 + 加入 ALL_PHASES + dispatch 按 current_node 路由", { x: 1.15, y: 5.35, w: 8.5, h: 0.25, fontFace: FONT, fontSize: 10.5, bold: true, color: C.accent, margin: 0 });
}

function addRag(slide, s) {
  addTitle(slide, s);
  addBulletList(slide, s.bullets, 0.95, 3.02, 5.7);
  const x0 = 7.3;
  ["JD 文本", "实体抽取", "混合召回", "知识追问"].forEach((label, i) => {
    const y = 2.9 + i * 0.62;
    slide.addShape(pptx.ShapeType.roundRect, { x: x0, y, w: 3.55, h: 0.42, rectRadius: 0.06, fill: { color: C.white }, line: { color: i === 3 ? C.accent : C.line, width: i === 3 ? 1.2 : 0.8 } });
    slide.addText(label, { x: x0 + 0.22, y: y + 0.13, w: 2.2, h: 0.12, fontFace: FONT, fontSize: 8.4, bold: true, color: C.ink, margin: 0 });
    if (i < 3) slide.addShape(pptx.ShapeType.line, { x: x0 + 1.8, y: y + 0.42, w: 0, h: 0.18, line: { color: C.line, endArrowType: "triangle" } });
  });
}

function addVoice(slide, s) {
  addTitle(slide, s);
  s.steps.forEach((label, i) => {
    const x = 0.95 + i * 2.25;
    slide.addShape(pptx.ShapeType.ellipse, { x, y: 3.02, w: 0.78, h: 0.78, fill: { color: i === 4 ? C.green : C.accent, transparency: 5 }, line: { color: i === 4 ? C.green : C.accent, transparency: 30 } });
    slide.addText(String(i + 1), { x: x + 0.29, y: 3.25, w: 0.2, h: 0.1, fontFace: FONT, fontSize: 9, bold: true, color: C.white, margin: 0 });
    slide.addText(label, { x: x - 0.25, y: 4.02, w: 1.3, h: 0.18, fontFace: FONT, fontSize: 8.8, bold: true, color: C.ink, align: "center", margin: 0 });
    if (i < s.steps.length - 1) slide.addShape(pptx.ShapeType.line, { x: x + 0.82, y: 3.41, w: 1.15, h: 0, line: { color: C.line, width: 1, endArrowType: "triangle" } });
  });
  slide.addShape(pptx.ShapeType.line, { x: 1.2, y: 5.28, w: 10.5, h: 0, line: { color: C.accent, transparency: 50, width: 1.2, dash: "dash" } });
  slide.addText("WebSocket 实时通道贯穿语音识别、对话生成和语音播报", { x: 2.2, y: 5.08, w: 7.5, h: 0.22, fontFace: FONT, fontSize: 10, bold: true, color: C.accent, align: "center", margin: 0 });
}

function addReport(slide, s) {
  addTitle(slide, s);
  panel(slide, 0.95, 2.72, 4.6, 2.8, C.white);
  slide.addText("综合评分", { x: 1.28, y: 3.0, w: 1.3, h: 0.18, fontFace: FONT, fontSize: 9.5, bold: true, color: C.muted, margin: 0 });
  slide.addText("8.1", { x: 1.25, y: 3.35, w: 1.6, h: 0.55, fontFace: HEAD_FONT, fontSize: 34, bold: true, color: C.accent, margin: 0 });
  slide.addText("推荐进入下一轮", { x: 1.32, y: 4.22, w: 1.8, h: 0.2, fontFace: FONT, fontSize: 10.2, bold: true, color: C.green, margin: 0 });
  slide.addText("优势：表达清晰，项目经历完整\n改进：算法复杂度分析需加强", { x: 1.32, y: 4.68, w: 3.4, h: 0.44, fontFace: FONT, fontSize: 8.5, color: C.muted, fit: "shrink", margin: 0 });
  s.dims.forEach(([name, val], i) => {
    const y = 2.84 + i * 0.48;
    slide.addText(name, { x: 6.35, y, w: 1.1, h: 0.12, fontFace: FONT, fontSize: 7.8, bold: true, color: C.ink, margin: 0 });
    slide.addShape(pptx.ShapeType.rect, { x: 7.65, y: y + 0.04, w: 3.2, h: 0.08, fill: { color: C.bg3 }, line: { color: C.bg3 } });
    slide.addShape(pptx.ShapeType.rect, { x: 7.65, y: y + 0.04, w: 3.2 * (val / 10), h: 0.08, fill: { color: val > 8 ? C.green : C.accent }, line: { color: val > 8 ? C.green : C.accent } });
    slide.addText(val.toFixed(1), { x: 11.03, y: y - 0.01, w: 0.4, h: 0.12, fontFace: FONT, fontSize: 7.5, bold: true, color: C.muted, margin: 0 });
  });
}

function addRoadmap(slide, s) {
  addTitle(slide, s);
  s.items.forEach(([title, desc], i) => {
    const x = 0.98 + i * 2.95;
    panel(slide, x, 3.0, 2.35, 1.65, C.white);
    slide.addText(`0${i + 1}`, { x: x + 0.25, y: 3.22, w: 0.45, h: 0.18, fontFace: FONT, fontSize: 10, bold: true, color: i % 2 ? C.green : C.accent, margin: 0 });
    slide.addText(title, { x: x + 0.25, y: 3.68, w: 1.65, h: 0.22, fontFace: FONT, fontSize: 10.5, bold: true, color: C.ink, margin: 0 });
    slide.addText(desc, { x: x + 0.25, y: 4.12, w: 1.78, h: 0.34, fontFace: FONT, fontSize: 7.8, color: C.muted, fit: "shrink", margin: 0 });
  });
}

function addSlide(s, idx) {
  const slide = pptx.addSlide();
  if (s.type === "cover") {
    addCover(slide, s);
  } else {
    addBg(slide);
    addHeader(slide, s, idx + 1);
    if (s.type === "split") addSplit(slide, s);
    if (s.type === "metrics") addMetrics(slide, s);
    if (s.type === "grid") addGrid(slide, s);
    if (s.type === "hr") addHr(slide, s);
    if (s.type === "flowCompare") addFlowCompare(slide, s);
    if (s.type === "architecture") addArchitecture(slide, s);
    if (s.type === "nodeMap") addNodeMap(slide, s);
    if (s.type === "rag") addRag(slide, s);
    if (s.type === "voice") addVoice(slide, s);
    if (s.type === "report") addReport(slide, s);
    if (s.type === "roadmap") addRoadmap(slide, s);
  }
  slide.addNotes(`本页用于说明：${s.title.replace(/\n/g, "")}`);
}

slides.forEach(addSlide);

function esc(str) {
  return String(str).replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" }[m]));
}

function svgText(text, x, y, size, color = `#${C.ink}`, weight = 600, extra = "") {
  const lines = String(text).split("\n");
  return lines.map((line, i) => `<text x="${x}" y="${y + i * size * 1.2}" font-family="Microsoft YaHei, Arial" font-size="${size}" font-weight="${weight}" fill="${color}" ${extra}>${esc(line)}</text>`).join("");
}

function previewSvg(s, idx) {
  const titleY = s.type === "cover" ? 280 : 188;
  let body = `<rect width="${SVG_W}" height="${SVG_H}" fill="#${C.bg}"/>`;
  body += `<circle cx="1510" cy="80" r="520" fill="none" stroke="#${C.accent}" stroke-opacity=".12" stroke-width="3"/>`;
  body += `<text x="108" y="88" font-family="Microsoft YaHei, Arial" font-size="18" font-weight="700" letter-spacing="2" fill="#${C.accent}">${esc(s.kicker)}</text>`;
  body += svgText(s.title, 108, titleY, s.type === "cover" ? 82 : 52, `#${C.ink}`, 800);
  body += `<rect x="108" y="${s.type === "cover" ? 474 : 262}" width="178" height="6" fill="#${C.accent}"/>`;
  body += svgText(s.subtitle, 108, s.type === "cover" ? 546 : 328, 28, `#${C.muted}`, 400);
  if (s.type === "cover") {
    body += `<rect x="1015" y="180" width="690" height="590" rx="24" fill="#fff" stroke="#${C.line}"/>`;
    [["简历", 1110, 330, C.accent], ["JD", 1355, 330, C.blue], ["Agent", 1240, 500, C.ink], ["技术面", 1100, 675, C.accent], ["HR 面", 1380, 675, C.green]].forEach(([t, x, y, c]) => {
      body += `<circle cx="${x}" cy="${y}" r="55" fill="#${c}"/><text x="${x}" y="${y + 8}" font-family="Microsoft YaHei" font-size="22" font-weight="700" text-anchor="middle" fill="#fff">${esc(t)}</text>`;
    });
  } else if (s.type === "flowCompare") {
    [s.tech, s.hr].forEach((arr, r) => arr.forEach((it, i) => {
      body += `<rect x="${300 + i * 280}" y="${460 + r * 190}" width="210" height="72" rx="16" fill="#fff" stroke="#${r ? C.green : C.accent}"/><text x="${405 + i * 280}" y="${504 + r * 190}" font-family="Microsoft YaHei" font-size="19" font-weight="700" text-anchor="middle" fill="#${C.ink}">${esc(it)}</text>`;
    }));
  } else if (s.bullets) {
    s.bullets.forEach((b, i) => {
      body += `<circle cx="124" cy="${470 + i * 70}" r="10" fill="#${i % 2 ? C.green : C.accent}"/>` + svgText(b, 158, 480 + i * 70, 26, `#${C.ink}`, 500);
    });
  } else if (s.cards) {
    s.cards.forEach(([t, d], i) => {
      const x = 125 + (i % 3) * 560, y = 420 + Math.floor(i / 3) * 190;
      body += `<rect x="${x}" y="${y}" width="460" height="132" rx="18" fill="#fff" stroke="#${C.line}"/>` + svgText(t, x + 44, y + 46, 24, `#${C.ink}`, 700) + svgText(d, x + 44, y + 88, 18, `#${C.muted}`, 400);
    });
  }
  body += `<line x1="108" y1="1000" x2="1810" y2="1000" stroke="#${C.line}"/><text x="108" y="1032" font-family="Microsoft YaHei" font-size="14" fill="#${C.soft}">InterviewAgent</text>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${SVG_W}" height="${SVG_H}" viewBox="0 0 ${SVG_W} ${SVG_H}">${body}</svg>`;
}

async function renderPreviews() {
  const artifact = await import("file:///C:/Users/wang/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs");
  const deck = await artifact.PresentationFile.importPptx(await artifact.FileBlob.load(PPTX_PATH));
  const previewPaths = [];
  const layoutDir = path.join(OUT_DIR, "layout");
  fs.mkdirSync(layoutDir, { recursive: true });

  for (let i = 0; i < deck.slides.count; i += 1) {
    const slide = deck.slides.getItem(i);
    const pngPath = path.join(PREVIEW_DIR, `slide-${String(i + 1).padStart(2, "0")}.png`);
    const pngBlob = await slide.export({ format: "png" });
    fs.writeFileSync(pngPath, Buffer.from(await pngBlob.arrayBuffer()));
    const layout = await slide.export({ format: "layout" });
    fs.writeFileSync(path.join(layoutDir, `slide-${String(i + 1).padStart(2, "0")}.layout.json`), JSON.stringify(layout, null, 2), "utf8");
    previewPaths.push(pngPath);
  }

  const thumbs = await Promise.all(previewPaths.map((p) => sharp(p).resize(480, 270).toBuffer()));
  const montage = sharp({
    create: { width: 480 * 3, height: 270 * 4, channels: 4, background: "#f7f4ee" },
  });
  await montage.composite(thumbs.map((input, i) => ({ input, left: (i % 3) * 480, top: Math.floor(i / 3) * 270 }))).png().toFile(path.join(PREVIEW_DIR, "montage.png"));
}

await pptx.writeFile({ fileName: PPTX_PATH });
await renderPreviews();
console.log(JSON.stringify({ pptx: PPTX_PATH, previews: PREVIEW_DIR, slides: slides.length }, null, 2));
