/* Sports Edge - piezas comunes a todas las paginas:
   cabecera con menu, modo dia/noche, ancho de pagina y columnas laterales de noticias.
   Cada pagina pone <header id="top"></header>, carga este archivo y llama a navRender(lang, "seccion")
   dentro de su render(). Los botones ES/EN llaman a setLang() de cada pagina. */
(function(){
  var TX={
    es:{home:"Inicio",futbol:"Fútbol",tenis:"Tenis",baloncesto:"Baloncesto",hockey:"Hockey",americano:"Fútbol americano",mma:"MMA",beisbol:"Béisbol",voleibol:"Voleibol",rugby:"Rugby",directo:"En directo",stats:"Estadísticas",guia:"Guía",
        news:"Noticias",newsof:"Noticias de",more:"Más noticias",ago_h:"hace %d h",ago_m:"hace %d min",tema:"Modo día / noche",picks:"⭐ Nuestros pronósticos",pick:"Pronóstico",odds:"Mejor cuota",at:"en",nopicks:"No hay pronósticos para las próximas horas.",allpicks:"Ver todos en Inicio →",today:"hoy",tomorrow:"mañana",draw:"Empate"},
    en:{home:"Home",futbol:"Football",tenis:"Tennis",baloncesto:"Basketball",hockey:"Hockey",americano:"American football",mma:"MMA",beisbol:"Baseball",voleibol:"Volleyball",rugby:"Rugby",directo:"Live",stats:"Statistics",guia:"Guide",
        news:"News",newsof:"News:",more:"More news",ago_h:"%dh ago",ago_m:"%d min ago",tema:"Light / dark mode",picks:"⭐ Our top picks",pick:"Pick",odds:"Best odds",at:"at",nopicks:"No picks for the next hours.",allpicks:"See all on Home →",today:"today",tomorrow:"tomorrow",draw:"Draw"}
  };
  var ITEMS=[
    ["home","index.html","🏠"],["directo","directo.html","🔴"],["futbol","futbol.html","⚽"],["tenis","tenis.html","🎾"],
    ["baloncesto","equipos.html?dep=baloncesto","🏀"],["hockey","equipos.html?dep=hockey","🏒"],["americano","equipos.html?dep=americano","🏈"],["mma","equipos.html?dep=mma","🥋"],["beisbol","equipos.html?dep=beisbol","⚾"],["voleibol","equipos.html?dep=voleibol","🏐"],["rugby","equipos.html?dep=rugby","🏉"],
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
    "#top .se-row{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 28px 6px}"+
    "#top .se-logo{font-weight:800;font-size:20px;letter-spacing:.5px;color:var(--txt);text-decoration:none}"+
    "#top .se-logo span{color:var(--acc)}"+
    "#top .se-r{display:flex;align-items:center;gap:10px}"+
    "#top .se-th{background:var(--card);border:1px solid var(--line);color:var(--txt);height:32px;min-width:38px;border-radius:8px;cursor:pointer;font-size:16px;line-height:1}"+
    "#top .se-lang button{background:var(--card);color:var(--mut);border:1px solid var(--line);padding:6px 12px;cursor:pointer;font-weight:700;font-size:13px}"+
    "#top .se-lang button.on{color:var(--bg);background:var(--acc);border-color:var(--acc)}"+
    "#top nav{display:flex;gap:4px;flex-wrap:wrap;padding:0 22px}"+
    "#top nav a{color:var(--mut);text-decoration:none;font-weight:600;font-size:14px;padding:10px 12px;border-bottom:3px solid transparent;white-space:nowrap}"+
    "#top nav a:hover{color:var(--txt)}"+
    "#top nav a.on{color:var(--txt);border-bottom-color:var(--acc)}"+
    /* Filtros de ligas: todos visibles, sin barra de desplazamiento */
    ".chips,.ligas,.sports,.tabs{flex-wrap:wrap!important;overflow:visible!important}"+
    /* Ancho de pagina con columnas laterales */
    ".se-wrap{display:flex;gap:26px;padding:0 28px;align-items:flex-start}"+
    ".se-wrap>main{flex:1 1 auto;min-width:0;max-width:none!important;margin:0!important;padding-left:0!important;padding-right:0!important}"+
    ".se-side{flex:0 0 300px;width:300px;padding-top:22px;position:sticky;top:96px;max-height:calc(100vh - 110px);overflow-y:auto;scrollbar-width:thin}"+
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
    "@media(min-width:1800px){.se-side{flex-basis:360px;width:360px}.se-n img{height:180px}}"+
    /* Columna izquierda: nuestros pronosticos destacados */
    ".se-pk{display:block;background:var(--card);border:1px solid var(--line);border-left:3px solid var(--acc);border-radius:10px;padding:9px 11px;margin-bottom:9px;text-decoration:none;color:var(--txt)}"+
    ".se-pk:hover{border-color:var(--acc)}"+
    ".se-pk .se-ps{font-size:11px;color:var(--mut);margin-bottom:2px}"+
    ".se-pk .se-pm{font-size:13.5px;font-weight:600;line-height:1.3}"+
    ".se-pk .se-pp{display:flex;justify-content:space-between;align-items:baseline;gap:8px;margin-top:5px;font-size:12.5px}"+
    ".se-pk .se-pp b{color:var(--acc);font-size:15px}"+
    ".se-pk .se-pc{font-size:11.5px;color:var(--mut);margin-top:2px}"+
    ".se-pk .se-pbar{height:5px;border-radius:3px;background:var(--line);margin-top:6px;overflow:hidden}"+
    ".se-pk .se-pbar i{display:block;height:100%;background:var(--acc)}"+
    ".se-side .se-empty{font-size:13px;color:var(--mut);border:1px dashed var(--line);border-radius:10px;padding:12px}"+
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
  var DEPS={futbol:1,tenis:1,baloncesto:1,hockey:1,americano:1,mma:1,beisbol:1,voleibol:1,rugby:1};
  function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];}); }
  function hace(iso,t){ var m=Math.round((Date.now()-Date.parse(iso))/60000); if(!(m>=0)) return "";
    return m<60 ? t.ago_m.replace("%d",m) : t.ago_h.replace("%d",Math.round(m/60)); }
  function tarjeta(x,t,peq){
    if(!/^https?:\/\//.test(x.url)) return "";
    var img=(x.img&&/^https:\/\//.test(x.img))?'<img src="'+esc(x.img)+'" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.classList.remove(\'sm\');this.remove()">':'';
    return '<a class="se-n'+(peq&&img?' sm':'')+'" href="'+esc(x.url)+'" target="_blank" rel="noopener nofollow">'+img
      +'<div class="b"><div class="s"><b>'+esc(x.fuente)+'</b> · '+esc(hace(x.fecha,t))+'</div><div class="h">'+esc(x.t)+'</div></div></a>';
  }
  function montarLados(){
    var m=document.querySelector("main"); if(!m||document.querySelector(".se-wrap")) return;
    var w=document.createElement("div"); w.className="se-wrap"; m.parentNode.insertBefore(w,m); w.appendChild(m);
    var r=document.createElement("aside"); r.className="se-side"; r.id="se-right"; w.appendChild(r);
    var l=document.createElement("aside"); l.className="se-side se-left"; l.id="se-left"; w.insertBefore(l,m);
  }
  function pintarLados(){
    var l0=document.getElementById("se-left");
    if(l0&&ultimo.act!=="home") pintarPicks(l0,TX[ultimo.lang]||TX.es);
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
    if(act!=="home") l=null;
    if(l){
      var izq=orden.filter(function(x,i){return i%2===0;}).slice(0,8), der=orden.filter(function(x,i){return i%2===1;}).slice(0,12);
      l.innerHTML='<h3>'+t.news+'</h3><div class="se-list">'+izq.map(function(x,i){return tarjeta(x,t,i>=3);}).join("")+'</div>';
      if(r) r.innerHTML='<h3>'+t.more+'</h3><div class="se-list">'+der.map(function(x,i){return tarjeta(x,t,i>=2);}).join("")+'</div>';
    } else if(r){
      r.innerHTML=orden.length?'<h3>'+esc(titulo)+'</h3><div class="se-list">'+orden.slice(0,12).map(function(x,i){return tarjeta(x,t,i>=3);}).join("")+'</div>':"";
    }
  }
  /* ---------- columna izquierda: pronosticos destacados (datos reales de data/) ---------- */
  var PK=null, pkPedido=false;
  var LG_DEP={nba:"baloncesto",euroliga:"baloncesto",eurocup:"baloncesto",ncaab:"baloncesto",wnba:"baloncesto",nhl:"hockey",ncaah:"hockey",
              nfl:"americano",ncaaf:"americano",ufc:"mma",mlb:"beisbol",voley:"voleibol",rug_6n:"rugby",rug_prem:"rugby",rug_top14:"rugby",rug_urc:"rugby",rug_cc:"rugby",rug_super:"rugby"};
  var ICO={futbol:"⚽",tenis:"🎾",baloncesto:"🏀",hockey:"🏒",americano:"🏈",mma:"🥋",beisbol:"⚾",voleibol:"🏐",rugby:"🏉"};
  function jget(f){ return fetch("data/"+f+"?v="+Date.now()).then(function(r){ if(!r.ok) throw 0; return r.json(); }).catch(function(){ return null; }); }
  function cargarPicks(){
    if(pkPedido) return; pkPedido=true;
    var lgs=Object.keys(LG_DEP);
    Promise.all([jget("predicciones.json"),jget("cuotas.json"),jget("tenis.json")].concat(lgs.map(function(lg){ return jget("equipos_"+lg+".json"); })))
    .then(function(r){
      var out=[], ahora=Date.now(), lim=ahora+36*3600*1000;
      function ok(f){ var x=Date.parse(f); return x>ahora && x<lim; }
      var fc=(r[1]&&r[1].partidos)||{};
      ((r[0]&&r[0].predicciones)||[]).forEach(function(p){ if(!ok(p.fecha)) return;
        var pr={"1":p.p_local,"X":p.p_empate,"2":p.p_visitante}, k="1"; if(pr.X>pr[k]) k="X"; if(pr["2"]>pr[k]) k="2";
        var c=fc[String(p.id)], mj=c&&c.mejor&&c.mejor[k];
        out.push({dep:"futbol",comp:p.liga,fecha:p.fecha,a:p.local,b:p.visitante,pick:k==="1"?p.local:(k==="2"?p.visitante:"X"),prob:pr[k],
          c:mj?mj.c:null,casa:mj?mj.casa:null,url:"futbol.html"}); });
      ((r[2]&&r[2].predicciones)||[]).forEach(function(q){ if(!ok(q.fecha)) return;
        var k=q.p1>=q.p2?"1":"2", mj=q.cuota&&q.cuota.mejor&&q.cuota.mejor[k];
        out.push({dep:"tenis",comp:q.torneo,fecha:q.fecha,a:q.j1,b:q.j2,pick:k==="1"?q.j1:q.j2,prob:Math.max(q.p1,q.p2),
          c:mj?mj.c:null,casa:mj?mj.casa:null,url:"tenis.html"}); });
      lgs.forEach(function(lg,i){ var d=r[3+i]; if(!d) return; var dep=LG_DEP[lg];
        (d.predicciones||[]).forEach(function(e){ if(!ok(e.fecha)) return;
          var k=e.pl>=e.pv?"L":"V", mj=e.cuota&&e.cuota.mejor&&e.cuota.mejor[k];
          out.push({dep:dep,comp:d.liga||lg.toUpperCase(),fecha:e.fecha,a:e.local,b:e.visitante,pick:k==="L"?e.local:e.visitante,
            prob:Math.max(e.pl,e.pv),c:mj?mj.c:null,casa:mj?mj.casa:null,url:"equipos.html?dep="+dep+"&liga="+lg}); }); });
      PK=out; pintarLados();
    });
  }
  function cuando(iso,t,lang){ var d=new Date(iso), hoy=new Date(), man=new Date(Date.now()+86400000);
    var h=d.toLocaleTimeString(lang==="es"?"es-ES":"en-GB",{hour:"2-digit",minute:"2-digit"});
    if(d.toDateString()===hoy.toDateString()) return t.today+" "+h;
    if(d.toDateString()===man.toDateString()) return t.tomorrow+" "+h;
    return d.toLocaleDateString(lang==="es"?"es-ES":"en-GB",{weekday:"short",day:"numeric"})+" "+h; }
  function pintarPicks(l,t){
    if(!PK){ l.innerHTML='<h3>'+t.picks+'</h3><div class="se-empty">…</div>'; return; }
    var dep=DEPS[ultimo.act]?ultimo.act:null, cnt={}, sel=[];
    var orden=PK.slice().sort(function(a,b){ return b.prob-a.prob; });
    if(dep) orden=orden.filter(function(x){return x.dep===dep;}).concat(orden.filter(function(x){return x.dep!==dep;}));
    orden.forEach(function(x){ var lim=(dep&&x.dep===dep)?6:2; cnt[x.dep]=(cnt[x.dep]||0)+1; if(cnt[x.dep]<=lim&&sel.length<12) sel.push(x); });
    if(!sel.length){ l.innerHTML='<h3>'+t.picks+'</h3><div class="se-empty">'+t.nopicks+'</div>'; return; }
    l.innerHTML='<h3>'+t.picks+'</h3>'+sel.map(function(x){
      var nom=x.pick==="X"?t.draw:x.pick;
      return '<a class="se-pk" href="'+esc(x.url)+'"><div class="se-ps">'+(ICO[x.dep]||"")+' '+esc(x.comp||"")+' · '+esc(cuando(x.fecha,t,ultimo.lang))+'</div>'
        +'<div class="se-pm">'+esc(x.a)+' – '+esc(x.b)+'</div>'
        +'<div class="se-pp"><span>'+t.pick+': <strong>'+esc(nom)+'</strong></span><b>'+Math.round(x.prob*100)+'%</b></div>'
        +'<div class="se-pbar"><i style="width:'+Math.round(x.prob*100)+'%"></i></div>'
        +(x.c?'<div class="se-pc">'+t.odds+' '+String(x.c.toFixed(2)).replace(".",ultimo.lang==="es"?",":".")+(x.casa?' '+t.at+' '+esc(x.casa):'')+'</div>':'')+'</a>';
    }).join("")+'<a class="se-pk" style="border-left-color:var(--blue);text-align:center;font-weight:700;font-size:13px" href="index.html">'+t.allpicks+'</a>';
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
    if(activo!=="guia"){ montarLados(); cargarNoticias(); if(activo!=="home") cargarPicks(); pintarLados(); }
  };
})();
