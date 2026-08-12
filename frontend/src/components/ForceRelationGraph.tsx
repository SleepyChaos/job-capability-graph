import { Graph } from '@antv/g6'
import type { GraphData, IElementEvent, NodeData } from '@antv/g6'
import { useEffect, useRef } from 'react'
import type { RelationGraphResponse } from '../api/graphs'
import { domainColors } from '../data/graphData'

interface ForceRelationGraphProps {
  data: RelationGraphResponse
  selected: string | null
  onSelect: (nodeId: string) => void
}

function toGraphData(data: RelationGraphResponse): GraphData {
  const relationNodes = [...data.role_nodes, ...data.capability_nodes]
  const nodes: NodeData[] = relationNodes.map((node) => ({
    id: node.id,
    type: node.type === 'job_cluster' ? 'rect' : 'circle',
    data: {
      nodeType: node.type,
      label: node.label,
      domainCode: node.domain_code,
      evidenceCount: node.evidence_count,
      metrics: node.metrics,
    },
  }))

  return {
    nodes,
    edges: data.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      data: {
        importance: edge.importance,
        coverageRate: edge.coverage_rate,
      },
    })),
  }
}

export function ForceRelationGraph({ data, selected, onSelect }: ForceRelationGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<Graph | null>(null)
  const graphReadyRef = useRef(false)
  const lastAppliedSelectedRef = useRef<string | null>(null)
  const selectedRef = useRef<string | null>(selected)
  const onSelectRef = useRef(onSelect)
  onSelectRef.current = onSelect
  selectedRef.current = selected

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const graph = new Graph({
      container,
      autoResize: true,
      autoFit: 'view',
      padding: [34, 34, 34, 34],
      animation: true,
      data: toGraphData(data),
      layout: {
        type: 'force',
        preventOverlap: true,
        nodeSize: (node: NodeData) => node.data?.nodeType === 'job_cluster' ? 128 : 18,
        nodeStrength: -120,
        edgeStrength: 0.35,
        gravity: 0.08,
        damping: 0.9,
        iterations: 260,
      },
      node: {
        type: (datum) => datum.data?.nodeType === 'job_cluster' ? 'rect' : 'circle',
        style: (datum) => {
          const isCluster = datum.data?.nodeType === 'job_cluster'
          const domainCode = String(datum.data?.domainCode ?? 'T7')
          const color = domainColors[domainCode] ?? domainColors.T7
          return {
            size: isCluster ? [128, 46] : 18,
            radius: isCluster ? 9 : 9,
            fill: isCluster ? color : '#ffffff',
            stroke: color,
            lineWidth: isCluster ? 1.8 : 2,
            labelText: String(datum.data?.label ?? datum.id),
            labelFill: isCluster ? '#ffffff' : '#24445f',
            labelFontSize: isCluster ? 10 : 9,
            labelFontWeight: isCluster ? 650 : 500,
            labelPlacement: 'center',
            labelMaxWidth: isCluster ? 112 : 140,
            labelWordWrap: true,
            labelWordWrapWidth: isCluster ? 112 : 140,
            labelBackground: !isCluster,
            labelBackgroundFill: '#ffffff',
            labelBackgroundOpacity: 0.88,
            labelPadding: [3, 5],
          }
        },
        state: {
          selected: {
            lineWidth: 3.5,
            shadowColor: '#1d65d8',
            shadowBlur: 18,
            halo: true,
            haloStroke: '#1d65d8',
            haloLineWidth: 2,
            haloLineDash: [4, 3],
          },
        },
      },
      edge: {
        type: 'line',
        style: (datum) => ({
          stroke: '#8ea4bb',
          lineWidth: Math.max(0.7, Math.min(2.8, Number(datum.data?.importance ?? 50) / 42)),
          opacity: Math.max(0.22, Math.min(0.78, Number(datum.data?.importance ?? 50) / 100)),
        }),
        state: {
          selected: { stroke: '#2368d7', lineWidth: 2.6, opacity: 0.9 },
        },
      },
      behaviors: [
        'drag-canvas',
        'zoom-canvas',
        'drag-element-force',
        'click-select',
        'hover-activate',
      ],
    })

    graph.on('node:click', (event: IElementEvent) => {
      const nodeId = String(event.target.id)
      onSelectRef.current(nodeId)
    })

    graph.on('canvas:click', () => {
      onSelectRef.current('')
    })

    graphRef.current = graph
    void graph.render().then(() => {
      graphReadyRef.current = true
      const initial = selectedRef.current
      if (initial) {
        lastAppliedSelectedRef.current = initial
        void graph.setElementState(initial, ['selected'])
      }
    })

    return () => {
      graphReadyRef.current = false
      lastAppliedSelectedRef.current = null
      graph.destroy()
      graphRef.current = null
    }
  }, [data])

  useEffect(() => {
    const graph = graphRef.current
    if (!graph || !graphReadyRef.current) return
    const previous = lastAppliedSelectedRef.current
    if (previous && previous !== selected) void graph.setElementState(previous, [])
    if (selected) void graph.setElementState(selected, ['selected'])
    lastAppliedSelectedRef.current = selected
  }, [selected])

  return <div ref={containerRef} className="g6-relation-canvas" aria-label="G6 力导向岗位能力关系图" />
}
