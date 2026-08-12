import { D3ForceLayout } from '@antv/g6'

interface RelationLayoutNode {
  id: string
  x: number
  y: number
  anchorX: number
  anchorY: number
  layoutCluster: string
}

interface RelationLayoutEdge {
  id: string
  source: string
  target: string
}

export interface RelationLayoutRequest {
  nodes: RelationLayoutNode[]
  edges: RelationLayoutEdge[]
  width: number
  height: number
}

export interface RelationLayoutResult {
  positions: Array<{ id: string; x: number; y: number }>
  error?: string
}

self.onmessage = async (event: MessageEvent<RelationLayoutRequest>) => {
  const { nodes, edges, width, height } = event.data
  const dense = nodes.length > 400
  const nodeDiameter = dense ? 136 : 72
  const layout = new D3ForceLayout({
    enableWorker: false,
    width,
    height,
    center: { x: width / 2, y: height / 2 },
    centerStrength: .025,
    linkDistance: dense ? 190 : Math.max(110, Math.min(width, height) * .2),
    edgeStrength: dense ? .012 : .025,
    nodeStrength: dense ? -250 : -360,
    distanceMax: Math.max(width, height) * .82,
    preventOverlap: true,
    nodeSize: nodeDiameter,
    nodeSpacing: dense ? 6 : 16,
    collideStrength: 1,
    collideIterations: dense ? 4 : 2,
    clustering: true,
    clusterBy: (node) => String(node._original.layoutCluster),
    clusterFociStrength: .92,
    clusterNodeStrength: dense ? -62 : -72,
    clusterEdgeDistance: dense ? 320 : 260,
    clusterEdgeStrength: .018,
    clusterNodeSize: nodeDiameter,
    alphaMin: .035,
    alphaDecay: .025,
    x: {
      strength: .64,
      x: (node) => Number(node._original.anchorX),
    },
    y: {
      strength: .64,
      y: (node) => Number(node._original.anchorY),
    },
  })

  try {
    await layout.execute({ nodes, edges })
    const positions: RelationLayoutResult['positions'] = []
    layout.forEachNode((node) => positions.push({ id: String(node.id), x: node.x, y: node.y }))
    self.postMessage({ positions } satisfies RelationLayoutResult)
  } catch (error) {
    self.postMessage({
      positions: [],
      error: error instanceof Error ? error.message : 'Worker 布局失败',
    } satisfies RelationLayoutResult)
  } finally {
    layout.destroy()
  }
}
