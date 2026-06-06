// ========== 认知作弊情报系统 v5 多用户版 ==========
// 功能：分类日报 + 原文链接 + AI小助手 + 一键导出知识库 + 多用户支持

let pollTimer = null;
let currentNoteItemId = null;
let aiChatHistory = [];

// ========== API 请求包装（401 自动跳转登录页）==========
async function apiFetch(url, options = {}) {
    const resp = await fetch(url, options);
    if (resp.status === 401) {
        window.location.href = '/login';
        throw new Error('Unauthorized');
    }
    return resp;
}

// ========== 加载用户信息 ==========
async function loadUserInfo() {
    try {
        const resp = await apiFetch('/api/user/info');
        const data = await resp.json();
        if (data.ok && data.user) {
            document.getElementById('sidebarUser').textContent = data.user.display_name || data.user.username;
        }
    } catch (e) {}
}

// ========== 页面切换 ==========
function switchPage(name) {
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.page').forEach(el => el.classList.remove('active'));
    document.querySelector(`[data-page="${name}"]`).classList.add('active');
    document.getElementById(`page-${name}`).classList.add('active');
    
    if (name === 'dashboard') refreshDashboard();
    if (name === 'reports') loadHistory();
    if (name === 'knowledge') searchKnowledge();
    if (name === 'settings') loadSettings();
}

// ========== Toast ==========
function showToast(msg, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.className = `toast ${type} show`;
    setTimeout(() => toast.classList.remove('show'), 3000);
}

// ========== 仪表盘 ==========
async function refreshDashboard() {
    try {
        const resp = await apiFetch('/api/status');
        const data = await resp.json();
        
        const status = data.scrape_status;
        document.getElementById('lastRun').textContent = 
            status.last_run ? `上次抓取: ${status.last_run}` : '尚未执行抓取';
        
        if (data.latest_data) {
            const cats = data.latest_data.stats.categories || {};
            document.getElementById('todayStats').innerHTML = `
                <div class="stat-card"><span class="stat-num">${data.latest_data.stats.total || 0}</span><span class="stat-label">总条数</span></div>
                <div class="stat-card"><span class="stat-num">${cats['🤖 AI/技术'] || 0}</span><span class="stat-label">🤖 AI/技术</span></div>
                <div class="stat-card"><span class="stat-num">${cats['💼 商业/创业'] || 0}</span><span class="stat-label">💼 商业/创业</span></div>
                <div class="stat-card"><span class="stat-num">${cats['🏛️ 政策/宏观'] || 0}</span><span class="stat-label">🏛️ 政策/宏观</span></div>
                <div class="stat-card"><span class="stat-num">${cats['💰 投资/财报'] || 0}</span><span class="stat-label">💰 投资/财报</span></div>
                <div class="stat-card"><span class="stat-num">${cats['🛒 消费/市场'] || 0}</span><span class="stat-label">🛒 消费/市场</span></div>
            `;
        }
        
        const kb = data.kb_stats || {};
        document.getElementById('kbOverview').innerHTML = `
            <div class="stat-card"><span class="stat-num">${kb.total || 0}</span><span class="stat-label">知识总量</span></div>
            <div class="stat-card"><span class="stat-num">${kb.favorites || 0}</span><span class="stat-label">⭐ 已收藏</span></div>
            <div class="stat-card"><span class="stat-num">${kb.with_notes || 0}</span><span class="stat-label">📝 有笔记</span></div>
        `;
        
        if (data.latest_data) renderCategoryPreview(data.latest_data);
        if (status.running) { showProgress(status.progress); startPolling(); }
    } catch (e) { console.error(e); }
}

