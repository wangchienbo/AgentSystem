
const API='/api/novel';
let cid=null,novelData=null,sidebarOpen=true,sessionUuid=null;
// 分页状态
let chatTotal=0, chatOffset=0; const CHAT_PAGE=50;

function $(id){return document.getElementById(id.startsWith('#')?id.slice(1):id)}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

function dbg(msg){
  var ts=new Date().toISOString().slice(11,19);
  fetch('/debug-log?msg='+encodeURIComponent(msg)+'&ts='+encodeURIComponent(ts));
  console.log('['+ts+'] '+msg);
}

async function api(path,body){
  try{
    const r=await fetch(API+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
    return await r.json();
  }catch(e){return {error:e.message}}
}

// === View switching ===
function showView(id){
  // Toggle CSS classes for consistency with other code
  document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id==id));
  // Also directly set style for reliability (QQ browser workaround)
  var views=document.querySelectorAll('.view');
  for(var i=0;i<views.length;i++){
    var v=views[i];
    if(v.id===id){
      v.style.display='flex';
    }else{
      v.style.display='none';
    }
  }
}

async function loadNovels(){
  const d=await api('/list');const grid=$('novel-grid');
  dbg('loadNovels: '+(d.novels?d.novels.length+' novels':'no novels'));
  if(!d.novels||!d.novels.length){grid.innerHTML='<div style="color:#666;grid-column:1/-1;text-align:center;padding:60px">还没有小说，点击右上角开始创作</div>';return}
  grid.innerHTML=d.novels.map(n=>`
    <div class="card" data-id="${esc(n.id)}" onclick="cardTap(event,'${esc(n.id)}')">
      <h3>${esc(n.title||'未命名')}</h3>
      <div class="cm"><span>📖 ${esc(n.genre||'未分类')}</span><span>👥 ${n.char_count||0}</span><span>📄 ${n.chapter_count||0}章</span></div>
      <div class="cm" style="margin-top:6px;color:#555">${esc(n.status||'草稿')} · ${(n.created_at||'').slice(0,10)}</div>
      <div class="card-desc" style="margin-top:6px;font-size:12px;color:#777;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical">${esc((n.description||'').slice(0,120))}</div>
    </div>
  `).join('')
  dbg('cards rendered');
}

function cardTap(ev,id){
  dbg('cardTap: '+id);
  // Show loading overlay immediately (use direct style, most reliable)
  var ol=$('loading-overlay');
  $('loading-text').textContent='加载小说...';
  ol.style.display='flex';
  // Visual feedback on card
  var card=ev.currentTarget;
  card.style.transition='background .15s';
  card.style.background='#e8f0fe';
  setTimeout(function(){card.style.background=''},200);
  // Navigate
  enterNovel(id);
}

function enterNovel(id){
  dbg('enterNovel: '+id);
  cid=id;showView('workspace');
  $('chat-msgs').innerHTML='<div class="empty"><div class="icon">⏳</div><p>加载小说数据...</p></div>';
  $('chat-input').disabled=true;$('send-btn').disabled=true;$('gen-btn').disabled=true;
  // Auto-collapse sidebar on mobile
  if(window.innerWidth<768){sidebarOpen=false;document.getElementById('sidebar').classList.add('collapsed')}
  loadNovelData(id);
}

async function loadNovelData(id){
  dbg('loadNovelData start');
  const d=await api('/get',{novel_id:id});
  if(!d.success||!d.novel){$('chat-msgs').innerHTML='<div class="empty"><div class="icon">❌</div><p>加载失败: 未找到该小说</p></div>';$('loading-overlay').style.display='none';dbg('loadNovelData FAIL: '+id);return}
  novelData=d.novel;
  $('tb-title').textContent=novelData.title||'未命名';
  $('tb-genre').textContent=novelData.genre||'';
  $('tb-desc').textContent=novelData.description||'';
  $('tb-desc').style.display=novelData.description?'':'none';
  buildSidebar();
  // Load chat history from ContextCenter
  $('chat-msgs').innerHTML='<div class="empty"><div class="icon">⏳</div><p>加载聊天记录...</p></div>';
  $('chat-input').disabled=true;$('send-btn').disabled=true;$('gen-btn').disabled=true;
  await loadChatHistory(id);
  // If chat history was loaded, the welcome message is already replaced
  var msgs=$('chat-msgs');
  if(msgs.children.length===0 || msgs.querySelector('.empty')){
    // No history — show welcome
    msgs.innerHTML=`<div class="empty"><div class="icon">📖</div><p>开始创作《${esc(novelData.title||'')}》<br>输入指令或选择快捷操作</p><div class="q-btns"><button class="q-btn" onclick="quick('帮我把故事大纲写好')">生成大纲</button><button class="q-btn" onclick="quick('写下一章')">写下一章</button><button class="q-btn" onclick="quick('列出所有角色和他们的关系')">查看角色</button></div></div>`;
  }
  $('chat-input').disabled=false;$('send-btn').disabled=false;$('gen-btn').disabled=false;
  // Load session list
  loadSessions(id);
  // Hide loading overlay
  $('loading-overlay').style.display='none';
  dbg('loadNovelData DONE: '+id);
}

async function loadChatHistory(id,append){
  dbg('loadChatHistory: '+id+(append?' (append)':''));
  const d=await api('/chat/history',{novel_id:id,session_uuid:sessionUuid,limit:CHAT_PAGE,offset:append?chatOffset:0});
  if(!d.success){
    dbg('loadChatHistory FAIL: '+(d.error||'unknown'));
    return;
  }
  if(d.session_uuid) sessionUuid=d.session_uuid;
  chatTotal=d.total||0;
  if(!append) chatOffset=Math.min(chatTotal,CHAT_PAGE);
  else chatOffset+= (d.records||[]).length;
  const msgs=$('chat-msgs');
  if(!append) msgs.innerHTML='';
  // 保留 load more button wrapper
  var lw=$('load-more-wrap');
  if(lw) lw.remove();
  if(d.records&&d.records.length){
    for(const r of d.records){
      const roleLabel=r.role==='user'?'user':'ai';
      var content=esc(r.content||'');
      msgs.innerHTML+=`<div class="msg ${roleLabel}">${content}</div>`;
    }
  }
  // 追加 load more button
  var remaining=chatTotal-chatOffset;
  if(remaining>0){
    var wrap=document.createElement('div');
    wrap.id='load-more-wrap';
    wrap.style.cssText='text-align:center;padding:8px 0;flex-shrink:0';
    wrap.innerHTML='<button onclick="loadMoreHistory()" style="background:none;border:1px solid #ddd;border-radius:16px;padding:6px 16px;font-size:12px;color:#888;cursor:pointer">加载更多消息 ('+remaining+' 条) ↺</button>';
    msgs.insertBefore(wrap,msgs.firstChild);
  }
  _scrollToBottom(msgs);
  dbg('loadChatHistory DONE: total='+chatTotal+' offset='+chatOffset);
}

function loadMoreHistory(){
  loadChatHistory(cid,true);
}

function editDescription(){
  if(!novelData) return;
  const d=prompt('编辑小说简介（面向读者）：', novelData.description||'');
  if(d===null) return; // cancelled
  fetch('/api/asset/call', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({asset_id:'asset:novel_studio:v1', method:'save_description', params:{novel_id:novelData.id, description:d}})
  }).then(res=>res.json()).then(result=>{
    if(result.success||result.ok){
      novelData.description=d;
      $('tb-desc').textContent=d;
      $('tb-desc').style.display=d?'':'none';
    }else{
      alert('保存失败');
    }
  }).catch(()=>alert('保存失败'));
}

