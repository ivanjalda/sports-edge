/* Sports Edge - cabecera y menu comunes a todas las paginas.
   Cada pagina pone <header id="top"></header>, carga este archivo y llama a navRender(lang, "seccion")
   dentro de su funcion render(). Los botones ES/EN llaman a setLang() de cada pagina. */
(function(){
  var TX={
    es:{home:"Inicio",futbol:"Fútbol",tenis:"Tenis",baloncesto:"Baloncesto",hockey:"Hockey",stats:"Estadísticas",guia:"Guía"},
    en:{home:"Home",futbol:"Football",tenis:"Tennis",baloncesto:"Basketball",hockey:"Hockey",stats:"Statistics",guia:"Guide"}
  };
  var ITEMS=[
    ["home","index.html","🏠"],["futbol","futbol.html","⚽"],["tenis","tenis.html","🎾"],
    ["baloncesto","equipos.html?dep=baloncesto","🏀"],["hockey","equipos.html?dep=hockey","🏒"],
    ["stats","estadisticas.html","📊"],["guia","guia.html","📘"]
  ];
  var css=
    "#top{display:block;padding:0;border-bottom:1px solid var(--line);background:var(--bg);position:sticky;top:0;z-index:20}"+
    "#top .se-row{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 24px 6px}"+
    "#top .se-logo{font-weight:800;font-size:20px;letter-spacing:.5px;color:var(--txt);text-decoration:none}"+
    "#top .se-logo span{color:var(--acc)}"+
    "#top .se-lang button{background:var(--card);color:var(--mut);border:1px solid var(--line);padding:6px 12px;cursor:pointer;font-weight:700;font-size:13px}"+
    "#top .se-lang button.on{color:var(--bg);background:var(--acc);border-color:var(--acc)}"+
    "#top nav{display:flex;gap:4px;overflow-x:auto;padding:0 18px;scrollbar-width:none}"+
    "#top nav::-webkit-scrollbar{display:none}"+
    "#top nav a{flex:0 0 auto;color:var(--mut);text-decoration:none;font-weight:600;font-size:14px;padding:10px 12px;border-bottom:3px solid transparent;white-space:nowrap}"+
    "#top nav a:hover{color:var(--txt)}"+
    "#top nav a.on{color:var(--txt);border-bottom-color:var(--acc)}"+
    "@media(max-width:720px){#top .se-row{padding:10px 16px 4px}#top nav{padding:0 10px}#top nav a{font-size:13px;padding:9px 9px}}";
  var st=document.createElement("style"); st.textContent=css; document.head.appendChild(st);
  window.navRender=function(lang,activo){
    var el=document.getElementById("top"); if(!el) return;
    var t=TX[lang]||TX.es, n="";
    for(var i=0;i<ITEMS.length;i++){ var it=ITEMS[i];
      n+='<a href="'+it[1]+'"'+(it[0]===activo?' class="on"':'')+'>'+it[2]+' '+t[it[0]]+'</a>'; }
    el.innerHTML='<div class="se-row"><a class="se-logo" href="index.html">SPORTS<span>EDGE</span></a>'
      +'<div class="se-lang"><button class="'+(lang==="es"?"on":"")+'" onclick="setLang(\'es\')">ES</button>'
      +'<button class="'+(lang==="en"?"on":"")+'" onclick="setLang(\'en\')">EN</button></div></div><nav>'+n+'</nav>';
    var on=el.querySelector("nav a.on"), nv=el.querySelector("nav");
    if(on&&nv){ nv.scrollLeft=Math.max(0,on.offsetLeft-nv.clientWidth/2+on.clientWidth/2); }
  };
})();