function renderCategoryPreview(data) {
    const cats = data.categories || {};
    let html = '';
    
    const allItems = Object.values(cats).flat();
    const topItems = allItems.filter(i => i.priority === 'high' || (i.tags && i.tags.length >= 3)).slice(0, 3);
    
    if (topItems.length > 0) {
        html += '<div style="background:rgba(124,92,252,0.1);padding:16px;border-radius:8px;margin-bottom:16px;">';
        html += '<h3 style="margin:0 0 8px;color:#9b7fff;">💡 今天这3条最重要</h3>';
        topItems.forEach((item, idx) => {
            html += `<div style="margin:8px 0;padding:8px;background:rgba(0,0,0,0.2);border-radius:6px;">`;
            html += `<p style="margin:0;font-size:14px;">${idx+1}. <strong>${item.title.substring(0,80)}</strong></p>`;
            html += `<p style="margin:4px 0;font-size:13px;color:#888;">${(item.ai_summary || '').substring(0,120)}</p>`;
            if (item.url) html += `<a href="${item.url}" target="_blank" style="font-size:12px;color:#7c5cfc;">📎 查看原文 →</a>`;
            html += `</div>`;
        });
        html += '</div>';
    }
    
    const catOrder = ['🏛️ 政策/宏观', '🤖 AI/技术', '💼 商业/创业', '💰 投资/财报', '🛒 消费/市场', '🌍 其他'];
    
    for (const cat of catOrder) {
        const items = cats[cat];
        if (!items || items.length === 0) continue;
        
        html += `<h3 style="margin:20px 0 10px;color:#7c5cfc;border-bottom:1px solid #2a2a3a;padding-bottom:6px;">${cat}（${items.length}条）</h3>`;
        
        items.slice(0, 8).forEach((item, idx) => {
            const priorityMark = item.priority === 'high' ? '🔴' : '';
            const tagsHtml = (item.tags || []).slice(0, 3).map(t => `<span class="kb-badge kb-badge-tag">${t}</span>`).join(' ');
            
            html += `
                <div class="report-item" style="margin:10px 0;padding:12px 14px;background:rgba(255,255,255,0.02);border:1px solid #2a2a3a;border-radius:8px;transition:border-color 0.2s;">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
                        <div style="flex:1;">
                            <p style="font-weight:600;font-size:14px;margin:0 0 6px;">${priorityMark} ${idx+1}. ${item.title.substring(0,100)}</p>
                            <p style="font-size:13px;color:#888;margin:0 0 6px;">💬 ${(item.ai_summary || '').substring(0,150)}</p>
                            <p style="font-size:12px;color:#666;margin:0;">${tagsHtml} · ${item.source || ''}</p>
                        </div>
                        <div style="display:flex;flex-direction:column;gap:4px;flex-shrink:0;">
                            ${item.url ? `<a href="${item.url}" target="_blank" class="btn btn-sm btn-primary" style="text-decoration:none;">📎 原文</a>` : ''}
                            <button class="btn btn-sm btn-secondary" onclick="saveToKB('${escapeHtml(item.title)}', '${escapeHtml(item.ai_summary || '')}', '${escapeHtml(item.url || '')}', '${escapeHtml(item.source || '')}', '${escapeHtml(cat)}', ${JSON.stringify(item.tags || []).replace(/"/g, '&quot;')})" style="white-space:nowrap;">💾 保存</button>
                            <button class="btn btn-sm btn-secondary" onclick="askAIAbout('${escapeHtml(item.title)}', '${escapeHtml(item.ai_summary || '')}')" style="white-space:nowrap;">🤖 问问AI</button>
                        </div>
                    </div>
                </div>
            `;
        });
    }
    
    document.getElementById('reportPreview').innerHTML = html || '<div class="empty-state">点击「立即抓取」获取今日情报</div>';
    
    // 给report-item加hover效果
    document.querySelectorAll('.report-item').forEach(el => {
        el.addEventListener('mouseenter', () => el.style.borderColor = '#7c5cfc');
        el.addEventListener('mouseleave', () => el.style.borderColor = '#2a2a3a');
    });
}

