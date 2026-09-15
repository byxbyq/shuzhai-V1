// 主题初始化：读取 localStorage 中的主题偏好，同步到 CSS 变量
(function(){
  var theme = localStorage.getItem('theme') || 'dark';
  if (theme === 'light') {
    var root = document.documentElement;
    root.style.setProperty('--bg','#f5f2eb');
    root.style.setProperty('--surface','#ffffff');
    root.style.setProperty('--paper','#ffffff');
    root.style.setProperty('--card','#ffffff');
    root.style.setProperty('--bg2','#f0ebe3');
    root.style.setProperty('--ink','#2c2416');
    root.style.setProperty('--muted','#8b7355');
    root.style.setProperty('--border','rgba(0,0,0,0.08)');
    root.style.setProperty('--border-soft','rgba(0,0,0,0.04)');
  }
})();
