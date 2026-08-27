import { useEffect, useMemo, useRef } from 'react'
import type { Graph as G6Graph, GraphData } from '@antv/g6'
import { classificationColor } from '../api/discovery'
import type { RelationEdge, RelationGraphResponse, RelationNode } from '../api/graphs'
import { domainColors } from '../data/graphData'
import type { RelationLayoutRequest, RelationLayoutResult } from './relationLayout.worker'

interface RelationForceGraphProps {
  graph: RelationGraphResponse
  selectedId: string | null
  onSelect: (id: string) => void
  onExpand: (id: string) => void
  layoutMode?: 'force' | 'dagre_lr'
}

interface RelationGraphDatum extends RelationNode {
  anchorX: number
  anchorY: number
  layoutCluster: string
  [key: string]: unknown
}

type SemanticZoomLevel = 'overview' | 'context' | 'detail'

const domainOrder = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']
const WORKER_LAYOUT_THRESHOLD = 120
const LARGE_GRAPH_NODE_DIAMETER = 136
const RADIAL_ROLE_SPACING = 104
const RADIAL_LANE_GAP = 112

function relationNodes(data: RelationGraphResponse): RelationNode[] {
  return [...data.role_nodes, ...data.domain_group_nodes, ...data.capability_nodes]
}

function filteredCapabilityDomain(data: RelationGraphResponse): string | null {
  const domainCode = data.filters.capability_domain_code
  return domainCode && domainOrder.includes(domainCode) ? domainCode : null
}

function radialProjection(data: RelationGraphResponse): RelationGraphResponse {
  const domainCode = filteredCapabilityDomain(data)
  if (!domainCode) return data

  const capabilityNodes = data.capability_nodes.filter((node) => node.domain_code === domainCode)
  const capabilityIds = new Set(capabilityNodes.map((node) => node.id))
  const relationEdges = data.edges.filter((edge) => (
    edge.relation_type === 'important_technology'
    && capabilityIds.has(edge.target)
  ))
  const connectedRoleIds = new Set(relationEdges.map((edge) => edge.source))
  const roleNodes = data.role_nodes.filter((node) => connectedRoleIds.has(node.id))
  const domainGroupNodes = data.domain_group_nodes.filter((node) => node.domain_code === domainCode)
  const visibleIds = new Set([
    ...roleNodes.map((node) => node.id),
    ...domainGroupNodes.map((node) => node.id),
    ...capabilityNodes.map((node) => node.id),
  ])

  return {
    ...data,
    role_nodes: roleNodes,
    domain_group_nodes: domainGroupNodes,
    capability_nodes: capabilityNodes,
    edges: data.edges.filter((edge) => (
      visibleIds.has(edge.source)
      && visibleIds.has(edge.target)
      && ['important_technology', 'dg_membership', 'hierarchy'].includes(edge.relation_type)
    )),
  }
}