// ========== 原文链接：保存到知识库 ==========
async function saveToKB(title, summary, url, source, category, tags) {
    try {
        const resp = await apiFetch('/api/kb/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title, ai_summary: summary, url, source, category, tags, priority: 'normal'})
        });
        const data = await resp.json();
        if (data.ok) {
            showToast('已保存到知识库 ✅', 'success');
        } else {
            showToast('保存失败', 'error');
        }
    } catch (e) {
        showToast('保存失败', 'error');
    }
}

// ========== AI小助手：打开侧边栏提问 ==========
function askAIAbout(title, summary) {
    const panel = document.getElementById('aiPanel');
    const input = document.getElementById('aiInput');
    panel.style.display = 'flex';
    
    // 预填上下文
    const ctx = `我想了解这条消息：\n\n标题：${title}\n摘要：${summary}\n\n`;
    input.value = ctx + '请帮我解释一下这条消息在说什么，有什么值得关注的点？';
    input.focus();
    
    // 滚动到输入框
    document.getElementById('aiMessages').scrollTop = document.getElementById('aiMessages').scrollHeight;
}

// ========== AI小助手聊天 ==========
async function sendAIMessage() {
    const input = document.getElementById('aiInput');
    const messages = document.getElementById('aiMessages');
    const question = input.value.trim();
    if (!question) return;
    
    // 显示用户消息
    messages.innerHTML += `<div class="ai-msg ai-msg-user">👤 ${escapeHtml(question)}</div>`;
    input.value = '';
    messages.innerHTML += `<div class="ai-msg ai-msg-bot"><span class="ai-thinking">🤖 思考中...</span></div>`;
    messages.scrollTop = messages.scrollHeight;
    
    try {
        const resp = await apiFetch('/api/ai/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({question, history: aiChatHistory.slice(-6)})
        });
        const data = await resp.json();
        
        // 移除思考中
        const thinkingEl = messages.querySelector('.ai-thinking');
        if (thinkingEl) thinkingEl.parentElement.remove();
        
        if (data.ok) {
            messages.innerHTML += `<div class="ai-msg ai-msg-bot">🤖 ${formatAIResponse(data.answer)}</div>`;
            aiChatHistory.push({role: 'user', content: question}, {role: 'assistant', content: data.answer});
        } else {
            messages.innerHTML += `<div class="ai-msg ai-msg-bot error">🤖 ${data.answer || '抱歉，暂时无法回答。'}</div>`;
        }
    } catch (e) {
        const thinkingEl = messages.querySelector('.ai-thinking');
        if (thinkingEl) thinkingEl.parentElement.remove();
        messages.innerHTML += `<div class="ai-msg ai-msg-bot error">🤖 网络错误，请重试。</div>`;
    }
    messages.scrollTop = messages.scrollHeight;
}

function formatAIResponse(text) {
    return text
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>')
        .replace(/^- (.+)$/gm, '• $1');
}

function toggleAIPanel() {
    const panel = document.getElementById('aiPanel');
    panel.style.display = panel.style.display === 'flex' ? 'none' : 'flex';
}

function closeAIPanel() {
    document.getElementById('aiPanel').style.display = 'none';
}

// ========== 抓取 ==========
async function triggerScrape(sendEmail) {
    const btn = document.getElementById('btnScrape');
    const btnMail = document.getElementById('btnScrapeMail');
    btn.disabled = true;
    btnMail.disabled = true;
    
    try {
        const resp = await apiFetch('/api/scrape', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({send_email: sendEmail})
        });
        const data = await resp.json();
        
        if (data.ok) {
            showToast('抓取任务已启动！', 'success');
            showProgress('启动中...');
            startPolling();
        } else {
            showToast(data.message, 'error');
            btn.disabled = false;
            btnMail.disabled = false;
        }
    } catch (e) {
        showToast('启动失败: ' + e.message, 'error');
        btn.disabled = false;
        btnMail.disabled = false;
    }
}

function showProgress(text) {
    document.getElementById('progressCard').style.display = 'block';
    document.getElementById('progressText').textContent = text;
    document.getElementById('progressBar').style.width = '30%';
}