function buildSidebar(){
  const s=$('sidebar');
  const nd=novelData;
  if(!nd){s.innerHTML='<div class="sidebar-section"><h3>📚 章节</h3><div class="empty-hint">暂无数据</div></div>';return}
  
  let html='';
  // === Chapters ===
  html+='<div class="sidebar-section"><h3>📚 章节</h3>';
  const chs=nd.chapters||[];
  html+=`<div class="tree-item" onclick="addChapter()" style="color:#1a73e8;font-size:12px">  ➕ 新建章节</div>`;
  if(chs.length){
    chs.forEach((ch,i)=>{
      const t=esc(ch.title||'第'+(i+1)+'章');
      const cid=ch.id||'';
      html+=`<div class="tree-item chapter" data-idx="${i}">
        <span class="dot" onclick="showDetail('chapter',${i})"></span>
        <span class="ch-title" onclick="showDetail('chapter',${i})">${t}</span>
        <span class="ch-actions">
          <button onclick="event.stopPropagation();deleteChapter('${cid}',${ch.number})" class="ch-btn" title="删除章节">✕</button>
        </span>
      </div>`;
      // scenes from outline
      const oc=nd.outline&&nd.outline.chapters&&nd.outline.chapters[i];
      if(oc&&oc.key_events&&oc.key_events.length){
        (oc.key_events||[]).forEach((ev,evi)=>html+=`<div class="tree-item sub" style="padding-left:28px" onclick="showDetail('event','${i}:${evi}')">  🎬 ${esc(ev)}</div>`);
      }
    });
  }else{
    html+='<div class="empty-hint">暂无章节</div>';
  }
  html+='</div>';

  // === Characters ===
  html+='<div class="sidebar-section"><h3>👥 角色</h3>';
  const rawChars=nd.characters||{};
  const chars=Array.isArray(rawChars)?rawChars:Object.values(rawChars);
  if(chars.length){
    chars.forEach((ch,i)=>{
      const name=typeof ch==='string'?ch:(ch.name||ch.role||'角色'+(i+1));
      const role=typeof ch==='string'?'':(ch.role||ch.archetype?'('+esc(ch.role||ch.archetype||'')+')':'');
      html+=`<div class="tree-item sub" onclick="showDetail('character',${i})">  👤 ${esc(name)}${role}</div>`;
    });
  }else{
    html+='<div class="empty-hint">暂无角色</div>';
  }
  html+=`<div class="tree-item" onclick="addCharacter()" style="color:#1a73e8;font-size:12px">  ➕ 添加角色</div>`;
  html+='</div>';

  // === World ===
  html+='<div class="sidebar-section"><h3>🌍 世界观</h3>';
  const w=nd.world||{};
  if(w.name||w.overview){
    html+=`<div class="tree-item sub" onclick="showDetail('world',0)">  🌏 ${esc(w.name||'世界')}</div>`;
    const scenes=w.scenes||{};
    const sceneEntries=typeof scenes==='object'&&!Array.isArray(scenes)?Object.entries(scenes):Array.isArray(scenes)?scenes.map((s,i)=>[i,s]):[];
    if(sceneEntries.length){
      sceneEntries.slice(0,5).forEach(([sk,sc])=>{
        html+=`<div class="tree-item sub" style="padding-left:28px" onclick="showDetail('scene','${esc(sk)}')">  🏞️ ${esc(sc.title||sc.name||String(sk).slice(0,8))}</div>`;
      });
    }
  }else{
    html+='<div class="empty-hint">暂无世界观设定</div>';
  }
  html+=`<div class="tree-item" onclick="addScene()" style="color:#1a73e8;font-size:12px">  ➕ 添加场景</div>`;
  html+='</div>';

  s.innerHTML=html;
}

function buildSubSection(label,arr){
  if(!arr||!arr.length) return '';
  let html='<div class="sidebar-section"><h3>'+label+'</h3>';
  arr.forEach((item,i)=>{
    const name=typeof item==='string'?item:(item.name||item.role||'项'+(i+1));
    html+=`<div class="tree-item sub"">  👤 ${esc(name)}</div>`;
  });
  return html+'</div>';
}

function toggleSidebar(){
  sidebarOpen=!sidebarOpen;
  document.getElementById('sidebar').classList.toggle('collapsed',!sidebarOpen);
}

function showDetail(type,idx){
  if(!novelData) return;
  const dt=$('detail-title');const db=$('detail-body');const da=$('detail-actions');
  let title='',body='';
  if(type==='chapter'){
    const ch=(novelData.chapters||[])[idx];
    if(!ch){title='章节未找到';body='';}
    else{
      title=ch.title||'第'+(idx+1)+'章';
      body='📄 **'+title+'**\n\n'+(ch.content||'（内容待生成）');
      if(ch.word_count) body+='\n\n_字数：'+ch.word_count+'_';
      if(ch.status) body+='\n_状态：'+ch.status+'_';
      // Action buttons
      da.innerHTML=`
        <button class="detail-btn edit" onclick="editChapter('${ch.id||''}',${ch.number},'${esc(ch.title||'')}')">✏️ 编辑</button>
        <button class="detail-btn delete" onclick="deleteChapter('${ch.id||''}',${ch.number})">🗑️ 删除</button>
      `;
    }
    }else if(type==='character'){
    const rawChars=novelData.characters||{};
    const chars=Array.isArray(rawChars)?rawChars:Object.values(rawChars);
    const ch=chars[idx];
    if(!ch){title='角色未找到';body='';}
    else{
      if(typeof ch==='string'){title=ch;body='角色：'+ch;}
      else{title=ch.name||ch.role||'角色';
        body='角色信息：\n';
        if(ch.name)body+='名称：'+ch.name+'\n';
        if(ch.role)body+='角色：'+ch.role+'\n';
        if(ch.archetype)body+='类型：'+ch.archetype+'\n';
        if(ch.description||ch.desc)body+='描述：'+(ch.description||ch.desc)+'\n';
        if(ch.personality||ch.traits)body+='特点：'+(Array.isArray(ch.personality||ch.traits)?(ch.personality||ch.traits).join('、'):(ch.personality||ch.traits));
        if(ch.background)body+='\n背景：'+ch.background;}
    }
    da.innerHTML=`
      <button class="detail-btn edit" onclick="editCharacter('${esc(ch.id||'')}')">✏️ 编辑</button>
      <button class="detail-btn delete" onclick="deleteCharacter('${esc(ch.id||'')}')">🗑️ 删除</button>
    `;
  }else if(type==='world'){
    const w=novelData.world||{};
    title=w.name||'世界观';
    body='🌍 '+title+'\n\n';
    if(w.overview)body+='概述：'+w.overview+'\n\n';
    if(w.rules&&w.rules.length)body+='规则：\n'+w.rules.map(r=>'• '+r).join('\n');
    if(w.scenes){
      const ks=Object.keys(w.scenes);
      if(ks.length){body+='\n\n场景：\n';ks.forEach(k=>{const s=w.scenes[k];body+='• '+(s.title||s.name||k.slice(0,8))+'\n';});}
    }
    da.innerHTML=`
      <button class="detail-btn edit" onclick="editWorld()">✏️ 编辑</button>
    `;
  }else if(type==='scene'){
    const scenes=novelData.world&&novelData.world.scenes||{};
    const sc=typeof scenes==='object'&&!Array.isArray(scenes)?scenes[idx]:null;
    if(sc){title=sc.title||sc.name||'场景';body=JSON.stringify(sc,null,2);}
    else{title='场景未找到';body='';}
    da.innerHTML=`
      <button class="detail-btn edit" onclick="editScene('${esc(sc&&sc.id||idx)}')">✏️ 编辑</button>
      <button class="detail-btn delete" onclick="deleteScene('${esc(sc&&sc.id||idx)}')">🗑️ 删除</button>
    `;
  }else if(type==='event'){
    const parts=idx.split(':');
    const ci=parseInt(parts[0]),ei=parseInt(parts[1]);
    const oc=novelData.outline&&novelData.outline.chapters&&novelData.outline.chapters[ci];
    const ev=oc&&oc.key_events&&oc.key_events[ei];
    if(ev){title='关键事件';body=ev;}
    else{title='事件未找到';body='';}
    da.innerHTML='';
  }
  dt.textContent=title;
  db.textContent=body;
  $('chat-area').style.display='none';
  $('detail-view').classList.add('active');
}

