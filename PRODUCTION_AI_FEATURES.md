# 🚀 AI Features Now Available in Production Dashboard!

## ✨ What's New

Your production dashboard at `https://guest-processing-production.up.railway.app/` now has **5 powerful AI features** integrated!

Since your `OPENAI_API_KEY` is already set in Railway, these features are **ready to use immediately** after deployment.

---

## 📡 New API Endpoints

### 1. **AI Status Check**
```
GET /api/ai/status
```

**Returns:**
```json
{
  "available": true,
  "configured": true,
  "model": "gpt-4o-mini"
}
```

**Use this to:** Show AI feature availability badge in your dashboard

---

### 2. **AI Email Draft Generator**
```
GET /api/guests/{guest_id}/ai-email-draft?type=acceptance&note=Custom%20message
```

**Parameters:**
- `type`: "acceptance" or "rejection"
- `note`: (optional) Custom message to include

**Returns:**
```json
{
  "guest_id": 123,
  "email_type": "acceptance",
  "subject": "Excited to have you on Mirror Talk, John! 🎙️",
  "body": "Hi John,\n\nWe're thrilled to welcome you...",
  "guest_name": "John Doe"
}
```

**Use this to:** Generate personalized acceptance/rejection emails with one click

---

### 3. **AI Interview Questions**
```
GET /api/guests/{guest_id}/ai-interview-questions?num=10
```

**Parameters:**
- `num`: Number of questions to generate (5-20, default: 10)

**Returns:**
```json
{
  "guest_id": 123,
  "guest_name": "John Doe",
  "num_questions": 10,
  "questions": [
    "What pivotal moment in your life led you to discover your purpose?",
    "How has your faith shaped your approach to challenges?",
    ...
  ]
}
```

**Use this to:** Auto-generate thoughtful, personalized interview questions

---

### 4. **AI Guest Analysis**
```
GET /api/guests/{guest_id}/ai-analysis
```

**Returns:**
```json
{
  "guest_id": 123,
  "guest_name": "John Doe",
  "analysis": {
    "fit_score": 8,
    "themes": ["Resilience", "Faith journey", "Community healing"],
    "conversation_angles": [
      "Explore their transition from corporate life to ministry",
      "Discuss how loss shaped their current mission"
    ],
    "concerns": "None identified",
    "best_timing": "Ideal for Advent season (December) with hope theme",
    "analyzed_at": "2026-05-09T10:30:00"
  }
}
```

**Use this to:** Get deep insights on guest fit and conversation angles

---

### 5. **Follow-Up Manager**
```
GET /api/ai/followups?days=7
```

**Parameters:**
- `days`: Days since last contact threshold (default: 7)

**Returns:**
```json
{
  "days_threshold": 7,
  "count": 3,
  "guests": [
    {
      "id": 123,
      "full_name": "John Doe",
      "email": "john@example.com",
      "email_status": "accepted",
      "email_sent_at": "2026-04-25T10:00:00"
    },
    ...
  ]
}
```

**Use this to:** Find guests who need follow-up emails

---

## 🎨 Frontend Integration Examples

### Add AI Badge to Dashboard

Add to your `index.html` stats panel:

```html
<div class="insight-card" id="ai-status-card">
  <p class="insight-title">✨ AI Features</p>
  <div id="ai-status-indicator">
    <span class="status-badge">Checking...</span>
  </div>
</div>
```

```javascript
// Check AI status on load
fetch('/api/ai/status')
  .then(res => res.json())
  .then(data => {
    const indicator = document.getElementById('ai-status-indicator');
    if (data.configured) {
      indicator.innerHTML = `<span class="status-badge success">✅ Enabled (${data.model})</span>`;
      // Show AI buttons
      document.querySelectorAll('.ai-feature-button').forEach(btn => {
        btn.style.display = 'inline-block';
      });
    } else {
      indicator.innerHTML = `<span class="status-badge warning">⚠️ Not configured</span>`;
    }
  });
```

---

### Add "Generate AI Email" Button

In your guest card actions, add:

```html
<button class="ai-button" onclick="generateAIEmail(${guest.id}, 'acceptance')">
  ✨ AI Email Draft
</button>
```

