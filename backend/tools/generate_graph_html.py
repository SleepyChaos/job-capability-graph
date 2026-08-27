"""生成可交互的 ECharts 力导向全景图（HTML，内嵌数据）。

渲染"骨架图"：技术点(L1-L3) + 技能族 + 能力项 + 企业（约 1000 节点），
岗位节点不直接渲染（3718 个太密），用节点大小体现"关联岗位数"。

产出：../data/processed/graph_build/graph.html
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
GRAPH_DIR = os.path.join(HERE, "..", "..", "data", "processed", "graph_build")


def main():
    nodes = json.load(open(os.path.join(GRAPH_DIR, "nodes.json"), encoding="utf-8"))
    edges = json.load(open(os.path.join(GRAPH_DIR, "edges.json"), encoding="utf-8"))

    # 关联岗位数（能力项 / 企业 / 技术点的邻接岗位数）
    # 技术点(L2/L3/L4) 的关联岗位数来自 classified_to_L2 / classified_to_L3 直接分类边
    job_degree = defaultdict(int)
    for e in edges:
        if e["type"] == "requires_capability":
            job_degree[e["target"]] += 1
        elif e["type"] == "posts_job":
            job_degree[e["source"]] += 1
        elif e["type"] in ("classified_to_L2", "classified_to_L3"):
            job_degree[e["target"]] += 1

    # 骨架：排除 job 节点
    keep_nodes = [n for n in nodes if n["type"] != "job"]
    keep_ids = {n["id"] for n in keep_nodes}
    keep_edges = [e for e in edges
                  if e["source"] in keep_ids and e["target"] in keep_ids]

    # 类别与颜色
    type_meta = {
        "technology": ("技术点", "#378ADD"),
        "capability_family": ("技能族", "#1D9E75"),
        "capability": ("能力项", "#5DCAA5"),
        "organization": ("企业", "#D85A30"),
    }
    cat_index = {t: i for i, t in enumerate(type_meta)}

    ech_nodes = []
    for n in keep_nodes:
        deg = job_degree.get(n["id"], 0)
        base = {"technology": 18, "capability_family": 24, "capability": 20, "organization": 16}[n["type"]]
        size = base + min(20, deg / 60) if deg else base
        ech_nodes.append({
            "id": n["id"], "name": n.get("label", n["id"]),
            "category": cat_index[n["type"]],
            "symbolSize": round(size, 1),
            "value": deg,
            "t": n["type"],
            "meta": {k: v for k, v in n.items() if k not in ("id", "label", "type")},
        })

    ech_links = []
    for e in keep_edges:
        line_style = {"belongs_to": {"color": "#888780", "width": 1},
                      "belongs_to_family": {"color": "#5DCAA5", "width": 1},
                      "supports_domain": {"color": "#EF9F27", "width": 2},
                      "posts_job": {"color": "#D85A30", "width": 1}}[e["type"]]
        ech_links.append({"source": e["source"], "target": e["target"],
                          "rel": e["type"], "lineStyle": line_style})

    payload = {
        "nodes": ech_nodes, "links": ech_links,
        "categories": [{"name": name, "itemStyle": {"color": color}}
                       for name, color in type_meta.values()],
        "stats": {"node": len(ech_nodes), "edge": len(ech_links)},
    }
    payload_json = json.dumps(payload, ensure_ascii=False)

    html = HTML_TEMPLATE.replace("__PAYLOAD__", payload_json)
    out = os.path.join(GRAPH_DIR, "graph.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("生成:", out)
    print(f"骨架节点 {len(ech_nodes)} / 边 {len(ech_links)}")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>能力图谱 + 技术图谱 全景</title>
<style>
  html,body{margin:0;height:100%;background:#14171c;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;}
  #chart{position:absolute;inset:0;}
  .bar{position:absolute;top:12px;left:12px;z-index:10;background:rgba(24,28,34,.92);border:1px solid #2c313a;border-radius:10px;padding:12px 16px;color:#e6e8eb;font-size:13px;box-shadow:0 2px 12px rgba(0,0,0,.4);}
  .bar b{font-size:15px;}
  .bar .stat{color:#9aa4b2;margin-top:4px;}
  .legend{position:absolute;bottom:16px;left:12px;z-index:10;display:flex;gap:14px;flex-wrap:wrap;background:rgba(24,28,34,.92);border:1px solid #2c313a;border-radius:10px;padding:8px 14px;color:#e6e8eb;font-size:12px;}
  .legend span{display:inline-flex;align-items:center;gap:6px;}
  .dot{width:10px;height:10px;border-radius:50%;display:inline-block;}
  .hint{position:absolute;top:12px;right:12px;z-index:10;color:#6b7280;font-size:11px;background:rgba(24,28,34,.9);border:1px solid #2c313a;border-radius:8px;padding:6px 10px;}
</style>
</head>
<body>
<div class="bar">
  <b>能力图谱 + 技术图谱 · 全景骨架</b>
  <div class="stat" id="stat">节点 / 边</div>
</div>
<div class="hint">滚轮缩放 · 拖拽平移 · 悬停看详情 · 节点大小=关联岗位数</div>
<div class="legend">
  <span><i class="dot" style="background:#378ADD"></i>技术点(L1-L4)</span>
  <span><i class="dot" style="background:#1D9E75"></i>技能族</span>
  <span><i class="dot" style="background:#5DCAA5"></i>能力项</span>
  <span><i class="dot" style="background:#D85A30"></i>企业</span>
  <span><i class="dot" style="background:#EF9F27;border-radius:2px;height:3px;width:14px"></i>技能族→技术域桥</span>
</div>
<div id="chart"></div>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<script>
var data = __PAYLOAD__;
var chart = echarts.init(document.getElementById('chart'), null, {renderer:'canvas'});
document.getElementById('stat').textContent = '骨架节点 ' + data.stats.node + ' · 边 ' + data.stats.edge;
var option = {
  backgroundColor:'transparent',
  tooltip:{
    formatter:function(p){
      if(p.dataType==='edge'){
        var rel = {belongs_to:'技术层级',belongs_to_family:'能力项→技能族',supports_domain:'技能族→技术域(桥)'}[p.data.rel]||p.data.rel;
        return p.data.source + ' — ' + rel + ' — ' + p.data.target;
      }
      var n = p.data;
      var extra = n.value ? '关联岗位 ' + n.value : '';
      var meta = '';
      if(n.t==='technology') meta = n.meta.level + ' · ' + n.meta.code;
      if(n.t==='capability') meta = n.meta.family + ' · 命中' + n.meta.mention_count;
      if(n.t==='organization') meta = n.meta.chain || '';
      return '<b>'+n.name+'</b><br/>'+n.t + (meta?'<br/>'+meta:'') + (extra?'<br/>'+extra:'');
    }
  },
  legend:[{data:data.categories.map(function(c){return c.name;}),textStyle:{color:'#e6e8eb'},top:8}],
  series:[{
    type:'graph', layout:'force', roam:true, draggable:true,
    data:data.nodes, links:data.links, categories:data.categories,
    force:{repulsion:260, edgeLength:[30,110], gravity:0.08, friction:0.6},
    label:{show:true, position:'right', fontSize:11, color:'#c7ccd4',
           formatter:function(p){return p.data.value?p.data.name:'';}},
    emphasis:{focus:'adjacency', lineStyle:{width:2}},
    lineStyle:{color:'#555c66', curveness:0.06},
    edgeSymbol:['none','arrow'], edgeSymbolSize:6,
    zoom:0.7
  }]
};
chart.setOption(option);
chart.on('click', function(p){
  if(p.dataType==='node'){
    var n = p.data;
    chart.dispatchAction({type:'highlight', seriesIndex:0, dataIndex:p.dataIndex});
  }
});
window.addEventListener('resize', function(){chart.resize();});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
