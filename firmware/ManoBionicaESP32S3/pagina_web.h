// Panel web de control de la mano (servido por la ESP32-S3 en http://mano.local)
#pragma once

const char PAGINA_WEB[] PROGMEM = R"HTML(<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mano Biónica</title>
<style>
:root{--bg:#0f1119;--panel:#181b26;--borde:#2a2f40;--txt:#e6e8ef;--sub:#9aa0b4;--acento:#00e0b0;--aviso:#ffb020}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,sans-serif;background:var(--bg);color:var(--txt)}
main{max-width:720px;margin:auto;padding:16px}h1{font-size:1.3rem;margin:4px 0 12px;color:var(--acento)}
h2{font-size:1rem;margin:0 0 10px;color:var(--sub);font-weight:600}
section{background:var(--panel);border:1px solid var(--borde);border-radius:10px;padding:14px;margin-bottom:14px}
.estado{display:flex;gap:14px;flex-wrap:wrap;font-size:.9rem;color:var(--sub)}.estado b{color:var(--txt)}
.dedo{display:grid;grid-template-columns:80px 1fr 46px;align-items:center;gap:10px;margin:10px 0}
.barra{height:6px;background:var(--borde);border-radius:3px;margin-top:4px;overflow:hidden}
.barra i{display:block;height:100%;background:var(--acento);width:0}
input[type=range]{width:100%;accent-color:var(--acento)}
.botones{display:flex;flex-wrap:wrap;gap:8px}
button{background:#232838;color:var(--txt);border:1px solid var(--borde);border-radius:8px;padding:9px 12px;font-size:.9rem;cursor:pointer}
button:hover{border-color:var(--acento)}button.aviso{border-color:var(--aviso);color:var(--aviso)}
table{width:100%;border-collapse:collapse;font-size:.85rem}td{padding:4px}
td input{width:64px;background:#0b0d14;color:var(--txt);border:1px solid var(--borde);border-radius:6px;padding:5px}
#log{font-family:monospace;font-size:.8rem;color:var(--sub);white-space:pre-wrap;min-height:1.2em}
</style></head><body><main>
<h1>Mano Biónica · ESP32-S3</h1>
<section><div class="estado">
<span>Modo: <b id="modo">-</b></span><span>Fuente: <b id="fuente">-</b></span><span>PCA9685: <b id="pca">-</b></span>
</div></section>

<section><h2>Dedos (% abierto)</h2><div id="dedos"></div>
<div class="dedo"><span>Velocidad</span><input type="range" id="vel" min="1" max="100"
 onchange="cmd('SPEED '+this.value)"><span id="velv"></span></div></section>

<section><h2>Gestos</h2><div class="botones" id="gestos"></div><br>
<div class="botones"><button onclick="cmd('OPEN')">Abrir</button><button onclick="cmd('CLOSE')">Cerrar</button>
<button onclick="cmd('DEMO')">Demo</button><button onclick="cmd('STOP')">Parar</button>
<button class="aviso" onclick="cmd('RELAX')">Relajar servos</button></div></section>

<section><h2>Calibración (ticks PCA9685, 100-600)</h2>
<table id="cal"></table><br>
<div class="botones"><button onclick="cmd('SAVE')">Guardar en la ESP32</button>
<button onclick="cmd('LOAD')">Recargar</button><button class="aviso" onclick="cmd('DEFAULTS')">Valores por defecto</button></div>
<p style="color:var(--sub);font-size:.8rem">"Probar" mueve el servo al pulso escrito. Ajusta hasta que el dedo
quede totalmente abierto / cerrado sin forzar el hilo, pulsa "Aplicar" y luego "Guardar".</p></section>
<div id="log"></div>
</main><script>
let iniciado=false,arrastrando=-1;
const $=id=>document.getElementById(id);
async function cmd(c){const r=await fetch('/api/cmd?c='+encodeURIComponent(c));$('log').textContent=await r.text();refrescar();}
function construir(e){
 $('dedos').innerHTML=e.dedos.map((d,i)=>`<div class="dedo"><span>${d.n}</span><div>
 <input type="range" min="0" max="100" id="s${i}" onpointerdown="arrastrando=${i}" onpointerup="arrastrando=-1"
 oninput="fetch('/api/cmd?c='+encodeURIComponent('SET ${i} '+this.value))">
 <div class="barra"><i id="b${i}"></i></div></div><span id="v${i}"></span></div>`).join('');
 $('gestos').innerHTML=e.gestos.map(g=>`<button onclick="cmd('GESTO ${g}')">${g}</button>`).join('');
 $('cal').innerHTML='<tr><td></td><td>Abierto</td><td></td><td>Cerrado</td><td></td><td></td></tr>'+
 e.dedos.map((d,i)=>`<tr><td>${d.n}</td><td><input id="a${i}" type="number" value="${d.a}"></td>
 <td><button onclick="cmd('PULSO ${i} '+$('a${i}').value)">Probar</button></td>
 <td><input id="c${i}" type="number" value="${d.c}"></td>
 <td><button onclick="cmd('PULSO ${i} '+$('c${i}').value)">Probar</button></td>
 <td><button onclick="cmd('CAL ${i} '+$('a${i}').value+' '+$('c${i}').value)">Aplicar</button></td></tr>`).join('');
 iniciado=true;}
async function refrescar(){try{const e=await (await fetch('/api/estado')).json();
 if(!iniciado)construir(e);
 $('modo').textContent=e.modo;$('fuente').textContent=e.fuente;$('pca').textContent=e.pca?'OK':'NO DETECTADO';
 $('velv').textContent=e.vel+'%';if(document.activeElement!==$('vel'))$('vel').value=e.vel;
 e.dedos.forEach((d,i)=>{$('b'+i).style.width=d.pos+'%';$('v'+i).textContent=d.pos+'%';
  if(arrastrando!==i)$('s'+i).value=d.obj;
  const a=$('a'+i),c=$('c'+i);if(document.activeElement!==a)a.value=d.a;if(document.activeElement!==c)c.value=d.c;});
}catch(err){$('modo').textContent='sin conexión';}}
refrescar();setInterval(refrescar,400);
</script></body></html>)HTML";