function radialGeometry(
  data: RelationGraphResponse,
  viewportWidth: number,
  viewportHeight: number,
): {
  width: number
  height: number
  anchors: Map<string, Pick<RelationGraphDatum, 'anchorX' | 'anchorY' | 'layoutCluster'>>
} {
  const capabilityNodes = [...data.capability_nodes].sort((left, right) => left.label.localeCompare(right.label, 'zh-CN') || left.id.localeCompare(right.id))
  const capabilityCount = Math.max(1, capabilityNodes.length)
  const capabilityRadius = Math.max(230, capabilityCount * 92 / (Math.PI * 2))
  const outerBaseRadius = capabilityRadius + 310
  const sectorSpan = Math.PI * 2 / capabilityCount
  const roleGroups = new Map<string, RelationNode[]>()
  const primaryCapabilityByRole = new Map<string, { capabilityId: string; importance: number }>()

  for (const edge of data.edges) {
    if (edge.relation_type !== 'important_technology') continue
    const current = primaryCapabilityByRole.get(edge.source)
    if (!current || edge.importance > current.importance) {
      primaryCapabilityByRole.set(edge.source, { capabilityId: edge.target, importance: edge.importance })
    }
  }
  for (const role of data.role_nodes) {
    const capabilityId = primaryCapabilityByRole.get(role.id)?.capabilityId ?? capabilityNodes[0]?.id
    if (!capabilityId) continue
    const group = roleGroups.get(capabilityId) ?? []
    group.push(role)
    roleGroups.set(capabilityId, group)
  }
  roleGroups.forEach((roles) => roles.sort((left, right) => left.label.localeCompare(right.label, 'zh-CN') || left.id.localeCompare(right.id)))

  let maxLane = 0
  for (const capability of capabilityNodes) {
    const groupSize = roleGroups.get(capability.id)?.length ?? 0
    const laneCapacity = Math.max(1, Math.floor(sectorSpan * outerBaseRadius * .78 / RADIAL_ROLE_SPACING))
    maxLane = Math.max(maxLane, Math.max(0, Math.ceil(groupSize / laneCapacity) - 1))
  }
  const outerRadius = outerBaseRadius + maxLane * RADIAL_LANE_GAP
  const extentSize = Math.max(viewportWidth, viewportHeight, (outerRadius + 180) * 2)
  const width = Math.max(viewportWidth, extentSize)
  const height = Math.max(viewportHeight, extentSize)
  const centerX = width / 2
  const centerY = height / 2
  const anchors = new Map<string, Pick<RelationGraphDatum, 'anchorX' | 'anchorY' | 'layoutCluster'>>()
  const domainCode = filteredCapabilityDomain(data) ?? capabilityNodes[0]?.domain_code ?? 'T7'

  for (const domainNode of data.domain_group_nodes) {
    anchors.set(domainNode.id, { anchorX: centerX, anchorY: centerY, layoutCluster: `radial:${domainCode}:center` })
  }
  capabilityNodes.forEach((capability, capabilityIndex) => {
    const angle = -Math.PI / 2 + capabilityIndex * sectorSpan
    anchors.set(capability.id, {
      anchorX: centerX + Math.cos(angle) * capabilityRadius,
      anchorY: centerY + Math.sin(angle) * capabilityRadius,
      layoutCluster: `radial:${domainCode}:capability`,
    })

    const roles = roleGroups.get(capability.id) ?? []
    const laneCapacity = Math.max(1, Math.floor(sectorSpan * outerBaseRadius * .78 / RADIAL_ROLE_SPACING))
    roles.forEach((role, roleIndex) => {
      const lane = Math.floor(roleIndex / laneCapacity)
      const laneRoles = roles.slice(lane * laneCapacity, (lane + 1) * laneCapacity)
      const slot = roleIndex % laneCapacity
      const localFraction = laneRoles.length === 1 ? 0 : slot / (laneRoles.length - 1) - .5
      const roleAngle = angle + localFraction * sectorSpan * .76
      const roleRadius = outerBaseRadius + lane * RADIAL_LANE_GAP
      anchors.set(role.id, {
        anchorX: centerX + Math.cos(roleAngle) * roleRadius,
        anchorY: centerY + Math.sin(roleAngle) * roleRadius,
        layoutCluster: `radial:${domainCode}:role:${capability.id}`,
      })
    })
  })

  return { width, height, anchors }
}

function layoutExtent(data: RelationGraphResponse, viewportWidth: number, viewportHeight: number) {
  if (filteredCapabilityDomain(data)) {
    const radial = radialGeometry(data, viewportWidth, viewportHeight)
    return { width: radial.width, height: radial.height }
  }
  const totalNodeCount = relationNodes(data).length
  if (totalNodeCount < WORKER_LAYOUT_THRESHOLD) {
    return { width: viewportWidth, height: viewportHeight }
  }
  const domainCounts = new Map<string, number>()
  for (const node of data.role_nodes) {
    domainCounts.set(node.domain_code, (domainCounts.get(node.domain_code) ?? 0) + 1)
  }
  const largestDomain = Math.max(1, ...domainCounts.values())
  const clusterRadius = Math.max(760, Math.sqrt(largestDomain) * 72)
  const width = Math.max(viewportWidth, clusterRadius * 5.6)
  const height = Math.max(viewportHeight, clusterRadius * 4.65)
  return { width, height }
}

function workerLayoutRequest(
  data: RelationGraphResponse,
  width: number,
  height: number,
): RelationLayoutRequest {
  const extent = layoutExtent(data, width, height)
  const anchors = graphAnchors(data, extent.width, extent.height)
  return {
    nodes: relationNodes(data).map((node) => {
      const anchor = anchors.get(node.id) ?? {
        anchorX: extent.width / 2,
        anchorY: extent.height / 2,
        layoutCluster: node.domain_code,
      }
      return {
        id: node.id,
        x: anchor.anchorX,
        y: anchor.anchorY,
        ...anchor,
      }
    }),
    edges: data.edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target })),
    width: extent.width,
    height: extent.height,
  }
}

