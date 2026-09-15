(function() {
  'use strict';

window.runFullDiagnosis = function() {
  var btn = document.getElementById('wt-btn-diagnosis');
  if (btn) { btn.textContent = '...'; btn.disabled = true; }
  api('/api/project/diagnosis', {method:'POST',body:JSON.stringify({})}).then(function(d){
    if (!d.ok) { showToast('诊断失败:'+(d.error||'')); return; }
    var s = d.summary;
    showToast('诊断完成：'+s.written_chapters+'/'+s.total_chapters+'章，'+s.total_issues+'个问题（'+s.high_issues+'严重）');
    // Show worklist
    var text = '全书诊断报告\n\n共'+s.total_chapters+'章，已写'+s.written_chapters+'章，'+s.total_words+'字\n发现问题:'+s.total_issues+'个（'+s.high_issues+'严重/'+s.medium_issues+'中等）\n\n';
    (d.worklist||[]).forEach(function(w){
      text += '第'+w.chapter+'章 '+w.title+' ('+w.word_count+'字)\n';
      w.issues.forEach(function(iss){ text += '  ['+iss.severity+'] '+iss.detail+'\n'; });
    });
    alert(text.substring(0, 5000));
  }).catch(function(e){showToast('诊断异常:'+e.message)}).finally(function(){if(btn){btn.textContent='诊断';btn.disabled=false;}});
}

})();