function hideDetail(){
  $('detail-view').classList.remove('active');
  $('chat-area').style.display='flex';
  if(!_isStreaming){
    $('chat-input').disabled=false;$('send-btn').disabled=false;$('gen-btn').disabled=false;
  }
}

function showList(){
  hideDetail();novelData=null;
  showView('list-view');
}

function showCreate(){$('create-modal').classList.add('show');$('ctitle').focus()}
function hideCreate(){$('create-modal').classList.remove('show')}

async function createNovel(){
  const title=$('ctitle').value.trim();const genre=$('cgenre').value.trim();const outline=$('coutline').value.trim();const description=$('cdescription').value.trim();
  if(!title){alert('请输入作品名称');return}
  const d=await api('/create',{title,genre,logline:outline,description});
  if(d.success&&d.novel_id){
    hideCreate();
    $('ctitle').value='';$('cgenre').value='';$('coutline').value='';$('cdescription').value='';
    enterNovel(d.novel_id);
  }else{alert('创建失败: '+(d.error||'未知错误'))}
}

let _msgId=0;
let _scrollPending=false;
let _isStreaming=false;
function _scrollToBottom(el){
  if(_scrollPending)return;
  _scrollPending=true;
  try{el.scrollTo({top:el.scrollHeight,behavior:'smooth'})}catch(e){el.scrollTop=el.scrollHeight}
  setTimeout(()=>{_scrollPending=false},80);
}

// ──── 聊天任务轮询（缓冲模式，断开不丢进度） ────
let _chatPollTimer=null,_chatPollActive=false;

async function _pollChatTask(taskId,msgDiv,msgs){
  if(_chatPollActive)return;
  _chatPollActive=true;
  try{
    let taskStatus='pending',taskResult=null,taskError=null;
    let lastIdx=0;
    while(true){
      const resp=await fetch(`/api/novel/task/${taskId}?from_event=${lastIdx}`);
      if(!resp.ok)throw new Error('Poll HTTP '+resp.status);
      const data=await resp.json();
      if(!data.success)throw new Error(data.error||'unknown');
      taskStatus=data.status;
      // Show progress events if available
      const evts=data.events||[];
      for(let i=lastIdx;i<data.total_events;i++){
        const ev=evts[i-lastIdx];
        if(ev&&ev.type==='status'&&ev.text==='running'){
          msgDiv.innerHTML='⏳ 思考中...';
        }
        lastIdx=i+1;
      }
      if(taskStatus==='complete'){
        taskResult=data.result;
        if(taskResult&&taskResult.content){
          msgDiv.innerHTML=esc(taskResult.content);
          if(taskResult.chapter&&taskResult.chapter.number){
            var tag=document.createElement('span');tag.className='ch-tag';
            tag.textContent='📚 已保存为第'+taskResult.chapter.number+'章'+(taskResult.chapter.title?'「'+taskResult.chapter.title+'」':'');
            msgDiv.appendChild(tag);
            refreshSidebar();
          }
        }else{
          msgDiv.innerHTML='（模型暂无回复）';
        }
        break;
      }
      if(taskStatus==='error'){
        msgDiv.innerHTML='⚠️ '+esc(data.error||'任务失败');
        break;
      }
      await new Promise(r=>{_chatPollTimer=setTimeout(r,2000)});
    }
  }catch(e){
    msgDiv.innerHTML='⚠️ 请求失败: '+esc(e.message);
  }finally{
    _chatPollActive=false;
    _isStreaming=false;
    $('send-btn').disabled=false;$('gen-btn').disabled=false;
    const inp=$('chat-input');if(inp)inp.disabled=false;
    try{localStorage.removeItem('chat_task_'+cid)}catch(_){}
    _scrollToBottom(msgs);
  }
}

async function sendMsg(){
  const inp=$('chat-input');const text=inp.value.trim();
  if(!text||!cid)return;
  _isStreaming=true;
  inp.value='';$('send-btn').disabled=true;$('gen-btn').disabled=true;inp.disabled=true;
  const msgs=$('chat-msgs');
  msgs.innerHTML+=`<div class="msg user">${esc(text)}</div>`;
  // Create AI message bubble that will be filled when task completes
  const mid='stream-msg-'+(++_msgId);
  msgs.innerHTML+=`<div class="msg ai" id="${mid}"><span class="thinking">⏳ 启动中...</span></div>`;
  const msgDiv=document.getElementById(mid);
  _scrollToBottom(msgs);
  try{
    // Start background chat task (buffered: browser disconnect won't lose response)
    const resp=await fetch(API+'/chat/start',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({novel_id:cid,message:text,session_uuid:sessionUuid})
    });
    const data=await resp.json();
    if(!data.success)throw new Error(data.error||'启动失败');

    // Save task_id to localStorage for reconnection
    try{localStorage.setItem('chat_task_'+cid,data.task_id)}catch(_){}

    // Wait for existing pollTask to finish (chapter gen)
    // Then poll for chat task completion
    msgDiv.innerHTML='⏳ 思考中...';
    await _pollChatTask(data.task_id,msgDiv,msgs);
  }catch(e){
    msgDiv.innerHTML='⚠️ 请求失败: '+esc(e.message);
    _isStreaming=false;
    $('send-btn').disabled=false;$('gen-btn').disabled=false;inp.disabled=false;
    _scrollToBottom(msgs);
  }
}

// ──── Pipeline state & helpers (global, used by pollTask & genNextChapter) ────
const PIPELINE_STEP_DEFS=[
  {id:'world_check',icon:'🌍',name:'世界观检查'},
  {id:'world_design',icon:'🎨',name:'事件池设计'},
  {id:'world_evolve',icon:'🌊',name:'世界演化'},
  {id:'chapter_plan',icon:'📋',name:'章节规划'},
  {id:'scene_loop',icon:'🔄',name:'场景循环'},
  {id:'scene_sequence',icon:'🎬',name:'场景序列'},
  {id:'scene_build',icon:'🌍',name:'场景构建'},
  {id:'character_action',icon:'🎭',name:'角色行为'},
  {id:'narrative',icon:'✍️',name:'叙事合成'},
  {id:'setting_check',icon:'🔍',name:'设定检查'},
  {id:'editorial_review',icon:'📝',name:'质量审核'},
  {id:'memory_update',icon:'💾',name:'记忆更新'},
];
let _pollTimer=null,_pollActive=false,_lastEventIdx=0;