function hideProgress() {
    document.getElementById('progressCard').style.display = 'none';
    document.getElementById('progressBar').style.width = '0%';
}

function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
        try {
            const resp = await apiFetch('/api/status');
            const data = await resp.json();
            const status = data.scrape_status;
            document.getElementById('progressText').textContent = status.progress || '';
            const bar = document.getElementById('progressBar');
            bar.style.width = (parseFloat(bar.style.width) + 5) + '%';
            if (parseFloat(bar.style.width) > 90) bar.style.width = '90%';
            
            if (!status.running) {
                clearInterval(pollTimer); pollTimer = null; hideProgress();
                document.getElementById('btnScrape').disabled = false;
                document.getElementById('btnScrapeMail').disabled = false;
                showToast(status.progress || '抓取完成！', status.progress && status.progress.includes('错误') ? 'error' : 'success');
                refreshDashboard();
            }
        } catch (e) { clearInterval(pollTimer); pollTimer = null; hideProgress(); }
    }, 2000);
}

// ========== 历史日报 ==========
async function loadHistory() {
    try {
        const resp = await apiFetch('/api/history');
        const data = await resp.json();
        const list = document.getElementById('historyList');
        
        if (!data.history || data.history.length === 0) {
            list.innerHTML = '<div class="empty-state">暂无历史日报</div>';
            return;
        }
        
        list.innerHTML = data.history.map(h => {
            const cats = h.stats?.categories || {};
            const catSummary = Object.entries(cats).map(([k,v]) => `${k.replace(/[^\u4e00-\u9fa5]/g,'')}${v}`).join(' ');
            return `
                <div class="history-item" onclick="loadReport('${h.date}')">
                    <span class="history-date">📄 ${h.date}</span>
                    <span class="history-meta">${catSummary} | ${formatSize(h.size)}</span>
                </div>
            `;
        }).join('');
    } catch (e) { console.error(e); }
}

async function loadReport(dateStr) {
    try {
        const resp = await apiFetch(`/api/report/${dateStr}`);
        const data = await resp.json();
        if (data.ok) {
            document.getElementById('reportDetailCard').style.display = 'block';
            document.getElementById('reportDetailTitle').textContent = `📄 ${dateStr} 情报日报`;
            document.getElementById('reportDetailContent').innerHTML = renderMarkdown(data.content);
            document.getElementById('reportDetailCard').scrollIntoView({behavior: 'smooth'});
        }
    } catch (e) { showToast('加载失败', 'error'); }
}

// ========== 知识库 ==========
async function searchKnowledge() {
    const query = document.getElementById('kbSearch').value;
    const category = document.getElementById('kbCategoryFilter').value;
    const favorite = document.getElementById('kbFavOnly').checked ? '1' : '0';
    
    try {
        const resp = await apiFetch(`/api/kb/search?q=${encodeURIComponent(query)}&category=${encodeURIComponent(category)}&favorite=${favorite}&limit=50`);
        const data = await resp.json();
        const list = document.getElementById('kbList');
        
        if (!data.items || data.items.length === 0) {
            list.innerHTML = '<div class="empty-state">📭 知识库还是空的，先执行一次抓取吧！</div>';
            return;
        }
        
        list.innerHTML = data.items.map(item => {
            const tagsHtml = (item.tags || []).map(t => `<span class="kb-badge kb-badge-tag">${t}</span>`).join(' ');
            const favClass = item.favorite ? 'active' : '';
            const favIcon = item.favorite ? '⭐' : '☆';
            
            return `
                <div class="kb-item">
                    <div class="kb-item-header">
                        <div class="kb-item-title">
                            ${item.url ? `<a href="${item.url}" target="_blank" style="color:var(--accent);text-decoration:none;">${item.title}</a>` : item.title}
                        </div>
                        <div class="kb-item-actions">
                            ${item.url ? `<a href="${item.url}" target="_blank" class="btn-icon" title="查看原文">🔗</a>` : ''}
                            <button class="btn-icon ${favClass}" onclick="toggleFavorite('${item.id}')" title="收藏">${favIcon}</button>
                            <button class="btn-icon" onclick="openNoteModal('${item.id}')" title="笔记">📝</button>
                            <button class="btn-icon" onclick="askAIAboutItem('${item.id}')" title="问AI">🤖</button>
                        </div>
                    </div>
                    ${item.ai_summary ? `<div class="kb-item-summary">💬 ${item.ai_summary}</div>` : ''}
                    <div class="kb-item-meta">
                        <span class="kb-badge kb-badge-cat">${item.category || '未分类'}</span>
                        <span class="kb-badge kb-badge-src">${item.source || ''}</span>
                        ${tagsHtml}
                    </div>
                    ${item.notes ? `<div class="kb-item-note">📝 ${item.notes}</div>` : ''}
                </div>
            `;
        }).join('');
    } catch (e) { console.error(e); }
}

