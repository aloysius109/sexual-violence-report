document.querySelectorAll('[data-explorer]').forEach(section=>{
  const controls=[...section.querySelectorAll('input,select')];
  const rows=[...section.querySelectorAll('tbody tr')];
  const count=section.querySelector('output');
  function filter(){
    let visible=0;
    for(const row of rows){
      const show=controls.every(c=>!c.value||(c.tagName==='INPUT'?row.textContent.toLowerCase().includes(c.value.toLowerCase()):row.dataset[c.dataset.field]===c.value));
      row.hidden=!show;if(show)visible++;
    }
    count.textContent=visible+' records shown';
  }
  controls.forEach(c=>c.addEventListener('input',filter));filter();
});