function _pipelineInitSteps(){
  const sc=$('pipe-steps'); if(!sc||sc.children.length>0)return;
  const pe=$('pipe-preparing'); if(pe)pe.style.display='none';
  sc.style.display='';
  PIPELINE_STEP_DEFS.forEach(s=>{
    const el=document.createElement('div');
    el.className='pipe-step waiting'; el.id='ps-'+s.id;
    el.innerHTML=`<span class="step-icon">⏸️</span><span class="step-name">${s.name}</span><span class="step-status">等待中</span>`;
    sc.appendChild(el);
  });
}
function _pipelineUpdateIcon(id,status,msg){
  _pipelineInitSteps();
  const el=document.getElementById('ps-'+id); if(!el)return;
  const icons={done:'✅',error:'❌',running:'⏳',waiting:'⏸️',regenerate:'🔄'};
  el.className='pipe-step '+status;
  const name=(PIPELINE_STEP_DEFS.find(s=>s.id==id)||{}).name||id;
  el.innerHTML=`<span class="step-icon">${icons[status]||'⏸️'}</span><span class="step-name">${name}</span><span class="step-status">${esc(msg||'')}</span>`;
  _scrollToBottom($('chat-msgs'));
}
function _pipelineAddCharCard(data){
  const ac=$('pipe-actions'); if(!ac)return;
  if(!ac.querySelector('.char-grid')){
    ac.innerHTML='<div style="font-weight:600;margin:8px 0 4px;font-size:13px">🎭 角色决策</div><div class="char-grid"></div>';
  }
  const grid=ac.querySelector('.char-grid'); if(!grid)return;
  const card=document.createElement('div'); card.className='pipe-char';
  const p=data.progress||{};
  card.innerHTML=`<div class="c-name">${esc(data.character||'')}</div>`+
    (data.action?`<div class="c-act">行动：${esc(data.action.slice(0,100))}</div>`:'')+
    (data.dialogue&&data.dialogue!=='沉默'?`<div class="c-diag">「${esc(data.dialogue.slice(0,80))}」</div>`:'')+
    (data.inner?`<div class="c-inner">（${esc(data.inner.slice(0,80))}）</div>`:'')+
    (p.done?`<div class="c-progress">${p.done}/${p.total}</div>`:'');
  grid.appendChild(card);
  _scrollToBottom($('chat-msgs'));
}
function _pipelineShowComplete(data){
  _pipelineInitSteps();
  _pipelineUpdateIcon('memory_update','done','记忆已保存');
  const ch=data.chapter_number||'?', title=data.title||'', content=data.content||'';
  const rc=$('pipe-result'); if(!rc)return;
  rc.innerHTML=`<div class="pipe-result"><div class="pr-title">✅ 第${ch}章「${esc(title)}」${data.word_count?`（${data.word_count}字）`:''}</div><div class="pr-preview">${esc(content.slice(0,500))}</div></div>`;
  setTimeout(refreshSidebar,500);
  _scrollToBottom($('chat-msgs'));
}
function _pipelineShowError(msg){
  _pipelineInitSteps();
  PIPELINE_STEP_DEFS.forEach(s=>_pipelineUpdateIcon(s.id,'error','失败'));
  const rc=$('pipe-result'); if(!rc)return;
  rc.innerHTML=`<div class="pipe-result" style="color:#e94560"><div class="pr-title">❌ 生成失败</div><div class="pr-preview">${esc(msg)}</div></div>`;
  _scrollToBottom($('chat-msgs'));
}
function _pipelineHandleEvent(data){
  switch(data.type){
    case 'step_waiting': _pipelineInitSteps(); break;
    case 'step_start': _pipelineInitSteps(); _pipelineUpdateIcon(data.module,'running',(data.description||'').replace(/^[^\s]+\s/,'')+'...'); break;
    case 'step_done': _pipelineInitSteps(); _pipelineUpdateIcon(data.module,'done',data.summary||'完成'); break;
    case 'step_regenerate': _pipelineInitSteps(); _pipelineUpdateIcon(data.module,'regenerate',data.summary||'重生成'); break;
    case 'character_done': _pipelineInitSteps(); _pipelineAddCharCard(data); break;
    case 'complete': _pipelineShowComplete(data); break;
    case 'error': _pipelineShowError(data.message); break;
  }
}

// ──── 后台任务轮询（缓冲模式，断开不丢进度） ────
async function pollTask(taskId){
  if(_pollActive)return;
  _pollActive=true;
  const inp=document.getElementById('chat-input');
  const pe=$('pipe-preparing'); if(pe)pe.style.display='';
  const sc=$('pipe-steps'); if(sc)sc.style.display='none'; sc.innerHTML='';
  const rc=$('pipe-result'); if(rc)rc.innerHTML='';
  const grid=document.querySelector('.char-grid'); if(grid)grid.innerHTML='';
  try{
    while(true){
      const resp=await fetch(`/api/novel/task/${taskId}?from_event=${_lastEventIdx}`);
      if(!resp.ok)throw new Error(`HTTP ${resp.status}`);
      const data=await resp.json();
      if(!data.success)throw new Error(data.error||'unknown');
      const evts=data.events||[];
      for(const ev of evts){
        try{_pipelineHandleEvent(ev)}catch(e){console.warn('[pipeline] event error',ev.type,e)}
        _lastEventIdx++;
      }
      if(data.status==='complete'){
        if(data.has_result&&data.result&&!evts.some(e=>e.type==='complete')){
          _pipelineHandleEvent({type:'complete',...data.result});
        }
        break;
      }
      if(data.status==='error'){
        _pipelineHandleEvent({type:'error',message:data.error||'管道执行失败'});
        break;
      }
      await new Promise(r=>{_pollTimer=setTimeout(r,2000)});
    }
  }catch(e){
    _pipelineShowError(e.message);
  }finally{
    _pollActive=false;
    if(inp)inp.disabled=false;
    const sb=$('send-btn'); if(sb)sb.disabled=false;
    const gb=$('gen-btn'); if(gb)gb.disabled=false;
    try{localStorage.removeItem('novel_task_'+cid)}catch(_){}
    _scrollToBottom($('chat-msgs'));
  }
}

// ──── 启动生成（点击按钮触发的入口） ────
async function genNextChapter(){
  if(!cid)return;
  const inp=$('chat-input');
  inp.disabled=true;$('send-btn').disabled=true;$('gen-btn').disabled=true;

  // Show pipeline progress message IMMEDIATELY with "preparing" state
  const pipeDiv=document.createElement('div');
  pipeDiv.className='msg ai';
  pipeDiv.id='pipeline-msg';
  pipeDiv.innerHTML='<div class="pipe-msg"><div style="font-weight:600;margin-bottom:8px">⚡ 多Agent管道生成下一章</div><div id="pipe-preparing" style="color:#888;font-size:13px;padding:8px 0">🚀 准备中，正在连接任务管道...</div><div id="pipe-steps" style="display:none"></div><div id="pipe-actions" style="margin-top:8px"></div><div id="pipe-result"></div></div>';
  $('chat-msgs').appendChild(pipeDiv);
  _scrollToBottom($('chat-msgs'));

  try{
    const resp=await fetch('/api/novel/generate/start',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({novel_id:cid,template:'write_next_chapter'}),
    });
    const data=await resp.json();
    if(!data.success)throw new Error(data.error||'启动失败');

    // 保存 task_id 到 localStorage（用于断线重连）
    try{localStorage.setItem('novel_task_'+cid,data.task_id)}catch(_){}

    // 开始轮询
    _lastEventIdx=0;
    pollTask(data.task_id);
  }catch(e){
    _pipelineShowError(e.message);
    inp.disabled=false;$('send-btn').disabled=false;$('gen-btn').disabled=false;
  }
}