```javascript
async function generateAIEmail(guestId, emailType) {
  const customNote = prompt("Add a custom note (optional):");
  const noteParam = customNote ? `&note=${encodeURIComponent(customNote)}` : '';
  
  const response = await fetch(`/api/guests/${guestId}/ai-email-draft?type=${emailType}${noteParam}`);
  const data = await response.json();
  
  if (response.ok) {
    // Show draft in modal
    showEmailDraftModal(data.subject, data.body, guestId, emailType);
  } else {
    alert(`Error: ${data.error}`);
  }
}

function showEmailDraftModal(subject, body, guestId, emailType) {
  // Create and show modal with draft
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML = `
    <div class="modal-content">
      <h2>✨ AI Generated Email Draft</h2>
      <label>Subject:</label>
      <input type="text" id="email-subject" value="${subject}" />
      <label>Body:</label>
      <textarea id="email-body" rows="15">${body}</textarea>
      <div class="modal-actions">
        <button onclick="copyEmailDraft()">📋 Copy</button>
        <button onclick="useEmailDraft(${guestId}, '${emailType}')">✅ Use This Draft</button>
        <button onclick="closeModal()">❌ Cancel</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
}
```

---

### Add "Generate Questions" Feature

In operations/guest detail view:

```html
<button class="ai-button" onclick="generateInterviewQuestions(${guest.id})">
  ❓ Generate Interview Questions
</button>
```

```javascript
async function generateInterviewQuestions(guestId) {
  const numQuestions = prompt("How many questions? (5-20)", "10");
  
  const response = await fetch(`/api/guests/${guestId}/ai-interview-questions?num=${numQuestions}`);
  const data = await response.json();
  
  if (response.ok) {
    showQuestionsModal(data.questions, data.guest_name);
  } else {
    alert(`Error: ${data.error}`);
  }
}

