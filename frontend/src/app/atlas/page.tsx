'use client';

import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import {
  forceSimulation, forceLink, forceManyBody, forceCollide, forceX, forceY,
  type SimulationLinkDatum,
} from 'd3-force';
import {
  Search, ZoomIn, ZoomOut, Filter,
  ChevronRight, Building2, MapPin, TrendingUp,
  Briefcase, Award, DollarSign, Globe,
} from 'lucide-react';
import {
  companyData,
  chainLevelToCategory, financeStageColors, regionColors,
  jobNodes as mockJobNodes, skillNodes as mockSkillNodes,
  type JobNode, type SkillNode,
} from '@/lib/mock-data';
import { fetchAtlasData, fetchHeatmap, type HeatmapRow } from '@/lib/api';
import { TechWarningPanel } from './tech-warning';
import { CompetitorPanel } from './competitor-panel';

const categoryLabels: Record<string, string> = {
  ai: '人工智能', bigdata: '大数据', iot: '物联网', smart: '智能系统', embodied: '具身智能',
};
const categoryColors: Record<string, string> = {
  ai: '#3B82F6', bigdata: '#10B981', iot: '#F59E0B', smart: '#8B5CF6', embodied: '#EF4444',
};
// 热力图/筛选的方向展示顺序（新一代信息技术四域 + 具身智能迁移主体域）
const CATEGORY_ORDER = ['ai', 'bigdata', 'iot', 'smart', 'embodied'];

// T1–T7 具身智能七子域（系统专精方向）：图谱按 T 域分簇着色，锚点呈正七边形分布
const T_DOMAIN_ORDER = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'] as const;
const tDomainLabels: Record<string, string> = {
  T1: 'T1 算法与智能', T2: 'T2 感知传感', T3: 'T3 硬件本体', T4: 'T4 仿真与数据',
  T5: 'T5 软件与系统', T6: 'T6 交互与标准', T7: 'T7 应用场景',
};
const tDomainColors: Record<string, string> = {
  T1: '#EF4444', T2: '#F97316', T3: '#F59E0B', T4: '#84CC16',
  T5: '#14B8A6', T6: '#8B5CF6', T7: '#EC4899',
};
const levelLabels: Record<string, string> = {
  junior: '初级', mid: '中级', senior: '高级',
};
const skillTypeLabels: Record<string, string> = {
  hard: '硬技能', soft: '软技能', domain: '领域知识', tool: '工具技能',
};
const skillTypeColors: Record<string, string> = {
  hard: '#3B82F6', soft: '#10B981', domain: '#F59E0B', tool: '#8B5CF6',
};

type ViewMode = 'network' | 'promotion' | 'heatmap' | 'company' | 'techWarning' | 'competitor';
type GraphNodeType = 'job' | 'skill' | 'company';

interface GraphNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  type: GraphNodeType;
  label: string;
  category?: string;
  l1?: string;
  skillType?: string;
  size: number;
  color: string;
  demand?: number;
  weight?: number;
  companyId?: string;
}

interface GraphEdge {
  source: string;
  target: string;
}

// 热力图行：L2 技能类目 × 职级，heat = 活跃岗位命中计数归一化（0..1）
interface HeatCell {
  level: string;
  label: string;
  count: number;
  heat: number;
}

interface HeatRow {
  l2Id: number;
  l1: string;
  label: string;
  color: string;
  cells: HeatCell[];
}