// ──── 页面加载时检查未完成任务 ────
(async function checkPendingTask(){
  if(!cid)return;
  try{
    const saved=localStorage.getItem('novel_task_'+cid);
    if(!saved)return;
    const resp=await fetch(`/api/novel/task/${saved}?from_event=0`);
    if(!resp.ok){localStorage.removeItem('novel_task_'+cid);return;}
    const data=await resp.json();
    if(!data.success){localStorage.removeItem('novel_task_'+cid);return;}

    if(data.status==='complete'){
      // 任务已完成，直接显示结果
      if(data.has_result&&data.result){
        _lastEventIdx=0;
        _pipelineShowComplete(data.result);
        // 重新启用按钮
        const inp=document.getElementById('chat-input');
        if(inp)inp.disabled=false;
        const sb=$('send-btn'); if(sb)sb.disabled=false;
        const gb=$('gen-btn'); if(gb)gb.disabled=false;
      }
      localStorage.removeItem('novel_task_'+cid);
    }else if(data.status==='running'||data.status==='pending'){
      _lastEventIdx=0;
      const evts=data.events||[];
      for(const ev of evts){
        try{_pipelineHandleEvent(ev)}catch(e){}
        _lastEventIdx++;
      }
      pollTask(saved);
    }else if(data.status==='error'){
      localStorage.removeItem('novel_task_'+cid);
    }
  }catch(e){
    console.warn('checkPendingTask error:',e.message);
    try{localStorage.removeItem('novel_task_'+cid)}catch(_){}
  }
  // ── 检查未完成的聊天任务 ──
  try{
    const chatTask=localStorage.getItem('chat_task_'+cid);
    if(chatTask){
      const resp=await fetch(`/api/novel/task/${chatTask}?from_event=0`);
      if(resp.ok){
        const data=await resp.json();
        if(data.success&&data.status==='complete'){
          // Chat task already complete → ContextCenter already has it
          // Just clean up localStorage, loadChatHistory will show it
          localStorage.removeItem('chat_task_'+cid);
          // Try reloading chat history to get the new message
          await loadChatHistory(cid);
        }else if(data.success&&(data.status==='running'||data.status==='pending')){
          // Running chat task → resume polling
          const msgs=$('chat-msgs');
          const mid='stream-msg-'+(++_msgId);
          msgs.innerHTML+=`<div class="msg ai" id="${mid}"><span class="thinking">⏳ 重连中...</span></div>`;
          const msgDiv=document.getElementById(mid);
          _pollChatTask(chatTask,msgDiv,msgs);
        }else{
          localStorage.removeItem('chat_task_'+cid);
        }
      }else{
        localStorage.removeItem('chat_task_'+cid);
      }
    }
  }catch(e){
    console.warn('checkPendingChatTask error:',e.message);
    try{localStorage.removeItem('chat_task_'+cid)}catch(_){}
  }
})();

function quick(q){
  $('chat-input').value=q;
  sendMsg();
}

// ──── 会话管理 ────
async function loadSessions(novelId){
  if(!novelId)return;
  try{
    const d=await api('/sessions',{novel_id:novelId});
    if(d.success&&d.sessions){
      var current=d.sessions.find(s=>s.is_current);
      if(current) sessionUuid=current.session_uuid;
      buildSessionsPanel(d.sessions);
      buildSessionDropdown(d.sessions);
    }
  }catch(e){dbg('loadSessions error: '+e.message);}
}

function buildSessionsPanel(sessions){
  const s=$('sidebar');
  if(!s)return;
  // Remove old session section if exists
  var old=document.getElementById('session-section');
  if(old)old.remove();
  var div=document.createElement('div');
  div.id='session-section';
  div.className='sidebar-section';
  var html='<h3>💬 对话</h3>';
  var has=(sessions||[]);
  has.forEach(function(si){
    var cls='session-item'+(si.is_current?' current':'');
    html+='<div class="'+cls+'">'+
      '<span class="s-label" onclick="switchSession(\''+si.session_uuid+'\')">'+esc(si.label||si.session_uuid.slice(0,8))+'</span>'+
      '<button class="s-del" onclick="event.stopPropagation();deleteSession(\''+si.session_uuid+'\')" title="删除会话">✕</button>'+
    '</div>';
  });
  html+='<div class="session-add" onclick="newSession()">➕ 新建对话</div>';
  div.innerHTML=html;
  s.appendChild(div);
}

async function newSession(){
  if(!cid)return;
  dbg('newSession');
  const d=await api('/session/create',{novel_id:cid});
  if(d.success&&d.session_uuid){
    sessionUuid=d.session_uuid;
    // Switch to new session: clear chat, welcome message
    $('chat-msgs').innerHTML='<div class="empty"><div class="icon">💬</div><p>新对话，输入指令开始</p></div>';
    loadSessions(cid);
    // Re-enable inputs
    $('chat-input').disabled=false;$('send-btn').disabled=false;$('gen-btn').disabled=false;
    dbg('newSession OK: '+sessionUuid);
  }else{
    dbg('newSession FAIL: '+(d.error||''));
  }
}

async function switchSession(uuid){
  if(!cid||!uuid||uuid===sessionUuid)return;
  dbg('switchSession: '+uuid);
  const d=await api('/session/switch',{novel_id:cid,session_uuid:uuid});
  if(d.success){
    sessionUuid=uuid;
    // Reload chat history for this session
    $('chat-msgs').innerHTML='<div class="empty"><div class="icon">⏳</div><p>加载对话记录...</p></div>';
    $('chat-input').disabled=true;$('send-btn').disabled=true;$('gen-btn').disabled=true;
    await loadChatHistory(cid);
    var msgs=$('chat-msgs');
    if(msgs.children.length===0 || msgs.querySelector('.empty')){
      msgs.innerHTML=`<div class="empty"><div class="icon">💬</div><p>切换至另一个对话</p></div>`;
    }
    $('chat-input').disabled=false;$('send-btn').disabled=false;$('gen-btn').disabled=false;
    loadSessions(cid);
  }else{
    dbg('switchSession FAIL: '+(d.error||''));
  }
}

async function deleteSession(uuid){
  if(!cid||!uuid)return;
  if(!confirm('确定删除这个会话吗？'))return;
  dbg('deleteSession: '+uuid);
  const d=await api('/session/delete',{novel_id:cid,session_uuid:uuid});
  if(d.success){
    if(uuid===sessionUuid){
      sessionUuid=null;
      $('chat-msgs').innerHTML=`<div class="empty"><div class="icon">💬</div><p>对话已切换</p></div>`;
    }
    loadSessions(cid);
  }else{
    dbg('deleteSession FAIL: '+(d.error||''));
  }
}

// ──── Session dropdown ────
function toggleSessionDropdown(){
  const dd=document.getElementById('session-dropdown');
  if(!dd)return;
  dd.classList.toggle('show');
  const btn=document.getElementById('session-btn');
  if(btn)btn.classList.toggle('open');
}

function buildSessionDropdown(sessions){
  const dd=document.getElementById('session-dropdown');
  if(!dd)return;
  const current=(sessions||[]).find(s=>s.is_current);
  const lbl=document.getElementById('sess-current-label');
  if(lbl) lbl.textContent=current?(current.label||current.session_uuid.slice(0,8)):'对话';
  var html='<div class="sd-header"><span>💬 对话历史</span><span class="sd-new" onclick="newSession();toggleSessionDropdown()">➕ 新建</span></div>';
  (sessions||[]).forEach(function(si){
    var cls='sd-item'+(si.is_current?' current':'');
    var label=esc(si.label||si.session_uuid.slice(0,8));
    var msgs=si.message_count||'0';
    html+='<div class="'+cls+'" onclick="switchSession(\''+si.session_uuid+'\');toggleSessionDropdown()">'+
      '<span class="sd-label">'+label+'</span>'+
      '<span class="sd-msgs">'+msgs+'条</span>'+
      '<button class="sd-del" onclick="event.stopPropagation();deleteSession(\''+si.session_uuid+'\')">✕</button>'+
    '</div>';
  });
  if(!sessions||sessions.length===0){
    html+='<div style="padding:16px;text-align:center;color:#999;font-size:13px">暂无对话记录</div>';
  }
  dd.innerHTML=html;
}