async function askAIAboutItem(itemId) {
    try {
        const resp = await apiFetch(`/api/kb/search?q=&limit=1000`);
        const data = await resp.json();
        const item = (data.items || []).find(i => i.id === itemId);
        if (item) {
            askAIAbout(item.title, item.ai_summary || '');
        }
    } catch (e) { showToast('获取失败', 'error'); }
}

async function toggleFavorite(itemId) {
    try {
        const resp = await apiFetch(`/api/kb/favorite/${itemId}`, {method: 'POST'});
        const data = await resp.json();
        if (data.ok) { searchKnowledge(); showToast('已更新', 'success'); }
    } catch (e) { showToast('操作失败', 'error'); }
}

function openNoteModal(itemId) {
    currentNoteItemId = itemId;
    apiFetch(`/api/kb/search?q=&limit=1000`).then(r => r.json()).then(data => {
        const item = (data.items || []).find(i => i.id === itemId);
        document.getElementById('noteText').value = item?.notes || '';
        document.getElementById('noteModal').style.display = 'flex';
    });
}

function closeNoteModal() {
    document.getElementById('noteModal').style.display = 'none';
    currentNoteItemId = null;
}

async function saveNote() {
    if (!currentNoteItemId) return;
    const note = document.getElementById('noteText').value;
    try {
        const resp = await apiFetch(`/api/kb/note/${currentNoteItemId}`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({note})
        });
        const data = await resp.json();
        if (data.ok) { closeNoteModal(); searchKnowledge(); showToast('笔记已保存', 'success'); }
    } catch (e) { showToast('保存失败', 'error'); }
}

async function exportKnowledge(format) {
    try {
        const resp = await apiFetch('/api/kb/export', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({format})
        });
        const data = await resp.json();
        if (data.ok) {
            showToast(`已导出: ${data.filename}`, 'success');
            window.open(`/api/reports/${data.filename}`, '_blank');
        }
    } catch (e) { showToast('导出失败', 'error'); }
}

// ========== 设置 ==========
async function loadSettings() {
    try {
        const resp = await apiFetch('/api/config');
        const cfg = await resp.json();
        document.querySelectorAll('#sourceCheckboxes input').forEach(cb => { cb.checked = cfg.sources.includes(cb.value); });
        document.getElementById('scheduleEnabled').checked = cfg.schedule?.enabled !== false;
        document.getElementById('scheduleTime').value = `${String(cfg.schedule?.hour || 8).padStart(2,'0')}:${String(cfg.schedule?.minute || 0).padStart(2,'0')}`;
        document.getElementById('emailEnabled').checked = cfg.email?.enabled || false;
        document.getElementById('smtpHost').value = cfg.email?.smtp_host || 'smtp.qq.com';
        document.getElementById('smtpPort').value = cfg.email?.smtp_port || 587;
        document.getElementById('senderEmail').value = cfg.email?.sender || '';
        document.getElementById('emailPassword').value = cfg.email?.password || '';
        document.getElementById('recipients').value = (cfg.email?.recipients || []).join(', ');
        document.getElementById('wechatEnabled').checked = cfg.wechat?.enabled || false;
        document.getElementById('wechatWebhook').value = cfg.wechat?.webhook_url || '';
        toggleEmailConfig();
        toggleWechatConfig();
    } catch (e) {}
}

