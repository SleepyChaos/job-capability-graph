import { useEffect, useRef } from 'react'
import type { Graph as G6Graph, GraphData } from '@antv/g6'
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

function layoutExtent(data: RelationGraphResponse, viewportWidth: number, viewportHeight: number) {
  const totalNodeCount = data.role_nodes.length + data.capability_nodes.length
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
    nodes: [...data.role_nodes, ...data.capability_nodes].map((node) => {
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
  const anchors = domainAnchors(width, height)
  const roleDomains = new Map(data.role_nodes.map((node) => [node.id, node.domain_code]))
  const roleIndexByDomain = new Map<string, number>()
  const result = new Map<string, Pick<RelationGraphDatum, 'anchorX' | 'anchorY' | 'layoutCluster'>>()

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
  const cluster = node.type === 'job_cluster'
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

function nodeStyle(node: RelationNode, compact: boolean, zoomLevel: SemanticZoomLevel, layered = false) {
  const cluster = node.type === 'job_cluster'
  const color = domainColors[node.domain_code] ?? '#64748b'
  const size = nodeSize(node, compact, zoomLevel)
  const showLabel = zoomLevel !== 'overview' || cluster
  return {
    size: layered ? (cluster ? [compact ? 116 : 154, 48] as [number, number] : [compact ? 92 : 126, 40] as [number, number]) : size,
    radius: layered ? (cluster ? 10 : 20) : undefined,
    fill: cluster ? color : '#ffffff',
    stroke: color,
    lineWidth: cluster ? (zoomLevel === 'overview' ? 1 : 2) : (zoomLevel === 'overview' ? 1.5 : 3),
    labelText: showLabel ? node.label : '',
    labelPlacement: 'center' as const,
    labelFill: cluster ? '#ffffff' : '#193a55',
    labelFontSize: cluster ? (compact ? 8 : 10) : (compact ? 7 : zoomLevel === 'context' ? 8 : 9),
    labelFontWeight: cluster ? 600 : 500,
    labelMaxWidth: Math.floor(size * .76),
    labelWordWrap: true,
    labelMaxLines: zoomLevel === 'overview' ? 1 : 2,
    labelTextOverflow: 'clip',
    shadowColor: cluster ? 'rgba(21, 65, 105, .22)' : 'rgba(21, 65, 105, .12)',
    shadowBlur: zoomLevel === 'overview' ? 0 : (cluster ? 10 : 5),
  }
}

function edgeStyle(edge: RelationEdge, capabilityDomains: Map<string, string>, zoomLevel: SemanticZoomLevel) {
  const baseWidth = Math.min(4, Math.max(1, .7 + edge.importance / 34))
  return {
    stroke: domainColors[capabilityDomains.get(edge.target) ?? 'T7'] ?? '#94a3b8',
    lineWidth: zoomLevel === 'overview' ? Math.min(1, baseWidth) : baseWidth,
    strokeOpacity: zoomLevel === 'overview'
      ? Math.min(.22, Math.max(.08, edge.coverage_rate * .3))
      : Math.min(.78, Math.max(.18, edge.coverage_rate)),
    lineDash: edge.importance >= 60 ? undefined : [4, 3] as number[],
  }
}

function graphData(data: RelationGraphResponse, width: number, height: number, zoomLevel: SemanticZoomLevel, layered = false): GraphData {
  const compact = width < 480
  const capabilityDomains = new Map(data.capability_nodes.map((node) => [node.id, node.domain_code]))
  const extent = layoutExtent(data, width, height)
  const anchors = graphAnchors(data, extent.width, extent.height)
  const nodes = [...data.role_nodes, ...data.capability_nodes].map((node) => {
    const anchor = anchors.get(node.id)
    return {
      id: node.id,
      type: layered ? 'rect' as const : 'circle' as const,
      data: { ...node, ...anchor } as RelationGraphDatum as Record<string, unknown>,
      style: {
        ...nodeStyle(node, compact, zoomLevel, layered),
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

function semanticUpdates(data: RelationGraphResponse, width: number, zoomLevel: SemanticZoomLevel, layered = false) {
  const compact = width < 480
  const capabilityDomains = new Map(data.capability_nodes.map((node) => [node.id, node.domain_code]))
  return {
    nodes: [...data.role_nodes, ...data.capability_nodes].map((node) => ({ id: node.id, style: nodeStyle(node, compact, zoomLevel, layered) })),
    edges: data.edges.map((edge) => ({ id: edge.id, style: edgeStyle(edge, capabilityDomains, zoomLevel) })),
  }
}

export function RelationForceGraph({ graph, selectedId, onSelect, onExpand, layoutMode = 'force' }: RelationForceGraphProps) {
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
      const nodeCount = graph.role_nodes.length + graph.capability_nodes.length
      const useDagre = layoutMode === 'dagre_lr'
      const useWorker = !useDagre && nodeCount >= WORKER_LAYOUT_THRESHOLD
      let appliedZoomLevel: SemanticZoomLevel = 'detail'
      let preparedData = graphData(graph, viewportWidth, viewportHeight, appliedZoomLevel, useDagre)
      if (useWorker) {
        try {
          const positions = await runWorkerLayout(
            workerLayoutRequest(graph, viewportWidth, viewportHeight),
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
        } : useWorker ? undefined : {
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
        const updates = semanticUpdates(graph, viewportWidth, nextLevel, useDagre)
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
        if (target?.id) {
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
      if (selectedRef.current) await nextGraph.setElementState(selectedRef.current, ['selected'])
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
            const extent = layoutExtent(graph, viewportWidth, viewportHeight)
            const anchors = graphAnchors(graph, extent.width, extent.height)
            if (useDagre || useWorker) {
              await nextGraph.fitView({ when: 'always', direction: 'both' }, false)
              applySemanticZoom(true)
              return
            } else {
              nextGraph.updateNodeData([...graph.role_nodes, ...graph.capability_nodes].map((node) => ({
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
  }, [graph, layoutMode])

  useEffect(() => {
    const instance = instanceRef.current
    if (!instance) return
    const nodeIds = [...graph.role_nodes, ...graph.capability_nodes].map((node) => node.id)
    if (!selectedId) {
      void Promise.all([
        ...nodeIds.map((id) => instance.setElementState(id, [])),
        ...graph.edges.map((edge) => instance.setElementState(edge.id, [])),
      ])
      return
    }
    const relatedEdgeIds = new Set<string>()
    for (const edge of graph.edges) {
      if (edge.source === selectedId || edge.target === selectedId) {
        relatedEdgeIds.add(edge.id)
      }
    }
    void Promise.all([
      ...nodeIds.map((id) => {
        const connected = graph.edges.some((edge) => relatedEdgeIds.has(edge.id) && (edge.source === id || edge.target === id))
        return instance.setElementState(id, id === selectedId ? ['selected'] : connected ? [] : ['inactive'])
      }),
      ...graph.edges.map((edge) => instance.setElementState(edge.id, relatedEdgeIds.has(edge.id) ? ['selected'] : ['inactive'])),
    ])
  }, [graph.capability_nodes, graph.edges, graph.role_nodes, selectedId])

  return <div ref={containerRef} className="relation-force-graph" role="img" aria-label="支持语义缩放、按需展开与 Worker 力导向布局的岗位聚类和标准技术能力关系网络" />
}