// Close session dropdown on outside click
document.addEventListener('click',function(e){
  var wrap=document.getElementById('session-btn-wrap');
  var dd=document.getElementById('session-dropdown');
  if(wrap&&dd&&dd.classList.contains('show')&&!wrap.contains(e.target)){
    dd.classList.remove('show');
    var btn=document.getElementById('session-btn');
    if(btn)btn.classList.remove('open');
  }
});

// ──── Lightweight sidebar refresh (does NOT replace chat) ────
async function refreshSidebar(){
  if(!cid)return;
  try{
    const d=await api('/get',{novel_id:cid});
    if(d.success&&d.novel){
      novelData=d.novel;
      $('tb-title').textContent=novelData.title||'未命名';
      $('tb-genre').textContent=novelData.genre||'';
      $('tb-desc').textContent=novelData.description||'';
      $('tb-desc').style.display=novelData.description?'':'none';
      buildSidebar();
    }
  }catch(e){dbg('refreshSidebar error: '+e.message);}
}

// ====== Reader View ======
let readerCurrentIdx=0;
let readerTocOpen=true;

function openReader(){
  if(!novelData) return;
  hideDetail();
  showView('reader-view');
  // Auto-collapse TOC on mobile
  if(window.innerWidth<768){readerTocOpen=false;document.getElementById('reader-toc').classList.add('collapsed')}
  buildReaderToc();
  const chs=novelData.chapters||[];
  if(chs.length){loadChapter(0)}else{
    $('reader-title').textContent=novelData.title||'未命名';
    $('reader-subtitle').textContent='暂无章节';
    $('reader-content').innerHTML='<div class="rc-empty">📝 还没有章节，返回创作室开始写作吧</div>';
  }
  dbg('openReader: '+cid);
}

function closeReader(){
  showView('workspace');
  dbg('closeReader');
}

function buildReaderToc(){
  const chs=novelData&&novelData.chapters||[];
  const list=$('reader-toc-list');
  if(!chs.length){list.innerHTML='<div class="toc-empty">暂无章节</div>';return}
  list.innerHTML=chs.map((ch,i)=>{
    const num=i+1;
    const title=esc(ch.title||'第'+num+'章');
    const wc=ch.word_count?esc(String(ch.word_count)):'';
    const active= i===readerCurrentIdx?' active':'';
    return '<div class="toc-item'+active+'" onclick="loadChapter('+i+')">'+
      '<span class="toc-num">'+num+'</span>'+
      '<span class="toc-title-text">'+title+'</span>'+
      (wc?'<span class="toc-wc">'+wc+'字</span>':'')+
    '</div>';
  }).join('');
}

function loadChapter(idx){
  const chs=novelData&&novelData.chapters||[];
  if(idx<0||idx>=chs.length)return;
  readerCurrentIdx=idx;
  const ch=chs[idx];
  const num=idx+1;
  const title=ch.title||'第'+num+'章';
  
  // Update topbar
  $('reader-title').textContent=novelData.title||'未命名';
  $('reader-subtitle').textContent='第'+num+'章：'+title;
  
  // Update TOC active state
  document.querySelectorAll('#reader-toc .toc-item').forEach(el=>el.classList.remove('active'));
  const items=document.querySelectorAll('#reader-toc .toc-item');
  if(items[idx])items[idx].classList.add('active');
  
  // Build content
  const content=ch.content||'（内容待生成）';
  const wc=ch.word_count||'';
  const status=ch.status||'';
  const lines=content.split('\n').filter(l=>l.trim());
  const paragraphs=lines.map(l=>'<p>'+esc(l)+'</p>').join('');
  
  $('reader-content').innerHTML=
    '<div class="rc-header">'+
      '<div class="rc-title">第'+num+'章 '+esc(title)+'</div>'+
      '<div class="rc-meta">'+
        (wc?'<span>📝 '+wc+'字</span>':'')+
        (status?'<span>🏷️ '+esc(status)+'</span>':'')+
        '<span>📄 第'+num+'/'+chs.length+'章</span>'+
      '</div>'+
    '</div>'+
    '<div class="rc-body">'+
      (content?paragraphs:'<p>（内容待生成）</p>')+
    '</div>';
  
  // Update nav
  $('prev-ch-btn').disabled=(idx===0);
  $('next-ch-btn').disabled=(idx===chs.length-1);
  $('reader-progress').textContent=num+' / '+chs.length;
  
  // Scroll to top
  $('reader-content').scrollTop=0;
  
  dbg('loadChapter: '+idx+' ('+title+')');
}

function prevChapter(){
  loadChapter(readerCurrentIdx-1);
}

function nextChapter(){
  loadChapter(readerCurrentIdx+1);
}

function toggleReaderToc(){
  readerTocOpen=!readerTocOpen;
  document.getElementById('reader-toc').classList.toggle('collapsed',!readerTocOpen);
}

// ──── Chapter Management ────

async function deleteChapter(chapterId, chapterNumber){
  if(!chapterId && !chapterNumber) return;
  const msg = `确定删除第${chapterNumber}章吗？此操作不可撤销。`;
  if(!confirm(msg)) return;
  const d = await api('/chapter/delete', {
    novel_id: cid,
    chapter_number: chapterNumber
  });
  if(d.success){
    hideDetail();
    await refreshSidebar();
  } else {
    alert('删除失败：' + (d.error || '未知错误'));
  }
}

async function saveChapter(chapterId, chapterNumber){
  const title = $('edit-title').value.trim();
  const content = $('edit-content').value.trim();
  if(!title){alert('请输入章节标题');return}
  if(!content){alert('请输入章节内容');return}
  const d = await api('/chapter/update', {
    novel_id: cid,
    chapter_id: chapterId,
    title: title,
    content: content
  });
  if(d.success){
    hideDetail(); await refreshSidebar();
  } else {
    alert('保存失败');
  }
}

function cancelEdit(){
  // Re-show the detail of the current chapter
  const da=$('detail-actions');
  da.innerHTML='';
  // Find which chapter was being edited
  const chs=novelData.chapters||[];
  for(let i=0;i<chs.length;i++){
    const ch=chs[i];
    if(ch.id===lastEditedChapterId || ch.number===lastEditedChapterNumber){
      showDetail('chapter',i);
      return;
    }
  }
  hideDetail();
}

let lastEditedChapterId='';
let lastEditedChapterNumber=0;

function editChapter(chapterId, chapterNumber, currentTitle){
  lastEditedChapterId=chapterId;
  lastEditedChapterNumber=chapterNumber;
  const ch = (novelData.chapters||[]).find(c => c.id === chapterId || c.number === chapterNumber);
  if(!ch) return;
  const db=$('detail-body');
  const da=$('detail-actions');
  const dt=$('detail-title');
  dt.textContent = '编辑第'+chapterNumber+'章';
  da.innerHTML = `<button class="detail-btn" onclick="cancelEdit()">取消</button>
    <button class="detail-btn edit" onclick="saveChapter('${chapterId}',${chapterNumber})">💾 保存</button>`;
  db.innerHTML = `
    <div style="margin-bottom:8px">
      <label style="font-size:12px;color:#666">章节标题</label>
      <input id="edit-title" type="text" value="${esc(ch.title||'')}" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box">
    </div>
    <div style="margin-bottom:8px">
      <label style="font-size:12px;color:#666">章节内容</label>
      <textarea id="edit-content" style="width:100%;min-height:400px;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:14px;font-family:monospace;box-sizing:border-box;line-height:1.6">${esc(ch.content||'')}</textarea>
    </div>
  `;
}

