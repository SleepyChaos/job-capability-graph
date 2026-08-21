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
    linkDistance: dense ? 270 : Math.max(150, Math.min(width, height) * .25),
    edgeStrength: dense ? .008 : .018,
    nodeStrength: dense ? -310 : -440,
    distanceMax: Math.max(width, height) * .82,
    preventOverlap: true,
    nodeSize: nodeDiameter,
    nodeSpacing: dense ? 6 : 16,
    collideStrength: 1,
    collideIterations: dense ? 4 : 2,
    clustering: true,
    clusterBy: (node) => String(node._original.layoutCluster),
    clusterFociStrength: .62,
    clusterNodeStrength: dense ? -72 : -90,
    clusterEdgeDistance: dense ? 390 : 330,
    clusterEdgeStrength: .012,
    clusterNodeSize: nodeDiameter,
    alphaMin: .035,
    alphaDecay: .025,
    x: {
      strength: .86,
      x: (node) => Number(node._original.anchorX),
    },
    y: {
      strength: .86,
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
