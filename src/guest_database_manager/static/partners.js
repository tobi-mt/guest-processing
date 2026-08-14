(() => {
  const $ = (selector) => document.querySelector(selector);
  const csrf = () => (document.cookie.split(';').map((v) => v.trim()).find((v) => v.startsWith('dashboard_csrf=')) || '').split('=').slice(1).join('=');
  const escape = (value) => String(value || '').replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  async function request(url, options = {}) {
    const response = await fetch(url, {...options, headers: {'Content-Type':'application/json','X-CSRF-Token':csrf(), ...(options.headers || {})}});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Request failed');
    return payload;
  }
  async function load() {
    const [data, suggestionData] = await Promise.all([request('/api/partners'), request('/api/partners/suggestions')]);
    $('#suggestions').innerHTML = suggestionData.suggestions.map((item, index) => `<article class="card"><h3>${escape(item.organisation_name)}</h3><p>${escape(item.research_summary)}</p><p>${item.evidence.length} public sources retained on import.</p><button class="secondary-button" type="button" data-import="${index}">Import for review</button></article>`).join('') || '<p>No current suggestions.</p>';
    $('#prospects').innerHTML = data.prospects.length ? data.prospects.map((item) => `<article class="card"><h3>${escape(item.organisation_name)}</h3><p>${escape(item.partner_type)} · ${escape(item.status)} · Fit ${escape(item.fit_score)}/100</p><p>${escape(item.research_summary) || 'No research summary yet.'}</p><p>${item.evidence.length} evidence source(s); ${item.drafts.length} draft(s).</p></article>`).join('') : '<p>No prospects yet.</p>';
  }
  $('#suggestions').addEventListener('click', async (event) => { const button = event.target.closest('[data-import]'); if (!button) return; try { button.disabled = true; await request(`/api/partners/suggestions/${button.dataset.import}/import`, {method:'POST', body:'{}'}); $('#message').textContent = 'Suggestion imported for review.'; await load(); } catch (error) { $('#message').textContent = error.message; button.disabled = false; } });
  $('#prospect-form').addEventListener('submit', async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); try { await request('/api/partners', {method:'POST', body:JSON.stringify(Object.fromEntries(form))}); $('#message').textContent = 'Research record created.'; event.currentTarget.reset(); await load(); } catch (error) { $('#message').textContent = error.message; } });
  load().catch((error) => { $('#suggestions').textContent = `Could not load research suggestions: ${error.message}`; $('#prospects').textContent = `Could not load prospects: ${error.message}`; });
})();