function runWorkerLayout(
  request: RelationLayoutRequest,
  activeWorkers: Set<Worker>,
): Promise<RelationLayoutResult['positions']> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL('./relationLayout.worker.ts', import.meta.url), { type: 'module' })
    activeWorkers.add(worker)
    const close = () => {
      worker.terminate()
      activeWorkers.delete(worker)
    }
    worker.onmessage = (event: MessageEvent<RelationLayoutResult>) => {
      const result = event.data
      close()
      if (result.error) reject(new Error(result.error))
      else resolve(result.positions)
    }
    worker.onerror = (event) => {
      close()
      reject(new Error(event.message || 'Worker 布局失败'))
    }
    worker.postMessage(request)
  })
}

function applyPositions(data: GraphData, positions: RelationLayoutResult['positions']): GraphData {
  const positionById = new Map(positions.map((position) => [position.id, position]))
  return {
    ...data,
    nodes: data.nodes?.map((node) => {
      const position = positionById.get(node.id)
      return position ? { ...node, style: { ...node.style, x: position.x, y: position.y } } : node
    }),
  }
}

function domainAnchors(width: number, height: number): Map<string, { x: number; y: number }> {
  const centerX = width / 2
  const centerY = height / 2
  const largeLayout = width > 1600 || height > 1400
  const radiusX = largeLayout ? width * .39 : Math.max(260, Math.min(width * .42, 720))
  const radiusY = largeLayout ? height * .38 : Math.max(220, Math.min(height * .40, 520))
  return new Map(domainOrder.map((domainCode, index) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / domainOrder.length
    return [domainCode, {
      x: centerX + Math.cos(angle) * radiusX,
      y: centerY + Math.sin(angle) * radiusY,
    }]
  }))
}

function graphAnchors(
  data: RelationGraphResponse,
  width: number,
  height: number,
): Map<string, Pick<RelationGraphDatum, 'anchorX' | 'anchorY' | 'layoutCluster'>> {
  if (filteredCapabilityDomain(data)) return radialGeometry(data, width, height).anchors
  const anchors = domainAnchors(width, height)
  const roleDomains = new Map(data.role_nodes.map((node) => [node.id, node.domain_code]))
  const roleIndexByDomain = new Map<string, number>()
  const result = new Map<string, Pick<RelationGraphDatum, 'anchorX' | 'anchorY' | 'layoutCluster'>>()

  for (const node of data.domain_group_nodes) {
    const anchor = anchors.get(node.domain_code) ?? { x: width / 2, y: height / 2 }
    result.set(node.id, {
      anchorX: anchor.x,
      anchorY: anchor.y,
      layoutCluster: node.domain_code,
    })
  }

  for (const node of data.role_nodes) {
    const localIndex = roleIndexByDomain.get(node.domain_code) ?? 0
    roleIndexByDomain.set(node.domain_code, localIndex + 1)
    const domainIndex = Math.max(0, domainOrder.indexOf(node.domain_code))
    const sectorCenter = -Math.PI / 2 + (Math.PI * 2 * domainIndex) / domainOrder.length
    const lane = Math.floor(localIndex / 9)
    const slot = localIndex % 9
    const localAngle = sectorCenter + (slot - 4) * .075 + lane * .025
    const localRadiusX = (width > 1600 ? width * .39 : Math.max(260, Math.min(width * .42, 720))) + lane * 92
    const localRadiusY = (height > 1400 ? height * .38 : Math.max(220, Math.min(height * .40, 520))) + lane * 72
    result.set(node.id, {
      anchorX: width / 2 + Math.cos(localAngle) * localRadiusX,
      anchorY: height / 2 + Math.sin(localAngle) * localRadiusY,
      layoutCluster: node.domain_code,
    })
  }

  const capabilitySums = new Map<string, { x: number; y: number; weight: number }>()
  const capabilityDomainWeights = new Map<string, Map<string, number>>()
  for (const edge of data.edges) {
    const roleDomain = roleDomains.get(edge.source)
    if (!roleDomain) continue
    const roleAnchor = anchors.get(roleDomain)
    if (!roleAnchor) continue
    const weight = Math.max(1, edge.importance / 25)
    const sum = capabilitySums.get(edge.target) ?? { x: 0, y: 0, weight: 0 }
    sum.x += roleAnchor.x * weight
    sum.y += roleAnchor.y * weight
    sum.weight += weight
    capabilitySums.set(edge.target, sum)
    const domainWeights = capabilityDomainWeights.get(edge.target) ?? new Map<string, number>()
    domainWeights.set(roleDomain, (domainWeights.get(roleDomain) ?? 0) + weight)
    capabilityDomainWeights.set(edge.target, domainWeights)
  }

  for (const node of data.capability_nodes) {
    const sum = capabilitySums.get(node.id)
    const fallback = anchors.get(node.domain_code) ?? { x: width / 2, y: height / 2 }
    const domainWeights = capabilityDomainWeights.get(node.id)
    const layoutCluster = domainWeights
      ? [...domainWeights].sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))[0]?.[0] ?? node.domain_code
      : node.domain_code
    const weightedX = sum && sum.weight ? sum.x / sum.weight : fallback.x
    const weightedY = sum && sum.weight ? sum.y / sum.weight : fallback.y
    result.set(node.id, {
      anchorX: width / 2 + (weightedX - width / 2) * .42,
      anchorY: height / 2 + (weightedY - height / 2) * .42,
      layoutCluster,
    })
  }
  return result
}

