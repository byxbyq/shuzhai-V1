// -*- coding: utf-8 -*-
/**
 * 白城主 Flow Editor — 通用节点连线编辑器
 *
 * 基于 SVG 画布，节点类型从 /api/flow/registry 动态加载。
 * 挂载到 window.WhiteCityEditor。
 */
(function () {
  'use strict';

  const API_BASE = '/api/flow';

  // ═══════════════════════════════════════
  // 状态
  // ═══════════════════════════════════════
  let nodeRegistry = [];       // 从后端拉取的节点类型列表
  let categories = {};         // 分类映射
  let pipelines = [];          // 预置流水线
  let nodeCounter = 0;         // 实例自增ID

  let nodes = [];              // 画布上的节点实例
  let edges = [];              // 连线
  let selectedNodeId = null;
  let selectedEdgeId = null;

  // 交互状态
  let dragging = null;         // {id, ox, oy}
  let connecting = null;       // {nodeId, portName, ox, oy}
  let panning = false;
  let panStart = { x: 0, y: 0 };
  let offsetX = 0, offsetY = 0;
  let scale = 1;

  // 撤销栈
  let undoStack = [];
  const MAX_UNDO = 50;

  // ═══════════════════════════════════════
  // SVG 元素
  // ═══════════════════════════════════════
  let svg, gMain, gEdges, gTemp, gNodes;
  let panelContainer;

  // ═══════════════════════════════════════
  // 常量
  // ═══════════════════════════════════════
  const NODE_W = 180;
  const NODE_H_MIN = 80;     // 最小高度，实际随端口数自适应
  const PORT_ROW = 26;       // 每个端口的行高
  const PORT_TOP = 52;       // 首个端口的 y 起始
  const PORT_R = 6;
  const COLORS = {
    bg: '#1a1a2e',
    grid: '#252540',
    nodeFill: '#16213e',
    nodeStroke: '#0f3460',
    nodeSelected: '#e94560',
    portInput: '#00d2ff',
    portOutput: '#ff6b6b',
    edgeDefault: '#4a4a8a',
    edgeHover: '#e94560',
    text: '#c0c0c0',
    textDim: '#707090',
    button: '#0f3460',
    buttonHover: '#e94560',
  };

  // ═══════════════════════════════════════
  // 初始化
  // ═══════════════════════════════════════
  async function init(containerId) {
    panelContainer = document.getElementById(containerId || 'white-city-panel');
    if (!panelContainer) {
      console.warn('[WhiteCity] 容器未找到:', containerId);
      return;
    }

    panelContainer.innerHTML = buildPanelHTML();
    svg = panelContainer.querySelector('#wc-canvas');
    gMain = svg.querySelector('#wc-main');
    gEdges = gMain.querySelector('#wc-edges');
    gTemp = gMain.querySelector('#wc-temp');
    gNodes = gMain.querySelector('#wc-nodes');

    bindEvents();
    await loadRegistry();
    renderToolbar();
    render();
  }

  function buildPanelHTML() {
    return `
    <div class="wc-panel" style="display:flex;flex-direction:column;width:100%;height:100%;background:${COLORS.bg};">
      <div class="wc-toolbar" id="wc-toolbar" style="display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid ${COLORS.grid};flex-shrink:0;"></div>
      <div style="flex:1;display:flex;overflow:hidden;">
        <div id="wc-canvas-wrap" style="flex:1;overflow:hidden;position:relative;">
          <svg id="wc-canvas" style="width:100%;height:100%;display:block;">
            <defs>
              <marker id="wc-arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                <polygon points="0 0, 8 3, 0 6" fill="${COLORS.edgeDefault}" />
              </marker>
            </defs>
            <g id="wc-main">
              <g id="wc-edges"></g>
              <g id="wc-nodes"></g>
              <g id="wc-temp"></g>
            </g>
          </svg>
        </div>
        <div id="wc-chat-panel" style="width:340px;display:flex;flex-direction:column;border-left:1px solid ${COLORS.grid};background:${COLORS.nodeFill};flex-shrink:0;">
          <div id="wc-chat-header" style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;border-bottom:1px solid ${COLORS.grid};flex-shrink:0;">
            <span style="font-size:13px;font-weight:600;color:${COLORS.text};">🤖 白城主 AI</span>
            <button id="wc-chat-toggle" onclick="WhiteCityEditor._toggleWCChat()" style="background:none;border:none;color:${COLORS.textDim};cursor:pointer;font-size:14px;" title="收起对话">◀</button>
          </div>
          <div id="wc-chat-messages" style="flex:1;overflow-y:auto;padding:10px;display:flex;flex-direction:column;gap:8px;">
            <div style="text-align:center;color:${COLORS.textDim};font-size:11px;padding:16px 8px;">
              告诉我你想编排什么流程，比如：<br>
              "把大纲改成章节草稿，加人物检查"
            </div>
          </div>
          <div id="wc-chat-input-bar" style="padding:12px;border-top:1px solid ${COLORS.grid};display:flex;gap:8px;align-items:center;">
            <input type="text" id="wc-chat-input" placeholder="描述你的编排意图..." style="flex:1;padding:12px 16px;background:${COLORS.bg};border:1px solid ${COLORS.nodeStroke};border-radius:22px;color:${COLORS.text};font-size:14px;outline:none;min-height:42px;" onkeydown="if(event.key==='Enter')WhiteCityEditor._sendWCCompose()">
            <button onclick="WhiteCityEditor._sendWCCompose()" style="width:40px;height:40px;border-radius:50%;background:${COLORS.buttonHover};color:#fff;border:none;cursor:pointer;font-size:18px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">➤</button>
          </div>
        </div>
      </div>
    </div>
    <div id="wc-context-menu" style="display:none;position:fixed;background:#1e1e3a;border:1px solid ${COLORS.nodeStroke};border-radius:6px;padding:4px 0;z-index:9999;min-width:120px;box-shadow:0 4px 12px rgba(0,0,0,0.5);">
      <div class="wc-cm-item" data-action="delete" style="padding:8px 16px;color:${COLORS.text};font-size:12px;cursor:pointer;white-space:nowrap;" onmouseover="this.style.background='${COLORS.buttonHover}'" onmouseout="this.style.background='transparent'">🗑 删除节点</div>
      <div class="wc-cm-item" data-action="duplicate" style="padding:8px 16px;color:${COLORS.text};font-size:12px;cursor:pointer;white-space:nowrap;" onmouseover="this.style.background='${COLORS.nodeStroke}'" onmouseout="this.style.background='transparent'">📋 复制节点</div>
    </div>`;
  }

  // ═══════════════════════════════════════
  // 注册表加载
  // ═══════════════════════════════════════
  async function loadRegistry() {
    try {
      const resp = await fetch(API_BASE + '/registry');
      const data = await resp.json();
      if (data.ok) {
        nodeRegistry = data.nodes || [];
        categories = data.categories || {};
        pipelines = data.pipelines || [];
        console.log('[WhiteCity] 加载节点:', nodeRegistry.length, '个, 流水线:', pipelines.length, '条');
      }
    } catch (e) {
      console.warn('[WhiteCity] 注册表加载失败:', e);
    }
  }

  // ═══════════════════════════════════════
  // 工具栏
  // ═══════════════════════════════════════
  function renderToolbar() {
    const tb = document.getElementById('wc-toolbar');
    if (!tb) return;

    let catOptions = '';
    for (const cat of Object.keys(categories)) {
      catOptions += `<optgroup label="${cat}">`;
      for (const nid of categories[cat]) {
        const meta = nodeRegistry.find(n => n.node_id === nid) || {};
        catOptions += `<option value="${nid}">${meta.node_name || nid}</option>`;
      }
      catOptions += '</optgroup>';
    }

    let pipeButtons = '';
    for (const p of pipelines) {
      pipeButtons += `<button class="wc-btn" onclick="WhiteCityEditor.loadPipeline('${p.id || p.name}')" title="${p.description || ''}">${p.name}</button>`;
    }

    tb.innerHTML = `
      <input id="wc-node-search" type="text" placeholder="搜索节点..." style="font-size:12px;padding:4px 8px;width:140px;background:${COLORS.nodeFill};color:${COLORS.text};border:1px solid ${COLORS.nodeStroke};border-radius:4px;outline:none;" oninput="WhiteCityEditor._onSearch(this.value)">
      <select id="wc-node-select" style="font-size:12px;padding:4px 6px;background:${COLORS.nodeFill};color:${COLORS.text};border:1px solid ${COLORS.nodeStroke};border-radius:4px;">
        ${catOptions}
      </select>
      <button class="wc-btn" onclick="WhiteCityEditor.addNode()" title="添加节点">+ 添加节点</button>
      <span style="color:${COLORS.textDim};font-size:11px;">|</span>
      ${pipeButtons}
      <span style="flex:1;"></span>
      <button class="wc-btn" onclick="WhiteCityEditor.exportComfyUI()" title="导出当前画布为 ComfyUI 工作流 JSON（可在 ComfyUI 中打开继续编排）">⇄ 导出ComfyUI</button>
      <button class="wc-btn" onclick="WhiteCityEditor.importComfyUI()" title="导入 ComfyUI 工作流 JSON 到当前画布（未知节点降级为可配置节点）">⇄ 导入ComfyUI</button>
      <span style="color:${COLORS.textDim};font-size:11px;">|</span>
      <button class="wc-btn" onclick="WhiteCityEditor.saveWorkflow()" title="保存工作流">💾 保存</button>
      <button class="wc-btn" onclick="WhiteCityEditor.showWorkflows()" title="加载工作流">📂 加载</button>
      <button class="wc-btn" id="wc-delete-node-btn" onclick="WhiteCityEditor.deleteSelected()" title="删除选中节点 (Delete)" style="opacity:0.4;pointer-events:none;">🗑 删除</button>
      <button class="wc-btn" onclick="WhiteCityEditor.undo()" title="撤销 Ctrl+Z">↩</button>
      <button class="wc-btn" onclick="WhiteCityEditor.run()" title="执行流程图" style="background:${COLORS.buttonHover};color:#fff;">▶ 运行</button>
      <button class="wc-btn" onclick="WhiteCityEditor.close()" title="关闭">✕</button>
    `;
  }

  // ═══════════════════════════════════════
  // 节点操作
  // ═══════════════════════════════════════

  /** 添加节点到画布 */
  function addNode(nodeId, x, y) {
    const sel = document.getElementById('wc-node-select');
    const id = nodeId || (sel ? sel.value : (nodeRegistry[0] && nodeRegistry[0].node_id));
    if (!id) return;

    const meta = nodeRegistry.find(n => n.node_id === id) || {};
    const instanceId = 'n' + (++nodeCounter);
    const posX = x !== undefined ? x : 100 + (nodeCounter % 5) * 220;
    const posY = y !== undefined ? y : 60 + Math.floor(nodeCounter / 5) * 220;

    const node = {
      instance_id: instanceId,
      node_id: id,
      node_name: meta.node_name || id,
      node_category: meta.node_category || '',
      inputs: meta.inputs || [],
      outputs: meta.outputs || [],
      values: {},
      x: posX,
      y: posY,
    };

    pushUndo();
    nodes.push(node);
    render();
  }

  /** 加载预置流水线 */
  function loadPipeline(name) {
    const pipe = pipelines.find(p => (p.id || p.name) === name);
    if (!pipe) return;

    pushUndo();
    // 流水线独占画布，避免与旧节点混淆
    nodes = [];
    edges = [];

    const idxMap = [];  // 流水线内节点索引 → 实例ID
    for (let i = 0; i < pipe.nodes.length; i++) {
      const pn = pipe.nodes[i];
      const instanceId = 'n' + (++nodeCounter);
      const meta = nodeRegistry.find(n => n.node_id === pn.node_id) || {};
      // 自动横向链式布局，避免节点叠在一起
      const node = {
        instance_id: instanceId,
        node_id: pn.node_id,
        node_name: meta.node_name || pn.node_id,
        node_category: meta.node_category || '',
        inputs: meta.inputs || [],
        outputs: meta.outputs || [],
        values: pn.params || pn.inputs || {},
        x: pn.x !== undefined ? pn.x : 60 + i * 260,
        y: pn.y !== undefined ? pn.y : 100,
      };
      nodes.push(node);
      idxMap.push(instanceId);
    }
    for (const pe of pipe.edges) {
      // 兼容索引式 from/to 与实例式 from_node/to_node
      const fromId = pe.from_node !== undefined ? pe.from_node : idxMap[pe.from];
      const toId = pe.to_node !== undefined ? pe.to_node : idxMap[pe.to];
      if (!fromId || !toId) continue;
      edges.push({
        from_node: fromId,
        from_port: pe.from_port,
        to_node: toId,
        to_port: pe.to_port,
        label: pe.label || '',
      });
    }
    render();
  }

  // ═══════════════════════════════════════
  // 渲染
  // ═══════════════════════════════════════
  function render() {
    if (!gNodes || !gEdges) return;
    renderEdges();
    renderNodes();
  }

  /** 节点自适应尺寸：高度随端口数量伸缩 */
  function nodeSize(node) {
    const rows = Math.max(node.inputs.length, node.outputs.length, 1);
    return { w: NODE_W, h: Math.max(NODE_H_MIN, PORT_TOP + rows * PORT_ROW + 8) };
  }

  /** 端口中心坐标（画布坐标系） */
  function portXY(node, dir, idx) {
    const { w } = nodeSize(node);
    const list = dir === 'in' ? node.inputs : node.outputs;
    const y = node.y + PORT_TOP + PORT_ROW * idx + PORT_ROW / 2;
    return { x: dir === 'in' ? node.x : node.x + w, y };
  }

  function renderNodes() {
    gNodes.innerHTML = '';
    for (const node of nodes) {
      const { w: NW, h: NH } = nodeSize(node);
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('transform', `translate(${node.x},${node.y})`);
      g.setAttribute('data-id', node.instance_id);
      g.setAttribute('class', 'wc-node');
      if (node.instance_id === selectedNodeId) {
        g.setAttribute('filter', 'drop-shadow(0 0 6px ' + COLORS.nodeSelected + ')');
      }

      // 主体
      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('width', NW);
      rect.setAttribute('height', NH);
      rect.setAttribute('rx', '6');
      rect.setAttribute('fill', COLORS.nodeFill);
      rect.setAttribute('stroke', node.instance_id === selectedNodeId ? COLORS.nodeSelected : COLORS.nodeStroke);
      rect.setAttribute('stroke-width', node.instance_id === selectedNodeId ? '2' : '1');
      rect.style.cursor = 'move';
      g.appendChild(rect);

      // 标题
      const title = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      title.setAttribute('x', NW / 2);
      title.setAttribute('y', 20);
      title.setAttribute('text-anchor', 'middle');
      title.setAttribute('fill', COLORS.text);
      title.setAttribute('font-size', '12');
      title.setAttribute('font-weight', 'bold');
      title.textContent = node.node_name;
      g.appendChild(title);

      // node_id 小字
      const subtitle = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      subtitle.setAttribute('x', NW / 2);
      subtitle.setAttribute('y', 36);
      subtitle.setAttribute('text-anchor', 'middle');
      subtitle.setAttribute('fill', COLORS.textDim);
      subtitle.setAttribute('font-size', '9');
      subtitle.textContent = node.node_id;
      g.appendChild(subtitle);

      // 输入端口（显示中文标签 + 英文小字）
      const inCount = node.inputs.length;
      for (let i = 0; i < inCount; i++) {
        const port = node.inputs[i];
        const py = PORT_TOP + PORT_ROW * i + PORT_ROW / 2;
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', 0);
        circle.setAttribute('cy', py);
        circle.setAttribute('r', PORT_R);
        circle.setAttribute('fill', COLORS.portInput);
        circle.setAttribute('stroke', COLORS.nodeFill);
        circle.setAttribute('stroke-width', '2');
        circle.setAttribute('data-port', port.name);
        circle.setAttribute('data-dir', 'in');
        circle.style.cursor = 'crosshair';
        g.appendChild(circle);

        const pLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        pLabel.setAttribute('x', 10);
        pLabel.setAttribute('y', py + 3);
        pLabel.setAttribute('fill', COLORS.text);
        pLabel.setAttribute('font-size', '10');
        pLabel.textContent = port.label || port.name;
        g.appendChild(pLabel);

        if (port.label && port.label !== port.name) {
          const pEn = document.createElementNS('http://www.w3.org/2000/svg', 'text');
          pEn.setAttribute('x', 10);
          pEn.setAttribute('y', py + 13);
          pEn.setAttribute('fill', COLORS.textDim);
          pEn.setAttribute('font-size', '7');
          pEn.textContent = port.name;
          g.appendChild(pEn);
        }
      }

      // 输出端口（显示中文标签 + 英文小字）
      const outCount = node.outputs.length;
      for (let i = 0; i < outCount; i++) {
        const port = node.outputs[i];
        const py = PORT_TOP + PORT_ROW * i + PORT_ROW / 2;
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', NW);
        circle.setAttribute('cy', py);
        circle.setAttribute('r', PORT_R);
        circle.setAttribute('fill', COLORS.portOutput);
        circle.setAttribute('stroke', COLORS.nodeFill);
        circle.setAttribute('stroke-width', '2');
        circle.setAttribute('data-port', port.name);
        circle.setAttribute('data-dir', 'out');
        circle.style.cursor = 'crosshair';
        g.appendChild(circle);

        const pLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        pLabel.setAttribute('x', NW - 10);
        pLabel.setAttribute('y', py + 3);
        pLabel.setAttribute('text-anchor', 'end');
        pLabel.setAttribute('fill', COLORS.text);
        pLabel.setAttribute('font-size', '10');
        pLabel.textContent = port.label || port.name;
        g.appendChild(pLabel);

        if (port.label && port.label !== port.name) {
          const pEn = document.createElementNS('http://www.w3.org/2000/svg', 'text');
          pEn.setAttribute('x', NW - 10);
          pEn.setAttribute('y', py + 13);
          pEn.setAttribute('text-anchor', 'end');
          pEn.setAttribute('fill', COLORS.textDim);
          pEn.setAttribute('font-size', '7');
          pEn.textContent = port.name;
          g.appendChild(pEn);
        }
      }

      // 删除按钮（右上角）
      const delBtn = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      delBtn.setAttribute('transform', `translate(${NW - 18}, 4)`);
      delBtn.style.cursor = 'pointer';
      delBtn.setAttribute('class', 'wc-node-delete');
      const delBg = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      delBg.setAttribute('cx', '8');
      delBg.setAttribute('cy', '8');
      delBg.setAttribute('r', '8');
      delBg.setAttribute('fill', 'transparent');
      delBtn.appendChild(delBg);
      const delX = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      delX.setAttribute('x', '8');
      delX.setAttribute('y', '12');
      delX.setAttribute('text-anchor', 'middle');
      delX.setAttribute('fill', COLORS.textDim);
      delX.setAttribute('font-size', '14');
      delX.setAttribute('font-weight', 'bold');
      delX.textContent = '×';
      delBtn.appendChild(delX);
      delBtn.addEventListener('mousedown', (ev) => { ev.stopPropagation(); });
      delBtn.addEventListener('click', (ev) => { ev.stopPropagation(); deleteNode(node.instance_id); });
      g.appendChild(delBtn);

      gNodes.appendChild(g);
    }
  }

  function renderEdges() {
    gEdges.innerHTML = '';
    for (let i = 0; i < edges.length; i++) {
      const e = edges[i];
      const src = nodes.find(n => n.instance_id === e.from_node);
      const dst = nodes.find(n => n.instance_id === e.to_node);
      if (!src || !dst) continue;

      const srcIdx = src.outputs.findIndex(p => p.name === e.from_port);
      const dstIdx = dst.inputs.findIndex(p => p.name === e.to_port);
      if (srcIdx < 0 || dstIdx < 0) continue;

      const s = portXY(src, 'out', srcIdx);
      const d = portXY(dst, 'in', dstIdx);

      const mid = (s.x + d.x) / 2;
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      const dStr = `M${s.x},${s.y} C${mid},${s.y} ${mid},${d.y} ${d.x},${d.y}`;
      path.setAttribute('d', dStr);
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', COLORS.edgeDefault);
      path.setAttribute('stroke-width', '2');
      path.setAttribute('marker-end', 'url(#wc-arrow)');
      path.setAttribute('data-edge-id', i);
      path.style.cursor = 'pointer';
      gEdges.appendChild(path);
    }
  }

  // ═══════════════════════════════════════
  // 事件处理
  // ═══════════════════════════════════════
  function bindEvents() {
    svg.addEventListener('mousedown', onMouseDown);
    svg.addEventListener('mousemove', onMouseMove);
    svg.addEventListener('mouseup', onMouseUp);
    svg.addEventListener('wheel', onWheel, { passive: false });
    svg.addEventListener('dblclick', onDblClick);
    svg.addEventListener('contextmenu', onContextMenu);
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('click', hideContextMenu);

    // 背景双击添加节点
    svg.addEventListener('dblclick', (e) => {
      if (e.target === svg || e.target === gMain) {
        const rect = svg.getBoundingClientRect();
        addNode(null, (e.clientX - rect.left) / scale - offsetX / scale, (e.clientY - rect.top) / scale - offsetY / scale);
      }
    });
  }

  function getNodeAt(clientX, clientY) {
    const rect = svg.getBoundingClientRect();
    const mx = (clientX - rect.left) / scale - offsetX / scale;
    const my = (clientY - rect.top) / scale - offsetY / scale;
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      const { w, h } = nodeSize(n);
      if (mx >= n.x && mx <= n.x + w && my >= n.y && my <= n.y + h) {
        return n;
      }
    }
    return null;
  }

  function getPortAt(clientX, clientY) {
    const rect = svg.getBoundingClientRect();
    const mx = (clientX - rect.left) / scale - offsetX / scale;
    const my = (clientY - rect.top) / scale - offsetY / scale;
    for (const node of nodes) {
      // 输入端口
      for (let i = 0; i < node.inputs.length; i++) {
        const p = portXY(node, 'in', i);
        if (Math.hypot(mx - p.x, my - p.y) < PORT_R + 4) {
          return { node, port: node.inputs[i].name, dir: 'in', x: p.x, y: p.y };
        }
      }
      // 输出端口
      for (let i = 0; i < node.outputs.length; i++) {
        const p = portXY(node, 'out', i);
        if (Math.hypot(mx - p.x, my - p.y) < PORT_R + 4) {
          return { node, port: node.outputs[i].name, dir: 'out', x: p.x, y: p.y };
        }
      }
    }
    return null;
  }

  function onMouseDown(e) {
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    // 端口连接
    const portHit = getPortAt(e.clientX, e.clientY);
    if (portHit) {
      connecting = {
        nodeId: portHit.node.instance_id,
        portName: portHit.port,
        dir: portHit.dir,
        ox: portHit.x * scale + offsetX,
        oy: portHit.y * scale + offsetY,
      };
      e.preventDefault();
      return;
    }

    // 节点拖拽
    const nodeHit = getNodeAt(e.clientX, e.clientY);
    if (nodeHit) {
      selectNode(nodeHit.instance_id);
      dragging = { id: nodeHit.instance_id, ox: nodeHit.x - mx / scale, oy: nodeHit.y - my / scale };
      e.preventDefault();
      return;
    }

    // 画布平移
    if (e.button === 0 || e.button === 1) {
      panning = true;
      panStart = { x: e.clientX - offsetX, y: e.clientY - offsetY };
      svg.style.cursor = 'grabbing';
    }

    // 取消选择
    selectNode(null);
  }

  function onMouseMove(e) {
    if (connecting) {
      drawTempLine(e);
      return;
    }

    if (dragging) {
      const rect = svg.getBoundingClientRect();
      const node = nodes.find(n => n.instance_id === dragging.id);
      if (node) {
        node.x = e.clientX - rect.left + dragging.ox;
        node.y = e.clientY - rect.top + dragging.oy;
        render();
      }
      return;
    }

    if (panning) {
      offsetX = e.clientX - panStart.x;
      offsetY = e.clientY - panStart.y;
      gMain.setAttribute('transform', `translate(${offsetX},${offsetY}) scale(${scale})`);
    }
  }

  function onMouseUp(e) {
    if (connecting) {
      const portHit = getPortAt(e.clientX, e.clientY);
      if (portHit && portHit.node.instance_id !== connecting.nodeId &&
          portHit.dir !== connecting.dir) {
        pushUndo();
        const fromNode = connecting.dir === 'out' ? connecting.nodeId : portHit.node.instance_id;
        const fromPort = connecting.dir === 'out' ? connecting.portName : portHit.port;
        const toNode = connecting.dir === 'out' ? portHit.node.instance_id : connecting.nodeId;
        const toPort = connecting.dir === 'out' ? portHit.port : connecting.portName;
        edges.push({ from_node: fromNode, from_port: fromPort, to_node: toNode, to_port: toPort, label: '' });
        render();
      }
      gTemp.innerHTML = '';
      connecting = null;
    }

    if (dragging) {
      pushUndo();
      dragging = null;
    }

    if (panning) {
      panning = false;
      svg.style.cursor = 'default';
    }
  }

  function drawTempLine(e) {
    if (!connecting) return;
    const srcNode = nodes.find(n => n.instance_id === connecting.nodeId);
    if (!srcNode) return;

    const rect = svg.getBoundingClientRect();
    let sx, sy;
    if (connecting.dir === 'out') {
      const idx = srcNode.outputs.findIndex(p => p.name === connecting.portName);
      const p = portXY(srcNode, 'out', Math.max(idx, 0));
      sx = p.x; sy = p.y;
    } else {
      const idx = srcNode.inputs.findIndex(p => p.name === connecting.portName);
      const p = portXY(srcNode, 'in', Math.max(idx, 0));
      sx = p.x; sy = p.y;
    }

    // 临时线在 gMain 内，需换算到画布坐标系
    const ex = (e.clientX - rect.left - offsetX) / scale;
    const ey = (e.clientY - rect.top - offsetY) / scale;
    const mid = (sx + ex) / 2;

    gTemp.innerHTML = `<path d="M${sx},${sy} C${mid},${sy} ${mid},${ey} ${ex},${ey}" fill="none" stroke="${COLORS.edgeHover}" stroke-width="2" stroke-dasharray="6,3" />`;
  }

  function onWheel(e) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    scale = Math.max(0.3, Math.min(3, scale + delta));
    gMain.setAttribute('transform', `translate(${offsetX},${offsetY}) scale(${scale})`);
  }

  function onDblClick(e) {
    const node = getNodeAt(e.clientX, e.clientY);
    if (node) {
      showInputDialog(node);
    }
  }

  function onKeyDown(e) {
    if (e.ctrlKey && e.key === 'z') { undo(); e.preventDefault(); }
    if (e.key === 'Delete' || e.key === 'Backspace') {
      if (selectedNodeId) { deleteNode(selectedNodeId); }
      if (selectedEdgeId !== null) { deleteEdge(selectedEdgeId); }
    }
  }

  // ═══════════════════════════════════════
  // 选择与编辑
  // ═══════════════════════════════════════
  function selectNode(id) {
    selectedNodeId = id;
    selectedEdgeId = null;
    render();
    updateToolbarState();
  }

  // 右键菜单
  let contextNodeId = null;

  function onContextMenu(e) {
    const node = getNodeAt(e.clientX, e.clientY);
    if (!node) { hideContextMenu(); return; }
    e.preventDefault();
    selectNode(node.instance_id);
    contextNodeId = node.instance_id;
    const menu = document.getElementById('wc-context-menu');
    if (!menu) return;
    menu.style.display = 'block';
    menu.style.left = e.clientX + 'px';
    menu.style.top = e.clientY + 'px';
    // 绑定菜单点击
    menu.querySelectorAll('.wc-cm-item').forEach(item => {
      item.onclick = (ev) => {
        ev.stopPropagation();
        const action = item.getAttribute('data-action');
        if (action === 'delete' && contextNodeId) { deleteNode(contextNodeId); }
        if (action === 'duplicate' && contextNodeId) { duplicateNode(contextNodeId); }
        hideContextMenu();
      };
    });
  }

  function hideContextMenu() {
    const menu = document.getElementById('wc-context-menu');
    if (menu) menu.style.display = 'none';
    contextNodeId = null;
  }

  function duplicateNode(id) {
    const src = nodes.find(n => n.instance_id === id);
    if (!src) return;
    pushUndo();
    const instanceId = 'n' + (++nodeCounter);
    nodes.push({
      instance_id: instanceId,
      node_id: src.node_id,
      node_name: src.node_name,
      node_category: src.node_category,
      inputs: JSON.parse(JSON.stringify(src.inputs)),
      outputs: JSON.parse(JSON.stringify(src.outputs)),
      values: JSON.parse(JSON.stringify(src.values)),
      x: src.x + 30,
      y: src.y + 30,
    });
    render();
  }

  function updateToolbarState() {
    const delBtn = document.getElementById('wc-delete-node-btn');
    if (delBtn) {
      delBtn.style.opacity = selectedNodeId ? '1' : '0.4';
      delBtn.style.pointerEvents = selectedNodeId ? 'auto' : 'none';
    }
  }

  function deleteNode(id) {
    pushUndo();
    nodes = nodes.filter(n => n.instance_id !== id);
    edges = edges.filter(e => e.from_node !== id && e.to_node !== id);
    if (selectedNodeId === id) selectedNodeId = null;
    render();
  }

  function deleteEdge(idx) {
    pushUndo();
    edges.splice(idx, 1);
    selectedEdgeId = null;
    render();
  }

  function showInputDialog(node) {
    const inputs = node.inputs;
    if (inputs.length === 0) return;

    // 用中文标签展示可选端口
    const labelOf = (p) => (p.label && p.label !== p.name ? `${p.label} (${p.name})` : p.name);
    let port;
    if (inputs.length === 1) {
      port = inputs[0];
    } else {
      const chosen = prompt('选择输入端口:\n' + inputs.map(labelOf).join('\n'), labelOf(inputs[0]));
      if (!chosen) return;
      port = inputs.find(p => chosen.includes(p.name)) || inputs.find(p => labelOf(p) === chosen);
      if (!port) return;
    }

    const current = node.values[port.name] || '';
    const value = prompt(`设置 "${port.label || port.name}" 的值:`, typeof current === 'object' ? JSON.stringify(current) : current);
    if (value === null) return;

    try {
      node.values[port.name] = JSON.parse(value);
    } catch {
      node.values[port.name] = value;
    }
  }

  // ═══════════════════════════════════════
  // 撤销
  // ═══════════════════════════════════════
  function pushUndo() {
    undoStack.push({
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
      nodeCounter: nodeCounter,
    });
    if (undoStack.length > MAX_UNDO) undoStack.shift();
  }

  function undo() {
    if (undoStack.length === 0) return;
    const state = undoStack.pop();
    nodes = state.nodes;
    edges = state.edges;
    nodeCounter = state.nodeCounter;
    selectedNodeId = null;
    selectedEdgeId = null;
    render();
  }

  // ═══════════════════════════════════════
  // 执行
  // ═══════════════════════════════════════
  async function run() {
    if (nodes.length === 0) {
      alert('画布上没有节点');
      return;
    }

    // 收集节点数据
    const nodeData = nodes.map(n => ({
      instance_id: n.instance_id,
      node_id: n.node_id,
      inputs: n.values,
    }));

    // 收集连线
    const edgeData = edges.map(e => ({
      from_node: e.from_node,
      from_port: e.from_port,
      to_node: e.to_node,
      to_port: e.to_port,
      label: e.label || '',
    }));

    try {
      const resp = await fetch(API_BASE + '/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nodes: nodeData, edges: edgeData }),
      });
      const data = await resp.json();
      showResult(data);
    } catch (e) {
      alert('执行失败: ' + e.message);
    }
  }

  function showResult(data) {
    let html = '<div style="max-height:400px;overflow-y:auto;font-size:12px;">';
    if (data.ok) {
      html += `<p style="color:#4ade80;margin-bottom:8px;">执行成功 (${data.total_duration_ms}ms)</p>`;
      for (const r of data.results) {
        const color = r.status === 'completed' ? '#4ade80' : r.status === 'failed' ? '#ef4444' : '#fbbf24';
        html += `<div style="margin-bottom:12px;padding:8px;background:${COLORS.nodeFill};border-left:3px solid ${color};border-radius:4px;">`;
        html += `<strong>${r.node_name}</strong> <span style="color:${COLORS.textDim};font-size:10px;">${r.node_id}</span>`;
        html += ` <span style="color:${color}">[${r.status}]</span>`;
        if (r.duration_ms) html += ` <span style="color:${COLORS.textDim}">${r.duration_ms}ms</span>`;
        if (r.error) html += `<p style="color:#ef4444;margin-top:4px;">${r.error}</p>`;
        if (r.outputs && r.outputs.reply) {
          html += `<p style="margin-top:4px;white-space:pre-wrap;word-break:break-word;">${r.outputs.reply}</p>`;
        }
        html += '</div>';
      }
    } else {
      html += `<p style="color:#ef4444;">${data.message || '执行失败'}</p>`;
    }
    html += '</div>';

    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.6);z-index:1000;display:flex;align-items:center;justify-content:center;';
    overlay.innerHTML = `<div style="background:${COLORS.bg};border:1px solid ${COLORS.nodeStroke};border-radius:8px;padding:20px;min-width:400px;max-width:600px;"><h3 style="margin:0 0 12px;color:${COLORS.text};">执行结果</h3>${html}<button onclick="this.parentElement.parentElement.remove()" style="margin-top:12px;padding:6px 16px;background:${COLORS.button};color:${COLORS.text};border:none;border-radius:4px;cursor:pointer;">关闭</button></div>`;
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
  }

  // ═══════════════════════════════════════
  // 双屏对话 — AI Compose 集成
  // ═══════════════════════════════════════

  /** 展开/收起右侧对话面板 */
  function toggleWCChat() {
    const panel = document.getElementById('wc-chat-panel');
    const toggleBtn = document.getElementById('wc-chat-toggle');
    if (!panel || !toggleBtn) return;
    if (panel.style.display === 'none') {
      panel.style.display = 'flex';
      toggleBtn.textContent = '◀';
    } else {
      panel.style.display = 'none';
      toggleBtn.textContent = '▶';
    }
  }

  /** 发送编排意图 → compose API → 渲染 graph → 回显结果 */
  async function sendWCCompose() {
    var inp = document.getElementById('wc-chat-input');
    var msg = inp.value.trim();
    if (!msg) return;

    addWCChatMessage('user', msg);
    inp.value = '';

    var msgs = document.getElementById('wc-chat-messages');
    var thinkingEl = document.createElement('div');
    thinkingEl.style.cssText = 'color:' + COLORS.textDim + ';font-size:12px;font-style:italic;padding:4px 0;';
    thinkingEl.textContent = '⏳ 正在编排...';
    msgs.appendChild(thinkingEl);
    msgs.scrollTop = msgs.scrollHeight;

    try {
      // 携带画布当前完整图（节点+连线），供 AI 感知已有实例并在其上追加
      var canvasNodes = nodes.map(function(n) {
        return {
          instance_id: n.instance_id,
          node_id: n.node_id,
          node_name: n.node_name,
          inputs: n.inputs,
          outputs: n.outputs,
          values: n.values || {},
        };
      });
      var canvasEdges = edges.map(function(e) {
        return {
          from_node: e.from_node,
          from_port: e.from_port,
          to_node: e.to_node,
          to_port: e.to_port,
          label: e.label || '',
        };
      });
      var nodeIdList = [];
      canvasNodes.forEach(function(n) {
        if (n.node_id && nodeIdList.indexOf(n.node_id) < 0) nodeIdList.push(n.node_id);
      });
      var resp = await fetch(API_BASE + '/compose', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: msg,
          existing_node_ids: nodeIdList,
          existing_graph: { nodes: canvasNodes, edges: canvasEdges },
        }),
      });
      var data = await resp.json();
    } catch (e) {
      thinkingEl.remove();
      addWCChatMessage('assistant', '❌ 编排请求失败: ' + e.message);
      return;
    }

    thinkingEl.remove();

    if (!data.ok) {
      addWCChatMessage('assistant', '❌ 编排失败: ' + (data.error || '未知错误') +
        (data.raw_response ? '\n\n' + data.raw_response.substring(0, 300) : ''));
      return;
    }

    var d = data.data;

    // 复合确认弹窗：代码预览 + 依赖清单 + 模型空间 + AST 告警，三按钮（确认执行/仅保存不运行/驳回重写）
    if (d.graph && d.graph.nodes && d.graph.nodes.length) {
      showComposeConfirm(d, msg, { nodes: canvasNodes, edges: canvasEdges, nodeIds: nodeIdList });
    } else {
      addWCChatMessage('assistant', '✅ ' + (d.explanation || '已生成节点编排') + '（未生成节点）');
    }
  }

  // ═══════════════════════════════════════
  // AI Compose 复合确认弹窗（代码预览 + 依赖清单 + 模型空间 + AST 告警）
  // ═══════════════════════════════════════

  // 当前弹窗上下文（供重写/落图/执行共用）
  var _composeCtx = null;

  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function _sevColor(sev) {
    if (sev === 'high') return '#ff5f5f';
    if (sev === 'medium') return '#ffb86b';
    return '#8a8aa8';
  }

  /** 渲染单个节点审查卡片（Schema / AST / 依赖 / 模型空间 / 代码预览） */
  function _renderReviewCard(nc, entry, idx) {
    var parts = [];
    var nodeName = nc.node_name || nc.node_id || ('节点' + (idx + 1));
    var runMode = nc.run_mode || 'sdk_local';
    var runCode = nc.run_code || '';
    var schemaOk = !entry || entry.schema_ok !== false;
    var astRisks = (entry && entry.ast_risks) || [];
    var depsOk = !entry || entry.all_ok !== false;

    // 头部 + 审查徽标
    parts.push(
      '<div style="border-bottom:1px solid ' + COLORS.grid + ';padding:8px 10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">' +
      '<span style="color:' + COLORS.textDim + ';font-size:11px;">#' + (idx + 1) + '</span>' +
      '<span style="color:' + COLORS.text + ';font-weight:600;font-size:13px;">' + _esc(nodeName) + '</span>' +
      '<span style="font-size:10px;color:#9aa;border:1px solid ' + COLORS.nodeStroke + ';border-radius:3px;padding:1px 6px;">' + _esc(runMode) + '</span>' +
      '<span style="font-size:10px;color:' + COLORS.textDim + ';">' + _esc(nc.node_id || '') + '</span>' +
      '<span style="font-size:10px;color:' + (schemaOk ? '#6fdc8c' : '#ff5f5f') + ';">' + (schemaOk ? '✓ Schema' : '✗ Schema') + '</span>' +
      '<span style="font-size:10px;color:' + (astRisks.length ? '#ffb86b' : '#6fdc8c') + ';">' + (astRisks.length ? '⚠ 代码 ' + astRisks.length + ' 项告警' : '✓ 代码') + '</span>' +
      '<span style="font-size:10px;color:' + (depsOk ? '#6fdc8c' : '#ff5f5f') + ';">' + (depsOk ? '✓ 依赖' : '✗ 依赖') + '</span>' +
      '</div>'
    );

    // Schema 错误
    if (entry && entry.schema_errors && entry.schema_errors.length) {
      parts.push('<div style="padding:6px 10px;background:rgba(255,95,95,0.08);border-bottom:1px solid ' + COLORS.grid + ';">' +
        entry.schema_errors.map(function (e) { return '<div style="color:#ff5f5f;font-size:11px;">✗ ' + _esc(e) + '</div>'; }).join('') +
        '</div>');
    }

    // AST 风险告警
    if (astRisks.length) {
      parts.push('<div style="padding:6px 10px;background:rgba(255,184,107,0.06);border-bottom:1px solid ' + COLORS.grid + ';">' +
        astRisks.map(function (r) {
          var color = _sevColor(r.severity);
          return '<div style="color:' + color + ';font-size:11px;padding:1px 0;">[' + (r.severity || '?').toUpperCase() + (r.line ? ' L' + r.line : '') + '] ' + _esc(r.code || '') + ' — ' + _esc(r.msg) + '</div>';
        }).join('') +
        '</div>');
    }

    // 依赖清单（pip / system / models / disk）
    var depHtml = '';
    if (entry && entry.note) {
      depHtml += '<div style="color:' + COLORS.textDim + ';font-size:11px;padding:2px 0;">' + _esc(entry.note) + '</div>';
    }
    if (entry && entry.pip_missing && entry.pip_missing.length) {
      depHtml += '<div style="color:#ff5f5f;font-size:11px;padding:2px 0;">缺少 pip 依赖：' +
        entry.pip_missing.map(function (p) {
          var txt = typeof p === 'string' ? p : (p.req || p.name || '');
          var extra = (p && p.reason === 'version') ? '（已装 ' + p.installed + '，需 ' + p.required + '）' : '';
          return '<span style="background:rgba(255,95,95,0.12);border-radius:3px;padding:1px 5px;margin-right:4px;">' + _esc(txt + extra) + '</span>';
        }).join('') + '</div>';
    }
    if (entry && entry.system_tools && entry.system_tools.length) {
      var sysMissing = entry.system_tools.filter(function (t) { return !t.found; });
      if (sysMissing.length) {
        depHtml += '<div style="color:#ffb86b;font-size:11px;padding:2px 0;">缺少系统工具：' +
          sysMissing.map(function (t) { return '<span style="background:rgba(255,184,107,0.12);border-radius:3px;padding:1px 5px;margin-right:4px;">' + _esc(t.name) + '</span>'; }).join('') + '（仅提示，不自动安装）</div>';
      }
    }
    if (entry && entry.models && entry.models.length) {
      var modelHtml = entry.models.map(function (m) {
        var sizeTxt = m.size_approx || (m.expected_bytes ? Math.round(m.expected_bytes / 1073741824 * 10) / 10 + ' GB' : '');
        var name = _esc(m.repo_id || m.path || '');
        if (m.ok) return '<span style="color:#6fdc8c;font-size:11px;padding:2px 0;">✓ 模型 ' + name + (sizeTxt ? '（' + _esc(sizeTxt) + '）' : '') + '</span>';
        return '<span style="color:#ff5f5f;font-size:11px;padding:2px 0;">✗ 模型缺失 ' + name + (sizeTxt ? '（约 ' + _esc(sizeTxt) + '）' : '') + ' — ' + _esc(m.reason || 'missing') + '</span>';
      }).join('<br>');
      depHtml += '<div>' + modelHtml + '</div>';
    }
    if (entry && entry.disk_issues && entry.disk_issues.length) {
      entry.disk_issues.forEach(function (di) {
        var needGB = di.needed_bytes ? Math.round(di.needed_bytes / 1073741824 * 10) / 10 : 0;
        var freeGB = di.free_bytes ? Math.round(di.free_bytes / 1073741824 * 10) / 10 : 0;
        depHtml += '<div style="color:#ff5f5f;font-size:11px;padding:2px 0;">磁盘空间不足：' + _esc(di.repo_id || '') + ' 需约 ' + needGB + ' GB，剩余 ' + freeGB + ' GB</div>';
      });
    }
    if (depHtml) {
      parts.push('<div style="padding:6px 10px;border-bottom:1px solid ' + COLORS.grid + ';">' + depHtml + '</div>');
    }

    // run_code 预览
    parts.push('<div style="padding:8px 10px;border-bottom:1px solid ' + COLORS.grid + ';">' +
      '<div style="color:' + COLORS.textDim + ';font-size:10px;margin-bottom:4px;">run_code 预览</div>' +
      '<pre style="margin:0;padding:8px;background:#101020;border:1px solid ' + COLORS.grid + ';border-radius:4px;color:#c8c8e0;font-size:11px;line-height:1.5;max-height:180px;overflow:auto;white-space:pre-wrap;word-break:break-all;">' +
      _esc(runCode || '（无 run_code，本节点由 run_mode 调度器执行）') +
      '</pre></div>');

    return '<div style="border:1px solid ' + COLORS.nodeStroke + ';border-radius:6px;margin-bottom:10px;overflow:hidden;">' + parts.join('') + '</div>';
  }

  /** 打开复合确认弹窗 */
  function showComposeConfirm(d, promptText, canvasCtx) {
    _composeCtx = { d: d, promptText: promptText, canvasCtx: canvasCtx || null };

    var old = document.getElementById('wc-compose-confirm');
    if (old) old.remove();

    var overlay = document.createElement('div');
    overlay.id = 'wc-compose-confirm';
    overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.72);z-index:1300;display:flex;align-items:center;justify-content:center;';
    overlay.addEventListener('click', function (e) { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
    renderComposeConfirm();
  }

  /** 渲染弹窗内容（初始与重写后共用） */
  function renderComposeConfirm() {
    var overlay = document.getElementById('wc-compose-confirm');
    if (!overlay || !_composeCtx) return;
    var d = _composeCtx.d;
    var checks = d.dependency_checks || {};
    var configs = d.node_configs || [];
    var cards = configs.map(function (nc, i) { return _renderReviewCard(nc, checks[nc.node_id], i); }).join('');

    overlay.innerHTML =
      '<div style="background:' + COLORS.bg + ';border:1px solid ' + COLORS.nodeStroke + ';border-radius:10px;width:880px;max-width:94vw;max-height:84vh;display:flex;flex-direction:column;box-shadow:0 8px 40px rgba(0,0,0,0.5);">' +
      '<div style="padding:14px 18px;border-bottom:1px solid ' + COLORS.grid + ';display:flex;align-items:center;justify-content:space-between;">' +
      '<div><div style="color:' + COLORS.text + ';font-size:15px;font-weight:600;">AI 编排确认</div>' +
      '<div style="color:' + COLORS.textDim + ';font-size:11px;margin-top:2px;">' + _esc(d.explanation || '已生成节点编排') + '</div></div>' +
      '<button onclick="WhiteCityEditor._composeAction(\'cancel\')" style="background:none;border:none;color:' + COLORS.textDim + ';font-size:18px;cursor:pointer;line-height:1;">×</button>' +
      '</div>' +
      '<div style="padding:12px 18px;overflow-y:auto;flex:1;">' + (cards || '<div style="color:' + COLORS.textDim + ';font-size:12px;">未生成任何节点</div>') + '</div>' +
      '<div style="padding:12px 18px;border-top:1px solid ' + COLORS.grid + ';">' +
      '<div id="wc-reject-box" style="display:none;margin-bottom:10px;">' +
      '<textarea id="wc-reject-reason" rows="2" placeholder="说明驳回原因，AI 将针对性重新生成…" style="width:100%;box-sizing:border-box;padding:8px;background:#101020;color:' + COLORS.text + ';border:1px solid ' + COLORS.nodeStroke + ';border-radius:4px;font-size:12px;resize:vertical;"></textarea>' +
      '<div style="margin-top:6px;text-align:right;"><button onclick="WhiteCityEditor._composeAction(\'reject\')" style="padding:5px 14px;background:#7a4a00;color:#ffd79a;border:none;border-radius:4px;cursor:pointer;font-size:12px;">提交重写</button></div>' +
      '</div>' +
      '<div style="display:flex;justify-content:flex-end;gap:8px;align-items:center;">' +
      '<button onclick="WhiteCityEditor._toggleRejectBox()" style="padding:7px 16px;background:#5a2a00;color:#ffb86b;border:none;border-radius:4px;cursor:pointer;font-size:12px;">驳回重写</button>' +
      '<button onclick="WhiteCityEditor._composeAction(\'save\')" style="padding:7px 16px;background:' + COLORS.button + ';color:' + COLORS.text + ';border:none;border-radius:4px;cursor:pointer;font-size:12px;">仅保存不运行</button>' +
      '<button onclick="WhiteCityEditor._composeAction(\'run\')" style="padding:7px 16px;background:' + COLORS.buttonHover + ';color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600;">确认执行</button>' +
      '</div></div></div>';
  }

  /** 弹窗按钮动作：cancel=放弃 / save=落图+保存 / run=落图+执行 / reject=提交重写 */
  function _composeAction(action) {
    var overlay = document.getElementById('wc-compose-confirm');
    if (!overlay || !_composeCtx) return;

    if (action === 'cancel') {
      overlay.remove();
      return;
    }
    if (action === 'reject') {
      var reasonEl = document.getElementById('wc-reject-reason');
      var reason = reasonEl ? reasonEl.value : '';
      if (!reason.trim()) { alert('请填写驳回原因'); return; }
      _composeRewrite(reason.trim());
      return;
    }

    // save / run：先落图再处理
    overlay.remove();
    var applied = _applyComposeGraph();
    if (action === 'save') {
      saveWorkflow();
    } else if (action === 'run') {
      _runComposeNodes(applied);
    }
  }

  function _toggleRejectBox() {
    var box = document.getElementById('wc-reject-box');
    if (box) box.style.display = box.style.display === 'none' ? 'block' : 'none';
  }

  /** 将确认后的 compose 图落图画布，返回新增节点信息 */
  function _applyComposeGraph() {
    var d = _composeCtx.d;
    if (!d || !d.graph || !d.graph.nodes || !d.graph.nodes.length) return null;

    var beforeIds = {};
    nodes.forEach(function (n) { beforeIds[n.instance_id] = true; });
    autoLayoutGraph(d.graph);
    var added = nodes.filter(function (n) { return !beforeIds[n.instance_id]; });
    var addedSet = {};
    added.forEach(function (n) { addedSet[n.instance_id] = true; });
    var addedEdges = (d.graph.edges || []).filter(function (e) {
      return addedSet[e.from_node] && addedSet[e.to_node];
    });
    var chain = d.graph.nodes.map(function (n) { return n.node_name || n.node_id; }).join(' → ');
    addWCChatMessage('assistant', '✅ ' + (d.explanation || '已生成节点编排') + '\n\n新增 ' + added.length + ' 个节点，当前共 ' + nodes.length + ' 个：' + chain);
    return { added: added, addedEdges: addedEdges, d: d };
  }

  /** 对新增节点发起执行（/run），结果回显到对话面板 */
  function _runComposeNodes(applied) {
    if (!applied || !applied.added.length) return;
    var req = {
      nodes: applied.added.map(function (n) {
        return { instance_id: n.instance_id, node_id: n.node_id, inputs: {} };
      }),
      edges: applied.addedEdges.map(function (e) {
        return { from_node: e.from_node, from_port: e.from_port, to_node: e.to_node, to_port: e.to_port, label: e.label || '' };
      }),
    };
    addWCChatMessage('assistant', '⏳ 正在执行 ' + applied.added.length + ' 个新增节点...');
    fetch(API_BASE + '/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }).then(function (r) { return r.json(); }).then(function (data) {
      if (data && data.ok) {
        var lines = (data.results || []).map(function (res) {
          return '· ' + (res.node_name || res.node_id) + ' [' + (res.status || '') + '] ' +
            (res.duration_ms != null ? res.duration_ms + 'ms' : '') +
            (res.error ? ' — ' + res.error : '');
        });
        addWCChatMessage('assistant', '✅ 执行完成' + (data.total_duration_ms != null ? '（' + data.total_duration_ms + 'ms）' : '') + '\n\n' + lines.join('\n'));
      } else {
        var em = (data && data.error && data.error.message) || (data && data.error) || '未知错误';
        addWCChatMessage('assistant', '❌ 执行失败: ' + em);
      }
    }).catch(function (e) {
      addWCChatMessage('assistant', '❌ 执行失败: ' + e.message);
    });
  }

  /** 驳回重写：携带原因重新调用 /compose，成功后刷新弹窗 */
  function _composeRewrite(reason) {
    var ctx = _composeCtx;
    var canvas = ctx.canvasCtx || { nodes: [], edges: [], nodeIds: [] };
    var overlay = document.getElementById('wc-compose-confirm');

    // 显示重写中状态
    var bodyEl = overlay ? overlay.querySelector('[style*="flex:1"]') : null;
    if (bodyEl) bodyEl.innerHTML = '<div style="color:' + COLORS.textDim + ';font-size:12px;padding:30px;text-align:center;">⏳ 正在按驳回原因重新生成…</div>';

    fetch(API_BASE + '/compose', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: ctx.promptText,
        existing_node_ids: canvas.nodeIds || [],
        existing_graph: { nodes: canvas.nodes || [], edges: canvas.edges || [] },
        rewrite: { reason: reason },
      }),
    }).then(function (r) { return r.json(); }).then(function (data) {
      if (data && data.ok && data.data) {
        _composeCtx.d = data.data;
        renderComposeConfirm();
      } else {
        if (overlay) overlay.remove();
        var em = (data && data.error && data.error.message) || (data && data.error) || '未知错误';
        addWCChatMessage('assistant', '❌ 重写失败: ' + em);
      }
    }).catch(function (e) {
      if (overlay) overlay.remove();
      addWCChatMessage('assistant', '❌ 重写失败: ' + e.message);
    });
  }

  /** 将 compose graph 合并进画布：已有节点保留位置，新节点自动分层布局 */
  function autoLayoutGraph(graph) {
    var gNodes = graph.nodes || [];
    var gEdges = graph.edges || [];

    // 已有画布节点（按 instance_id 保留位置与配置）
    var existingMap = {};
    nodes.forEach(function(n) { existingMap[n.instance_id] = n; });

    // 仅对"画布不存在"的新节点做拓扑分层布局
    var newNodes = gNodes.filter(function(gn) { return !existingMap[gn.instance_id]; });
    var newNodeIds = newNodes.map(function(n) { return n.instance_id; });
    var newNodeSet = {};
    newNodeIds.forEach(function(id) { newNodeSet[id] = true; });

    var layers = [];
    var indeg = {};
    var adj = {};
    newNodeIds.forEach(function(id) { indeg[id] = 0; adj[id] = []; });
    gEdges.forEach(function(e) {
      // 只统计新节点之间的边；引用旧节点的边无需参与新节点分层
      if (!newNodeSet[e.from_node] || !newNodeSet[e.to_node]) return;
      indeg[e.to_node] = (indeg[e.to_node] || 0) + 1;
      if (!adj[e.from_node]) adj[e.from_node] = [];
      adj[e.from_node].push(e.to_node);
    });

    // BFS 分层
    var queue = [];
    newNodeIds.forEach(function(id) { if (!indeg[id]) queue.push(id); });

    var depth = {};
    queue.forEach(function(id) { depth[id] = 0; });

    while (queue.length) {
      var cur = queue.shift();
      (adj[cur] || []).forEach(function(next) {
        if (depth[next] === undefined || depth[next] < depth[cur] + 1) {
          depth[next] = depth[cur] + 1;
        }
        indeg[next]--;
        if (indeg[next] <= 0) queue.push(next);
      });
    }

    // 按层分组
    var maxDepth = 0;
    newNodeIds.forEach(function(id) {
      var d = depth[id] !== undefined ? depth[id] : 0;
      if (!layers[d]) layers[d] = [];
      layers[d].push(id);
      if (d > maxDepth) maxDepth = d;
    });

    var marginX = 80, marginY = 60;
    var gapX = 250, gapY = 200;

    // 新节点起始列放在画布已有节点最右侧之后，避免重叠
    var baseX = marginX;
    nodes.forEach(function(n) {
      if (n.x > baseX) baseX = n.x;
    });
    baseX = (baseX >= marginX ? baseX + gapX : marginX);

    // 位置分配
    var posMap = {};
    for (var l = 0; l <= maxDepth; l++) {
      if (!layers[l]) continue;
      var count = layers[l].length;
      var startY = marginY + (maxDepth > 0 ? (maxDepth - l) * gapY * 0.3 : 0);
      layers[l].forEach(function(id, i) {
        posMap[id] = {
          x: baseX + l * gapX,
          y: startY + i * gapY,
        };
      });
    }

    // 合并节点：已有实例保留，新实例追加
    var finalNodes = nodes.slice();
    newNodes.forEach(function(gn) {
      var pos = posMap[gn.instance_id] || { x: marginX, y: marginY };
      finalNodes.push({
        instance_id: gn.instance_id,
        node_id: gn.node_id,
        node_name: gn.node_name || gn.node_id,
        inputs: gn.inputs || [],
        outputs: gn.outputs || [],
        values: gn.values || {},
        x: pos.x,
        y: pos.y,
      });
    });

    // 合并边：按 (from_node,from_port,to_node,to_port) 去重
    var edgeKey = function(e) { return e.from_node + '|' + e.from_port + '|' + e.to_node + '|' + e.to_port; };
    var seenEdge = {};
    edges.forEach(function(e) { seenEdge[edgeKey(e)] = true; });

    var finalEdges = edges.slice();
    gEdges.forEach(function(e) {
      var ne = {
        from_node: e.from_node,
        from_port: e.from_port,
        to_node: e.to_node,
        to_port: e.to_port,
        label: e.label || '',
      };
      var k = edgeKey(ne);
      if (!seenEdge[k]) {
        finalEdges.push(ne);
        seenEdge[k] = true;
      }
    });

    pushUndo();
    nodes = finalNodes;
    edges = finalEdges;
    nodeCounter = Math.max(nodeCounter, finalNodes.length);
    render();
  }

  /** 向对话面板添加消息气泡 */
  function addWCChatMessage(role, text) {
    var msgs = document.getElementById('wc-chat-messages');
    if (!msgs) return;

    var bubble = document.createElement('div');
    var isUser = role === 'user';
    bubble.style.cssText =
      'max-width:90%;padding:8px 12px;border-radius:12px;font-size:12px;line-height:1.5;word-break:break-word;white-space:pre-wrap;' +
      (isUser
        ? 'align-self:flex-end;background:' + COLORS.buttonHover + ';color:#fff;'
        : 'align-self:flex-start;background:' + COLORS.bg + ';color:' + COLORS.text + ';border:1px solid ' + COLORS.nodeStroke + ';');

    bubble.textContent = text;
    msgs.appendChild(bubble);
    msgs.scrollTop = msgs.scrollHeight;
  }

  // ═══════════════════════════════════════
  // 节点搜索过滤
  // ═══════════════════════════════════════
  function onSearch(query) {
    const sel = document.getElementById('wc-node-select');
    if (!sel) return;
    const q = query.trim().toLowerCase();

    // 重建下拉选项，根据搜索词过滤
    let html = '';
    for (const cat of Object.keys(categories)) {
      let anyMatch = false;
      let catHtml = '';
      for (const nid of categories[cat]) {
        const meta = nodeRegistry.find(n => n.node_id === nid) || {};
        const name = (meta.node_name || nid).toLowerCase();
        if (!q || name.includes(q) || nid.toLowerCase().includes(q)) {
          catHtml += `<option value="${nid}">${meta.node_name || nid}</option>`;
          anyMatch = true;
        }
      }
      if (anyMatch) {
        html += `<optgroup label="${cat}">${catHtml}</optgroup>`;
      }
    }
    if (!html) {
      html = '<option value="" disabled>无匹配节点</option>';
    }
    sel.innerHTML = html;
  }

  // ═══════════════════════════════════════
  // 工作流持久化
  // ═══════════════════════════════════════

  function saveWorkflow() {
    if (!nodes.length) {
      alert('画布为空，请先添加节点。');
      return;
    }

    // 收集当前画布状态
    const graphNodes = nodes.map(n => ({
      instance_id: n.instance_id,
      node_id: n.node_id,
      node_name: n.node_name,
      node_category: n.node_category,
      inputs: n.inputs,
      outputs: n.outputs,
      values: n.values,
      x: n.x,
      y: n.y,
    }));
    const graphEdges = edges.map(e => ({
      from_node: e.from_node,
      from_port: e.from_port,
      to_node: e.to_node,
      to_port: e.to_port,
      label: e.label || '',
    }));

    // 弹出命名对话框
    const name = prompt('工作流名称：', currentWorkflowName || '');
    if (!name || !name.trim()) return;

    const workflowId = currentWorkflowId || '';

    fetch(API_BASE + '/workflows', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name.trim(),
        nodes: graphNodes,
        edges: graphEdges,
        workflow_id: workflowId,
      }),
    })
      .then(r => r.json())
      .then(data => {
        if (data.ok) {
          currentWorkflowId = data.data.id;
          currentWorkflowName = data.data.name;
          alert('✅ 工作流已保存: ' + data.data.name);
        } else {
          alert('❌ 保存失败: ' + (data.error?.message || '未知错误'));
        }
      })
      .catch(e => alert('❌ 保存失败: ' + e.message));
  }

  function showWorkflows() {
    fetch(API_BASE + '/workflows')
      .then(r => r.json())
      .then(data => {
        if (!data.ok) { alert('加载失败'); return; }
        const wfs = data.workflows || [];
        showWorkflowModal(wfs);
      })
      .catch(e => alert('加载失败: ' + e.message));
  }

  function showWorkflowModal(workflows) {
    // 移除已有弹层
    const old = document.getElementById('wc-workflow-modal');
    if (old) old.remove();

    let rows = '';
    if (!workflows.length) {
      rows = '<tr><td colspan="4" style="padding:12px;text-align:center;color:#707090;">暂无保存的工作流</td></tr>';
    } else {
      for (const wf of workflows) {
        const isCurrent = wf.id === currentWorkflowId ? ' (当前)' : '';
        rows += `
          <tr style="border-bottom:1px solid #252540;">
            <td style="padding:8px 12px;color:#c0c0c0;">${wf.name}${isCurrent}</td>
            <td style="padding:8px 12px;color:#707090;font-size:11px;">${wf.node_count} 节点 ${wf.edge_count} 连线</td>
            <td style="padding:8px 12px;color:#707090;font-size:11px;">${wf.saved_at || ''}</td>
            <td style="padding:8px 12px;">
              <button onclick="WhiteCityEditor._loadWorkflowById('${wf.id}')" style="padding:4px 10px;background:${COLORS.button};color:${COLORS.text};border:none;border-radius:3px;cursor:pointer;">加载</button>
              <button onclick="WhiteCityEditor._deleteWorkflowById('${wf.id}')" style="padding:4px 10px;background:#500;color:#f66;border:none;border-radius:3px;cursor:pointer;margin-left:4px;">删除</button>
            </td>
          </tr>`;
      }
    }

    const html = `
    <div id="wc-workflow-modal" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.6);z-index:1100;display:flex;align-items:center;justify-content:center;">
      <div style="background:${COLORS.bg};border:1px solid ${COLORS.nodeStroke};border-radius:8px;padding:20px;min-width:500px;max-width:700px;">
        <h3 style="margin:0 0 16px;color:${COLORS.text};">已保存的工作流</h3>
        <div style="max-height:400px;overflow-y:auto;">
          <table style="width:100%;border-collapse:collapse;">
            <tbody>${rows}</tbody>
          </table>
        </div>
        <button onclick="document.getElementById('wc-workflow-modal').remove()" style="margin-top:12px;padding:6px 16px;background:${COLORS.button};color:${COLORS.text};border:none;border-radius:4px;cursor:pointer;">关闭</button>
      </div>
    </div>`;

    const overlay = document.createElement('div');
    overlay.innerHTML = html;
    document.body.appendChild(overlay.firstElementChild);
    document.getElementById('wc-workflow-modal').addEventListener('click', function(e) {
      if (e.target === this) this.remove();
    });
  }

  function loadWorkflowById(id) {
    fetch(API_BASE + '/workflows/' + id)
      .then(r => r.json())
      .then(data => {
        if (!data.ok) { alert('加载失败: ' + (data.error?.message || '')); return; }
        const wf = data.data;
        pushUndo();
        nodes = [];
        edges = [];
        nodeCounter = 0;
        for (const sn of wf.nodes) {
          const meta = nodeRegistry.find(n => n.node_id === sn.node_id) || {};
          nodes.push({
            instance_id: sn.instance_id || ('n' + (++nodeCounter)),
            node_id: sn.node_id,
            node_name: sn.node_name || meta.node_name || sn.node_id,
            node_category: sn.node_category || meta.node_category || '',
            inputs: sn.inputs || meta.inputs || [],
            outputs: sn.outputs || meta.outputs || [],
            values: sn.values || sn.inputs || {},
            x: sn.x || 60 + nodes.length * 260,
            y: sn.y || 100,
          });
        }
        for (const se of wf.edges) {
          edges.push({
            from_node: se.from_node,
            from_port: se.from_port,
            to_node: se.to_node,
            to_port: se.to_port,
            label: se.label || '',
          });
        }
        currentWorkflowId = id;
        currentWorkflowName = wf.name;
        nodeCounter = nodes.length;
        render();
        // 关闭弹窗
        const modal = document.getElementById('wc-workflow-modal');
        if (modal) modal.remove();
      })
      .catch(e => alert('加载失败: ' + e.message));
  }

  function deleteWorkflowById(id) {
    if (!confirm('确定删除该工作流？')) return;
    fetch(API_BASE + '/workflows/' + id, { method: 'DELETE' })
      .then(r => r.json())
      .then(data => {
        if (data.ok) {
          if (id === currentWorkflowId) { currentWorkflowId = ''; currentWorkflowName = ''; }
          // 刷新列表
          fetch(API_BASE + '/workflows')
            .then(r => r.json())
            .then(d => showWorkflowModal(d.workflows || []));
        } else {
          alert('删除失败: ' + (data.error?.message || ''));
        }
      })
      .catch(e => alert('删除失败: ' + e.message));
  }

  // 当前画布关联的工作流 ID（保存后记录，以便更新而非新建）
  let currentWorkflowId = '';
  let currentWorkflowName = '';

  // ═══════════════════════════════════════
  // ComfyUI 互通
  // ═══════════════════════════════════════

  /** 收集当前画布为标准图数据（与保存工作流共用） */
  function collectGraphData() {
    const graphNodes = nodes.map(n => ({
      instance_id: n.instance_id,
      node_id: n.node_id,
      node_name: n.node_name,
      node_category: n.node_category,
      inputs: n.inputs || [],
      outputs: n.outputs || [],
      values: n.values || {},
      x: n.x,
      y: n.y,
    }));
    const graphEdges = edges.map(e => ({
      from_node: e.from_node,
      from_port: e.from_port,
      to_node: e.to_node,
      to_port: e.to_port,
      label: e.label || '',
    }));
    return { nodes: graphNodes, edges: graphEdges };
  }

  /** 导出当前画布为 ComfyUI workflow JSON 并下载 */
  async function exportComfyUI() {
    if (!nodes.length) { alert('画布为空，请先添加节点。'); return; }
    const { nodes: graphNodes, edges: graphEdges } = collectGraphData();
    try {
      const resp = await fetch(API_BASE + '/comfyui/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nodes: graphNodes, edges: graphEdges }),
      });
      const data = await resp.json();
      if (!data.ok) {
        alert('❌ 导出失败: ' + (data.message || data.error?.message || '未知错误'));
        return;
      }
      // 下载 JSON 文件（可直接拖入 ComfyUI）
      const blob = new Blob([JSON.stringify(data.workflow, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const ts = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19);
      a.href = url;
      a.download = 'comfyui_workflow_' + ts + '.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      alert('✅ 已导出 ComfyUI 工作流（' + (data.workflow.nodes || []).length + ' 节点）');
    } catch (e) {
      alert('❌ 导出失败: ' + e.message);
    }
  }

  /** 选择 ComfyUI workflow JSON 文件并导入到画布 */
  function importComfyUI() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json,application/json';
    input.style.display = 'none';
    input.onchange = async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      let workflow;
      try {
        workflow = JSON.parse(await file.text());
      } catch (e) {
        alert('❌ 文件不是有效的 JSON: ' + e.message);
        return;
      }
      try {
        const resp = await fetch(API_BASE + '/comfyui/import', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ workflow }),
        });
        const data = await resp.json();
        if (!data.ok) {
          alert('❌ 导入失败: ' + (data.message || data.error?.message || '未知错误'));
          return;
        }
        pushUndo();
        nodes = data.nodes || [];
        edges = data.edges || [];
        nodeCounter = nodes.length;
        render();
        let msg = '✅ 已导入 ' + nodes.length + ' 节点, ' + edges.length + ' 连线';
        if (data.warnings && data.warnings.length) {
          msg += '\n\n⚠️ 提示:\n' + data.warnings.slice(0, 5).join('\n');
          if (data.warnings.length > 5) msg += '\n…等共 ' + data.warnings.length + ' 条';
        }
        alert(msg);
      } catch (e) {
        alert('❌ 导入失败: ' + e.message);
      }
    };
    document.body.appendChild(input);
    input.click();
    document.body.removeChild(input);
  }

  // ═══════════════════════════════════════
  // 面板开关
  // ═══════════════════════════════════════
  function open() {
    const panel = document.getElementById('white-city-panel');
    if (panel) {
      panel.style.display = 'flex';
      panel.style.flexDirection = 'column';
      // 隐藏右下角浮动AI助手，避免双Ai重复
      var fab = document.getElementById('ai-assistant-fab');
      var aip = document.getElementById('ai-assistant-panel');
      if (fab) fab.style.display = 'none';
      if (aip) aip.style.display = 'none';
      if (!nodes.length && !svg) init('white-city-panel');
      else render();
    }
  }

  function close() {
    var fab = document.getElementById('ai-assistant-fab');
    if (fab) fab.style.display = '';
    var panel = document.getElementById('white-city-panel');
    if (panel) panel.style.display = 'none';
  }

  function toggle() {
    const panel = document.getElementById('white-city-panel');
    if (!panel || panel.style.display === 'none') open();
    else close();
  }

  // ═══════════════════════════════════════
  // 导出
  // ═══════════════════════════════════════
  window.WhiteCityEditor = {
    init,
    open,
    close,
    toggle,
    addNode,
    loadPipeline,
    undo,
    run,
    saveWorkflow,
    showWorkflows,
    deleteSelected: () => { if (selectedNodeId) deleteNode(selectedNodeId); },
    getGraph: () => ({ nodes, edges }),
    setGraph: (n, e) => { nodes = n || []; edges = e || []; nodeCounter = nodes.length; render(); },
    // ComfyUI 互通
    exportComfyUI,
    importComfyUI,
    // 内部方法（toolbar onclick 需要公开）
    _onSearch: onSearch,
    _loadWorkflowById: loadWorkflowById,
    _deleteWorkflowById: deleteWorkflowById,
    // 双屏对话
    _toggleWCChat: toggleWCChat,
    _sendWCCompose: sendWCCompose,
    _addWCChatMessage: addWCChatMessage,
    // 复合确认弹窗（onclick 需要公开）
    _composeAction: _composeAction,
    _toggleRejectBox: _toggleRejectBox,
  };

  console.log('[WhiteCity] Editor loaded');
})();
