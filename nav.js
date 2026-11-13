/* Sports Edge - piezas comunes a todas las paginas:
   cabecera con menu, modo dia/noche, ancho de pagina y columnas laterales de noticias.
   Cada pagina pone <header id="top"></header>, carga este archivo y llama a navRender(lang, "seccion")
   dentro de su render(). Los botones ES/EN llaman a setLang() de cada pagina. */
(function(){
  var TX={
    es:{home:"Inicio",futbol:"Fútbol",tenis:"Tenis",baloncesto:"Baloncesto",hockey:"Hockey",americano:"Fútbol americano",stats:"Estadísticas",guia:"Guía",
        news:"Noticias",newsof:"Noticias de",more:"Más noticias",ago_h:"hace %d h",ago_m:"hace %d min",tema:"Modo día / noche"},
    en:{home:"Home",futbol:"Football",tenis:"Tennis",baloncesto:"Basketball",hockey:"Hockey",americano:"American football",stats:"Statistics",guia:"Guide",
        news:"News",newsof:"News:",more:"More news",ago_h:"%dh ago",ago_m:"%d min ago",tema:"Light / dark mode"}
  };
  var ITEMS=[
    ["home","index.html","🏠"],["futbol","futbol.html","⚽"],["tenis","tenis.html","🎾"],
    ["baloncesto","equipos.html?dep=baloncesto","🏀"],["hockey","equipos.html?dep=hockey","🏒"],["americano","equipos.html?dep=americano","🏈"],
    ["stats","estadisticas.html","📊"],["guia","guia.html","📘"]
  ];
  var css=
    /* Modo dia: misma familia de colores que Equity Intelligence (gris claro, dorado y verde) */
    ":root[data-theme=light]{--bg:#f3f4f6;--card:#ffffff;--card2:#f7f7f5;--line:#e2e4e8;--txt:#1f2328;--mut:#5c6370;"+
      "--acc:#1e7a4c;--blue:#8a6a00;--red:#c0392b;--amb:#a15c00}"+
    ":root[data-theme=light] body{background:var(--bg);color:var(--txt)}"+
    ":root[data-theme=light] #top{background:#ffffff}"+
    ":root[data-theme=light] #top .se-logo{color:#8a6a00}"+
    ":root[data-theme=light] #top nav a.on{border-bottom-color:#8a6a00}"+
    ":root[data-theme=light] #top .se-lang button.on{background:#8a6a00;border-color:#8a6a00;color:#fff}"+
    /* Cabecera */
    "#top{display:block;padding:0;border-bottom:1px solid var(--line);background:var(--bg);position:sticky;top:0;z-index:20}"+
    "#top .se-row{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 24px 6px;max-width:1500px;margin:0 auto}"+
    "#top .se-logo{font-weight:800;font-size:20px;letter-spacing:.5px;color:var(--txt);text-decoration:none}"+
    "#top .se-logo span{color:var(--acc)}"+
    "#top .se-r{display:flex;align-items:center;gap:10px}"+
    "#top .se-th{background:var(--card);border:1px solid var(--line);color:var(--txt);height:32px;min-width:38px;border-radius:8px;cursor:pointer;font-size:16px;line-height:1}"+
    "#top .se-lang button{background:var(--card);color:var(--mut);border:1px solid var(--line);padding:6px 12px;cursor:pointer;font-weight:700;font-size:13px}"+
    "#top .se-lang button.on{color:var(--bg);background:var(--acc);border-color:var(--acc)}"+
    "#top nav{display:flex;gap:4px;flex-wrap:wrap;padding:0 18px;max-width:1500px;margin:0 auto}"+
    "#top nav a{color:var(--mut);text-decoration:none;font-weight:600;font-size:14px;padding:10px 12px;border-bottom:3px solid transparent;white-space:nowrap}"+
    "#top nav a:hover{color:var(--txt)}"+
    "#top nav a.on{color:var(--txt);border-bottom-color:var(--acc)}"+
    /* Filtros de ligas: todos visibles, sin barra de desplazamiento */
    ".chips,.ligas,.sports,.tabs{flex-wrap:wrap!important;overflow:visible!important}"+
    /* Ancho de pagina con columnas laterales */
    ".se-wrap{display:flex;gap:22px;max-width:1500px;margin:0 auto;padding:0 20px;align-items:flex-start}"+
    ".se-wrap>main{flex:1 1 auto;min-width:0;max-width:none!important;margin:0!important;padding-left:0!important;padding-right:0!important}"+
    ".se-side{flex:0 0 290px;width:290px;padding-top:22px;position:sticky;top:96px;max-height:calc(100vh - 110px);overflow-y:auto;scrollbar-width:thin}"+
    ".se-side h3{font-size:13px;text-transform:uppercase;letter-spacing:1px;color:var(--blue);margin:0 0 10px}"+
    ".se-n{display:block;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-bottom:10px;text-decoration:none;color:var(--txt)}"+
    ".se-n:hover{border-color:var(--acc)}"+
    ".se-n img{display:block;width:100%;height:150px;object-fit:cover;background:var(--card2)}"+
    ".se-n .b{padding:9px 11px}"+
    ".se-n .s{font-size:11px;color:var(--mut);margin-bottom:3px}"+
    ".se-n .s b{color:var(--blue)}"+
    ".se-n .h{font-size:13.5px;line-height:1.35;font-weight:600}"+
    ".se-n.sm{display:grid;grid-template-columns:76px 1fr}"+
    ".se-n.sm img{height:100%;min-height:70px}"+
    ".se-n.sm .h{font-size:13px;font-weight:500}"+
    ".se-left{order:-1}"+
    "@media(max-width:1340px){.se-left{display:none}}"+
    "@media(max-width:1060px){.se-wrap{display:block}.se-side{position:static;width:auto;max-height:none;overflow:visible;padding-top:10px}"+
      ".se-side .se-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}.se-side .se-n{margin-bottom:0}}"+
    "@media(max-width:720px){#top .se-row{padding:10px 16px 4px}#top nav{padding:0 8px;gap:0}#top nav a{font-size:13px;padding:8px 8px}"+
      ".se-wrap{padding:0 16px}}";
  var st=document.createElement("style"); st.textContent=css; document.head.appendChild(st);

  /* ---------- modo dia / noche ---------- */
  function temaGuardado(){ try{ return localStorage.getItem("tema"); }catch(e){ return null; } }
  function temaInicial(){ var g=temaGuardado(); if(g==="light"||g==="dark") return g;
    try{ return window.matchMedia&&window.matchMedia("(prefers-color-scheme: light)").matches?"light":"dark"; }catch(e){ return "dark"; } }
  function aplicarTema(t){ if(t==="light") document.documentElement.setAttribute("data-theme","light"); else document.documentElement.removeAttribute("data-theme"); }
  aplicarTema(temaInicial());
  window.cambiarTema=function(){ var t=document.documentElement.getAttribute("data-theme")==="light"?"dark":"light";
    aplicarTema(t); try{ localStorage.setItem("tema",t); }catch(e){} var b=document.getElementById("se-th"); if(b) b.textContent=t==="light"?"🌙":"☀️"; };

  /* ---------- columnas laterales de noticias ---------- */
  var NEWS=null, pedido=false, ultimo={lang:"es",act:"home"};
  var DEPS={futbol:1,tenis:1,baloncesto:1,hockey:1,americano:1};
  function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];}); }
  function hace(iso,t){ var m=Math.round((Date.now()-Date.parse(iso))/60000); if(!(m>=0)) return "";
    return m<60 ? t.ago_m.replace("%d",m) : t.ago_h.replace("%d",Math.round(m/60)); }
  function tarjeta(x,t,peq){
    if(!/^https?:\/\//.test(x.url)) return "";
    var img=(x.img&&/^https:\/\//.test(x.img))?'<img src="'+esc(x.img)+'" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">':'';
    return '<a class="se-n'+(peq&&img?' sm':'')+'" href="'+esc(x.url)+'" target="_blank" rel="noopener nofollow">'+img
      +'<div class="b"><div class="s"><b>'+esc(x.fuente)+'</b> · '+esc(hace(x.fecha,t))+'</div><div class="h">'+esc(x.t)+'</div></div></a>';
  }
  function montarLados(){
    var m=document.querySelector("main"); if(!m||document.querySelector(".se-wrap")) return;
    var w=document.createElement("div"); w.className="se-wrap"; m.parentNode.insertBefore(w,m); w.appendChild(m);
    var r=document.createElement("aside"); r.className="se-side"; r.id="se-right"; w.appendChild(r);
    if(ultimo.act==="home"){ var l=document.createElement("aside"); l.className="se-side se-left"; l.id="se-left"; w.insertBefore(l,m); }
  }
  function pintarLados(){
    if(!NEWS) return;
    var t=TX[ultimo.lang]||TX.es, all=NEWS[ultimo.lang]||NEWS.es||[], act=ultimo.act;
    var dep=DEPS[act]?act:null, lista=all;
    if(dep){ var propias=all.filter(function(x){return x.dep===dep;}); lista=propias.concat(all.filter(function(x){return x.dep!==dep;})); }
    /* se alternan los medios (AS, Marca, Mundo Deportivo...) para que salgan todos, no solo uno */
    function alternar(l){ var g={}, fs=[], out=[];
      l.forEach(function(x){ if(!g[x.fuente]){ g[x.fuente]=[]; fs.push(x.fuente); } g[x.fuente].push(x); });
      for(var i=0; out.length<l.length; i++){ fs.forEach(function(f){ if(g[f][i]) out.push(g[f][i]); }); }
      return out; }
    var orden=dep ? alternar(lista.filter(function(x){return x.dep===dep;})).concat(alternar(lista.filter(function(x){return x.dep!==dep;})))
                  : alternar(lista);
    var r=document.getElementById("se-right"), l=document.getElementById("se-left");
    var titulo=dep?(t.newsof+" "+t[dep].toLowerCase()):t.news;
    if(l){
      var izq=orden.filter(function(x,i){return i%2===0;}).slice(0,8), der=orden.filter(function(x,i){return i%2===1;}).slice(0,12);
      l.innerHTML='<h3>'+t.news+'</h3><div class="se-list">'+izq.map(function(x,i){return tarjeta(x,t,i>=3);}).join("")+'</div>';
      if(r) r.innerHTML='<h3>'+t.more+'</h3><div class="se-list">'+der.map(function(x,i){return tarjeta(x,t,i>=2);}).join("")+'</div>';
    } else if(r){
      r.innerHTML=orden.length?'<h3>'+esc(titulo)+'</h3><div class="se-list">'+orden.slice(0,12).map(function(x,i){return tarjeta(x,t,i>=3);}).join("")+'</div>':"";
    }
  }
  function cargarNoticias(){
    if(pedido) return; pedido=true;
    fetch("data/noticias.json?v="+Date.now()).then(function(r){ if(!r.ok) throw 0; return r.json(); })
      .then(function(j){ NEWS=j; pintarLados(); }).catch(function(){ NEWS=null; });
  }

  /* ---------- cabecera ---------- */
  window.navRender=function(lang,activo){
    ultimo={lang:lang,act:activo};
    var el=document.getElementById("top"); if(!el) return;
    var t=TX[lang]||TX.es, n="";
    for(var i=0;i<ITEMS.length;i++){ var it=ITEMS[i];
      n+='<a href="'+it[1]+'"'+(it[0]===activo?' class="on"':'')+'>'+it[2]+' '+t[it[0]]+'</a>'; }
    el.innerHTML='<div class="se-row"><a class="se-logo" href="index.html">SPORTS<span>EDGE</span></a>'
      +'<div class="se-r"><button id="se-th" class="se-th" onclick="cambiarTema()" title="'+t.tema+'">'
      +(document.documentElement.getAttribute("data-theme")==="light"?"🌙":"☀️")+'</button>'
      +'<div class="se-lang"><button class="'+(lang==="es"?"on":"")+'" onclick="setLang(\'es\')">ES</button>'
      +'<button class="'+(lang==="en"?"on":"")+'" onclick="setLang(\'en\')">EN</button></div></div></div><nav>'+n+'</nav>';
    if(activo!=="guia"){ montarLados(); cargarNoticias(); pintarLados(); }
  };
})();