function getZoomLevel(zoom: number): SemanticZoomLevel {
  if (zoom < .36) return 'overview'
  if (zoom < .62) return 'context'
  return 'detail'
}

function nodeSize(node: RelationNode, compact: boolean, zoomLevel: SemanticZoomLevel): number {
  // 候选与聚类同属 role 一侧，尺寸口径相同——它们是同级的，只是一个是观测、
  // 一个是提议，区别体现在描边与虚线上，不体现在大小上。
  const cluster = node.type === 'job_cluster' || node.type === 'emerging_candidate'
  const domainGroup = node.type === 'technology_domain'
  if (domainGroup) return zoomLevel === 'overview' ? (compact ? 58 : 70) : (compact ? 68 : 82)
  if (zoomLevel === 'overview') return cluster ? (compact ? 68 : 84) : (compact ? 40 : 52)
  if (zoomLevel === 'context') return cluster ? (compact ? 76 : 96) : (compact ? 46 : 58)
  if (cluster) return Math.min(
    compact ? 108 : 132,
    Math.max(compact ? 78 : 92, 64 + Math.sqrt(node.evidence_count) * (compact ? 8 : 10)),
  )
  return Math.min(
    compact ? 76 : 92,
    Math.max(compact ? 54 : 62, 38 + Math.sqrt(node.evidence_count) * (compact ? 6 : 7)),
  )
}

function nodeStyle(node: RelationNode, compact: boolean, zoomLevel: SemanticZoomLevel, layered = false, radial = false) {
  const proposal = node.type === 'emerging_candidate'
  const cluster = node.type === 'job_cluster' || proposal
  const domainGroup = node.type === 'technology_domain'
  /*
    提议节点按**分类**着色，而不是按技术域。

    观测到的聚类用技术域色回答「这个岗位属于哪个技术方向」；提议节点在图上要
    回答的是另一个问题——「这条提议是哪来的、可信到什么程度」。同用技术域色，
    一个里程碑信号和一个已被覆盖的候选会长成同一个颜色，而这两者的性质差着
    一次参照系的切换。色值与候选墙的分类色同源，跨页一致。

    色相与技术域色刻意错开（分类色偏中低饱和），加上空心 + 虚线描边，
    提议在图上不会被误读成一个已入库的岗位。
  */
  const color = proposal
    ? classificationColor[node.classification_code ?? '']?.dot ?? '#8fa0b3'
    : domainColors[node.domain_code] ?? '#64748b'
  const size = nodeSize(node, compact, zoomLevel)
  const showLabel = radial || zoomLevel !== 'overview' || cluster || domainGroup
  return {
    size: layered ? (cluster ? [compact ? 116 : 154, 48] as [number, number] : domainGroup ? [compact ? 106 : 138, 44] as [number, number] : [compact ? 92 : 126, 40] as [number, number]) : size,
    radius: layered ? (cluster ? 10 : domainGroup ? 12 : 20) : undefined,
    // 提议节点用空心 + 虚线描边：与观测到的聚类同级同尺寸，但一眼能看出它还没入库。
    fill: proposal ? '#ffffff' : cluster ? color : domainGroup ? `${color}18` : '#ffffff',
    stroke: color,
    lineDash: proposal ? [5, 4] : undefined,
    lineWidth: domainGroup ? 4 : cluster ? (zoomLevel === 'overview' ? 1 : 2) : (zoomLevel === 'overview' ? 1.5 : 3),
    labelText: showLabel ? node.label : '',
    labelPlacement: 'center' as const,
    labelFill: proposal ? color : cluster ? '#ffffff' : domainGroup ? color : '#193a55',
    labelFontSize: cluster ? (compact ? 8 : 10) : domainGroup ? (compact ? 8 : 10) : (compact ? 7 : zoomLevel === 'context' ? 8 : 9),
    labelFontWeight: proposal ? 600 : cluster || domainGroup ? 700 : 500,
    labelMaxWidth: Math.floor(size * .76),
    labelWordWrap: true,
    labelMaxLines: radial || zoomLevel !== 'overview' ? 2 : 1,
    labelTextOverflow: 'clip',
    shadowColor: cluster ? 'rgba(21, 65, 105, .22)' : 'rgba(21, 65, 105, .12)',
    shadowBlur: zoomLevel === 'overview' ? 0 : (cluster ? 10 : 5),
  }
}