function showQuestionsModal(questions, guestName) {
  const modal = document.createElement('div');
  modal.className = 'modal';
  
  const questionsList = questions.map((q, i) => `<li>${q}</li>`).join('');
  
  modal.innerHTML = `
    <div class="modal-content">
      <h2>❓ Interview Questions for ${guestName}</h2>
      <ol class="questions-list">${questionsList}</ol>
      <div class="modal-actions">
        <button onclick="copyQuestions()">📋 Copy All</button>
        <button onclick="closeModal()">✅ Done</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
}
```

---

### Add "AI Analysis" Feature

In guest review workflow:

```html
<button class="ai-button" onclick="analyzeGuestWithAI(${guest.id})">
  🔍 Deep Analysis
</button>
```

```javascript
async function analyzeGuestWithAI(guestId) {
  showLoader("Analyzing guest profile...");
  
  const response = await fetch(`/api/guests/${guestId}/ai-analysis`);
  const data = await response.json();
  
  hideLoader();
  
  if (response.ok) {
    showAnalysisModal(data.analysis, data.guest_name);
  } else {
    alert(`Error: ${data.error}`);
  }
}

function showAnalysisModal(analysis, guestName) {
  const modal = document.createElement('div');
  modal.className = 'modal';
  
  const themes = analysis.themes ? analysis.themes.join(', ') : 'N/A';
  const angles = analysis.conversation_angles?.map(a => `<li>${a}</li>`).join('') || 'N/A';
  
  modal.innerHTML = `
    <div class="modal-content">
      <h2>🔍 AI Analysis: ${guestName}</h2>
      <div class="analysis-grid">
        <div class="metric">
          <strong>Fit Score</strong>
          <span class="score">${analysis.fit_score}/10</span>
        </div>
        <div class="section">
          <strong>Key Themes:</strong>
          <p>${themes}</p>
        </div>
        <div class="section">
          <strong>Conversation Angles:</strong>
          <ul>${angles}</ul>
        </div>
        <div class="section">
          <strong>Best Timing:</strong>
          <p>${analysis.best_timing || 'Flexible'}</p>
        </div>
        <div class="section">
          <strong>Concerns:</strong>
          <p>${analysis.concerns || 'None'}</p>
        </div>
      </div>
      <button onclick="closeModal()">✅ Close</button>
    </div>
  `;
  document.body.appendChild(modal);
}
```

---

### Add "Follow-Up Dashboard"

Create a new section in operations:

```html
<section class="panel" id="followup-panel">
  <h2>📧 Follow-Up Manager</h2>
  <div class="controls">
    <label>Days since last contact:</label>
    <input type="number" id="followup-days" value="7" min="1" max="30" />
    <button onclick="checkFollowups()">🔍 Check Follow-Ups</button>
  </div>
  <div id="followup-results"></div>
</section>
```

```javascript
async function checkFollowups() {
  const days = document.getElementById('followup-days').value;
  
  const response = await fetch(`/api/ai/followups?days=${days}`);
  const data = await response.json();
  
  const resultsDiv = document.getElementById('followup-results');
  
  if (response.ok) {
    if (data.count === 0) {
      resultsDiv.innerHTML = `<p class="success">✅ All caught up! No guests need follow-up.</p>`;
    } else {
      const guestsList = data.guests.map(g => `
        <div class="guest-card">
          <strong>${g.full_name}</strong> (${g.email})
          <br>Last contact: ${new Date(g.email_sent_at).toLocaleDateString()}
          <button onclick="sendFollowupEmail(${g.id})">📧 Send Follow-Up</button>
        </div>
      `).join('');
      
      resultsDiv.innerHTML = `
        <p class="info">Found ${data.count} guest(s) needing follow-up:</p>
        ${guestsList}
      `;
    }
  } else {
    resultsDiv.innerHTML = `<p class="error">Error: ${data.error}</p>`;
  }
}
```

---

## 🎨 CSS Styles for AI Features

Add to your `styles.css`:

```css
/* AI Feature Buttons */
.ai-button {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  transition: transform 0.2s;
}

.ai-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

/* AI Status Badge */
.status-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 0.85rem;
  font-weight: 600;
}

.status-badge.success {
  background: #10b981;
  color: white;
}

.status-badge.warning {
  background: #f59e0b;
  color: white;
}

/* Modal for AI results */
.modal {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  padding: 24px;
  border-radius: 12px;
  max-width: 600px;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.analysis-grid {
  display: grid;
  gap: 16px;
  margin: 16px 0;
}

.analysis-grid .metric {
  text-align: center;
  padding: 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 8px;
}

.analysis-grid .score {
  display: block;
  font-size: 2rem;
  font-weight: bold;
  margin-top: 8px;
}
```

---

## 🚀 Deployment

1. **Commit and push** your updated code:
   ```bash
   git add .
   git commit -m "Add AI features to production dashboard"
   git push
   ```

2. **Railway will auto-deploy** with:
   - ✅ New AI endpoints available
   - ✅ OPENAI_API_KEY already configured
   - ✅ Features ready to use

3. **Test the features:**
   - Visit `/api/ai/status` to verify AI is working
   - Try generating an email draft
   - Generate interview questions
   - Run AI analysis on a guest

---

## 💡 Usage Tips

### Best Practices

1. **Check AI status first** - Display the AI badge so users know features are available

2. **Use AI drafts as starting points** - Always allow editing before sending

3. **Batch operations** - Generate questions for multiple accepted guests at once

4. **Weekly follow-up checks** - Add to your workflow routine

5. **Copy-paste friendly** - Make it easy to copy AI outputs to other tools

### Workflow Integration

**For Guest Review:**
1. View guest application
2. Click "🔍 Deep Analysis" for AI insights
3. Review fit score and themes
4. Make accept/reject decision
5. Click "✨ AI Email Draft" if accepting/rejecting
6. Edit draft and send

**For Interview Prep:**
1. Go to accepted guest
2. Click "❓ Generate Interview Questions"
3. Review and select best questions
4. Copy to interview prep doc

**For Follow-Ups:**
1. Check "📧 Follow-Up Manager" weekly
2. Review guests needing contact
3. Send personalized follow-ups

---

## 📊 Expected Performance

### API Response Times
- AI Status: <100ms
- Email Draft: 2-5 seconds
- Interview Questions: 3-7 seconds
- Guest Analysis: 2-5 seconds
- Follow-Up Check: <500ms

### Costs
With Railway's OPENAI_API_KEY:
- **~$0.003** per email draft
- **~$0.007** per question set
- **~$0.005** per analysis
- **Very affordable** for the value!

---

## 🐛 Troubleshooting

### AI Features Not Working?

**Check 1:** Verify AI status
```javascript
fetch('/api/ai/status').then(r => r.json()).then(console.log)
```

**Check 2:** Confirm OPENAI_API_KEY is set in Railway
- Go to Railway project → Variables
- Verify `OPENAI_API_KEY` exists

**Check 3:** Check Railway logs
```bash
railway logs
```

### Error Messages

**"AI features are not available"**
- OPENAI_API_KEY not set or invalid
- Check Railway environment variables

**"AI analysis failed"**
- Guest data might be incomplete
- Try with a guest who has more filled-in fields

**"Unauthorized dashboard request"**
- Ensure you're logged in
- Check dashboard credentials

---

## 🎉 You're Ready!

Your production dashboard now has:
- ✅ Smart email draft generation
- ✅ Personalized interview questions
- ✅ Deep guest analysis
- ✅ Automated follow-up tracking
- ✅ All powered by AI with your existing OPENAI_API_KEY

**Deploy and enjoy your smarter workflow!** 🚀
