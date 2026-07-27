(function(){
  const y=document.getElementById('year'); if(y) y.textContent=new Date().getFullYear();
  document.querySelectorAll('[data-copy]').forEach(btn=>btn.addEventListener('click',()=>navigator.clipboard.writeText(btn.dataset.copy).then(()=>{btn.textContent='Copied!';setTimeout(()=>btn.textContent='Copy link',1200)})));
})();