function edgeStyle(edge: RelationEdge, capabilityDomains: Map<string, string>, zoomLevel: SemanticZoomLevel) {
  const baseWidth = Math.min(4, Math.max(1, .7 + edge.importance / 34))
    // 候选的边是**提议**而非观测到的关联，没有覆盖率——用固定的疏虚线和较低不透明度
    // 与聚类的实测边区分开，避免读者把提议当成既有事实。
    // 层级边（技术域归属、层次关系）另用密虚线，与二者都区分开。
    const proposal = edge.relation_type === 'proposed_technology'
    const hierarchyEdge = edge.relation_type === 'dg_membership' || edge.relation_type === 'hierarchy'
    const coverage = edge.coverage_rate ?? 0
    return {
      stroke: domainColors[capabilityDomains.get(edge.target) ?? 'T7'] ?? '#94a3b8',
      lineWidth: zoomLevel === 'overview' ? Math.min(1, baseWidth) : baseWidth,
      strokeOpacity: proposal
        ? (zoomLevel === 'overview' ? .16 : .42)
        : zoomLevel === 'overview'
          ? Math.min(.22, Math.max(.08, coverage * .3))
          : Math.min(.78, Math.max(.18, coverage)),
      lineDash: proposal
        ? [7, 5] as number[]
        : hierarchyEdge || edge.importance < 60
          ? [4, 3] as number[]
          : undefined,
  }
}

function graphData(data: RelationGraphResponse, width: number, height: number, zoomLevel: SemanticZoomLevel, layered = false, radial = false): GraphData {
  const compact = width < 480
  const capabilityDomains = new Map(data.capability_nodes.map((node) => [node.id, node.domain_code]))
  const extent = layoutExtent(data, width, height)
  const anchors = graphAnchors(data, extent.width, extent.height)
  const nodes = relationNodes(data).map((node) => {
    const anchor = anchors.get(node.id)
    return {
      id: node.id,
      type: layered ? 'rect' as const : 'circle' as const,
      data: { ...node, ...anchor } as RelationGraphDatum as Record<string, unknown>,
      style: {
        ...nodeStyle(node, compact, zoomLevel, layered, radial),
        x: anchor?.anchorX,
        y: anchor?.anchorY,
      },
    }
  })
  const edges = data.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    data: edge as unknown as Record<string, unknown>,
    style: edgeStyle(edge, capabilityDomains, zoomLevel),
  }))
  return { nodes, edges }
}

function semanticUpdates(data: RelationGraphResponse, width: number, zoomLevel: SemanticZoomLevel, layered = false, radial = false) {
  const compact = width < 480
  const capabilityDomains = new Map(data.capability_nodes.map((node) => [node.id, node.domain_code]))
  return {
    nodes: relationNodes(data).map((node) => ({ id: node.id, style: nodeStyle(node, compact, zoomLevel, layered, radial) })),
    edges: data.edges.map((edge) => ({ id: edge.id, style: edgeStyle(edge, capabilityDomains, zoomLevel) })),
  }
}