// ──── Character / World / Scene Management ────

let editTargetType=''; let editTargetId='';

function editCharacter(charId){
  const rawChars=novelData.characters||{};
  const chars=Array.isArray(rawChars)?rawChars:Object.values(rawChars);
  const ch=chars.find(c=>c.id===charId);
  if(!ch){alert('角色未找到');return;}
  editTargetType='character'; editTargetId=charId;
  const dt=$('detail-title'); const db=$('detail-body'); const da=$('detail-actions');
  dt.textContent='编辑角色：'+esc(ch.name||'');
  da.innerHTML=`<button class="detail-btn" onclick="cancelEditItem()">取消</button>
    <button class="detail-btn edit" onclick="saveCurrentItem()">💾 保存</button>`;
  const pers = Array.isArray(ch.personality)?ch.personality.join('、'):(ch.personality||'');
  db.innerHTML=`
    <div><label style="font-size:12px;color:#666">名称</label>
    <input id="edit-field-name" type="text" value="${esc(ch.name||'')}" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">类型（英雄/女主角/反派/导师/配角）</label>
    <input id="edit-field-archetype" type="text" value="${esc(ch.archetype||'')}" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">性格特点（逗号分隔）</label>
    <input id="edit-field-personality" type="text" value="${esc(pers)}" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">说话风格</label>
    <input id="edit-field-speech_style" type="text" value="${esc(ch.speech_style||'')}" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">背景故事</label>
    <textarea id="edit-field-background" style="width:100%;min-height:80px;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:14px;font-family:inherit;box-sizing:border-box;line-height:1.6">${esc(ch.background||'')}</textarea></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">目标</label>
    <input id="edit-field-goal" type="text" value="${esc(ch.goal||'')}" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">缺陷</label>
    <input id="edit-field-flaw" type="text" value="${esc(ch.flaw||'')}" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>`;
}

function editWorld(){
  const w=novelData.world||{};
  editTargetType='world'; editTargetId='';
  const dt=$('detail-title'); const db=$('detail-body'); const da=$('detail-actions');
  dt.textContent='编辑世界观';
  da.innerHTML=`<button class="detail-btn" onclick="cancelEditItem()">取消</button>
    <button class="detail-btn edit" onclick="saveCurrentItem()">💾 保存</button>`;
  const rules=Array.isArray(w.rules)?w.rules.join('\n'):'';
  db.innerHTML=`
    <div><label style="font-size:12px;color:#666">世界名称</label>
    <input id="edit-field-world_name" type="text" value="${esc(w.name||'')}" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">概述</label>
    <textarea id="edit-field-overview" style="width:100%;min-height:60px;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:14px;font-family:inherit;box-sizing:border-box;line-height:1.6">${esc(w.overview||'')}</textarea></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">世界规则（每行一条）</label>
    <textarea id="edit-field-rules" style="width:100%;min-height:60px;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:14px;font-family:inherit;box-sizing:border-box;line-height:1.6">${esc(rules)}</textarea></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">魔法/超自然体系</label>
    <input id="edit-field-magic_system" type="text" value="${esc(w.magic_system||'')}" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">历史背景</label>
    <textarea id="edit-field-history" style="width:100%;min-height:50px;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:14px;font-family:inherit;box-sizing:border-box;line-height:1.6">${esc(w.history||'')}</textarea></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">地理</label>
    <textarea id="edit-field-geography" style="width:100%;min-height:50px;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:14px;font-family:inherit;box-sizing:border-box;line-height:1.6">${esc(w.geography||'')}</textarea></div>`;
}

function editScene(sceneId){
  const scenes=novelData.world&&novelData.world.scenes||{};
  const sc=scenes[sceneId];
  if(!sc){alert('场景未找到');return;}
  editTargetType='scene'; editTargetId=sceneId;
  const dt=$('detail-title'); const db=$('detail-body'); const da=$('detail-actions');
  dt.textContent='编辑场景：'+esc(sc.name||'');
  da.innerHTML=`<button class="detail-btn" onclick="cancelEditItem()">取消</button>
    <button class="detail-btn edit" onclick="saveCurrentItem()">💾 保存</button>`;
  db.innerHTML=`
    <div><label style="font-size:12px;color:#666">场景名称</label>
    <input id="edit-field-name" type="text" value="${esc(sc.name||'')}" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">地点</label>
    <input id="edit-field-location" type="text" value="${esc(sc.location||'')}" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">描述</label>
    <textarea id="edit-field-description" style="width:100%;min-height:80px;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:14px;font-family:inherit;box-sizing:border-box;line-height:1.6">${esc(sc.description||'')}</textarea></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">时代/时间</label>
    <input id="edit-field-time_period" type="text" value="${esc(sc.time_period||'')}" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">天气</label>
    <input id="edit-field-weather" type="text" value="${esc(sc.weather||'')}" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>`;
}

function cancelEditItem(){
  if(editTargetType==='character'){showDetail('character',0);}
  else if(editTargetType==='world'){showDetail('world',0);}
  else if(editTargetType==='scene'){const scenes=novelData.world&&novelData.world.scenes||{}; const keys=Object.keys(scenes); const i=keys.indexOf(editTargetId); showDetail('scene',i>=0?i:0);}
  editTargetType=''; editTargetId='';
}

async function saveCurrentItem(){
  const t=editTargetType; const id=editTargetId;
  if(!t) return;
  let d;
  if(t==='character'){
    const personality=$('edit-field-personality').value.split(/[,，]/).map(s=>s.trim()).filter(Boolean);
    d=await api('/character/update',{
      novel_id:cid, char_id:id,
      name:$('edit-field-name').value.trim(),
      archetype:$('edit-field-archetype').value.trim(),
      personality:personality,
      speech_style:$('edit-field-speech_style').value.trim(),
      background:$('edit-field-background').value.trim(),
      goal:$('edit-field-goal').value.trim(),
      flaw:$('edit-field-flaw').value.trim(),
    });
  }else if(t==='world'){
    const rules=$('edit-field-rules').value.split('\n').map(s=>s.trim()).filter(Boolean);
    d=await api('/world/save',{
      novel_id:cid,
      name:$('edit-field-world_name').value.trim(),
      overview:$('edit-field-overview').value.trim(),
      rules:rules,
      magic_system:$('edit-field-magic_system').value.trim(),
      history:$('edit-field-history').value.trim(),
      geography:$('edit-field-geography').value.trim(),
    });
  }else if(t==='scene'){
    d=await api('/scene/update',{
      novel_id:cid, scene_id:id,
      name:$('edit-field-name').value.trim(),
      location:$('edit-field-location').value.trim(),
      description:$('edit-field-description').value.trim(),
      time_period:$('edit-field-time_period').value.trim(),
      weather:$('edit-field-weather').value.trim(),
    });
  }
  if(d&&d.success){
    await refreshSidebar();
  }else{
    alert('保存失败：'+(d&&d.error||'未知错误'));
  }
  editTargetType=''; editTargetId='';
}

// ──── Inline Add Functions ────