export default function AtlasPage() {
  const [viewMode, setViewMode] = useState<ViewMode>('network');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [selectedLevel, setSelectedLevel] = useState<string>('all');
  const [selectedSkillType, setSelectedSkillType] = useState<string>('all');
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [containerSize, setContainerSize] = useState(0);
  const [zoom, setZoom] = useState(1);
  // 画布平移偏移（拖拽图谱产生）；zoomRef/panRef 供原生滚轮/拖拽监听读取最新值
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  const panRef = useRef(pan);
  panRef.current = pan;
  const [searchQuery, setSearchQuery] = useState('');
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  // 真实数据（统一库）：替代 mock 的 jobNodes / skillNodes
  const [jobNodes, setJobNodes] = useState<JobNode[]>([]);
  const [skillNodes, setSkillNodes] = useState<SkillNode[]>([]);
  const [dataSource, setDataSource] = useState<'api' | 'loading' | 'fallback'>('loading');
  // L2 粒度热力图数据（活跃岗位命中计数）
  const [heatmapRows, setHeatmapRows] = useState<HeatmapRow[]>([]);
  const [heatmapTotal, setHeatmapTotal] = useState(0);
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const containerRef = React.useRef<HTMLDivElement>(null);

  // 从统一后端加载图谱数据；接口不可用时回退 mock，保证页面始终可展示
  useEffect(() => {
    let cancelled = false;
    fetchAtlasData()
      .then(({ jobs, skills }) => {
        if (cancelled) return;
        if (jobs.length > 0) {
          setJobNodes(jobs);
          setSkillNodes(skills);
          setDataSource('api');
        }
      })
      .catch(() => {
        if (!cancelled) {
          // 后端不可用时回退 mock 数据，保证演示不中断
          setJobNodes(mockJobNodes);
          setSkillNodes(mockSkillNodes);
          setDataSource('fallback');
        }
      });
    return () => { cancelled = true; };
  }, []);

  // L2 粒度热力图：热力值 = 活跃岗位命中计数（最近 180 天收录 + 无时间戳视为近期收录）
  useEffect(() => {
    let cancelled = false;
    fetchHeatmap(180)
      .then(d => {
        if (cancelled) return;
        setHeatmapRows(d.rows);
        setHeatmapTotal(d.total_jobs);
      })
      .catch(() => {
        if (!cancelled) {
          setHeatmapRows([]);
          setHeatmapTotal(0);
        }
      });
    return () => { cancelled = true; };
  }, []);

  // Company filters
  const [companyChainLevel, setCompanyChainLevel] = useState<string>('all');
  const [companyRegion, setCompanyRegion] = useState<string>('all');
  const [companyFinance, setCompanyFinance] = useState<string>('all');
  const [companySearch, setCompanySearch] = useState('');

  // Filtered companies
  const filteredCompanies = useMemo(() => {
    return companyData.companies.filter(c => {
      if (companyChainLevel !== 'all' && c.chainLevel !== companyChainLevel) return false;
      if (companyRegion !== 'all' && c.region !== companyRegion) return false;
      if (companyFinance !== 'all' && c.financeStage !== companyFinance) return false;
      if (companySearch && !c.name.includes(companySearch) && !c.subField.includes(companySearch) && !c.products.includes(companySearch)) return false;
      return true;
    });
  }, [companyChainLevel, companyRegion, companyFinance, companySearch]);

  // Initialize graph nodes and edges
  useEffect(() => {
    const w = 800;
    const h = 600;
    const cx = w / 2;
    const cy = h / 2;

    if (viewMode === 'company') {
      // Company graph mode
      const graphNodes: GraphNode[] = filteredCompanies.slice(0, 60).map((c, i) => {
        const angle = (i / Math.min(filteredCompanies.length, 60)) * Math.PI * 2;
        const radius = 150 + Math.random() * 150;
        const cat = chainLevelToCategory[c.chainLevel] || 'smart';
        return {
          id: `company-${c.id}`,
          x: cx + Math.cos(angle) * radius,
          y: cy + Math.sin(angle) * radius,
          vx: 0, vy: 0,
          type: 'company' as const,
          label: c.name.length > 8 ? c.name.slice(0, 8) + '...' : c.name,
          category: cat,
          size: 16 + (c.skills.length * 2),
          color: financeStageColors[c.financeStage] || '#94A3B8',
          companyId: c.id,
        };
      });

      // Create edges between companies with shared skills
      const graphEdges: GraphEdge[] = [];
      for (let i = 0; i < graphNodes.length; i++) {
        for (let j = i + 1; j < graphNodes.length; j++) {
          const ci = filteredCompanies[i];
          const cj = filteredCompanies[j];
          if (!ci || !cj) continue;
          const sharedSkills = ci.skills.filter(s => cj.skills.includes(s));
          if (sharedSkills.length >= 2) {
            graphEdges.push({ source: graphNodes[i].id, target: graphNodes[j].id });
          }
        }
      }

      setNodes(graphNodes);
      setEdges(graphEdges);
    } else {
      // Job/Skill graph mode
      const filteredJobs = jobNodes.filter(j => {
        if (selectedCategory !== 'all' && j.category !== selectedCategory) return false;
        if (selectedLevel !== 'all' && j.level !== selectedLevel) return false;
        if (searchQuery && !j.name.includes(searchQuery) && !j.skills.some(s => s.includes(searchQuery))) return false;
        return true;
      });

      const filteredSkills = skillNodes.filter(s => {
        if (selectedSkillType !== 'all' && s.type !== selectedSkillType) return false;
        if (searchQuery && !s.name.includes(searchQuery)) return false;
        return true;
      });

      const jobIds = new Set(filteredJobs.map(j => j.id));
      const relevantSkills = filteredSkills.filter(s => s.jobs.some(j => jobIds.has(j)));

      const graphNodes: GraphNode[] = [
        ...filteredJobs.map((j) => ({
          id: j.id,
          x: cx + (Math.random() - 0.5) * 400,
          y: cy + (Math.random() - 0.5) * 300,
          vx: 0, vy: 0,
          type: 'job' as const,
          label: j.name,
          category: j.category,
          l1: j.l1,
          size: 24 + (j.demand / 10),
          // T 域岗位按子域着色（七簇分色），非具身岗位沿用五域配色
          color: (j.l1 && tDomainColors[j.l1]) || categoryColors[j.category],
          demand: j.demand,
        })),
        ...relevantSkills.map((s) => ({
          id: s.id,
          x: cx + (Math.random() - 0.5) * 500,
          y: cy + (Math.random() - 0.5) * 400,
          vx: 0, vy: 0,
          type: 'skill' as const,
          label: s.name,
          skillType: s.type,
          size: 12 + (s.weight / 10),
          color: skillTypeColors[s.type],
          weight: s.weight,
        })),
      ];

      const graphEdges: GraphEdge[] = [];
      relevantSkills.forEach(s => {
        s.jobs.forEach(jId => {
          if (jobIds.has(jId)) {
            graphEdges.push({ source: s.id, target: jId });
          }
        });
      });

      setNodes(graphNodes);
      setEdges(graphEdges);
    }
  }, [viewMode, selectedCategory, selectedLevel, selectedSkillType, searchQuery, filteredCompanies, jobNodes, skillNodes]);

  // Force simulation：d3-force 引擎 + T 域锚点聚类布局
  // 岗位节点被 forceX/forceY 拉向所属 T1–T7 锚点（正七边形分布）形成七个语义簇；
  // 技能节点锚定到相邻岗位 T 域锚点的加权质心，跨域技能自然成为簇间桥梁；
  // 链接弹簧低强度 0.03 防小簇被拉回中央；alpha 衰减至 0.0125 后保持轻微动态
  useEffect(() => {
    if (nodes.length === 0) return;

    type SimLink = SimulationLinkDatum<GraphNode>;

    // T 域锚点：正七边形，中心 (400,300)，半径 260（经无头仿真调参：保证相邻簇质心距 >200px）
    const anchors: Record<string, { x: number; y: number }> = {};
    T_DOMAIN_ORDER.forEach((t, i) => {
      const ang = -Math.PI / 2 + (i * 2 * Math.PI) / T_DOMAIN_ORDER.length;
      anchors[t] = { x: 400 + 260 * Math.cos(ang), y: 300 + 260 * Math.sin(ang) };
    });

    // 非岗位节点（技能）的锚点 = 相邻岗位所属 T 域锚点的均值
    const jobL1 = new Map<string, string>(
      nodes.filter(n => n.type === 'job' && n.l1 && anchors[n.l1]).map(n => [n.id, n.l1 as string])
    );
    const anchorSum = new Map<string, { x: number; y: number; w: number }>();
    edges.forEach(e => {
      const srcL1 = jobL1.get(e.source);
      const tgtL1 = jobL1.get(e.target);
      const [jobId, otherId] = srcL1 ? [e.source, e.target] : tgtL1 ? [e.target, e.source] : [null, null];
      if (!jobId || !otherId) return;
      const a = anchors[jobL1.get(jobId)!];
      const cur = anchorSum.get(otherId) || { x: 0, y: 0, w: 0 };
      cur.x += a.x; cur.y += a.y; cur.w += 1;
      anchorSum.set(otherId, cur);
    });
    const CENTER = { x: 400, y: 300 };
    const anchorOf = (n: GraphNode) => {
      if (n.l1 && anchors[n.l1]) return anchors[n.l1];
      const s = anchorSum.get(n.id);
      return s && s.w > 0 ? { x: s.x / s.w, y: s.y / s.w } : CENTER;
    };

    const sim = forceSimulation<GraphNode>(nodes)
      // 链接弹簧：传入副本避免 d3 改写 source/target；低强度弱弹簧防小簇被拉回中央（无头仿真调参结果）
      .force('link', forceLink<GraphNode, SimLink>(edges.map(e => ({ source: e.source, target: e.target }) as SimLink))
        .id(d => d.id)
        .distance(100)
        .strength(0.03))
      // 多体斥力（Barnes-Hut，O(n log n)）：大电荷+大作用半径，节点更松散
      .force('charge', forceManyBody<GraphNode>()
        .strength(n => (n.type === 'job' || n.type === 'company' ? -320 : -190))
        .distanceMax(300))
      // 碰撞消解：间距小于半径和+间隙时强制推开（间隙 18px 进一步拉开）
      .force('collide', forceCollide<GraphNode>()
        .radius(n => n.size + 18)
        .strength(0.9))
      // T 域锚点聚类力（替代 forceCenter）：高强度确保小簇也贴紧各自锚点（实测同域最近邻率 88%）
      .force('anchorX', forceX<GraphNode>(n => anchorOf(n).x).strength(0.3))
      .force('anchorY', forceY<GraphNode>(n => anchorOf(n).y).strength(0.3))
      .velocityDecay(0.4)
      .alphaDecay(0.035)
      // 低能量微动：alpha 快速衰减到 0.0125 后保持轻微扰动（用户逐档调参选定）
      .alphaTarget(0.0125)
      .on('tick', () => {
        // d3 就地修改节点坐标，数组浅拷贝触发重绘（deps 中 edges 引用不变，不会重启仿真）
        setNodes(prev => [...prev]);
      });

    return () => { sim.stop(); };
  }, [edges, nodes.length]);

  // Canvas 尺寸自适应：轮询父容器尺寸变化（ResizeObserver 在部分嵌入式环境不触发，改用 interval 兜底）
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const sync = () => {
      const r = container.getBoundingClientRect();
      const key = Math.round(r.width) * 10000 + Math.round(r.height);
      setContainerSize(prev => (prev === key ? prev : key));
    };
    sync();
    const iv = window.setInterval(sync, 400);
    return () => window.clearInterval(iv);
  }, []);

  // Canvas rendering（尺寸以父容器为准，切断 canvas 属性高度→布局高度的正反馈环）
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = container.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(rect.width * dpr));
    canvas.height = Math.max(1, Math.round(rect.height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    ctx.clearRect(0, 0, rect.width, rect.height);
    ctx.save();
    ctx.translate(rect.width / 2 + pan.x, rect.height / 2 + pan.y);
    ctx.scale(zoom, zoom);
    ctx.translate(-400, -300);

    const nodeMap = new Map(nodes.map(n => [n.id, n]));

    // Draw edges
    edges.forEach(e => {
      const a = nodeMap.get(e.source);
      const b = nodeMap.get(e.target);
      if (!a || !b) return;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.2)';
      ctx.lineWidth = 1;
      ctx.stroke();
    });

    // Draw nodes
    nodes.forEach(n => {
      const isSelected = selectedNode?.id === n.id;

      // Glow
      if (isSelected) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.size + 8, 0, Math.PI * 2);
        ctx.fillStyle = n.color + '20';
        ctx.fill();
      }

      // Node shape
      if (n.type === 'company') {
        // Draw company nodes as rounded rectangles
        const w = n.size * 2;
        const h = n.size * 1.4;
        const r = 4;
        ctx.beginPath();
        ctx.moveTo(n.x - w / 2 + r, n.y - h / 2);
        ctx.lineTo(n.x + w / 2 - r, n.y - h / 2);
        ctx.quadraticCurveTo(n.x + w / 2, n.y - h / 2, n.x + w / 2, n.y - h / 2 + r);
        ctx.lineTo(n.x + w / 2, n.y + h / 2 - r);
        ctx.quadraticCurveTo(n.x + w / 2, n.y + h / 2, n.x + w / 2 - r, n.y + h / 2);
        ctx.lineTo(n.x - w / 2 + r, n.y + h / 2);
        ctx.quadraticCurveTo(n.x - w / 2, n.y + h / 2, n.x - w / 2, n.y + h / 2 - r);
        ctx.lineTo(n.x - w / 2, n.y - h / 2 + r);
        ctx.quadraticCurveTo(n.x - w / 2, n.y - h / 2, n.x - w / 2 + r, n.y - h / 2);
        ctx.closePath();
        const gradient = ctx.createLinearGradient(n.x - w / 2, n.y - h / 2, n.x + w / 2, n.y + h / 2);
        gradient.addColorStop(0, n.color + 'DD');
        gradient.addColorStop(1, n.color + '88');
        ctx.fillStyle = gradient;
        ctx.fill();
        if (isSelected) {
          ctx.strokeStyle = n.color;
          ctx.lineWidth = 2;
          ctx.stroke();
        } else {
          ctx.strokeStyle = 'rgba(255,255,255,0.5)';
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      } else {
        // Draw job/skill nodes as circles
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.size, 0, Math.PI * 2);
        const gradient = ctx.createRadialGradient(n.x - n.size * 0.3, n.y - n.size * 0.3, 0, n.x, n.y, n.size);
        gradient.addColorStop(0, n.color + 'DD');
        gradient.addColorStop(1, n.color + '99');
        ctx.fillStyle = gradient;
        ctx.fill();
        if (isSelected) {
          ctx.strokeStyle = n.color;
          ctx.lineWidth = 3;
          ctx.stroke();
        } else {
          ctx.strokeStyle = 'rgba(255,255,255,0.6)';
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }
      }

      // Label
      ctx.font = `${n.type === 'job' ? '600' : '400'} ${n.type === 'company' ? 10 : n.type === 'job' ? 12 : 10}px "PingFang SC", sans-serif`;
      ctx.fillStyle = '#1E293B';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(n.label, n.x, n.y + n.size + 4);
    });

    ctx.restore();
  }, [nodes, edges, zoom, pan, selectedNode, containerSize]);

  // 滚轮缩放：以光标位置为中心（原生监听才能 preventDefault，否则页面会跟着滚动）
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left - rect.width / 2;
      const my = e.clientY - rect.top - rect.height / 2;
      const oldZoom = zoomRef.current;
      const newZoom = Math.min(4, Math.max(0.25, oldZoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
      if (newZoom === oldZoom) return;
      // 保持光标下的世界坐标点不动：pan' = m - k·(m - pan)
      const k = newZoom / oldZoom;
      const p = panRef.current;
      setPan({ x: mx - k * (mx - p.x), y: my - k * (my - p.y) });
      setZoom(newZoom);
    };
    canvas.addEventListener('wheel', onWheel, { passive: false });
    return () => canvas.removeEventListener('wheel', onWheel);
  }, [viewMode]);

  // 拖拽平移整个图谱；位移 <5px 视为点击，做节点命中选择
  const dragRef = useRef<{ startX: number; startY: number; panX: number; panY: number; moved: boolean } | null>(null);

  const handleCanvasMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    dragRef.current = { startX: e.clientX, startY: e.clientY, panX: panRef.current.x, panY: panRef.current.y, moved: false };
  }, []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const d = dragRef.current;
      if (!d) return;
      const dx = e.clientX - d.startX;
      const dy = e.clientY - d.startY;
      if (Math.abs(dx) > 4 || Math.abs(dy) > 4) d.moved = true;
      if (d.moved) setPan({ x: d.panX + dx, y: d.panY + dy });
    };
    const onUp = (e: MouseEvent) => {
      const d = dragRef.current;
      dragRef.current = null;
      if (!d || d.moved) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const x = (e.clientX - rect.left - rect.width / 2 - panRef.current.x) / zoomRef.current + 400;
      const y = (e.clientY - rect.top - rect.height / 2 - panRef.current.y) / zoomRef.current + 300;
      const clicked = nodes.find(n => {
        const dx2 = n.x - x;
        const dy2 = n.y - y;
        return Math.sqrt(dx2 * dx2 + dy2 * dy2) < n.size;
      });
      setSelectedNode(clicked || null);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [nodes]);

  // Skill tree data
  const skillTree = useMemo(() => {
    const types = ['hard', 'soft', 'domain', 'tool'] as const;
    return types.map(type => ({
      type,
      label: skillTypeLabels[type],
      color: skillTypeColors[type],
      skills: skillNodes.filter(s => s.type === type),
    }));
  }, [skillNodes]);

  // Selected node details
  const selectedDetails = useMemo(() => {
    if (!selectedNode) return null;
    if (selectedNode.type === 'job') {
      const job = jobNodes.find(j => j.id === selectedNode.id);
      if (!job) return null;
      const relatedSkills = skillNodes.filter(s => s.jobs.includes(job.id));
      return { type: 'job' as const, data: job, relatedSkills };
    } else if (selectedNode.type === 'skill') {
      const skill = skillNodes.find(s => s.id === selectedNode.id);
      if (!skill) return null;
      const relatedJobs = jobNodes.filter(j => skill.jobs.includes(j.id));
      return { type: 'skill' as const, data: skill, relatedJobs };
    } else if (selectedNode.type === 'company') {
      const company = companyData.companies.find(c => c.id === selectedNode.companyId);
      if (!company) return null;
      // Find related jobs based on shared skills
      const relatedJobs = jobNodes.filter(j =>
        j.skills.some(s => company.skills.includes(s))
      );
      return { type: 'company' as const, data: company, relatedJobs };
    }
    return null;
  }, [selectedNode]);

  // Heatmap data：行 = T1–T7 下的 L2 技能类目（按活跃岗位命中计数，去重岗位数），列 = 职级
  const heatmapData = useMemo(() => {
    const levels = ['junior', 'mid', 'senior'] as const;
    if (heatmapRows.length === 0) return [] as HeatRow[];
    const maxCount = Math.max(1, ...heatmapRows.flatMap(r => levels.map(lv => r.cells[lv] ?? 0)));
    return heatmapRows.map(r => ({
      l2Id: r.l2_id,
      l1: r.l1_code,
      label: r.l2_name,
      color: tDomainColors[r.l1_code] || '#94A3B8',
      cells: levels.map(lv => {
        const count = r.cells[lv] ?? 0;
        return {
          level: lv,
          label: levelLabels[lv],
          count,
          heat: count > 0 ? 0.12 + 0.88 * (count / maxCount) : 0,
        };
      }),
    }));
  }, [heatmapRows]);

  // 热力图行按 T1–T7 分组（组标题 + L2 明细行）
  const heatGroups = useMemo(() => {
    const g: Record<string, HeatRow[]> = {};
    heatmapData.forEach(r => { (g[r.l1] = g[r.l1] || []).push(r); });
    return T_DOMAIN_ORDER
      .filter(t => g[t] && g[t].length > 0)
      .map(t => ({ l1: t, label: tDomainLabels[t], color: tDomainColors[t], rows: g[t] }));
  }, [heatmapData]);

  // Promotion path data
  const promotionPaths = useMemo(() => {
    return [
      { from: 'AI训练师', to: 'AI算法工程师', path: '2-3年', skills: '深度学习, PyTorch, 论文阅读' },
      { from: 'AI算法工程师', to: '大模型应用工程师', path: '3-5年', skills: 'LLM, RAG, Agent架构' },
      { from: '数据分析师', to: '数据工程师', path: '2-3年', skills: 'Spark, Flink, 数据建模' },
      { from: '数据工程师', to: '数据治理专家', path: '3-5年', skills: '数据标准, 元数据管理, 合规' },
      { from: '嵌入式开发', to: 'IoT架构师', path: '3-5年', skills: '系统架构, 边缘计算, 数字孪生' },
      { from: '智能硬件工程师', to: '智能产品经理', path: '3-5年', skills: '产品规划, 用户研究, AI应用' },
    ];
  }, []);

  // Company chain level options
  const chainLevelOptions = useMemo(() => {
    const levels = Object.entries(companyData.chainLevels).sort((a, b) => b[1] - a[1]);
    return levels;
  }, []);

  // Company region options
  const regionOptions = useMemo(() => {
    const regions = Object.entries(companyData.regions).sort((a, b) => b[1] - a[1]);
    return regions;
  }, []);

  // Company finance options
  const financeOptions = useMemo(() => {
    const stages = Object.entries(companyData.financeStages).sort((a, b) => b[1] - a[1]);
    return stages;
  }, []);

  // Top skills from companies
  const topCompanySkills = useMemo(() => {
    return companyData.skills.slice(0, 20);
  }, []);

  return (
    <>
      {/* Sidebar */}
      <aside className="fixed left-0 top-14 bottom-0 w-60 bg-white border-r border-slate-200 overflow-y-auto z-10">
        <div className="p-4">
          {viewMode !== 'company' ? (
            <>
              {/* Job/Skill Filters */}
              <div className="mb-5">
                <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3 px-1">筛选条件</p>
                <div className="space-y-3">
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">技术栈方向</label>
                    <select
                      value={selectedCategory}
                      onChange={e => setSelectedCategory(e.target.value)}
                      className="w-full h-8 px-2 rounded-md border border-slate-200 text-sm bg-white focus:outline-none focus:border-blue-400"
                    >
                      <option value="all">全部方向</option>
                      <option value="ai">人工智能</option>
                      <option value="bigdata">大数据</option>
                      <option value="iot">物联网</option>
                      <option value="smart">智能系统</option>
                      <option value="embodied">具身智能</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">岗位级别</label>
                    <select
                      value={selectedLevel}
                      onChange={e => setSelectedLevel(e.target.value)}
                      className="w-full h-8 px-2 rounded-md border border-slate-200 text-sm bg-white focus:outline-none focus:border-blue-400"
                    >
                      <option value="all">全部级别</option>
                      <option value="junior">初级</option>
                      <option value="mid">中级</option>
                      <option value="senior">高级</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Skill tree */}
              <div>
                <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3 px-1">技能分类</p>
                <div className="space-y-1">
                  {skillTree.map(group => (
                    <div key={group.type}>
                      <button
                        onClick={() => setSelectedSkillType(selectedSkillType === group.type ? 'all' : group.type)}
                        className={`w-full flex items-center justify-between px-2 py-1.5 rounded-md text-sm transition-colors ${
                          selectedSkillType === group.type ? 'bg-blue-50 text-blue-700' : 'text-slate-600 hover:bg-slate-50'
                        }`}
                      >
                        <span className="flex items-center gap-2">
                          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: group.color }} />
                          {group.label}
                        </span>
                        <span className="text-xs text-slate-400">{group.skills.length}</span>
                      </button>
                      {selectedSkillType === group.type && (
                        <div className="ml-6 mt-1 space-y-0.5">
                          {group.skills.map(s => (
                            <div key={s.id} className="text-xs text-slate-500 py-0.5 px-2">
                              {s.name} <span className="text-slate-300">({s.jobs.length})</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <>
              {/* Company Filters */}
              <div className="mb-5">
                <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3 px-1">企业筛选</p>
                <div className="space-y-3">
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">产业链层级</label>
                    <select
                      value={companyChainLevel}
                      onChange={e => setCompanyChainLevel(e.target.value)}
                      className="w-full h-8 px-2 rounded-md border border-slate-200 text-sm bg-white focus:outline-none focus:border-blue-400"
                    >
                      <option value="all">全部层级</option>
                      {chainLevelOptions.map(([level, count]) => (
                        <option key={level} value={level}>{level} ({count})</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">地区</label>
                    <select
                      value={companyRegion}
                      onChange={e => setCompanyRegion(e.target.value)}
                      className="w-full h-8 px-2 rounded-md border border-slate-200 text-sm bg-white focus:outline-none focus:border-blue-400"
                    >
                      <option value="all">全部地区</option>
                      {regionOptions.map(([region, count]) => (
                        <option key={region} value={region}>{region} ({count})</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">融资阶段</label>
                    <select
                      value={companyFinance}
                      onChange={e => setCompanyFinance(e.target.value)}
                      className="w-full h-8 px-2 rounded-md border border-slate-200 text-sm bg-white focus:outline-none focus:border-blue-400"
                    >
                      <option value="all">全部阶段</option>
                      {financeOptions.map(([stage, count]) => (
                        <option key={stage} value={stage}>{stage} ({count})</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">搜索企业</label>
                    <input
                      type="text"
                      placeholder="企业名/产品/领域..."
                      value={companySearch}
                      onChange={e => setCompanySearch(e.target.value)}
                      className="w-full h-8 px-2 rounded-md border border-slate-200 text-sm focus:outline-none focus:border-blue-400"
                    />
                  </div>
                </div>
                <div className="mt-3 px-1">
                  <p className="text-xs text-slate-400">
                    匹配 <span className="font-semibold text-blue-600">{filteredCompanies.length}</span> / {companyData.totalCompanies} 家企业
                  </p>
                </div>
              </div>

              {/* Top Skills from Companies */}
              <div>
                <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3 px-1">核心技术分布</p>
                <div className="space-y-1.5">
                  {topCompanySkills.map(skill => (
                    <div key={skill.name} className="flex items-center gap-2">
                      <div className="flex-1">
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-xs text-slate-600">{skill.name}</span>
                          <span className="text-xs text-slate-400">{skill.count}家</span>
                        </div>
                        <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all"
                            style={{
                              width: `${(skill.count / (topCompanySkills[0]?.count || 1)) * 100}%`,
                              backgroundColor: '#3B82F6',
                            }}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </aside>

      {/* Main content */}
      <div className="ml-60 flex-1 flex flex-col h-screen">
        {/* View tabs + search */}
        <div className="flex items-center justify-between px-6 py-3 bg-white border-b border-slate-200">
          <div className="flex items-center gap-1">
            <span
              className={`mr-2 px-2 py-0.5 rounded text-xs font-medium ${
                dataSource === 'api'
                  ? 'bg-emerald-50 text-emerald-700'
                  : dataSource === 'fallback'
                    ? 'bg-amber-50 text-amber-700'
                    : 'bg-slate-100 text-slate-500'
              }`}
              title="数据来源：统一库 unified.db（API）或本地 mock 回退"
            >
              {dataSource === 'api' ? '数据源：统一库' : dataSource === 'fallback' ? '数据源：mock 回退' : '加载中…'}
            </span>
            {([
              { id: 'network', label: '全景网络' },
              { id: 'heatmap', label: '技能热力' },
              // 以下视图仍为 mock 数据，暂不展示（对应开发阶段接入真实数据后恢复）：
              // { id: 'promotion', label: '晋升路径' },
              // { id: 'company', label: '企业图谱' },
              // { id: 'techWarning', label: '技术预警' },
              // { id: 'competitor', label: '竞品围栏' },
            ] as { id: ViewMode; label: string }[]).map(tab => (
              <button
                key={tab.id}
                onClick={() => { setViewMode(tab.id); setSelectedNode(null); }}
                className={`px-4 py-1.5 rounded-md text-sm transition-colors ${
                  viewMode === tab.id
                    ? 'bg-blue-50 text-blue-700 font-medium'
                    : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            {viewMode !== 'company' && (
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <input
                  type="text"
                  placeholder="搜索节点..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  className="w-48 h-8 pl-8 pr-3 rounded-md border border-slate-200 text-sm focus:outline-none focus:border-blue-400"
                />
              </div>
            )}
            <div className="flex items-center gap-1 border border-slate-200 rounded-md">
              <button onClick={() => setZoom(z => Math.min(z + 0.2, 2))} className="p-1.5 hover:bg-slate-50 rounded-l-md">
                <ZoomIn className="w-4 h-4 text-slate-500" />
              </button>
              <button onClick={() => setZoom(1)} className="px-2 py-1.5 text-xs text-slate-500 hover:bg-slate-50 border-x border-slate-200">
                {Math.round(zoom * 100)}%
              </button>
              <button onClick={() => setZoom(z => Math.max(z - 0.2, 0.4))} className="p-1.5 hover:bg-slate-50 rounded-r-md">
                <ZoomOut className="w-4 h-4 text-slate-500" />
              </button>
            </div>
          </div>
        </div>

        {/* Canvas / Visualization area */}
        <div className="flex-1 flex">
          <div className="flex-1 relative" ref={containerRef}>
            {(viewMode === 'network' || viewMode === 'company') && (
              <canvas
                ref={canvasRef}
                className="absolute inset-0 w-full h-full cursor-grab active:cursor-grabbing"
                onMouseDown={handleCanvasMouseDown}
              />
            )}
            {/* T 域图例：具身智能七子域分簇配色说明（仅网络视图） */}
            {viewMode === 'network' && (
              <div className="absolute top-3 left-3 z-10 bg-white/85 backdrop-blur rounded-lg border border-slate-200 px-3 py-2 shadow-sm">
                <p className="text-[10px] font-semibold text-slate-500 mb-1.5">具身智能子域分簇</p>
                <div className="flex flex-col gap-1">
                  {T_DOMAIN_ORDER.map(t => (
                    <div key={t} className="flex items-center gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: tDomainColors[t] }} />
                      <span className="text-[11px] text-slate-600 whitespace-nowrap">{tDomainLabels[t]}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {viewMode === 'promotion' && (
              <div className="p-8 overflow-auto h-full">
                <h3 className="text-lg font-semibold text-slate-800 mb-6">岗位晋升路径</h3>
                <div className="grid grid-cols-2 gap-4">
                  {promotionPaths.map((p, i) => (
                    <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 hover:shadow-md transition-shadow">
                      <div className="flex items-center gap-3 mb-3">
                        <div className="flex items-center gap-2">
                          <span className="px-2.5 py-1 rounded-md bg-blue-50 text-blue-700 text-sm font-medium">{p.from}</span>
                          <ChevronRight className="w-4 h-4 text-slate-300" />
                          <span className="px-2.5 py-1 rounded-md bg-violet-50 text-violet-700 text-sm font-medium">{p.to}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
                        <span className="px-2 py-0.5 rounded bg-slate-100">周期: {p.path}</span>
                      </div>
                      <div className="text-xs text-slate-500">
                        <span className="font-medium text-slate-600">关键技能：</span>{p.skills}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {viewMode === 'heatmap' && (
              <div className="p-8 overflow-auto h-full">
                <h3 className="text-lg font-semibold text-slate-800 mb-1">技能需求热力图（L2 粒度）</h3>
                <p className="text-xs text-slate-400 mb-2">行 = 具身智能七子域（T1–T7）下的 L2 技能类目；单元格 = 最近 180 天活跃岗位（收录于 180 天内或近期收录）中命中该类目技能的岗位数（去重），技能在活跃岗位 JD 中出现越频繁颜色越深</p>
                <div className="flex items-center gap-2 mb-4 text-xs text-slate-500">
                  <span>活跃岗位总数</span>
                  <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 font-medium">{heatmapTotal} 个</span>
                  <span className="ml-3">热度：</span>
                  <span className="px-2 py-0.5 rounded bg-slate-100">浅 = 少</span>
                  <span className="px-2 py-0.5 rounded bg-slate-100">深 = 多</span>
                </div>
                <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                  <table className="w-full">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200">
                        <th className="text-left px-6 py-3 text-sm font-medium text-slate-600">技能类目（L2）</th>
                        <th className="text-center px-6 py-3 text-sm font-medium text-slate-600">初级</th>
                        <th className="text-center px-6 py-3 text-sm font-medium text-slate-600">中级</th>
                        <th className="text-center px-6 py-3 text-sm font-medium text-slate-600">高级</th>
                      </tr>
                    </thead>
                    <tbody>
                      {heatGroups.length === 0 && (
                        <tr>
                          <td colSpan={4} className="px-6 py-10 text-center text-sm text-slate-400">热力图数据加载中……</td>
                        </tr>
                      )}
                      {heatGroups.map(g => (
                        <React.Fragment key={g.l1}>
                          <tr className="bg-slate-50/80 border-b border-slate-200">
                            <td colSpan={4} className="px-6 py-2">
                              <div className="flex items-center gap-2">
                                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: g.color }} />
                                <span className="text-xs font-semibold text-slate-600">{g.label}</span>
                                <span className="text-xs text-slate-400">（{g.rows.length} 个类目）</span>
                              </div>
                            </td>
                          </tr>
                          {g.rows.map(row => (
                            <tr key={row.l2Id} className="border-b border-slate-100">
                              <td className="px-6 py-3">
                                <span className="text-sm text-slate-700">{row.label}</span>
                              </td>
                              {row.cells.map(cell => (
                                <td key={cell.level} className="px-6 py-3 text-center">
                                  <div
                                    className="inline-flex items-center justify-center rounded-lg px-4 py-2 min-w-16"
                                    style={{
                                      backgroundColor: cell.count > 0
                                        ? `${row.color}${Math.round(cell.heat * 255).toString(16).padStart(2, '0')}`
                                        : '#f1f5f9',
                                    }}
                                  >
                                    <span className="text-sm font-bold" style={{ color: cell.heat > 0.6 ? '#fff' : row.color }}>
                                      {cell.count > 0 ? cell.count : '-'}
                                    </span>
                                  </div>
                                  <div className="text-[10px] text-slate-400 mt-1">个岗位</div>
                                </td>
                              ))}
                            </tr>
                          ))}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {viewMode === 'techWarning' && (
              <div className="p-6 overflow-auto h-full bg-slate-50">
                <div className="max-w-2xl mx-auto">
                  <TechWarningPanel />
                </div>
              </div>
            )}
            {viewMode === 'competitor' && (
              <div className="p-6 overflow-auto h-full bg-slate-50">
                <div className="max-w-2xl mx-auto">
                  <CompetitorPanel />
                </div>
              </div>
            )}
          </div>
          {selectedNode && selectedDetails && (
            <div className="w-80 bg-white border-l border-slate-200 overflow-y-auto">
              <div className="p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-base font-semibold text-slate-800 truncate">{selectedNode.label}</h3>
                  <button onClick={() => setSelectedNode(null)} className="text-slate-400 hover:text-slate-600 text-xs shrink-0 ml-2">关闭</button>
                </div>

                {selectedDetails.type === 'job' && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2">
                      {/* T 域岗位显示子域徽章，其余沿用五域分类 */}
                      <span className="px-2 py-0.5 rounded text-xs font-medium" style={{
                        backgroundColor: ((selectedDetails.data.l1 && tDomainColors[selectedDetails.data.l1]) || categoryColors[selectedDetails.data.category]) + '15',
                        color: (selectedDetails.data.l1 && tDomainColors[selectedDetails.data.l1]) || categoryColors[selectedDetails.data.category],
                      }}>
                        {(selectedDetails.data.l1 && tDomainLabels[selectedDetails.data.l1]) || categoryLabels[selectedDetails.data.category]}
                      </span>
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-xs text-slate-600">
                        {levelLabels[selectedDetails.data.level]}
                      </span>
                    </div>
                    <p className="text-sm text-slate-600">{selectedDetails.data.description}</p>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="bg-slate-50 rounded-lg p-3">
                        <p className="text-xs text-slate-400 mb-1">需求指数</p>
                        <p className="text-xl font-bold text-blue-600">{selectedDetails.data.demand}</p>
                      </div>
                      <div className="bg-slate-50 rounded-lg p-3">
                        <p className="text-xs text-slate-400 mb-1">薪资范围</p>
                        <p className="text-sm font-bold text-slate-700">{selectedDetails.data.salary}</p>
                      </div>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-slate-500 mb-2">核心技能</p>
                      <div className="flex flex-wrap gap-1.5">
                        {selectedDetails.data.skills.map(s => (
                          <span key={s} className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 text-xs">{s}</span>
                        ))}
                      </div>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-slate-500 mb-2">关联技能节点 ({selectedDetails.relatedSkills.length})</p>
                      <div className="space-y-1">
                        {selectedDetails.relatedSkills.map(s => (
                          <div key={s.id} className="flex items-center justify-between py-1 px-2 rounded hover:bg-slate-50">
                            <span className="text-sm text-slate-600">{s.name}</span>
                            <span className="text-xs text-slate-400">权重 {s.weight}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-slate-500 mb-2">需求趋势</p>
                      <div className="bg-slate-50 rounded-lg p-3 h-24 flex items-end gap-1">
                        {[65, 72, 68, 78, 82, 85, 88, 84, 90, 92, 95, selectedDetails.data.demand].map((v, i) => (
                          <div key={i} className="flex-1 rounded-t" style={{
                            height: `${(v / 100) * 100}%`,
                            backgroundColor: categoryColors[selectedDetails.data.category] + '80',
                          }} />
                        ))}
                      </div>
                      <p className="text-xs text-slate-400 mt-1 text-center">近12个月</p>
                    </div>
                  </div>
                )}

                {selectedDetails.type === 'skill' && (
                  <div className="space-y-4">
                    <span className="px-2 py-0.5 rounded text-xs font-medium" style={{
                      backgroundColor: skillTypeColors[selectedDetails.data.type] + '15',
                      color: skillTypeColors[selectedDetails.data.type],
                    }}>
                      {skillTypeLabels[selectedDetails.data.type]}
                    </span>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="bg-slate-50 rounded-lg p-3">
                        <p className="text-xs text-slate-400 mb-1">技能权重</p>
                        <p className="text-xl font-bold text-violet-600">{selectedDetails.data.weight}</p>
                      </div>
                      <div className="bg-slate-50 rounded-lg p-3">
                        <p className="text-xs text-slate-400 mb-1">关联岗位</p>
                        <p className="text-xl font-bold text-slate-700">{selectedDetails.data.jobs.length}</p>
                      </div>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-slate-500 mb-2">关联岗位</p>
                      <div className="space-y-1">
                        {selectedDetails.relatedJobs.map(j => (
                          <div key={j.id} className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-slate-50">
                            <span className="text-sm text-slate-600">{j.name}</span>
                            <span className="text-xs text-slate-400">{j.salary}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {selectedDetails.type === 'company' && (
                  <div className="space-y-4">
                    {/* Company header */}
                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0" style={{
                        backgroundColor: financeStageColors[selectedDetails.data.financeStage] + '20',
                      }}>
                        <Building2 className="w-5 h-5" style={{ color: financeStageColors[selectedDetails.data.financeStage] }} />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-800 truncate">{selectedDetails.data.name}</p>
                        {selectedDetails.data.englishName && (
                          <p className="text-xs text-slate-400 truncate">{selectedDetails.data.englishName}</p>
                        )}
                      </div>
                    </div>

                    {/* Tags */}
                    <div className="flex flex-wrap gap-1.5">
                      <span className="px-2 py-0.5 rounded text-xs font-medium" style={{
                        backgroundColor: financeStageColors[selectedDetails.data.financeStage] + '15',
                        color: financeStageColors[selectedDetails.data.financeStage],
                      }}>
                        {selectedDetails.data.financeStage}
                      </span>
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-xs text-slate-600">
                        {selectedDetails.data.chainLevel}
                      </span>
                      {selectedDetails.data.region && (
                        <span className="px-2 py-0.5 rounded text-xs text-slate-600" style={{
                          backgroundColor: (regionColors[selectedDetails.data.region] || '#94A3B8') + '15',
                          color: regionColors[selectedDetails.data.region] || '#94A3B8',
                        }}>
                          {selectedDetails.data.region}
                        </span>
                      )}
                    </div>

                    {/* Key info */}
                    <div className="space-y-2">
                      {selectedDetails.data.subField && (
                        <div>
                          <p className="text-xs text-slate-400 mb-1">细分领域</p>
                          <p className="text-sm text-slate-700">{selectedDetails.data.subField}</p>
                        </div>
                      )}
                      {selectedDetails.data.productType && (
                        <div>
                          <p className="text-xs text-slate-400 mb-1">产品类型</p>
                          <p className="text-sm text-slate-700">{selectedDetails.data.productType}</p>
                        </div>
                      )}
                      {selectedDetails.data.city && (
                        <div className="flex items-center gap-1.5">
                          <MapPin className="w-3 h-3 text-slate-400" />
                          <span className="text-xs text-slate-500">{selectedDetails.data.city}</span>
                        </div>
                      )}
                    </div>

                    {/* Products */}
                    {selectedDetails.data.products && (
                      <div>
                        <p className="text-xs font-medium text-slate-500 mb-2">代表产品</p>
                        <p className="text-xs text-slate-600 leading-relaxed line-clamp-3">{selectedDetails.data.products}</p>
                      </div>
                    )}

                    {/* Mass production */}
                    {selectedDetails.data.massProduction && (
                      <div>
                        <p className="text-xs font-medium text-slate-500 mb-2">量产进展</p>
                        <p className="text-xs text-slate-600 leading-relaxed line-clamp-3">{selectedDetails.data.massProduction}</p>
                      </div>
                    )}

                    {/* Skills */}
                    {selectedDetails.data.skills.length > 0 && (
                      <div>
                        <p className="text-xs font-medium text-slate-500 mb-2">核心技术 ({selectedDetails.data.skills.length})</p>
                        <div className="flex flex-wrap gap-1.5">
                          {selectedDetails.data.skills.map(s => (
                            <span key={s} className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 text-xs">{s}</span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Positions */}
                    {selectedDetails.data.positions.length > 0 && (
                      <div>
                        <p className="text-xs font-medium text-slate-500 mb-2">相关岗位 ({selectedDetails.data.positions.length})</p>
                        <div className="flex flex-wrap gap-1.5">
                          {selectedDetails.data.positions.map(p => (
                            <span key={p} className="px-2 py-0.5 rounded bg-violet-50 text-violet-700 text-xs">{p}</span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Related jobs */}
                    {selectedDetails.relatedJobs.length > 0 && (
                      <div>
                        <p className="text-xs font-medium text-slate-500 mb-2">匹配岗位图谱 ({selectedDetails.relatedJobs.length})</p>
                        <div className="space-y-1">
                          {selectedDetails.relatedJobs.slice(0, 6).map(j => (
                            <div key={j.id} className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-slate-50">
                              <span className="text-sm text-slate-600">{j.name}</span>
                              <span className="text-xs text-slate-400">{j.salary}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Website */}
                    {selectedDetails.data.website && (
                      <div className="pt-2 border-t border-slate-100">
                        <a
                          href={selectedDetails.data.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-700"
                        >
                          <Globe className="w-3 h-3" />
                          访问官网
                        </a>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
