/**
 * VirtualList — 虚拟滚动基类
 * 用于章节列表、大纲列表、时间线导航等大列表场景
 * 只渲染可视区域的 DOM 元素，大幅减少节点数量
 *
 * 使用方式:
 *   var vl = new VirtualList(containerEl, {
 *     itemHeight: 36,          // 每项固定高度(px)
 *     items: chapterData,       // 数据数组
 *     renderFn: function(item, index) {
 *       return '<div class="chapter-item">' + item.title + '</div>';
 *     },
 *     onSelect: function(item, index) { ... }
 *   });
 */

var VirtualList = (function() {

  function VirtualList(container, opts) {
    this.container = container;
    this.itemHeight = opts.itemHeight || 36;
    this.items = opts.items || [];
    this.renderFn = opts.renderFn || function(item, idx) { return '<div>' + (item.title || item) + '</div>'; };
    this.onSelect = opts.onSelect || null;
    this.selectedIdx = opts.selectedIdx || -1;
    this.bufferSize = opts.bufferSize || 5;  // 额外渲染的缓冲项数
    this.className = opts.className || '';

    // 创建内部结构
    this._setupDOM();
    this._bindEvents();
    this.render();
  }

  VirtualList.prototype._setupDOM = function() {
    // 容器需要 overflow-y: auto
    this.container.style.overflowY = 'auto';
    this.container.style.position = 'relative';

    // 总高度占位元素（撑开滚动区域）
    this.spacer = document.createElement('div');
    this.spacer.style.cssText = 'position:absolute;top:0;left:0;right:0;height:' +
      (this.items.length * this.itemHeight) + 'px;pointer-events:none';
    this.container.appendChild(this.spacer);

    // 可视区域渲染容器
    this.viewport = document.createElement('div');
    this.viewport.style.cssText = 'position:relative;z-index:1';
    this.container.appendChild(this.viewport);
  };

  VirtualList.prototype._bindEvents = function() {
    var self = this;
    this.container.addEventListener('scroll', function() {
      self.render();
    });
  };

  VirtualList.prototype.render = function() {
    var scrollTop = this.container.scrollTop;
    var containerHeight = this.container.clientHeight;
    var totalItems = this.items.length;

    // 计算可视范围
    var startIdx = Math.floor(scrollTop / this.itemHeight) - this.bufferSize;
    startIdx = Math.max(0, startIdx);

    var endIdx = Math.ceil((scrollTop + containerHeight) / this.itemHeight) + this.bufferSize;
    endIdx = Math.min(totalItems, endIdx);

    // 更新 spacer 高度
    this.spacer.style.height = (totalItems * this.itemHeight) + 'px';

    // 渲染可视项
    var html = '';
    for (var i = startIdx; i < endIdx; i++) {
      var item = this.items[i];
      var isSelected = (i === this.selectedIdx);
      var itemHtml = this.renderFn(item, i, isSelected);
      html += itemHtml;
    }

    // 设置偏移量
    this.viewport.style.transform = 'translateY(' + (startIdx * this.itemHeight) + 'px)';
    this.viewport.innerHTML = html;

    // 绑定选择事件
    if (this.onSelect) {
      var items = this.viewport.children;
      for (var j = 0; j < items.length; j++) {
        var idx = startIdx + j;
        (function(el, itemIdx) {
          el.addEventListener('click', function(e) {
            self.select(itemIdx, e);
          });
        })(items[j], idx);
      }
    }
  };

  VirtualList.prototype.select = function(idx, e) {
    this.selectedIdx = idx;
    if (this.onSelect) {
      this.onSelect(this.items[idx], idx, e);
    }
    this.render();  // 重新渲染以更新选中状态
  };

  VirtualList.prototype.setItems = function(newItems) {
    this.items = newItems;
    this.spacer.style.height = (newItems.length * this.itemHeight) + 'px';
    this.render();
  };

  VirtualList.prototype.scrollToIndex = function(idx) {
    var targetTop = idx * this.itemHeight;
    this.container.scrollTop = targetTop;
  };

  VirtualList.prototype.destroy = function() {
    this.container.innerHTML = '';
    this.container.style.overflowY = '';
    this.container.style.position = '';
  };

  return VirtualList;
})();

window.VirtualList = VirtualList;