function addChapter(){
  if(!cid) return;
  editTargetType='add_chapter'; editTargetId='';
  const dt=$('detail-title'); const db=$('detail-body'); const da=$('detail-actions');
  dt.textContent='新建章节';
  da.innerHTML=`<button class="detail-btn" onclick="cancelAddItem()">取消</button>
    <button class="detail-btn edit" onclick="saveAddItem()">💾 创建</button>`;
  db.innerHTML=`
    <div><label style="font-size:12px;color:#666">章节标题</label>
    <input id="add-field-title" type="text" value="" placeholder="输入章节标题" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">章节内容（可选）</label>
    <textarea id="add-field-content" style="width:100%;min-height:300px;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:14px;font-family:monospace;box-sizing:border-box;line-height:1.6" placeholder="输入章节内容，留空则创建空白章节"></textarea></div>`;
  $('chat-area').style.display='none';
  $('detail-view').classList.add('active');
}

function addCharacter(){
  if(!cid) return;
  editTargetType='add_character'; editTargetId='';
  const dt=$('detail-title'); const db=$('detail-body'); const da=$('detail-actions');
  dt.textContent='添加角色';
  da.innerHTML=`<button class="detail-btn" onclick="cancelAddItem()">取消</button>
    <button class="detail-btn edit" onclick="saveAddItem()">💾 创建</button>`;
  db.innerHTML=`
    <div><label style="font-size:12px;color:#666">名称</label>
    <input id="add-field-name" type="text" value="" placeholder="角色名称" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">类型（英雄/女主角/反派/导师/配角）</label>
    <input id="add-field-archetype" type="text" value="配角" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">性格特点（逗号分隔）</label>
    <input id="add-field-personality" type="text" value="" placeholder="勇敢，智慧，幽默" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">说话风格</label>
    <input id="add-field-speech_style" type="text" value="" placeholder="温和/直率/讽刺..." style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">背景故事</label>
    <textarea id="add-field-background" style="width:100%;min-height:60px;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:14px;font-family:inherit;box-sizing:border-box;line-height:1.6" placeholder="角色背景故事..."></textarea></div>`;
  $('chat-area').style.display='none';
  $('detail-view').classList.add('active');
}

function addScene(){
  if(!cid) return;
  editTargetType='add_scene'; editTargetId='';
  const dt=$('detail-title'); const db=$('detail-body'); const da=$('detail-actions');
  dt.textContent='添加场景';
  da.innerHTML=`<button class="detail-btn" onclick="cancelAddItem()">取消</button>
    <button class="detail-btn edit" onclick="saveAddItem()">💾 创建</button>`;
  db.innerHTML=`
    <div><label style="font-size:12px;color:#666">场景名称</label>
    <input id="add-field-name" type="text" value="" placeholder="场景名称" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">地点</label>
    <input id="add-field-location" type="text" value="" placeholder="地点" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">描述</label>
    <textarea id="add-field-description" style="width:100%;min-height:80px;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:14px;font-family:inherit;box-sizing:border-box;line-height:1.6" placeholder="场景描述..."></textarea></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">时代/时间</label>
    <input id="add-field-time_period" type="text" value="" placeholder="如：明朝、未来2077年" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>
    <div style="margin-top:8px"><label style="font-size:12px;color:#666">天气</label>
    <input id="add-field-weather" type="text" value="" placeholder="如：晴、雨、雪" style="width:100%;padding:6px 8px;border:1px solid #ddd;border-radius:6px;font-size:14px;box-sizing:border-box"></div>`;
  $('chat-area').style.display='none';
  $('detail-view').classList.add('active');
}

function cancelAddItem(){
  editTargetType=''; editTargetId='';
  hideDetail();
}

async function saveAddItem(){
  const t=editTargetType; if(!t||!cid)return;
  let d;
  if(t==='add_chapter'){
    const title=$('add-field-title').value.trim()||'新章节';
    const content=$('add-field-content').value.trim();
    d=await api('/chapter/add',{novel_id:cid,title:title,content:content});
  }else if(t==='add_character'){
    const personality=$('add-field-personality').value.split(/[,，]/).map(s=>s.trim()).filter(Boolean);
    d=await api('/character/add',{
      novel_id:cid,
      name:$('add-field-name').value.trim()||'新角色',
      archetype:$('add-field-archetype').value.trim()||'配角',
      personality:personality,
      speech_style:$('add-field-speech_style').value.trim(),
      background:$('add-field-background').value.trim(),
    });
  }else if(t==='add_scene'){
    d=await api('/scene/add',{
      novel_id:cid,
      name:$('add-field-name').value.trim()||'新场景',
      location:$('add-field-location').value.trim(),
      description:$('add-field-description').value.trim(),
      time_period:$('add-field-time_period').value.trim(),
      weather:$('add-field-weather').value.trim(),
    });
  }
  if(d&&d.success){
    editTargetType=''; editTargetId='';
    await refreshSidebar();
    hideDetail();
  }else{
    alert('创建失败：'+(d&&d.error||'未知错误'));
  }
}

async function deleteCharacter(charId){
  if(!confirm('确定删除该角色吗？'))return;
  const d=await api('/character/delete',{novel_id:cid,char_id:charId});
  if(d.success){hideDetail();await refreshSidebar();}
  else{alert('删除失败：'+(d.error||'未知错误'));}
}

async function deleteScene(sceneId){
  if(!confirm('确定删除该场景吗？'))return;
  const d=await api('/scene/delete',{novel_id:cid,scene_id:sceneId});
  if(d.success){hideDetail();await refreshSidebar();}
  else{alert('删除失败：'+(d.error||'未知错误'));}
}

// Key bindings
document.addEventListener('keydown',e=>{
  if(e.key==='Enter'&&!e.shiftKey&&e.target.id==='chat-input'){e.preventDefault();sendMsg()}
  if(e.key==='Enter'&&$('create-modal').classList.contains('show')&&e.target.id!=='coutline'){e.preventDefault();createNovel()}
});

// ── Auth ──────────────────────────────────────────────────────
let _currentUser = null;

function showLogin(msg, isError){
  $('#loginScreen').style.display='flex';
  $('#chatMain').style.display='none';
  const lm=$('#loginMsg');
  lm.className=isError?'loginMsg-error':'loginMsg-info';
  lm.textContent=msg||'输入任意用户名即可进入';
}
function showApp(){
  $('#loginScreen').style.display='none';
  $('#chatMain').style.display='flex';
}

async function doLogin(){
  const u=$('#loginUser').value.trim();
  if(!u){showLogin('请输入用户名',true);return;}
  const btn=$('#loginBtn'); btn.disabled=true; btn.textContent='登录中...';
  showLogin('登录中...');
  try{
    const resp=await fetch('/login',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username:u}),
    });
    const d=await resp.json();
    if(d.success){
      _currentUser=d.username;
      showApp();
      loadNovels();
      // Try to restore last selected novel from URL hash or localStorage
      const savedCid=localStorage.getItem('last_novel_id');
      if(savedCid) refreshSidebar();
    }else{
      showLogin('登录失败: '+(d.error||'未知错误'),true);
    }
  }catch(e){
    showLogin('网络错误: '+e.message,true);
  }finally{
    const btn=$('#loginBtn'); btn.disabled=false; btn.textContent='进入工作室';
  }
}
$('#loginBtn').onclick=doLogin;
$('#loginUser').onkeydown=e=>{if(e.key==='Enter')doLogin()};

// Check existing session on page load
(async function checkSession(){
  try{
    const resp=await fetch('/api/novel/list',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:'{}',
    });
    if(resp.ok){
      const d=await resp.json();
      if(d.success){
        showApp();
        loadNovels();
        return;
      }
    }
  }catch(_){}
  showLogin();
})();