export function RelationForceGraph({ graph, selectedId, onSelect, onExpand, layoutMode = 'force' }: RelationForceGraphProps) {
  const renderedGraph = useMemo(() => radialProjection(graph), [graph])
  const containerRef = useRef<HTMLDivElement | null>(null)
  const instanceRef = useRef<G6Graph | null>(null)
  const selectedRef = useRef(selectedId)
  const callbacksRef = useRef({ onSelect, onExpand })
  selectedRef.current = selectedId
  callbacksRef.current = { onSelect, onExpand }

  useEffect(() => {
    const container = containerRef.current
    if (!container) return undefined
    let disposed = false
    let graphInstance: G6Graph | null = null
    let frameId = 0
    let resizeTimer: number | null = null
    let resizeObserver: ResizeObserver | null = null
    const activeWorkers = new Set<Worker>()

    void import('@antv/g6').then(async ({ Graph }) => {
      if (disposed) return
      let viewportWidth = Math.max(container.clientWidth, 320)
      let viewportHeight = Math.max(container.clientHeight, 440)
      const nodeCount = relationNodes(renderedGraph).length
      const useDagre = layoutMode === 'dagre_lr'
      const useRadial = !useDagre && Boolean(filteredCapabilityDomain(renderedGraph))
      const useWorker = !useDagre && !useRadial && nodeCount >= WORKER_LAYOUT_THRESHOLD
      let appliedZoomLevel: SemanticZoomLevel = 'detail'
      let preparedData = graphData(renderedGraph, viewportWidth, viewportHeight, appliedZoomLevel, useDagre, useRadial)
      if (useWorker) {
        try {
          const positions = await runWorkerLayout(
            workerLayoutRequest(renderedGraph, viewportWidth, viewportHeight),
            activeWorkers,
          )
          preparedData = applyPositions(preparedData, positions)
        } catch {
          // The deterministic domain anchors in graphData remain a readable fallback.
        }
      }
      if (disposed) return
      const nextGraph = new Graph({
        container,
        data: preparedData,
        autoResize: true,
        background: '#ffffff',
        animation: false,
        zoomRange: [.025, 3.2],
        node: {
          state: {
            selected: { lineWidth: 4, shadowColor: '#1769e0', shadowBlur: 18 },
            inactive: { opacity: .16 },
          },
        },
        edge: {
          state: {
            selected: { lineWidth: 3.5, strokeOpacity: 1 },
            inactive: { strokeOpacity: .035 },
          },
        },
        layout: useDagre ? {
          type: 'dagre',
          rankdir: 'LR',
          align: 'UL',
          nodesep: 30,
          ranksep: 118,
          controlPoints: false,
          nodeSize: [150, 48],
        } : useRadial || useWorker ? undefined : {
          type: 'd3-force',
          enableWorker: false,
          iterations: 100,
          linkDistance: Math.max(120, Math.min(viewportWidth, viewportHeight) * (nodeCount > 400 ? .18 : .25)),
          edgeStrength: nodeCount > 400 ? .009 : .018,
          nodeStrength: nodeCount > 400 ? -260 : -440,
          distanceMax: Math.max(viewportWidth, viewportHeight) * .68,
          preventOverlap: true,
          nodeSize: nodeCount > 400 ? LARGE_GRAPH_NODE_DIAMETER : 72,
          collideStrength: .9,
          collideIterations: nodeCount > 400 ? 1 : 2,
          clustering: true,
          clusterBy: 'node.data.layoutCluster',
          clusterFociStrength: .62,
          clusterNodeStrength: nodeCount > 400 ? -55 : -78,
          clusterEdgeDistance: nodeCount > 400 ? 250 : 310,
          clusterEdgeStrength: .014,
          clusterNodeSize: nodeCount > 400 ? LARGE_GRAPH_NODE_DIAMETER : 72,
          alphaMin: .08,
          alphaDecay: .045,
          x: { strength: .78, x: (node) => Number((node.data as RelationGraphDatum).anchorX) },
          y: { strength: .78, y: (node) => Number((node.data as RelationGraphDatum).anchorY) },
        },
        behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element', 'hover-activate'],
      })
      graphInstance = nextGraph
      const applySemanticZoom = (force = false) => {
        frameId = 0
        const nextLevel = getZoomLevel(nextGraph.getZoom())
        if (!force && nextLevel === appliedZoomLevel) return
        appliedZoomLevel = nextLevel
        const updates = semanticUpdates(renderedGraph, viewportWidth, nextLevel, useDagre, useRadial)
        nextGraph.updateNodeData(updates.nodes)
        nextGraph.updateEdgeData(updates.edges)
        void nextGraph.draw()
      }
      nextGraph.on('aftertransform', () => {
        if (!frameId) frameId = requestAnimationFrame(() => applySemanticZoom())
      })
      nextGraph.on('node:click', (event) => {
        const target = (event as unknown as { target?: { id?: string } }).target
        if (target?.id) callbacksRef.current.onSelect(target.id)
      })
      nextGraph.on('node:dblclick', (event) => {
        const target = (event as unknown as { target?: { id?: string } }).target
        if (target?.id && !target.id.startsWith('dg-')) {
          callbacksRef.current.onSelect(target.id)
          callbacksRef.current.onExpand(target.id)
        }
      })
      await nextGraph.render()
      if (disposed) {
        nextGraph.destroy()
        return
      }
      instanceRef.current = nextGraph
      const renderedNodeIds = new Set(relationNodes(renderedGraph).map((node) => node.id))
      if (selectedRef.current && renderedNodeIds.has(selectedRef.current)) await nextGraph.setElementState(selectedRef.current, ['selected'])
      await nextGraph.fitView({ when: 'always', direction: 'both' })
      applySemanticZoom()

      resizeObserver = new ResizeObserver(() => {
        if (resizeTimer !== null) window.clearTimeout(resizeTimer)
        resizeTimer = window.setTimeout(() => {
          resizeTimer = null
          if (disposed) return
          const nextWidth = Math.max(container.clientWidth, 320)
          const nextHeight = Math.max(container.clientHeight, 440)
          if (disposed) return
          viewportWidth = nextWidth
          viewportHeight = nextHeight
          nextGraph.resize(viewportWidth, viewportHeight)
          void (async () => {
            const extent = layoutExtent(renderedGraph, viewportWidth, viewportHeight)
            const anchors = graphAnchors(renderedGraph, extent.width, extent.height)
            if (useDagre || useWorker || useRadial) {
              await nextGraph.fitView({ when: 'always', direction: 'both' }, false)
              applySemanticZoom(true)
              return
            } else {
              nextGraph.updateNodeData(relationNodes(renderedGraph).map((node) => ({
                id: node.id,
                data: { ...node, ...anchors.get(node.id) },
              })))
              await nextGraph.layout()
            }
            if (disposed) return
            await nextGraph.fitView({ when: 'always', direction: 'both' }, false)
            applySemanticZoom(true)
          })()
        }, 240)
      })
      resizeObserver.observe(container)
    }).catch(() => undefined)

    return () => {
      disposed = true
      if (frameId) cancelAnimationFrame(frameId)
      if (resizeTimer !== null) window.clearTimeout(resizeTimer)
      resizeObserver?.disconnect()
      activeWorkers.forEach((worker) => worker.terminate())
      activeWorkers.clear()
      instanceRef.current = null
      graphInstance?.destroy()
    }
  }, [layoutMode, renderedGraph])

  useEffect(() => {
    const instance = instanceRef.current
    if (!instance) return
    const nodeIds = relationNodes(renderedGraph).map((node) => node.id)
    const effectiveSelectedId = selectedId && nodeIds.includes(selectedId) ? selectedId : null
    if (!effectiveSelectedId) {
      void Promise.all([
        ...nodeIds.map((id) => instance.setElementState(id, [])),
        ...renderedGraph.edges.map((edge) => instance.setElementState(edge.id, [])),
      ])
      return
    }
    const relatedEdgeIds = new Set<string>()
    for (const edge of renderedGraph.edges) {
      if (edge.source === effectiveSelectedId || edge.target === effectiveSelectedId) {
        relatedEdgeIds.add(edge.id)
      }
    }
    void Promise.all([
      ...nodeIds.map((id) => {
        const connected = renderedGraph.edges.some((edge) => relatedEdgeIds.has(edge.id) && (edge.source === id || edge.target === id))
        return instance.setElementState(id, id === effectiveSelectedId ? ['selected'] : connected ? [] : ['inactive'])
      }),
      ...renderedGraph.edges.map((edge) => instance.setElementState(edge.id, relatedEdgeIds.has(edge.id) ? ['selected'] : ['inactive'])),
    ])
  }, [renderedGraph, selectedId])

  return <div ref={containerRef} className="relation-force-graph" role="img" aria-label="能力领域筛选时按领域、L2 能力、岗位簇三层同心展开的岗位能力关系网络" />
}