function toggleEmailConfig() {
    const enabled = document.getElementById('emailEnabled').checked;
    const group = document.getElementById('emailConfigGroup');
    group.style.opacity = enabled ? '1' : '0.4';
    group.style.pointerEvents = enabled ? 'auto' : 'none';
}

function toggleWechatConfig() {
    const enabled = document.getElementById('wechatEnabled').checked;
    const group = document.getElementById('wechatConfigGroup');
    group.style.opacity = enabled ? '1' : '0.4';
    group.style.pointerEvents = enabled ? 'auto' : 'none';
}

async function testWechat() {
    const webhook = document.getElementById('wechatWebhook').value.trim();
    if (!webhook) { showToast('请先输入Webhook地址', 'error'); return; }
    
    try {
        const resp = await apiFetch('/api/wechat/test', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({webhook_url: webhook})
        });
        const data = await resp.json();
        showToast(data.message, data.ok ? 'success' : 'error');
    } catch (e) { showToast('测试失败', 'error'); }
}

async function pushWechatNow() {
    try {
        const resp = await apiFetch('/api/wechat/push', {method: 'POST'});
        const data = await resp.json();
        if (data.ok) {
            showToast(`推送成功！发送${data.sent}条，失败${data.failed}条`, 'success');
        } else {
            showToast(data.message || '推送失败', 'error');
        }
    } catch (e) { showToast('推送失败', 'error'); }
}

async function saveSettings() {
    const cfg = {
        sources: Array.from(document.querySelectorAll('#sourceCheckboxes input:checked')).map(cb => cb.value),
        schedule: { enabled: document.getElementById('scheduleEnabled').checked, hour: parseInt(document.getElementById('scheduleTime').value.split(':')[0]), minute: parseInt(document.getElementById('scheduleTime').value.split(':')[1]) },
        email: { enabled: document.getElementById('emailEnabled').checked, smtp_host: document.getElementById('smtpHost').value, smtp_port: parseInt(document.getElementById('smtpPort').value) || 587, sender: document.getElementById('senderEmail').value, password: document.getElementById('emailPassword').value, recipients: document.getElementById('recipients').value.split(',').map(s => s.trim()).filter(Boolean) },
        wechat: { enabled: document.getElementById('wechatEnabled').checked, webhook_url: document.getElementById('wechatWebhook').value.trim() }
    };
    try {
        const resp = await apiFetch('/api/config', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(cfg) });
        const data = await resp.json();
        if (data.ok) { showToast('设置已保存', 'success'); document.getElementById('saveStatus').textContent = '✅ 已保存'; setTimeout(() => document.getElementById('saveStatus').textContent = '', 3000); }
    } catch (e) { showToast('保存失败', 'error'); }
}

// ========== Markdown渲染 ==========
function renderMarkdown(md) {
    let html = md;
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank" style="color:#7c5cfc;">$1</a>');
    html = html.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
    html = html.replace(/^---$/gm, '<hr>');
    html = html.replace(/`(.+?)`/g, '<code>$1</code>');
    html = html.replace(/\n/g, '<br>');
    return html;
}

function formatSize(bytes) {
    if (!bytes) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

// ========== 键盘快捷键 ==========
document.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && document.activeElement === document.getElementById('aiInput')) {
        e.preventDefault();
        sendAIMessage();
    }
});

// ========== 初始化 ==========
document.addEventListener('DOMContentLoaded', () => {
    loadUserInfo();
    refreshDashboard();
    document.getElementById('emailEnabled')?.addEventListener('change', toggleEmailConfig);
    setInterval(refreshDashboard, 30000);
});
